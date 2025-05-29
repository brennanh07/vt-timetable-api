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
        self.term = term

        # initialize a persistent session object
        self.session = requests.Session()

        logging.info("TimetableFetcher initialized with persistent session")

    def fetch_html(self, subject: Optional[str] = "%") -> Optional[str]:
        """Sends a POST request to the timetable server and returns the raw HTML content.

        Args:
            subject (Optional[str]): The subject code (e.g., "CS"). Defaults to "%" for all subjects

        Returns:
            Optional[str]: The HTML content of the timetable page, or None if an error occurs.
                           Returning None instead of raising allows the parser to continue with other subjects.

        Raises:
            RuntimeError: If there is a network-related error or HTTP error.
        """
        # construct payload dynamically
        payload = {
            "CAMPUS": "0",
            "TERMYEAR": self.term,
            "CORE_CODE": "AR%",
            "subj_code": subject if subject is not None else "%",
            "SCHDTYPE": "%",
            "CRSE_NUMBER": "",
            "crn": "",
            "open_only": "",
            "disp_comments_in": "",
            "sess_code": "%",
            "BTN_PRESSED": "FIND class sections",
            "inst_name": "",
        }

        response = None
        try:
            logging.info(
                f"Fetching timetable for term {self.term}, subject '{subject}'..."
            )

            # use session object to make POST request
            response = self.session.post(self.base_url, data=payload, timeout=20)

            # check for HTTP errors (4xx or 5xx)
            response.raise_for_status()
            logging.info(f"Timetable fetch successful for subject '{subject}'.")

            # decode using detected encoding, fall back to utf-8
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text

        except Timeout:
            logging.error(f"The request timed out while fetching subject '{subject}'.")
            return None

        except HTTPError as http_err:
            status_code = response.status_code if response else "N/A"
            logging.error(
                f"HTTP error occurred fetching subject '{subject}': {http_err} - Status Code: {status_code}"
            )
            # logging.debug(f"Response Body: {response.text[:500]}...") # Uncomment for debugging server errors
            return None

        except ConnectionError as conn_err:
            logging.error(
                f"A connection error occurred fetching subject '{subject}': {conn_err}"
            )
            return None

        except RequestException as req_error:
            logging.error(
                f"An error occurred fetching subject '{subject}': {req_error}"
            )
            return None  # Return None on other request errors

    def close_session(self):
        """Closes the persistent session."""
        logging.info("Closing TimetableFetcher session.")
        self.session.close()
