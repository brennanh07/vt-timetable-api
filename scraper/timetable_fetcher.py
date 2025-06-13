import requests
import logging
from requests.exceptions import RequestException, HTTPError, Timeout, ConnectionError
from typing import Optional
from tidylib import tidy_document


class TimetableFetcher:
    """Fetches the HTML content of the Virginia Tech Timetable website for a specific term and subject."""

    def __init__(self, term: str):
        """Constructs a fetcher with the specified academic term and subject code.

        Args:
            term (str): The academic term year code (e.g., "202509" for Fall 2025)
            subject (str): The subject code (e.g., "CS" for Computer Science)
        """
        self.base_url = "https://selfservice.banner.vt.edu/ssb/HZSKVTSC.P_ProcRequest"
        self.term = term

        # initialize a persistent session object
        self.session = requests.Session()

        # set cookie
        # self.session.cookies.update(
        #     {
        #         "TESTID": "set",
        #         "JSESSIONID": "53EF6C1AA6C7A81ACC78DEA84C991E30",
        #         "SESSID": "WDhHQU1JMTMwNjY3MzM=",
        #         "__utmc": "53132202",
        #         "_gcl_au": "1.1.1825573836.1743980846",
        #         "cebs": "1",
        #         "_fbp": "fb.1.1744216546386.502454092834801554",
        #         "_ga_6NH85V357P": "GS1.2.1744216547.1.0.1744216547.0.0.0",
        #         "cebsp_": "9",
        #         "_ga_D99RC0R2WH": "GS1.1.1744216833.1.0.1744216839.0.0.0",
        #         "_ga_0HYE8YG0M6": "GS1.1.1744216840.1.1.1744218472.60.0.0",
        #         "_ce.s": "v~236301ecf4eb4ac0963ed282837245a733183336~lcw~1744220552419~vir~returning~lva~1744216547773~vpv~0~v11.fhb~1744216549325~v11.lhb~1744220552418~v11.cs~279989~v11.s~b1d81ee0-1560-11f0-94bf-4900aa19583a~v11.sla~1744216635640~v11.send~1744220825935~lcw~1744220825935",
        #         "_ga_3KYJBSR9WZ": "GS1.1.1744220825.2.0.1744220825.0.0.0",
        #         "_ga_DTEQ1JM2SG": "GS1.1.1744220825.9.0.1744220825.0.0.0",
        #         "_ga_5Z60EH83Q9": "GS1.1.1744220825.9.0.1744220825.60.0.0",
        #         "_ga_T9PY1ZDFJ5": "GS1.1.1744570822.7.1.1744570833.0.0.0",
        #         "__utmz": "53132202.1744570838.8.3.utmcsr=api-dc4a4e89.duosecurity.com|utmccn=(referral)|utmcmd=referral|utmcct=/",
        #         "__utma": "53132202.1423708268.1735163482.1744570838.1744573010.9",
        #         "_ga": "GA1.2.1423708268.1735163482",
        #         "_ga_VPVQ2Q69QH": "GS1.2.1744585539.49.1.1744585549.0.0.0",
        #         "ssb-ords.selfservice.banner.vt.edu": "f7bcc6026c739bff",
        #         "ssomgr.selfservice.banner.vt.edu": "e321e3a53635350f",
        #         "IDMSESSID": "3A2CEEDF6C8068F17387A7249C125BB28C07535EDD9D631C3AB95A6268561A3BD9C82E0FE508AAC30B1461752F59CB84F1F5D031D62721933F71949DD0440C09",
        #     }
        # )

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

            return self.fix_html(response.text)

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

    def fix_html(self, html: str) -> str:
        cleaned, errors = tidy_document(html, options={"numeric-entities": 1})
        return cleaned

    def close_session(self):
        """Closes the persistent session."""
        logging.info("Closing TimetableFetcher session.")
        self.session.close()
