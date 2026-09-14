"""Cheap geography checks. No paid geocoder."""

from __future__ import annotations

from event_radar.processing.score import haversine_km

BOSTON = (42.3601, -71.0589)


def city_allowed(
    *,
    city: str | None,
    latitude: float | None = None,
    longitude: float | None = None,
    allowlist: list[str] | None = None,
    virtual: bool = False,
    origin: tuple[float, float] = BOSTON,
    max_km: float = 40,
    allow_missing: bool = False,
) -> bool:
    """Keep events in an allowlisted city, near origin, or virtual.

    Missing city is NOT treated as in-geo unless coordinates confirm it
    or allow_missing is explicitly True.
    """
    if virtual:
        return True
    allowlist = allowlist or []
    if city:
        city_l = city.lower().split(",")[0].strip()
        if allowlist and any(city_l.startswith(item.lower()) or item.lower() in city_l for item in allowlist):
            return True
        if not allowlist:
            # no allowlist → coordinates or accept named city
            if latitude is None or longitude is None:
                return True
    if latitude is not None and longitude is not None:
        return haversine_km(origin[0], origin[1], latitude, longitude) <= max_km
    if allow_missing and not city:
        return True
    if city and not allowlist:
        return True
    return False
