from bs4 import BeautifulSoup

class TimetableParser:
    """Uses bs4 to parse the HTML content fetched from the Virginia Tech Timetable website
    """
    def __init__(self, html: str):
        self.soup = BeautifulSoup(html, "html.parser")
        self.subjects = []

    def parse_subjects(self):
        # TODO: extract subjects using regex from lines like this:
        """
        document.ttform.subj_code.options[44]=new Option("CS - Computer Science","CS",false, true);
        """

    def parse_courses(self):
        """

        """
