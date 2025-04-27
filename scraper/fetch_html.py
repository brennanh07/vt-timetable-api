import requests

class TimetableFetcher:
    """Fetches the HTML content of the Virginia Tech Timetable website for a specific term and subject.
    """
    def __init__(self, term: str, subject: str):
        """Constructs a fetcher with the specified academic term and subject code.

        Args:
            term (str): The academic term year code (e.g., "202509" for Fall 2025)
            subject (str): The subject code (e.g., "CS" for Computer Science)
        """
        self.base_url = "https://selfservice.banner.vt.edu/ssb/HZSKVTSC.P_ProcRequest"
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
            "inst_name": ""
        }

    def fetch_html(self) -> str:
        """Sends a POST request to the timetable server and returns the raw HTML content.

        Returns:
            str: The HTML content of the timetable page
        """
        response = requests.post(self.base_url, data=self.payload)
        response.raise_for_status()
        return response.text
