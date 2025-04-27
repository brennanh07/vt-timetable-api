import unittest
from unittest.mock import patch, MagicMock
from scraper.timetable_fetcher import TimetableFetcher


class TimetableFetcherTest(unittest.TestCase):
    def setUp(self):
        """Sets up the text fixture. Runs once at the beginning of each test."""
        self.term = "202509"
        self.subject = "CS"
        self.fetcher = TimetableFetcher(self.term, self.subject)

    def tearDown(self):
        return super().tearDown()

    @patch("scraper.timetable_fetcher.requests.post")
    def test_fetch_html_success(self, mock_post):
        """Tests that the fetch_html() function returns the expected HTML content.

        Args:
            mock_post (MagicMock): A mock of the requests.post method, injected
            by the @patch decorator to simulate an HTTP response.
        """
        # ===== Arrange =====
        expected_html = "<html>Test HTML</html>"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = expected_html
        mock_post.return_value = mock_response

        # ===== Act ======
        actual_html = self.fetcher.fetch_html()

        # ===== Assert =====
        self.assertEqual(actual_html, expected_html)
        mock_post.assert_called_once_with(
            self.fetcher.base_url, data=self.fetcher.payload
        )
