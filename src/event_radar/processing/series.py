from __future__ import annotations

from rapidfuzz import fuzz

from event_radar.models import EventRecord, RecurringSeries


def match_series(event: EventRecord, series_list: list[RecurringSeries]) -> RecurringSeries | None:
    title = event.title.lower()
    blob = " ".join([event.title, event.organizer or ""]).lower()
    best: tuple[float, RecurringSeries] | None = None
    for series in series_list:
        full = series.name.lower()
        if full and full in blob:
            score = 120.0
            if best is None or score > best[0]:
                best = (score, series)
            continue
        for name in [series.name, *series.aliases]:
            name_l = name.lower()
            if not name_l:
                continue
            if len(name_l) >= 16 and name_l in title:
                score = 110.0
                if best is None or score > best[0]:
                    best = (score, series)
                continue
            ratio = fuzz.token_sort_ratio(name_l, title)
            if ratio >= 90:
                if best is None or ratio > best[0]:
                    best = (float(ratio), series)
    return best[1] if best else None
