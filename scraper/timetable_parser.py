from bs4 import BeautifulSoup
import re
from timetable_fetcher import TimetableFetcher
import logging
from typing import Optional, List, Dict, Any

logging.basicConfig(level=logging.DEBUG)


class TimetableParser:
    """Uses bs4 to parse the HTML content fetched from the Virginia Tech Timetable website"""

    def __init__(self, fetcher: TimetableFetcher, term: str):
        """Constructs a new parser with a TimetableFetcher instance and the target term.

        Args:
            fetcher (TimetableFetcher): An instance of TimetableFetcher
            term (str): The academic term identifier (e.g., "202509" for Fall 2025)
        """
        self.fetcher: TimetableFetcher = fetcher
        self.term: str = term
        self.subjects: List[str] = []
        self.course_data: List[Dict[str, Any]] = []  # to store final structured data
        self.soup: Optional[BeautifulSoup] = None  # initial soup for subject parsing

    def _initialize_subjects(self) -> bool:
        """Fetches the initial HTML and parses subjects if not already done."""
        if self.subjects:
            return True

        logging.info("Subjects list is empty. Fetching initial page to parse subjects.")
        initial_html = self.fetcher.fetch_html(subject="%")

        if not initial_html:
            logging.error("Failed to fetch initial HTML for subject parsing")
            return False

        self.soup = BeautifulSoup(initial_html, "html.parser")
        self.parse_subjects(self.term)

        if not self.subjects:
            logging.error("Failed to parse subjects from the initial page.")
            return False

        return True

    def parse_subjects(self, term: str):
        """
        Extracts subject codes for a specified term by parsing JavaScript within the page source.

        This method orchestrates finding the relevant script, extracting the term-specific
        code block, and parsing subject codes from that block. The results are appended
        to the instance's `self.subjects` list.

        Args:
            term (str): The academic term identifier (e.g., "202409") to extract subjects for.
                        It's expected to be a string that uniquely identifies the term
                        within the JavaScript 'case' statement.
        """
        logging.info(f"Starting subject parsing for term: {term}")

        # Step 1: Find the relevant script tag's text content
        script_text = self._find_term_script_text(term)
        if script_text is None:
            logging.error(
                f"Processing stopped: Could not find script text for term '{term}'."
            )
            return  # Stop processing if script not found

        # Step 2: Extract the term-specific block from the script text
        term_script_block = self._extract_term_script_block(script_text, term)
        if term_script_block is None:
            logging.error(
                f"Processing stopped: Could not extract script block for term '{term}'."
            )
            return  # Stop processing if block not extracted

        # Step 3: Parse subject codes from the extracted block
        parsed_codes = self._parse_subject_codes_from_block(term_script_block)

        if not parsed_codes:
            logging.warning(
                f"No subject codes were successfully parsed for term '{term}' from the extracted block."
            )
        else:
            # Append the newly found subjects to the main list
            count_before = len(self.subjects)
            self.subjects.extend(parsed_codes)

            count_after = len(self.subjects)
            new_codes_count = (
                count_after - count_before
            )  # Accounts for potential duplicates if not removed
            logging.info(
                f"Successfully parsed and added {new_codes_count} subject codes for term '{term}'. Total subjects now: {count_after}"
            )

    def _find_term_script_text(self, term: str) -> Optional[str]:
        """Finds the text content of the script tag containing the specified term's data.

        Args:
            term (str): The academic term identifier (e.g., "202509" for Fall 2025)

        Returns:
            Optional[str]: The text content of the matching script tag, or None if not found
        """
        script_tags = self.soup.find_all("script")
        if not script_tags:
            logging.warning("No <script> tags found in the provided soup object.")
            return None

        # the specific string indicating the term's data block
        term_marker = f'case "{term}"'

        for script_tag in script_tags:
            # check if the script tag has text content before searching within it
            if not script_tag.string:
                continue

            script_content = script_tag.string
            if term_marker in script_content:
                logging.debug(f"Found script tag containing marker for term '{term}'.")
                return script_content

        logging.error(
            f"Could not find a script tag containing the marker '{term_marker}' for term '{term}'."
        )
        return None

    def _extract_term_script_block(self, script_text: str, term: str) -> Optional[str]:
        """Extracts the block of JavaScript code specific to the term from the full script text.

        Args:
            script_text (str): The full text content of the relevant script tag
            term (str): The academic term identifier used in the 'case' statement

        Returns:
            Optional[str]: The extracted block of JavaScript code for the term (between 'case' and 'break;'),
                           stripped of leading/trailing whitespace, or None if the block cannot be found
        """
        # Regex to find the block between 'case "{term}":' and the next 'break;'
        pattern = rf'case "{term}"\s*:(.*?)break;'
        match = re.search(pattern, script_text, re.DOTALL | re.IGNORECASE)

        if match:
            # Return the captured group (the code block), stripped of surrounding whitespace.
            extracted_block = match.group(1).strip()
            logging.debug(f"Successfully extracted script block for term '{term}'.")
            return extracted_block
        else:
            # Log details to help diagnose regex failure
            logging.error(
                f"Could not extract the script block for term '{term}'. Regex pattern '{pattern}' did not find a match in the provided script text."
            )
            # logging.debug(f"Script text searched:\n---\n{script_text[:500]}...\n---") # Uncomment for debugging
            return None

    def _parse_subject_codes_from_block(self, script_block: str) -> List[str]:
        """
        Parses individual subject codes from the extracted JavaScript block using a flattened structure.

        Assumes subject codes are defined in lines like:
        `... = new Option("Subject Name", "CODE"[, optional_args]);`

        Args:
            script_block (str): The block of JavaScript code containing subject option definitions.

        Returns:
            List[str]: A list of extracted subject codes (e.g., ["ACCT", "CS", "MATH"]).
        """
        subject_codes: List[str] = []
        lines = script_block.splitlines()  # Split the block into individual lines

        # Regex pattern looks for 'new Option("...", "CODE"' and captures the CODE.
        line_pattern = re.compile(r'new Option\(".*?",\s*"(.*?)"', re.IGNORECASE)

        for line in lines:  # Removed enumerate as 'i' is no longer needed
            line = line.strip()

            # --- Guard Clauses using 'continue' to flatten structure ---

            # Skip empty lines
            if not line:
                continue

            # Skip the "All Subjects" line
            if "All Subjects" in line and "new Option" in line:
                logging.debug(f"Skipping 'All Subjects' line: {line}")
                continue

            # Attempt to match the pattern
            match = line_pattern.search(line)

            # If no match is found for the pattern
            if not match:
                # Log a warning only if it looks like it should have matched but didn't
                if "new Option" in line and not line.startswith("//"):
                    logging.warning(
                        f"Regex did not find subject code pattern in line: {line}"
                    )
                continue  # Move to the next line

            # --- Match found, proceed with validation ---
            subject_code = match.group(1)

            # Validate that the extracted code looks like a typical subject code
            if not re.match(r"^[A-Z0-9]+$", subject_code):
                logging.warning(
                    f"Extracted value '{subject_code}' from line '{line}' does not match expected subject code format (A-Z, 0-9)."
                )
                continue  # Move to the next line if format is invalid

            # --- All checks passed, append the valid subject code ---
            subject_codes.append(subject_code)
            logging.debug(f"Extracted subject code: {subject_code}")

        return subject_codes

    def parse_courses(self):
        """TODO: Parses individual course listings for each subject."""
        if not self._initialize_subjects():
            logging.error("Could not initialize subjects. Aborting course parsing.")
            return []

        logging.info(
            f"Starting course parsing term {self.term} across {len(self.subjects)} subjects."
        )
        self.course_data = []  # reset data for this run

        # temp map: {course_key : course_dict}
        all_courses_map: Dict[str, Dict[str, Any]] = {}

        for subject in self.subjects:
            logging.info(f"--- Processing subject: {subject} ---")
            subject_html = self.fetcher.fetch_html(subject=subject)

            if not subject_html:
                logging.warning(f"Failed to fetch HTML for subject {subject}. Skipping")
                continue

            subject_soup = BeautifulSoup(subject_html, "html.parser")


if __name__ == "__main__":
    fetcher = TimetableFetcher("202509", "%")
    raw_html = fetcher.fetch_html()
    parser = TimetableParser(raw_html)
    parser.parse_subjects("202509")
