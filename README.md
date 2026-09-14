# Boston Event Radar

I found Boston Blockchain Week through a university email, volunteered, and it
was worth more than most paid mixers. This tool exists so that does not have
to be luck.

It watches public Boston/Cambridge event sources, merges duplicate listings,
and answers five questions for each event:

1. Is this worth attending?
2. How can I get in?
3. What should I do next?
4. How urgent is it?
5. What evidence supports those conclusions?

It is a personal research system for a UMass Amherst data-analytics master's
student in the Boston tech/startup circuit. It is **not** a generic nightlife
calendar, a marketplace bot, or a ticket purchaser.

Normal aggregators collapse “the event” with “the $695 ticket.” That is the
wrong model. Boston FinTech Week can be expensive at the door and still have
a student coupon, a founder coupon, and a volunteer inquiry email on a
different page. Those are separate **access routes**, each with provenance.

## Architecture

```
config/*.yaml
        │
        ▼
 source adapters (public JSON / ICS / HTML / Tribe REST)
        │
        ▼
   RawEvent[]  →  normalize  →  access-route extraction
        │
        ▼
   dedupe (keep every source)  →  series match
        │                         (historical ≠ current)
        ▼
   deterministic score + explanation
        │
        ▼
   SQLite  →  CLI  (optional Telegram)
```

LLMs are not in the scoring path. If no Telegram credentials are set, nothing
is sent.

## Source strategy

Prefer cheap public structure, in order: RSS/Atom → ICS → JSON-LD → HTML →
the same JSON the public webpage already loads. No paid Luma/Eventbrite APIs.
No login, CAPTCHA, or access-control bypass.

### ✅ Working (live public data)

- **Luma discover** — `api.lu.ma/discover/get-paginated-events` for Boston
  `ai`, `crypto`, `tech`, `climate`
- **Luma event detail** — ticket types (e.g. Fintech That Thinks $695 / closed early-bird)
- **Localist JSON** — MIT, UMass Amherst, Northeastern, Boston College, Bentley, Suffolk
- **The Events Calendar REST** — MassRobotics, Greentown Labs
- **HTML + related pages** — bostonfintechweek.com plus the FAQ (student/founder
  coupons and volunteer email)

### 🧪 Experimental

- **ICS adapter** (MIT calendar.ics works; disabled by default because it
  duplicates Localist and is noisy)
- **RSS/Atom adapter** (implemented, no high-signal Boston feed enabled yet)
- **Luma calendar follow** (`calendar/get-items`) — implemented; add
  `calendar_api_id` rows in `config/sources.yaml` to use it
- **Newsletter file-drop** — drop `.txt`/`.eml` into `data/newsletters/`

### 🗺 Planned

- Harvard Localist (Akamai 403)
- Venture Café Cambridge listing (main site 403 to bots; community list is login-walled)
- MassChallenge / CIC / The Engine / Startup Boston calendars when a public
  JSON/ICS/RSS path exists
- Gmail/newsletter ingestion beyond local files
- Eventbrite/Meetup without paid keys, if a public feed appears

## Access routes

An event can have a $695 standard ticket **and** a student coupon **and** a
founder coupon **and** a volunteer email on the FAQ. Those stay separate.

Each route has type, price, status, eligibility, deadline, URL, email,
evidence, confidence, and an observation kind:

- `confirmed_current` — seen on a live page/API this run
- `historical` — true of a past year / watchlist, **not** this cycle
- `inferred` — text heuristic, lower confidence

Historical volunteer programs are never reported as open volunteer slots.

## Quick start

Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd boston-event-radar
uv sync --group dev
cp .env.example .env   # optional Telegram
uv run event-radar doctor
uv run event-radar discover
uv run event-radar upcoming
uv run event-radar opportunities
uv run event-radar show <id>
uv run event-radar sources
uv run event-radar status
uv run event-radar watchlist
```

SQLite: `data/events.db` (gitignored). HTTP cache: `data/cache/`.

```bash
uv run pytest
uv run ruff check src tests
uv run mypy src/event_radar
```

### Example output

```
🔥 95/100 — Boston Fintech Week
Tue Sep 22 08:00 · Boston

WHY: fintech + AI + industry networking
STANDARD: $695
BEST ACCESS: student_ticket ? (uncertain) · coupon STUDENT2026
ALSO FOUND: founder_ticket, volunteer
URGENCY: HIGH
ACTION: Request student access now. Volunteer route as fallback.
EVIDENCE: luma.com/fintechthatthinks · bostonfintechweek.org/faqs/
```

## CLI

| command | what it does |
|---|---|
| `event-radar discover` | fetch, merge, score, store |
| `event-radar discover --source luma` | only matching source ids/types |
| `event-radar list` / `upcoming` | ranked upcoming events |
| `event-radar opportunities` | student/free/volunteer/founder routes |
| `event-radar show <id>` | one event with evidence |
| `event-radar sources` | registry + discovered organizers |
| `event-radar status` | latest per-source health |
| `event-radar watchlist` | recurring weeks (historical = WATCH) |
| `event-radar doctor` | config, sqlite, cache, optional Telegram, Luma ping |

## Config

| file | purpose |
|---|---|
| `config/sources.yaml` | enable/disable sources; universities and orgs belong here |
| `config/profile.yaml` | student + Boston-metro scoring weights |
| `config/keywords.yaml` | client-side topic filter for noisy campus calendars |
| `config/series.yaml` | recurring weeks; historical ≠ current |

## Automation

Persistent SQLite on **this machine** (or a cheap always-on box). GitHub
Actions is CI only — see `docs/automation.md`. Nothing in this repo turns
scheduling on by itself.

## Ethical / public-data boundary

- Identifiable User-Agent, timeouts, retries, per-host delay, file cache
- Public pages and the JSON those pages already load
- No credentials stuffing, no CAPTCHA solving, no private APIs, no registration

## Limitations

- Luma's public JSON can change without notice
- University calendars are noisy; keyword filters miss some good talks and
  still let some weak ones through
- Missing city/coordinates on a Luma card is treated as out-of-geo
- Scores are weighted rules, not taste
- Telegram is optional and will not run without env vars

## Roadmap

Follow more Luma calendars discovered from events. Add a public Venture Café
path if one appears. Newsletter parser for “volunteers wanted / student
ticket / applications open.” Daily digest once Telegram is configured.

## License

Private repository. License intentionally not chosen yet. See `docs/license.md`.

Research notes: `docs/research.md`. Architecture: `docs/architecture.md`.
Audit of the inherited v0.1: `docs/audit.md`.
