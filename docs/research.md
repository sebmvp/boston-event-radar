# Research notes — event discovery building blocks

Researched 2026-09-11 before writing application code. Goal: learn patterns
and legally reusable libraries, not clone a product.

Nothing below was copied into this repository except publicly documented
API/URL shapes and our own implementations.

## What we actually use

| Library | License | Why |
|---|---|---|
| [pydantic](https://github.com/pydantic/pydantic) | MIT | Normalized event / access / score models |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | MIT | SQLite persistence |
| [httpx](https://github.com/encode/httpx) | BSD-3-Clause | HTTP with timeouts |
| [selectolax](https://github.com/rushter/selectolax) | MIT | Fast HTML parsing |
| [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) + lxml | MIT / BSD | Fallback HTML / JSON-LD script tags |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | MIT | Fuzzy title/venue dedup |
| [icalendar](https://github.com/collective/icalendar) | BSD-2-Clause | ICS/iCal ingestion |
| [Typer](https://github.com/fastapi/typer) + [Rich](https://github.com/Textualize/rich) | MIT | CLI |
| [PyYAML](https://github.com/yaml/pyyaml) | MIT | Source / profile config |

Not added in v0.1 even though useful later:

| Library | License | Notes |
|---|---|---|
| [feedparser](https://github.com/kurtmckee/feedparser) | BSD-2-Clause | RSS/Atom. Architecture supports a `rss` adapter; not wired yet. |
| [extruct](https://github.com/scrapinghub/extruct) | BSD-3-Clause | Heavy JSON-LD stack (rdflib). We extract `application/ld+json` ourselves. |
| [ics](https://github.com/ics-py/ics-py) | Apache-2.0 / custom | Overlap with `icalendar`; skip. |
| Playwright | Apache-2.0 | Only if a source has no public JSON/ICS/HTML. Not required for v0.1. |
| Official Luma / Eventbrite / Meetup SDKs | various | Paid or login-gated. Avoided. |

## GitHub projects reviewed (do not clone)

### Luma

- **vm-mishchenko/luma** — CLI over Luma discover/calendar JSON. **No license
  listed.** Do not copy. Useful *idea*: city lat/lng + category slug against
  `https://api.lu.ma/discover/get-paginated-events`, calendar items via
  `calendar/get-items`, event detail via `event/get`. Those URLs are the same
  public endpoints the Luma website uses. We reimplemented with httpx, caching,
  and our own models.
- **montaguegabe/luma-events-mcp** — official Luma API, needs a Plus key.
  Out of scope for $0 operation.
- **YejinjinZhang/luma-event-kit**, **go9x/newsletter-agent** — operator tools
  around *your own* Luma calendar + API key. Different problem.
- **mwanjeronie/luma-events-scraper** — unlicensed scraper, 1 star. Ignore.

Live check (2026-09-11): Luma discover JSON for Boston
(`latitude=42.3601&longitude=-71.0589`) returns events with `ticket_info`
(`is_free`, `require_approval`, `price.cents`, waitlist). Category slug `ai`
returns relevant Boston/Cambridge events. Slug `crypto` works; `startups` /
`web3` returned empty that day.

`event/get?event_api_id=fintechthatthinks` resolves Boston Fintech Week's
"Fintech That Thinks" forum: Standard $695, Early Bird $495 (window ended
2026-08-22). Student/founder coupons are **not** in public `ticket_types`;
they appear on bostonfintechweek.com. This is why multi-source merge matters.

### Eventbrite / Meetup

- **eventbrite/eventbrite-sdk-python** — Apache-2.0 official SDK. Needs API
  key; Eventbrite has restricted public search. Deferred.
- **pnijjar/eventbrite-helpers** — Apache-2.0, RSS from the official API.
  Same key problem.
- **lorenanicole/eventbrite_scraper** — MIT, old HTML scraper. Pattern only.
- **0xZDH/EventBot** — ticket-sniping bot. Do not use.
- Meetup official Python client is discontinued. Public group ICS still
  exists for some groups (`/events/ical/`). Adapter shape reserved; not v0.1.

### University calendars / Localist

Many Boston-area schools publish **Localist** JSON:

`GET {host}/api/2/events?days=N&pp=P`

Live 200s: `calendar.mit.edu`, `events.umass.edu`,
`calendar.northeastern.edu`. Harvard `events.harvard.edu/api/2/events`
returned 403 (Akamai). Babson hosts did not resolve.

Localist event objects include `title`, `description_text`, `localist_url`,
`localist_ics_url`, `event_instances[].start/end`, `location_name`, `geo`,
`free`, `ticket_cost`, `ticket_url`, `tags`. MIT also serves a large
`/calendar.ics` (text/calendar, ~1.3MB). Prefer filtered JSON over dumping
the full ICS.

- **CornellCustomDev/CD_cwd_events_localist_pull** — GPL-3. Do not copy.
  Confirms Localist as a campus-wide API, not a one-off MIT quirk.

### ICS / RSS / JSON-LD

- **collective/icalendar** — the library to use.
- **feedparser** — RSS/Atom later (university news, ecosystem blogs).
- **extruct** — skipped as a dependency; JSON-LD Event is a few script tags.

### Dedup / ranking / Telegram

- RapidFuzz is the right fuzzy matcher (title + date + venue).
- **vinayak-mehta/conrad** (Apache-2.0) — terminal conference tracker.
  Different corpus (CFP lists), similar CLI-first taste.
- **TGmeetup/TGmeetup** (MIT) — technical group registry, not event
  intelligence. Telegram as a *delivery* channel, not a source.
- No well-maintained "Boston event radar" product to extend. Build ours.

### Ecosystem pages

- **Boston Fintech Week** (`bostonfintechweek.com` → `.org`): 2026 dates
  Sep 22–25. Public HTML advertises Student Tickets (current undergrad/grad,
  ID required, limited; Luma coupon `STUDENT2026`), founder coupon
  `FINTECH-FOUNDER`, and reviewed free tickets for eligible early-stage
  fintech entrepreneurs. Student button was `pointer-events: none` on
  2026-09-11 — treat as **uncertain current availability**, not confirmed open.
- **Venture Cafe Cambridge**: WordPress site is public; `/thursday-gathering/`
  returned empty on HEAD/GET during research. Worth a dedicated adapter later.
- **Startup Boston** (`startupboston.com`): thin HTML, not a calendar.
- UMass CampusLabs Engage events redirect to login — skip (not public).

## Architectural patterns we take

1. **Source adapters behind a protocol** — fetch → raw → normalize. A dead
   scraper must not kill the run (per-source status).
2. **Public structured endpoints first** — Luma discover JSON, Localist JSON,
   ICS, JSON-LD. HTML second. Browser last. LLM last.
3. **Merge, don't replace** — university page may reveal a student route the
   organizer Luma page hides. Keep all provenance.
4. **Observation kind** — `confirmed_current` vs `historical` vs `inferred`.
   Last year's volunteer program is not this year's volunteer program.
5. **Deterministic scoring** with an explanation list. No mystery LLM score.
6. **Polite HTTP** — identifiable User-Agent, timeouts, retries on 429/5xx,
   per-host delay, response cache.

## Explicit non-goals for v0.1

- Bypassing logins, CAPTCHAs, or anti-bot walls
- Paid Eventbrite/Meetup/Luma APIs
- Autonomous registration or ticket purchase
- A frontend
- Pretending Harvard Localist works when it 403s
