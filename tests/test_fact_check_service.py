import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import requests

APP_DIR = Path(__file__).resolve().parents[1] / "news detector"
sys.path.insert(0, str(APP_DIR))
import fact_check_service  # noqa: E402


FEED_XML = b"""<?xml version="1.0"?>
<rss><channel><item>
  <title>Did city council approve the plan to close three schools?</title>
  <link>https://www.snopes.com/fact-check/school-closures/</link>
  <description>The council vote was reviewed.</description>
  <pubDate>Thu, 19 Nov 2026 10:00:00 +0000</pubDate>
</item></channel></rss>
"""


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self.content


class FactCheckServiceTests(unittest.TestCase):
    def test_returns_matching_fact_check_with_source_link(self):
        with patch(
            "fact_check_service.requests.get",
            return_value=FakeResponse(FEED_XML),
        ):
            result = fact_check_service.find_related_fact_checks(
                "Did city council approve the plan to close three schools?"
            )

        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].source, "Snopes")
        self.assertEqual(
            result.matches[0].url,
            "https://www.snopes.com/fact-check/school-closures/",
        )
        self.assertEqual(result.failed_sources, ())
        self.assertEqual(result.checked_sources, ("Snopes",))

    def test_matches_short_claims_with_two_shared_terms(self):
        with patch(
            "fact_check_service.requests.get",
            return_value=FakeResponse(FEED_XML),
        ):
            result = fact_check_service.find_related_fact_checks("council approve")

        self.assertEqual(len(result.matches), 1)

    def test_long_claim_does_not_get_full_score_from_two_shared_terms(self):
        fact_check = fact_check_service.FactCheck(
            "Council approves",
            "https://www.snopes.com/fact-check/example/",
            "Snopes",
            "",
            "",
        )
        query_terms = {"council", "approves"} | {
            f"claim{index}" for index in range(18)
        }

        score = fact_check_service._match_score(query_terms, fact_check)

        self.assertLess(score, fact_check_service.MIN_MATCH_SCORE)

    def test_searches_configured_news_feeds_locally_without_api_key(self):
        related = fact_check_service.FactCheck(
            "Council approves school plan",
            "https://www.theguardian.com/world/example",
            "The Guardian",
            "",
            "Mon, 23 Nov 2026 09:00:00 GMT",
        )
        unrelated = fact_check_service.FactCheck(
            "Markets close higher after trading",
            "https://www.aljazeera.com/news/example",
            "Al Jazeera",
            "",
            "Mon, 23 Nov 2026 09:00:00 GMT",
        )
        def feed_entries(feed):
            return [related] if feed.name == "The Guardian" else [unrelated]

        with patch(
            "fact_check_service._parse_feed",
            side_effect=feed_entries,
        ) as parse_feed:
            result = fact_check_service.find_related_news(
                "Council approves the school plan"
            )

        self.assertEqual(len(result.articles), 1)
        self.assertEqual(result.articles[0].title, related.title)
        self.assertEqual(
            result.checked_sources,
            self._expected_news_sources(),
        )
        self.assertEqual(result.failed_sources, ())
        self.assertEqual(
            parse_feed.call_count,
            len(fact_check_service.NEWS_FEEDS) + 1,
        )

    def test_searches_google_news_rss_using_the_submitted_claim(self):
        claim = "Council approves school plan & budget " + "extra " * 100
        google_article = fact_check_service.FactCheck(
            "Council approves school plan",
            "https://news.google.com/rss/articles/example",
            "Google News",
            "",
            "",
        )
        feeds = []

        def feed_entries(feed):
            feeds.append(feed)
            return [google_article] if feed.name == "Google News" else []

        with patch(
            "fact_check_service._parse_feed",
            side_effect=feed_entries,
        ):
            result = fact_check_service.find_related_news(claim)

        google_feed = next(feed for feed in feeds if feed.name == "Google News")
        self.assertEqual(
            parse_qs(urlsplit(google_feed.url).query)["q"],
            [claim[: fact_check_service.MAX_GOOGLE_NEWS_QUERY_LENGTH]],
        )
        self.assertEqual(urlsplit(google_feed.url).hostname, "news.google.com")
        self.assertEqual(result.checked_sources, self._expected_news_sources())
        self.assertEqual(result.articles[0].source, "Google News")

    def test_parses_google_news_links_but_rejects_external_item_links(self):
        google_feed = fact_check_service.RSSFeed(
            "Google News",
            "https://news.google.com/rss/search?q=school",
            "news.google.com",
        )
        content = b"""<rss><channel>
        <item>
          <title>School plan approved by council</title>
          <link>https://news.google.com/rss/articles/example</link>
        </item>
        <item>
          <title>Fake school plan report</title>
          <link>https://example.com/fake</link>
        </item>
        </channel></rss>"""

        with patch(
            "fact_check_service.requests.get",
            return_value=FakeResponse(content),
        ):
            entries = fact_check_service._parse_feed(google_feed)

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0].url,
            "https://news.google.com/rss/articles/example",
        )

    def test_reports_news_feed_failures_separately_from_no_matches(self):
        with patch(
            "fact_check_service._parse_feed",
            side_effect=requests.Timeout("feed timed out"),
        ):
            result = fact_check_service.find_related_news("A claim to search")

        self.assertEqual(result.articles, ())
        self.assertEqual(result.checked_sources, ())
        self.assertEqual(
            result.failed_sources,
            self._expected_news_sources(),
        )

    @staticmethod
    def _expected_news_sources():
        return tuple(feed.name for feed in fact_check_service.NEWS_FEEDS) + (
            "Google News",
        )

    def test_ignores_feed_links_outside_the_verified_source_domain(self):
        unsafe_feed = FEED_XML.replace(
            b"https://www.snopes.com/fact-check/school-closures/",
            b"https://example.com/fake-check/",
        )
        with patch(
            "fact_check_service.requests.get",
            return_value=FakeResponse(unsafe_feed),
        ):
            result = fact_check_service.find_related_fact_checks(
                "Did city council approve the plan to close three schools?"
            )

        self.assertEqual(result.matches, ())
        self.assertEqual(result.checked_sources, ("Snopes",))

    def test_reports_feed_failure_without_claiming_it_was_checked(self):
        with patch(
            "fact_check_service.requests.get",
            side_effect=requests.Timeout("feed timed out"),
        ):
            result = fact_check_service.find_related_fact_checks("A sample claim")

        self.assertEqual(result.matches, ())
        self.assertEqual(result.checked_sources, ())
        self.assertEqual(result.failed_sources, ("Snopes",))

    def test_rejects_oversized_feed(self):
        oversized = b"x" * (fact_check_service.MAX_FEED_BYTES + 1)
        with patch(
            "fact_check_service.requests.get",
            return_value=FakeResponse(oversized),
        ):
            result = fact_check_service.find_related_fact_checks("A sample claim")

        self.assertEqual(result.matches, ())
        self.assertEqual(result.checked_sources, ())
        self.assertEqual(result.failed_sources, ("Snopes",))


if __name__ == "__main__":
    unittest.main()
