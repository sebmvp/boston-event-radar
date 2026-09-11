from event_radar.processing.text import has_term


def test_short_terms_use_word_boundaries():
    assert has_term("boston ai mixer", "ai")
    assert not has_term("mit career fair", "ai")
    assert not has_term("said the organizer", "ai")
    assert has_term("data science seminar", "data")
    assert has_term("fintech sandbox", "fintech")
