import sys
import unittest
from pathlib import Path
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
