# Boston Event Radar

I found Boston Blockchain Week through a university email, volunteered, and it was
worth more than most paid mixers. This tool exists so that does not have to be
luck.

It watches public Boston/Cambridge event sources, merges duplicate listings, and
answers three questions for each event:

1. Is this worth attending?
2. How can I get in cheaply or for free?
3. How urgent is the window?

It is a personal research system for a UMass Amherst data-analytics master's
student who spends time in the Boston tech/startup circuit. It is not a
marketplace bot and it does not register you for anything.

## What v0.1 actually does

Live adapters:

- **Luma discover** (public JSON the website uses) for Boston AI / crypto
- **Luma event detail** for Boston Fintech Week / Fintech That Thinks
- **Localist JSON** for MIT, UMass Amherst, Northeastern
- **ICS** for MIT's public calendar
- **HTML page** for bostonfintechweek.com (student/founder coupon evidence
  that Luma ticket types do not show)

Then: normalize → dedupe (keep every source) → extract access routes →
match recurring series → deterministic score → SQLite → CLI.

Telegram alerts are implemented but optional. Leave `.env` blank and nothing
is sent.

## Not this, not yet

- No login, CAPTCHA, or anti-bot bypass
- No paid Luma / Eventbrite / Meetup APIs
- No autonomous ticket buying
- Harvard Localist currently 403s; it is in the registry, disabled
- Newsletter/Gmail adapter is a file-drop stub
- Scores are weighted rules, not an LLM

## Setup

Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cd boston-event-radar
uv sync --group dev
cp .env.example .env   # optional Telegram
uv run event-radar discover
uv run event-radar list
uv run event-radar opportunities
uv run event-radar show <id>
uv run event-radar status
```

SQLite lives at `data/events.db` (gitignored). HTTP responses cache under
`data/cache/`.

```bash
uv run pytest
uv run ruff check src tests
```

## Config

| file | purpose |
|---|---|
| `config/sources.yaml` | enable/disable sources; universities and orgs belong here, not in code |
| `config/profile.yaml` | student + Boston-metro scoring weights |
| `config/keywords.yaml` | client-side topic filter for noisy campus calendars |
| `config/series.yaml` | recurring weeks (Fintech, Blockchain, …); historical ≠ current |

## Access routes

An event can have a $695 standard ticket **and** a student coupon **and** a
founder coupon **and** a closed early-bird. Those are separate routes, each
with evidence, confidence, and an observation kind:

- `confirmed_current` — seen on a live page/API this run
- `historical` — true of a past year or a watchlist, not this cycle
- `inferred` — text heuristic, lower confidence

Historical volunteer programs are never reported as open volunteer slots.

## License

Private repository. License intentionally not chosen yet. See `docs/license.md`.

Research notes: `docs/research.md`. Architecture: `docs/architecture.md`.
