from datetime import UTC, datetime

from event_radar.sources.rss import parse_feed

RSS = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>Boston AI Mixer</title>
      <link>https://example.com/ai-mixer</link>
      <guid>abc-1</guid>
      <pubDate>Tue, 22 Sep 2026 18:00:00 GMT</pubDate>
      <description>Free student tickets. Volunteers wanted — apply now.</description>
    </item>
  </channel>
</rss>
"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example</title>
  <entry>
    <title>Demo Day</title>
    <id>urn:demo</id>
    <link href="https://example.com/demo"/>
    <published>2026-10-01T15:00:00Z</published>
    <summary>Founders and investors</summary>
  </entry>
</feed>
"""


def test_rss_and_atom_items():
    now = datetime.now(UTC)
    rss = parse_feed(RSS, source_id="rss", fetched_at=now, org="Org", source_url="https://example.com/feed")
    assert len(rss) == 1
    assert rss[0].title == "Boston AI Mixer"
    assert rss[0].canonical_url == "https://example.com/ai-mixer"
    atom = parse_feed(ATOM, source_id="rss", fetched_at=now, org=None, source_url="https://example.com/atom")
    assert atom[0].title == "Demo Day"
    assert "example.com/demo" in (atom[0].canonical_url or "")
