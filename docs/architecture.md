# Architecture

```
sources.yaml ─┐
profile.yaml ─┤
series.yaml  ─┤
keywords.yaml─┤
              ▼
        Source registry
              │
              ▼
   adapters (luma, localist, ics, html, newsletter stub)
              │
              ▼
          RawEvent[]
              │
              ▼
         normalize
              │
              ▼
     dedupe / merge (keep ALL provenance)
              │
              ▼
     access-route extraction
              │
              ▼
     recurring-series match (historical labeled as historical)
              │
              ▼
     deterministic score + explanation
              │
              ▼
         SQLite
              │
              ├── CLI (discover / list / opportunities / show / status)
              └── Telegram (high-priority / digest; optional)
```

## Invariants

1. Structured public endpoints beat HTML beat Playwright beat LLM.
2. A failed source records `source_runs` and continues.
3. Access routes carry `observation_kind`: `confirmed_current`,
   `historical`, or `inferred`. Historical never presents as current.
4. Duplicate listings merge. Sources are unioned, not overwritten.
5. Scores are weighted sums from `config/profile.yaml`, not model output.
6. No login bypass, no CAPTCHA bypass, no marketplace writes.

## Adapters

Each adapter implements `SourceAdapter.discover(ctx) -> SourceFetchResult`.

| type | v0.1 | input |
|---|---|---|
| `luma_discover` | yes | lat/lng + optional category slugs |
| `luma_event` | yes | slug or event_api_id (detail + ticket types) |
| `localist` | yes | `{base_url}/api/2/events` |
| `ics` | yes | public ICS URL |
| `html_page` | yes | public event/marketing page (JSON-LD + text signals) |
| `newsletter` | stub | raw email/text file |
| `rss` | reserved | Atom/RSS URL |

## Storage

SQLite (`data/events.db`):

- `events` — normalized event + score
- `event_sources` — provenance rows
- `access_routes` — ways in
- `series` — recurring watch list
- `source_runs` — observability

## Cost

Local process + SQLite + public HTTP. Telegram Bot API is free.
No cloud requirement.
