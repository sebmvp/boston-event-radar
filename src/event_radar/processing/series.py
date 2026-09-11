from __future__ import annotations

from rapidfuzz import fuzz

from event_radar.models import EventRecord, RecurringSeries


def match_series(event: EventRecord, series_list: list[RecurringSeries]) -> RecurringSeries | None:
    blob = " ".join([event.title, event.organizer or "", event.canonical_url]).lower()
    best: tuple[int, RecurringSeries] | None = None
    for series in series_list:
        names = [series.name, *series.aliases]
        for name in names:
            ratio = fuzz.token_set_ratio(name.lower(), event.title.lower())
            contained = name.lower() in blob
            score = ratio + (15 if contained else 0)
            if contained or ratio >= 86:
                if best is None or score > best[0]:
                    best = (score, series)
    return best[1] if best else None
