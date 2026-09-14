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
| `luma_calendar` | yes | `calendar_api_id` via `calendar/get-items` |
| `localist` | yes | `{base_url}/api/2/events` |
| `tribe` | yes | WordPress The Events Calendar `/wp-json/tribe/events/v1/events` |
| `ics` | yes | public ICS URL |
| `html_page` | yes | public page + optional `related_urls` |
| `rss` | yes | RSS 2 / Atom |
| `newsletter` | stub | raw email/text file |

## Storage

SQLite (`data/events.db`):

- `events` — JSON payload of the normalized `EventRecord` (including access
  routes, sources, score). Extra columns for list/sort.
- `source_runs` — observability
- `organizers` — calendars/orgs discovered from events

This is deliberately not Postgres. Repeated `discover` upserts/merges by
id and canonical URL.

## Cost

Local process + SQLite + public HTTP. Telegram Bot API is free.
No cloud requirement.
