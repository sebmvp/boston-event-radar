"""Newsletter / forwarded-email adapter.

v0.1 accepts local .txt / .eml files. Gmail integration is intentionally later.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from event_radar.models import RawEvent
from event_radar.sources.base import FetchContext, SourceFetchResult, finish_run, start_run

_URL_RE = re.compile(r"https?://[^\s>]+")
_TITLE_RE = re.compile(r"^(?:subject|event)\s*:\s*(.+)$", re.I | re.M)


class NewsletterAdapter:
    source_type = "newsletter"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.source_id = config["id"]

    def discover(self, ctx: FetchContext) -> SourceFetchResult:
        run = start_run(self.source_id, self.source_type, ctx.now)
        folder = Path(self.config.get("path") or "data/newsletters")
        events: list[RawEvent] = []
        if not folder.exists():
            finish_run(run, events=[], error=f"newsletter folder missing: {folder}")
            return SourceFetchResult(run=run, events=[])
        for path in sorted(folder.glob("*")):
            if path.suffix.lower() not in {".txt", ".eml", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            title_match = _TITLE_RE.search(text)
            title = title_match.group(1).strip() if title_match else path.stem.replace("_", " ")
            urls = _URL_RE.findall(text)
            url = urls[0] if urls else path.as_uri()
            events.append(
                RawEvent(
                    source_id=self.source_id,
                    source_type="newsletter",
                    external_id=path.name,
                    source_url=url,
                    title=title,
                    description=text[:4000],
                    registration_url=url,
                    canonical_url=url,
                    fetched_at=ctx.now,
                    raw={"path": str(path)},
                )
            )
        finish_run(run, events=events)
        return SourceFetchResult(run=run, events=events)
