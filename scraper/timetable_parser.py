from bs4 import BeautifulSoup
import re
from timetable_fetcher import TimetableFetcher
import logging

logging.basicConfig(level=logging.DEBUG)


class TimetableParser:
    """Uses bs4 to parse the HTML content fetched from the Virginia Tech Timetable website"""

    def __init__(self, html: str):
        self.soup = BeautifulSoup(html, "html.parser")
        self.subjects = []

    def parse_subjects(self, term: str):
        # TODO: extract subjects using regex from lines like this:
        """
        document.ttform.subj_code.options[44]=new Option("CS - Computer Science","CS",false, true);
        """
        script_tags = self.soup.find_all("script")

        target_script_text = None
        for script_tag in script_tags:
            if f'case "{term}"' in script_tag.text:
                target_script_text = script_tag.text

        match = re.search(rf'case "{term}" :(.*?)break', target_script_text, re.DOTALL)
        if not match:
            logging.error(f"Error: Could not find script block for term {term}")
            return

        # get the first match, and strip empty lines
        target_term_subjects = match.group(1).strip()

        # remove the first "document.ttform.subj_code.options[0]=..." (all subjects) line
        all_lines = target_term_subjects.splitlines()
        if all_lines and "All Subjects" in all_lines[0]:
            all_lines = all_lines[1:]

        # extract subject code from each line
        for line in all_lines:
            subject_match = re.search(r'new Option\(".*?","(.*?)"', line)

            if subject_match:
                subject_code = subject_match.group(1)
                self.subjects.append(subject_code)  # add to global subjects list

    def parse_courses(self):
        """ """


if __name__ == "__main__":
    fetcher = TimetableFetcher("202509", "%")
    raw_html = fetcher.fetch_html()
    parser = TimetableParser(raw_html)
    parser.parse_subjects("202509")
