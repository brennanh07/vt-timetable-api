import unittest
from unittest.mock import patch, MagicMock
from requests.exceptions import RequestException, HTTPError, Timeout, ConnectionError
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
            self.fetcher.base_url, data=self.fetcher.payload, timeout=10
        )

    @patch("scraper.timetable_fetcher.requests.post")
    def test_fetch_html_timeout(self, mock_post):
        """Tests that fetch_html() raises RuntimeError on timeout."""
        mock_post.side_effect = Timeout()

        with self.assertRaises(RuntimeError) as context:
            self.fetcher.fetch_html()

        self.assertIn("timed out", str(context.exception).lower())

    @patch("scraper.timetable_fetcher.requests.post")
    def test_fetch_html_http_error(self, mock_post):
        """Tests that fetch_html() raises RuntimeError on HTTP error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError("404 Client Error")
        mock_post.return_value = mock_response

        with self.assertRaises(RuntimeError) as context:
            self.fetcher.fetch_html()

        self.assertIn("http error", str(context.exception).lower())

    @patch("scraper.timetable_fetcher.requests.post")
    def test_fetch_html_connection_error(self, mock_post):
        """Tests that fetch_html() raises RuntimeError on connection error."""
        mock_post.side_effect = ConnectionError()

        with self.assertRaises(RuntimeError) as context:
            self.fetcher.fetch_html()

        self.assertIn("connection error", str(context.exception).lower())

    @patch("scraper.timetable_fetcher.requests.post")
    def test_fetch_html_generic_request_exception(self, mock_post):
        """Tests that fetch_html() raises RuntimeError on general request exception."""
        mock_post.side_effect = RequestException("Unexpected error")

        with self.assertRaises(RuntimeError) as context:
            self.fetcher.fetch_html()

        self.assertIn("error occurred", str(context.exception).lower())
