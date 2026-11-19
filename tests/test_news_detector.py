import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1] / "news detector"
sys.path.insert(0, str(APP_DIR))
import app as news_app  # noqa: E402
from fact_check_service import FactCheck, FactCheckSearchResult  # noqa: E402


class NewsDetectorTests(unittest.TestCase):
    def test_home_describes_fact_check_sources_and_inconclusive_results(self):
        response = news_app.app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Snopes", response.data)
        self.assertIn(b"does not mean a claim is true or false", response.data)

    def test_empty_submission_shows_validation_message(self):
        response = news_app.app.test_client().post(
            "/predict",
            data={"news_article": "   "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Paste a claim, headline, or article", response.data)

    def test_submission_displays_matching_fact_checks(self):
        check = FactCheck(
            "Did a council approve the plan?",
            "https://www.snopes.com/fact-check/example/",
            "Snopes",
            "The council vote was reviewed.",
            "Thu, 19 Nov 2026 10:00:00 +0000",
        )
        result = FactCheckSearchResult((check,), ("Snopes",), ())
        with patch.object(news_app, "find_related_fact_checks", return_value=result):
            response = news_app.app.test_client().post(
                "/predict",
                data={"news_article": "Did a council approve the plan?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Did a council approve the plan?", response.data)
        self.assertIn(b"https://www.snopes.com/fact-check/example/", response.data)
        self.assertNotIn(b"Model screening", response.data)

    def test_no_match_is_not_presented_as_a_truth_verdict(self):
        result = FactCheckSearchResult((), ("Snopes",), ())
        with patch.object(news_app, "find_related_fact_checks", return_value=result):
            response = news_app.app.test_client().post(
                "/predict",
                data={"news_article": "A claim with no related check"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No related fact-check found", response.data)
        self.assertIn(b"not a verdict", response.data)

    def test_all_feed_failures_are_reported_as_unavailable(self):
        result = FactCheckSearchResult((), (), ("Snopes",))
        with patch.object(news_app, "find_related_fact_checks", return_value=result):
            response = news_app.app.test_client().post(
                "/predict",
                data={"news_article": "A claim to check"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"could not reach any fact-check feeds", response.data)
        self.assertNotIn(b"No related fact-check found", response.data)

    def test_submission_over_limit_is_rejected(self):
        response = news_app.app.test_client().post(
            "/predict",
            data={"news_article": "a" * (news_app.MAX_ARTICLE_LENGTH + 1)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please keep the article under", response.data)


if __name__ == "__main__":
    unittest.main()
