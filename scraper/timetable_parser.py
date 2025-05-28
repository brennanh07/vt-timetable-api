import re
import logging
from bs4 import BeautifulSoup, Tag
from typing import List, Optional, Dict, Any
from datetime import datetime
from scraper.timetable_fetcher import TimetableFetcher

# --- Configure logging (Set level to DEBUG to see detailed logs) ---
# logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')


class TimetableParser:
    """
    Parses subjects and course details from HTML content fetched
    from the Virginia Tech Timetable website using a TimetableFetcher.
    """

    def __init__(self, fetcher: TimetableFetcher, term: str):
        """
        Initializes the parser with a TimetableFetcher instance and the target term.

        Args:
            fetcher (TimetableFetcher): An instance of TimetableFetcher.
            term (str): The academic term identifier (e.g., "202509").
        """
        if not isinstance(fetcher, TimetableFetcher):
            raise TypeError("Input 'fetcher' must be a TimetableFetcher object.")
        self.fetcher: TimetableFetcher = fetcher
        self.term: str = term
        self.subjects: List[str] = []
        self.courses_data: List[Dict[str, Any]] = []  # To store final structured data
        self.soup: Optional[BeautifulSoup] = None  # Initial soup for subject parsing

    def _initialize_subjects(self):
        """Fetches the initial HTML and parses subjects if not already done."""
        if not self.subjects:
            logging.info(
                "Subjects list is empty. Fetching initial page to parse subjects."
            )
            initial_html = self.fetcher.fetch_html(subject="%")
            if not initial_html:
                logging.error("Failed to fetch initial HTML for subject parsing.")
                return False

            self.soup = BeautifulSoup(initial_html, "html.parser")

            # Store length before parsing
            subjects_before = len(self.subjects)
            self.parse_subjects(self.term)
            # Store length after parsing
            subjects_after = len(self.subjects)

            # Check if any subjects were actually found *and added* during this call
            if subjects_after == subjects_before or not self.subjects:
                # Log error only if parsing was attempted but yielded nothing *new*
                # and the list is still empty overall.
                if not self.subjects:
                    logging.error("Failed to parse subjects from the initial page.")
                # Return False if no subjects were effectively initialized
                return False

            logging.info(
                f"Initialized {len(self.subjects)} subjects for term {self.term}."
            )
        # If self.subjects was already populated, or if parsing succeeded, return True
        return True

    # --- Public Methods ---
    def parse_subjects(self, term: str):
        """
        Extracts subject codes for a specified term by parsing JavaScript within the page source.
        Requires self.soup to be initialized.
        """
        if not self.soup:
            logging.error("Cannot parse subjects, self.soup is not initialized.")
            return
        logging.info(f"Starting subject parsing for term: {term}")
        script_text = self._find_term_script_text(term)
        if script_text is None:
            logging.error(
                f"Processing stopped: Could not find script text for term '{term}'."
            )
            return
        term_script_block = self._extract_term_script_block(script_text, term)
        if term_script_block is None:
            logging.error(
                f"Processing stopped: Could not extract script block for term '{term}'."
            )
            return

        parsed_codes_raw = self._parse_subject_codes_from_block(term_script_block)

        # Use dict.fromkeys to preserve order while getting unique codes
        parsed_codes_unique_this_call = list(dict.fromkeys(parsed_codes_raw))

        if not parsed_codes_unique_this_call:  # Check the de-duplicated list
            logging.warning(
                f"No unique subject codes were successfully parsed for term '{term}'."
            )
        else:
            count_before = len(self.subjects)
            # Now check these unique codes against codes already present in self.subjects
            unique_new_codes = [
                code
                for code in parsed_codes_unique_this_call
                if code not in self.subjects
            ]
            self.subjects.extend(unique_new_codes)
            count_after = len(self.subjects)
            new_codes_count = count_after - count_before
            logging.info(
                f"Successfully parsed and added {new_codes_count} unique subject codes for term '{term}'. Total subjects now: {count_after}"
            )

    def parse_courses(self) -> List[Dict[str, Any]]:
        """
        Parses course listings for all subjects for the initialized term.
        Iterates through subjects, fetches HTML for each, parses the course table,
        and structures the data according to the Course/Section/MeetingTime model.
        Returns a list of dictionaries representing Courses, ready for JSON serialization.
        """
        if not self._initialize_subjects():
            logging.error("Could not initialize subjects. Aborting course parsing.")
            return []

        logging.info(
            f"Starting course parsing for term {self.term} across {len(self.subjects)} subjects."
        )
        self.courses_data = []
        all_courses_map: Dict[str, Dict[str, Any]] = {}

        for subject in self.subjects:
            logging.info(f"--- Processing Subject: {subject} ---")
            subject_html = self.fetcher.fetch_html(subject=subject)
            if not subject_html:
                logging.warning(
                    f"Failed to fetch HTML for subject {subject}. Skipping."
                )
                continue

            subject_soup = BeautifulSoup(subject_html, "html.parser")
            search_results_div = subject_soup.find("div", class_="class1")
            course_table = None
            if search_results_div:
                course_table = search_results_div.find("table", class_="dataentrytable")
                if course_table:
                    logging.debug(
                        f"Found course table (class='dataentrytable') inside div.class1 for subject {subject}."
                    )
                else:
                    logging.warning(
                        f"Found div.class1 but could not find table.dataentrytable within it for subject {subject}."
                    )
            else:
                logging.warning(
                    f"Could not find search results div (class='class1') for subject {subject}. Table finding might fail."
                )
                course_table = subject_soup.find("table", class_="dataentrytable")
                if course_table:
                    logging.debug(
                        f"Found course table (class='dataentrytable') using fallback search for subject {subject}."
                    )

            if not course_table:
                logging.warning(
                    f"Could not find course table for subject {subject}. Skipping."
                )
                continue

            rows = course_table.find_all("tr")
            logging.debug(
                f"Found {len(rows)} total <tr> elements in the identified table for subject {subject}."
            )

            if len(rows) < 2:
                logging.info(
                    f"No data rows (found {len(rows)} total rows, need >= 2) in table for subject {subject}."
                )
                continue

            current_course_key = None
            current_section_crn = None

            for i, row in enumerate(rows[1:], 1):
                cells = row.find_all("td", recursive=False)
                num_cells = len(cells)
                cell_preview = [c.get_text(strip=True)[:20] for c in cells[:5]]
                logging.debug(
                    f"Row {i + 1} ({num_cells} cells): Preview={cell_preview}..."
                )

                if num_cells == 0:
                    logging.debug(f"Skipping empty row {i + 1}.")
                    continue

                # --- Try parsing as Additional Time Row First ---
                # _parse_additional_meeting_row now returns a LIST of meeting times
                additional_meeting_list = self._parse_additional_meeting_row(cells)
                if (
                    additional_meeting_list is not None
                ):  # Check for None explicitly (empty list [] is valid for TBA/ARR)
                    logging.debug(
                        f"Row {i + 1} successfully parsed as additional meeting(s): {additional_meeting_list}"
                    )
                    if current_course_key and current_section_crn:
                        if current_course_key in all_courses_map:
                            course = all_courses_map[current_course_key]
                            section_found = False
                            for section in reversed(course["courseSections"]):
                                if section["crn"] == current_section_crn:
                                    # Use extend to add all items from the list
                                    section["meetingTimes"].extend(
                                        additional_meeting_list
                                    )
                                    logging.debug(
                                        f"Extended meeting times for CRN {current_section_crn} with {len(additional_meeting_list)} new time(s)."
                                    )
                                    section_found = True
                                    break
                            if not section_found:
                                logging.warning(
                                    f"Found additional meeting time(s) row {i + 1}, but couldn't find matching section CRN {current_section_crn} in course {current_course_key}"
                                )
                        else:
                            logging.warning(
                                f"Found additional meeting time(s) row {i + 1}, but course key {current_course_key} not found in map."
                            )
                    else:
                        logging.warning(
                            f"Found additional meeting time(s) row {i + 1} but no current section context (CRN)."
                        )
                    continue  # Processed as additional time, move to next row

                # --- If not additional time, try to parse as a new section/course row ---
                parsed_section_data = self._parse_section_row(cells, subject)
                if parsed_section_data:
                    logging.debug(
                        f"Row {i + 1} successfully parsed as section CRN {parsed_section_data['crn']}."
                    )
                    course_number_int = 0
                    try:
                        num_match = re.match(
                            r"^(\d+)", parsed_section_data["courseNumber"]
                        )
                        if num_match:
                            course_number_int = int(num_match.group(1))
                        else:
                            logging.warning(
                                f"Could not extract numeric part from course number {parsed_section_data['courseNumber']} for CRN {parsed_section_data['crn']}"
                            )
                    except ValueError:
                        logging.warning(
                            f"Could not convert extracted course number part to int for {parsed_section_data['courseNumber']}"
                        )

                    course_key = f"{parsed_section_data['subject']}-{course_number_int}"
                    current_course_key = course_key
                    current_section_crn = parsed_section_data["crn"]

                    if course_key not in all_courses_map:
                        all_courses_map[course_key] = {
                            "name": parsed_section_data["courseName"],
                            "subject": parsed_section_data["subject"],
                            "courseNumber": course_number_int,
                            "courseSections": [],
                        }
                        logging.debug(f"Created new course entry: {course_key}")

                    section_to_add = {
                        "crn": current_section_crn,
                        "meetingTimes": parsed_section_data["meetingTimes"],
                        "examCode": parsed_section_data["examCode"],
                        "instructor": parsed_section_data["instructor"],
                        "capacity": parsed_section_data["capacity"],
                        "sectionType": parsed_section_data["sectionType"],
                        "credits": parsed_section_data["credits"],
                        "mode": parsed_section_data["mode"],
                    }
                    all_courses_map[course_key]["courseSections"].append(section_to_add)
                    logging.debug(
                        f"Added section CRN {current_section_crn} to course {course_key}"
                    )

                # --- Row didn't match expected structure for section or additional time ---
                elif (
                    additional_meeting_list is None
                ):  # Only log/reset if not already handled as additional time
                    logging.debug(
                        f"Skipping row {i + 1}: Did not match section or additional time structure. Cell count: {num_cells}. Content preview: {cell_preview}..."
                    )
                    # Reset context only if we are sure it's not related to the previous section
                    # Keep context if it might be a comment or separator row related to the last section
                    # current_section_crn = None # Keep context for now
                    # current_course_key = None

        self.courses_data = list(all_courses_map.values())
        logging.info(
            f"Finished course parsing. Found {len(self.courses_data)} courses total."
        )
        return self.courses_data

    # --- Internal Helper Methods ---

    def _find_term_script_text(self, term: str) -> Optional[str]:
        """Finds the text content of the script tag containing the specified term's data."""
        # (Implementation remains the same)
        if not self.soup:
            return None
        script_tags = self.soup.find_all("script")
        if not script_tags:
            logging.warning("No <script> tags found in the provided soup object.")
            return None
        term_marker = f'case "{term}"'
        for script_tag in script_tags:
            if script_tag.string:
                script_content = script_tag.string
                if term_marker in script_content:
                    logging.debug(
                        f"Found script tag containing marker for term '{term}'."
                    )
                    return script_content
        logging.error(
            f"Could not find a script tag containing the marker '{term_marker}' for term '{term}'."
        )
        return None

    def _extract_term_script_block(self, script_text: str, term: str) -> Optional[str]:
        """Extracts the block of JavaScript code specific to the term."""
        # (Implementation remains the same)
        pattern = rf'case "{term}"\s*:(.*?)break;'
        match = re.search(pattern, script_text, re.DOTALL | re.IGNORECASE)
        if match:
            extracted_block = match.group(1).strip()
            logging.debug(f"Successfully extracted script block for term '{term}'.")
            return extracted_block
        else:
            logging.error(
                f"Could not extract the script block for term '{term}'. Regex pattern '{pattern}' did not find a match."
            )
            return None

    def _parse_subject_codes_from_block(self, script_block: str) -> List[str]:
        """Parses individual subject codes from the extracted JavaScript block."""
        # (Implementation remains the same)
        subject_codes: List[str] = []
        lines = script_block.splitlines()
        line_pattern = re.compile(r'new Option\(".*?",\s*"(.*?)"', re.IGNORECASE)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "All Subjects" in line and "new Option" in line:
                logging.debug(f"Skipping 'All Subjects' line: {line}")
                continue
            match = line_pattern.search(line)
            if not match:
                if "new Option" in line and not line.startswith("//"):
                    logging.warning(
                        f"Regex did not find subject code pattern in line: {line}"
                    )
                continue
            subject_code = match.group(1)
            if not re.match(r"^[A-Z0-9]+$", subject_code):
                logging.warning(
                    f"Extracted value '{subject_code}' from line '{line}' does not match expected format."
                )
                continue
            subject_codes.append(subject_code)
            logging.debug(f"Extracted subject code: {subject_code}")
        return subject_codes

    def _parse_section_row(
        self, cells: List[Tag], subject: str
    ) -> Optional[Dict[str, Any]]:
        """
        Attempts to parse a table row (list of <td> tags) as a new course section.
        Handles standard 13-column rows and common edge cases with fewer columns.
        Returns a dictionary with section details or None.
        """
        # (Implementation remains the same as v17)
        IDX_CRN = 0
        IDX_SUBJ_COURSE = 1
        IDX_TITLE = 2
        IDX_TYPE = 3
        IDX_MODE = 4
        IDX_CREDITS = 5
        IDX_CAP_TOTAL = 6
        IDX_INSTRUCTOR = 7
        IDX_DAYS = 8
        IDX_START_TIME = 9
        IDX_END_TIME = 10
        IDX_LOCATION = 11
        IDX_EXAM = 12
        MIN_EXPECTED_CELLS = 8
        EXPECTED_FULL_CELL_COUNT = 13

        num_cells = len(cells)
        if num_cells < MIN_EXPECTED_CELLS:
            logging.debug(
                f"Skipping row as section: Too few cells ({num_cells} < {MIN_EXPECTED_CELLS})."
            )
            return None

        crn_link = cells[IDX_CRN].find("a")
        crn_tag = crn_link.find("b") if crn_link else None
        crn_text = crn_tag.get_text(strip=True) if crn_tag else ""
        if not crn_text.isdigit():
            logging.debug(
                f"Skipping row as section: Cell {IDX_CRN} CRN text '{crn_text}' is not numeric or not found in expected tags."
            )
            return None

        logging.debug(f"Attempting to parse row as section CRN {crn_text}...")
        try:
            crn = int(crn_text)

            def get_cell_text(index, default=""):
                return (
                    cells[index].get_text(strip=True) if index < num_cells else default
                )

            subj_course_text = get_cell_text(IDX_SUBJ_COURSE)
            course_match = re.match(r"([A-Z]+)\s*-\s*(\d+[A-Z]*)", subj_course_text)
            course_number_str = course_match.group(2) if course_match else "0"
            parsed_subject = course_match.group(1) if course_match else subject
            if course_number_str == "0":
                logging.warning(
                    f"Could not parse course number from '{subj_course_text}' for CRN {crn}. Skipping section."
                )
                return None

            course_name = get_cell_text(IDX_TITLE)
            type_text = get_cell_text(IDX_TYPE)
            mode_str = get_cell_text(IDX_MODE)
            section_type = self._map_section_type(type_text, mode_str)
            credits_text = get_cell_text(IDX_CREDITS)
            credits_val = 0
            if re.match(r"^\d+(\.\d+)?$", credits_text):
                credits_val = int(float(credits_text))
            elif " TO " in credits_text.upper():
                range_match = re.search(
                    r"(\d+)\s+TO\s+\d+", credits_text, re.IGNORECASE
                )
                if range_match:
                    try:
                        credits_val = int(range_match.group(1))
                        logging.debug(
                            f"Parsed variable credit '{credits_text}' as {credits_val} for CRN {crn}."
                        )
                    except ValueError:
                        logging.warning(
                            f"Could not parse lower bound from credit range '{credits_text}' for CRN {crn}."
                        )
                else:
                    logging.warning(
                        f"Unusual credit range format '{credits_text}' for CRN {crn}."
                    )
            elif credits_text:
                logging.debug(
                    f"Unusual credit format '{credits_text}' for CRN {crn}. Defaulting to 0."
                )

            capacity_text = get_cell_text(IDX_CAP_TOTAL)
            capacity = int(capacity_text) if capacity_text.isdigit() else 0

            instructor_text = get_cell_text(IDX_INSTRUCTOR)
            instructor = (
                instructor_text
                if instructor_text and instructor_text != "N/A"
                else "Staff"
            )

            meeting_times = []
            if num_cells >= IDX_LOCATION + 1:
                meeting_times = self._parse_meeting_time_cells(
                    cells, IDX_DAYS, IDX_START_TIME, IDX_END_TIME, IDX_LOCATION
                )
            else:
                logging.debug(
                    f"Meeting time columns missing or insufficient for CRN {crn} (found {num_cells} cells)."
                )

            exam_code = ""
            if num_cells >= IDX_EXAM + 1:
                exam_link = cells[IDX_EXAM].find("a")
                exam_code = exam_link.get_text(strip=True) if exam_link else ""
            else:
                logging.debug(
                    f"Exam column missing for CRN {crn} (found {num_cells} cells)."
                )

            if not meeting_times:
                days_val = get_cell_text(IDX_DAYS, "").upper()
                start_time_val = get_cell_text(IDX_START_TIME, "")
                loc_val = get_cell_text(IDX_LOCATION, "").upper()
                if (
                    "(ARR)" in days_val
                    or "TBA" in days_val
                    or "-----" in start_time_val
                    or "ONLINE" in loc_val
                    or "TBA" in loc_val
                ):
                    logging.debug(
                        f"CRN {crn} has no specific meeting times (ARR/TBA/Online)."
                    )
                elif section_type not in [
                    "ONLINE_ASYNCHRONOUS",
                    "INDEPENDENT_STUDY",
                    "RESEARCH",
                    "OTHER",
                ]:
                    logging.warning(
                        f"Section CRN {crn} parsed but has no meeting times and isn't typically async/arranged type ({section_type})."
                    )

            return {
                "crn": crn,
                "subject": parsed_subject,
                "courseNumber": course_number_str,
                "courseName": course_name,
                "sectionType": section_type,
                "capacity": capacity,
                "instructor": instructor,
                "examCode": exam_code,
                "meetingTimes": meeting_times,
                "credits": credits_val,
                "mode": mode_str,
            }
        except (ValueError, AttributeError, TypeError) as e:
            logging.warning(
                f"Error processing potential section row CRN {crn_text}: {e} - Row Preview: {[c.get_text(strip=True)[:20] for c in cells]}"
            )
            return None
        except IndexError:
            logging.warning(
                f"Index error processing section row CRN {crn_text}. Row Preview: {[c.get_text(strip=True)[:20] for c in cells]}"
            )
            return None

    def _parse_additional_meeting_row(
        self, cells: List[Tag]
    ) -> Optional[List[Dict[str, str]]]:
        IDX_MARKER_CELL = 4
        MIN_CELLS_FOR_MARKER_CHECK = IDX_MARKER_CELL + 1
        num_cells = len(cells)

        # --- Basic marker checks ---
        if num_cells < MIN_CELLS_FOR_MARKER_CHECK:
            return None
        marker_cell = cells[IDX_MARKER_CELL]
        has_colspan = marker_cell.has_attr("colspan")
        marker_cell_text = marker_cell.get_text(strip=True)
        is_additional_time_marker = "* Additional Times *" in marker_cell_text
        if not (has_colspan and is_additional_time_marker):
            return None
        is_prev_empty = all(not c.get_text(strip=True) for c in cells[:IDX_MARKER_CELL])
        if not is_prev_empty:
            return None
        # --- End basic checks ---

        logging.debug(
            f"Attempting to parse row as additional time... (Cell count: {num_cells})"
        )
        try:
            idx_days, idx_start, idx_end, idx_loc = -1, -1, -1, -1

            # --- REVISED AND CONFIRMED INDEX LOGIC ---
            if num_cells >= 11:  # Standard rows (11+)
                idx_days, idx_start, idx_end, idx_loc = 8, 9, 10, 11
                logging.debug(
                    f"Using standard indices for {num_cells} cells: D=8, S=9, E=10, L=11"
                )
            elif num_cells == 10:  # Often Marker(4)+D(5)+S(6)+E(7)+L(8)+EmptyExam?(9)
                idx_days, idx_start, idx_end, idx_loc = 5, 6, 7, 8
                logging.debug("Using 10-cell indices: D=5, S=6, E=7, L=8")
            elif num_cells == 9:  # The problematic case: Marker(4)+D(5)+S(6)+E(7)+L(8)
                idx_days, idx_start, idx_end, idx_loc = (
                    5,
                    6,
                    7,
                    8,
                )  # DEFINITELY USE 7 AND 8
                logging.debug("Using 9-cell indices: D=5, S=6, E=7, L=8")
            # Added explicit handling for 8 based on review - might need adjustment
            elif num_cells == 8:  # Maybe Marker(4)+D(5)+S(6)+L(7)? End time missing?
                idx_days, idx_start, idx_end, idx_loc = (
                    5,
                    6,
                    6,
                    7,
                )  # Guess: Use start time for end, Loc=7
                logging.debug("Using tentative 8-cell indices: D=5, S=6, E=6, L=7")
            else:
                logging.warning(
                    f"Addl time row marker found, but cell count ({num_cells}) unhandled."
                )
                return None
            # --- END INDEX LOGIC ---

            # Check validity (copied from previous version, seems reasonable)
            if idx_days >= num_cells:
                logging.warning(f"Index D={idx_days} OOB for {num_cells} cells")
                return None
            if idx_start >= num_cells:
                logging.warning(f"Index S={idx_start} OOB for {num_cells} cells")
                return None
            if idx_end >= num_cells and idx_end != idx_start:
                logging.warning(f"Index E={idx_end} OOB for {num_cells} cells")
                return None
            if idx_loc >= num_cells:
                logging.warning(f"Index L={idx_loc} OOB for {num_cells} cells")
                return None

            # Call the parsing function
            meeting_times = self._parse_meeting_time_cells(
                cells, idx_days, idx_start, idx_end, idx_loc
            )

            logging.debug(
                f"Parsed {len(meeting_times)} meeting times from additional time row."
            )
            return meeting_times

        except Exception as e:
            logging.warning(
                f"Error processing additional meeting row: {type(e).__name__}: {e} - Row Preview: {[c.get_text(strip=True)[:20] for c in cells]}"
            )
            return None

    def _parse_meeting_time_cells(
        self,
        cells: List[Tag],
        idx_days: int,
        idx_start: int,
        idx_end: int,
        idx_loc: int,
    ) -> List[Dict[str, str]]:
        """
        Parses day, time, and location from the relevant cells of a row using provided indices.
        Includes checks for sufficient cell count.
        Returns a list of meeting time dictionaries. Handles multi-day entries (e.g., MWF).
        """
        # (Implementation remains the same)
        meeting_times = []
        num_cells = len(cells)
        if not all(idx < num_cells for idx in [idx_days, idx_start, idx_end, idx_loc]):
            logging.warning(
                f"Insufficient cells ({num_cells}) to parse meeting time using indices D={idx_days}, S={idx_start}, E={idx_end}, L={idx_loc}."
            )
            return []
        try:
            days_text = cells[idx_days].get_text(strip=True)
            time_text = cells[idx_start].get_text(strip=True)
            end_time_text_check = cells[idx_end].get_text(strip=True)
            location_text = cells[idx_loc].get_text(strip=True)

            if (
                "(ARR)" in days_text
                or "TBA" in days_text.upper()
                or "TBA" in time_text.upper()
                or not time_text
                or "-----" in time_text
                or "TBA" in end_time_text_check.upper()
                or not end_time_text_check
                or "-----" in end_time_text_check
            ):
                logging.debug(
                    f"Skipping meeting time due to TBA/ARR: Days='{days_text}', Start='{time_text}', End='{end_time_text_check}'"
                )
                return []
            start_time_str_raw = time_text
            end_time_str_raw = end_time_text_check
            start_time_str = self._convert_to_24hr(start_time_str_raw)
            end_time_str = self._convert_to_24hr(end_time_str_raw)

            if start_time_str is None or end_time_str is None:
                logging.warning(
                    f"Could not parse or convert time: Start='{start_time_str_raw}', End='{end_time_str_raw}'"
                )
                return []
            day_map = {
                "M": "MONDAY",
                "T": "TUESDAY",
                "W": "WEDNESDAY",
                "R": "THURSDAY",
                "F": "FRIDAY",
                "S": "SATURDAY",
                "U": "SUNDAY",
            }
            parsed_days = []
            processed_days_text = "".join(days_text.split())
            for char in processed_days_text:
                day_enum = day_map.get(char.upper())
                if day_enum:
                    parsed_days.append(day_enum)
                elif char.strip():
                    logging.warning(
                        f"Unrecognized day character '{char}' in days string '{days_text}'"
                    )

            for day in parsed_days:
                meeting_times.append(
                    {
                        "day": day,
                        "startTime": start_time_str,
                        "endTime": end_time_str,
                        "location": location_text if location_text else "TBA",
                    }
                )
        except Exception as e:
            if isinstance(
                e, AttributeError
            ) and "'module' object has no attribute 'strptime'" in str(e):
                logging.error(
                    f"DATETIME IMPORT ERROR: {e}. Make sure 'import datetime' is used, not 'from datetime import datetime'."
                )
            else:
                logging.warning(f"Error parsing meeting time cells content: {e}")
        return meeting_times

    def _convert_to_24hr(self, time_str: str) -> Optional[str]:
        """Converts a time string (e.g., "9:30AM", "5:00PM") to HH:MM format."""
        # (Implementation remains the same)
        if (
            not time_str
            or "TBA" in time_str.upper()
            or "ARR" in time_str.upper()
            or "-----" in time_str
        ):
            return None
        try:
            time_str_cleaned = time_str.upper().replace(" ", "")
            # Use datetime.datetime.strptime
            time_obj = datetime.strptime(time_str_cleaned, "%I:%M%p")
            return time_obj.strftime("%H:%M")
        except ValueError:
            try:
                # Use datetime.datetime.strptime
                time_obj = datetime.strptime(time_str_cleaned, "%H:%M")
                return time_obj.strftime("%H:%M")
            except ValueError:
                logging.warning(f"Could not parse time string: '{time_str}'")
                return None

    def _map_section_type(self, type_text: str, mode_str: str) -> str:
        """Maps the type text/char and mode string to the SectionType enum string."""
        # (Implementation remains the same as v17)
        type_text = type_text.upper().strip()
        mode_str = mode_str.upper().strip()

        if "ONLINE COURSE" in type_text:
            if "SYNCHRONOUS" in mode_str:
                return "ONLINE_SYNCHRONOUS"
            elif "ASYNCHRONOUS" in mode_str:
                return "ONLINE_ASYNCHRONOUS"
            else:
                logging.debug(
                    f"Online course marker found but mode unclear: '{mode_str}'. Defaulting to ASYNCHRONOUS."
                )
                return "ONLINE_ASYNCHRONOUS"
        # Handle standard types (potentially with trailing numbers like L01, B02)
        base_type = re.match(r"^([A-Z]+)", type_text)
        type_code = base_type.group(1) if base_type else type_text

        if type_code == "L":
            return "LECTURE"
        if type_code == "B":
            return "LAB"
        if type_code == "R":
            return "RESEARCH"
        if type_code == "I":
            return "INDEPENDENT_STUDY"
        # Add other common codes if needed
        # if type_code == 'C': return "RECITATION" # Example

        if "HYBRID" in mode_str:
            logging.debug(
                f"Hybrid modality found: Type='{type_text}', Mode='{mode_str}'. Mapping to OTHER."
            )
            return "OTHER"
        logging.debug(
            f"Unmapped section type/mode: Type='{type_text}', Mode='{mode_str}'. Defaulting to OTHER."
        )
        return "OTHER"
