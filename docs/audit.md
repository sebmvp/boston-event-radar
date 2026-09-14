# Audit — 2026-09-14

Inspected the existing `main` at `659cf3a` (`Implement live discover pipeline, adapters, scoring, and CLI.`).
Remote `origin` is `https://github.com/sebmvp/boston-event-radar.git` (private, reachable via `gh`).
Working tree was clean. `.venv` and `data/events.db` already existed from a 2026-09-11 run.

## What exists

A real v0.1, not a scaffold:

- Config-driven source registry (`config/sources.yaml`) plus profile, keywords, series
- Adapters: Luma discover, Luma event detail, Localist JSON, ICS, HTML/JSON-LD, newsletter file-drop stub
- Normalize → access extraction → RapidFuzz dedupe (union provenance) → series match → deterministic scoring → SQLite
- CLI: `discover`, `list`, `opportunities`, `show`, `status`
- Optional Telegram formatter (no send unless env vars set)
- 18 unit tests, all passing; Ruff clean; mypy not clean (17 errors)
- Prior live run stored **325** events; all 8 enabled sources reported HTTP success that day

## What genuinely works

Verified 2026-09-14 against live public endpoints (not mocks):

| Source | Live status | Notes |
|---|---|---|
| Luma `discover/get-paginated-events` (Boston + `ai`) | HTTP 200 | Current events, `ticket_info.is_free` / `require_approval`, pagination cursors |
| Luma `event/get?event_api_id=fintechthatthinks` | HTTP 200 | Standard $695, Early Bird $495 **closed** |
| MIT Localist `/api/2/events` | HTTP 200 | |
| `bostonfintechweek.com` | HTTP 200 | `STUDENT2026` + `FINTECH-FOUNDER` still in HTML |

Dedup already merged Fintech Week from Luma discover + Luma detail + organizer HTML, keeping standard/early-bird **and** student/founder coupons with provenance. That is the product concept working.

## What is partially implemented

- Access routes (student/volunteer/free/approval/coupons) — good on structured Luma + Fintech HTML; weak on university pages
- Recurring series — match + historical-vs-current labeling works; watchlist/CLI and “start monitoring on date” are thin
- Scoring — transparent weights, but university keyword leakage (`data`, `career`, `product`) floods SQLite with low-value talks
- Source health — `source_runs` rows exist; no drop-detection, no `doctor`, CLI `status` is last-40-runs dump
- Newsletter — local `.txt/.eml` parser only
- Telegram — format exists; no digest/deduped-alert state
- University registry — many school rows exist but **disabled placeholders** without URLs
- `discover.hydrate_luma_details_for_top_n` is in YAML and **never called**

## What is dead / stubbed / fake

- Empty leftover packages: `src/event_radar/{models,storage,alerts}/` (unused dirs; real code is sibling `.py` files)
- `tests/fixtures/` empty (adapters tested with inline dicts, not captured fixtures)
- Newsletter source disabled
- No RSS adapter (architecture says “reserved”)
- No GitHub Actions
- No Playwright, no LLM path (correct for v0.1)
- Architecture doc claims `event_sources` / `access_routes` / `series` SQL tables — **not true**. Events are a JSON payload column plus `source_runs`

## What is brittle

- Luma depends on undocumented public JSON the website uses (`api.lu.ma` + Origin/Referer). Fine and cheap; will break if Luma changes shape
- City allowlist treats **missing city as in-geo** → possible non-Boston leakage
- Naive ICS datetimes forced to UTC
- HTML adapter concatenates the whole page text into `description` (noisy, but useful for coupon regex)
- SQLite upsert keys on `uuid5(title|date|city)` — title drift can duplicate; URL match in dedupe is same-run only, not vs DB
- HTTP file cache has no invalidation besides TTL; 403s are not cached as failures (good)

## What is missing vs the product spec

- CLI: `sources`, `source-status`, `upcoming`, `watchlist`, `doctor`, `discover --source`
- List/opportunities do not default to **upcoming**
- Organizer/source discovery (calendars found via events should become followable sources)
- Related evidence pages (FAQ / volunteer page attached to an event)
- Idempotency tests; “do not merge distinct AI Boston events” tests
- CI; launchd/cron truthful persistence docs
- Broader live university + ecosystem coverage (only MIT / UMass Amherst / NEU / Fintech Week / Luma)

## Architectural problems

1. **Event identity is not stable across runs vs DB.** In-memory dedupe is decent; persistence does not merge a new source into an existing row unless the uuid matches.
2. **Keyword-filter-as-relevance** on giant campus ICS/Localist dumps stores hundreds of weak events. Radar should keep a tight working set.
3. **Config advertises unused features** (Luma detail hydration).
4. **No upcoming filter in the user-facing CLI** — the 2026-09-11 DB already shows past events at the top (`MIT delta v Demo Day` same day as the run).

## Immediate repair priorities

1. Prove a fresh live `discover` still works; fix anything that fails
2. Upcoming-first CLI + `doctor` + `sources` + `--source`
3. Wire Luma detail hydration; follow public Luma calendars when cheap
4. Tighten university filtering; add at least one more live university Localist and one more live ecosystem source
5. Related evidence URLs + access-route provenance already on Fintech Week, generalize
6. Idempotent upsert (merge by canonical URL / external id)
7. Tests for timezone, non-merge, idempotency, provenance
8. CI + cron/launchd docs + honest README
9. Do **not** bypass logins, CAPTCHAs, or access controls — public data only
