from event_radar.processing.geo import city_allowed


def test_missing_city_is_not_automatically_in_geo():
    assert not city_allowed(city=None, allowlist=["Boston"])
    assert city_allowed(city="Boston", allowlist=["Boston"])
    assert not city_allowed(city="New York", allowlist=["Boston"])
    assert city_allowed(city=None, latitude=42.36, longitude=-71.06, allowlist=["Boston"])
    assert city_allowed(city=None, virtual=True, allowlist=["Boston"])
