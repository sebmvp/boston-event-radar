# Running Event Radar on a schedule

Discovered events live in **local SQLite** (`data/events.db`). GitHub Actions
runners are ephemeral, so CI is for tests/lint only — it is **not** a
persistent crawler.

## macOS launchd (this machine)

Copy `docs/launchd.boston-event-radar.plist.example` to
`~/Library/LaunchAgents/com.sebmvp.boston-event-radar.plist`, fix the paths,
then:

```bash
launchctl load ~/Library/LaunchAgents/com.sebmvp.boston-event-radar.plist
launchctl start com.sebmvp.boston-event-radar
```

Default example: 7:30am local, weekdays. Logs go to `data/launchd.log`.

Unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.sebmvp.boston-event-radar.plist
```

## cron (Linux / always-on box)

```cron
30 7 * * 1-5 cd /home/you/Projects/boston-event-radar && uv run event-radar discover >> data/cron.log 2>&1
```

Keep `data/` on a persistent disk. Do not point this at a GitHub Actions workspace.

Automatic execution is **not** enabled by this repository. You opt in locally.
