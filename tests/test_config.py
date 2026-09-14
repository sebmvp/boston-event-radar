from event_radar.config import load_keywords, load_profile, load_series, load_sources


def test_config_files_load():
    sources = load_sources()
    assert any(s.get("id") == "luma_boston_ai" and s.get("enabled") for s in sources["sources"])
    assert any(s.get("type") == "tribe" and s.get("enabled") for s in sources["sources"])
    profile = load_profile()
    assert profile["student"] is True
    assert "topic_relevance" in profile["scoring"]["weights"]
    keywords = load_keywords()
    assert "ai" in keywords["include"]
    assert "data" not in keywords["include"]
    series = load_series()
    assert any(s["id"] == "boston-fintech-week" for s in series["series"])
