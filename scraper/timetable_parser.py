from bs4 import BeautifulSoup
import re
from timetable_fetcher import TimetableFetcher

class TimetableParser:
    """Uses bs4 to parse the HTML content fetched from the Virginia Tech Timetable website
    """
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
            if f"case \"{term}\"" in script_tag.text:
                target_script_text = script_tag.text

        target_term_subjects = re.search(rf'case "{term}" :(.*?)break', target_script_text, re.DOTALL)
        

        with open("subjects.html", "w", encoding="utf-8") as f:
            f.write(target_term_subjects.group(1).strip())


    def parse_courses(self):
        """

        """

if __name__ == "__main__":
    fetcher = TimetableFetcher("202509", "%")
    raw_html = fetcher.fetch_html()
    parser = TimetableParser(raw_html)
    parser.parse_subjects("202509")