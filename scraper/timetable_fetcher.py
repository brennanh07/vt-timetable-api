import requests
import logging
from requests.exceptions import RequestException, HTTPError, Timeout, ConnectionError
from typing import Optional


class TimetableFetcher:
    """Fetches the HTML content of the Virginia Tech Timetable website for a specific term and subject."""

    def __init__(self, term: str, subject: str):
        """Constructs a fetcher with the specified academic term and subject code.

        Args:
            term (str): The academic term year code (e.g., "202509" for Fall 2025)
            subject (str): The subject code (e.g., "CS" for Computer Science)
        """
        self.base_url = "https://selfservice.banner.vt.edu/ssb/HZSKVTSC.P_ProcRequest"
        self.default_subject = subject
        self.term = term

        self.payload = {
            "CAMPUS": "0",
            "TERMYEAR": term,
            "CORE_CODE": "AR%",
            "subj_code": subject,
            "SCHDTYPE": "%",
            "CRSE_NUMBER": "",
            "crn": "",
            "open_only": "",
            "disp_comments_in": "",
            "sess_code": "%",
            "BTN_PRESSED": "FIND class sections",
            "inst_name": "",
        }

        # single persistent session for all requests
        self.session = requests.Session()

    def fetch_html(self, subject: Optional[str] = None) -> Optional[str]:
        """Sends a POST request to the timetable server and returns the raw HTML content.

        Returns:
            str: The HTML content of the timetable page

        Raises:
            RuntimeError: If there is a network-related error or HTTP error.
        """
        try:
            used_subject = subject if subject else self.default_subject
            payload = self.payload.copy()
            payload["subj_code"] = used_subject

            logging.info(f"Fetching timetable for subject: {used_subject}...")

            response = requests.post(self.base_url, data=self.payload, timeout=10)
            response.raise_for_status()
            logging.info("Timetable fetch successful.")
            return response.text
        except Timeout:
            logging.error("The request timed out.")
            raise RuntimeError("The request timed out.")
        except HTTPError as http_err:
            logging.error(f"HTTP error occurred: {http_err}")
            raise RuntimeError(f"HTTP error occurred: {http_err}")
        except ConnectionError:
            logging.error("A connection error occurred.")
            raise RuntimeError("A connection error occurred.")
        except RequestException as req_error:
            logging.error(
                f"An error occurred while fetching the timetable: {req_error}"
            )
            raise RuntimeError(
                f"An error occurred while fetching the timetable: {req_error}"
            )

        return None

    def close(self):
        """Closes the session when done."""
        self.session.close()
