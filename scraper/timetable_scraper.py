import json
import logging
import re
from collections import defaultdict
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag

from .timetable_fetcher import TimetableFetcher

logging.basicConfig(
    filename="parse.log",
    filemode="w",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

SectionData = dict[str, Any]
CourseMap = dict[str, list[SectionData]]
SubjectMap = dict[str, CourseMap]

DAY_MAPPING = {
    "M": 1,
    "T": 2,
    "W": 3,
    "R": 4,
    "F": 5,
    "S": 6,
    "U": 7,
}


# ======================================================
# Helper Functions
# ======================================================


def parse_time(time_str: Optional[str]) -> str:
    """Convert the time string from 12-hour format to 24-hour format.

    Handles university timetable time formats and converts them to standardized
    24-hour format for consistent data processing.

    Args:
        time_str(Optional[str]): Time string in format "HH:MMAM/PM" or special
                                 arranged time indicators like "----- (ARR) -----"

    Returns:
        str: Time in 24-hour format "HH:MM" or "ARR" for arranged times
    """
    if not time_str or time_str == "----- (ARR) -----":
        return "ARR"

    time_part = time_str[:-2].strip()
    am_pm = time_str[-2:].strip()

    hour, minute = map(int, time_part.split(":"))

    if am_pm == "PM" and hour != 12:
        hour += 12
    elif am_pm == "AM" and hour == 12:
        hour = 0

    # format specifier:
    # 0 - pad with zeros
    # 2 - min width of 2 chars
    # d - decimal integer format
    return f"{hour:02d}:{minute:02d}"


def safe_extract_text(element: Tag, selector: Optional[str] = None) -> Optional[str]:
    """Safely extract text content from BeautifulSoup HTML elements.

    Provides text extraction with CSS selector support and handles
    edge cases like None elements, empty text, and "N/A" values.

    Args:
        element (Tag): BeautifulSoup Tag element to extract text from
        selector (Optional[str]): Optional CSS selector to find child elements first

    Returns:
        Optional[str]: Extracted text content, or None if extraction fails or
                       text is empty/invalid
    """
    if not element or not isinstance(element, Tag):
        return None

    if selector:
        found = element.find(selector)
        if not found or not isinstance(found, Tag):
            return None
        element = found

    text = element.get_text(strip=True)

    return text if text and text != "" and text != "N/A" else None


def is_additional_times_row(cols: list[Tag], expected_length: int) -> bool:
    """Check if a table row contains additional meeting times for a course section.

    Identifies rows that specify additional meeting times for previously parsed
    course sections by looking for the "* Additional Times *" marker.

    Args:
        cols (list[Tag]): List of table cell elements from the row
        expected_length (int): Expected number of columns in the row

    Returns:
        bool: True if row contains additional times marker, False otherwise
    """
    if len(cols) != expected_length:
        return False

    col_four = cols[4]
    if not col_four:
        return False

    b_element = col_four.find("b")
    return (
        b_element is not None
        and b_element.get_text(strip=True) == "* Additional Times *"
    )


# ====================================================================
# Data Parsing (depend on helper functions)
# ====================================================================


def parse_new_section_data(
    cols: list[Tag], row_type: str
) -> Optional[dict[str, Optional[str]]]:
    """Parse course section data from timetable table row columns.

    Extracts structured course information from HTML table cells based on
    the row type (arranged vs regular schedule). Handles different column
    layouts for different types of courses.

    Args:
        cols (list[Tag]): List of table cell elements containing course data
        row_type (str): Type of row - "arranged" for flexible schedule courses,
                       "regular" for standard scheduled courses

    Returns:
        Optional[dict[str, Optional[str]]]: Dictionary containing parsed course
                                           data fields, or None if parsing fails
    """
    if row_type == "arranged":
        return {
            "crn": safe_extract_text(cols[0], "b"),
            "course": safe_extract_text(cols[1], "font"),
            "title": safe_extract_text(cols[2]),
            "schedule_type": safe_extract_text(cols[3]),
            "modality": safe_extract_text(cols[4], "p"),
            "credit_hours": safe_extract_text(cols[5]),
            "capacity": safe_extract_text(cols[6]),
            "instructor": safe_extract_text(cols[7]),
            "days": safe_extract_text(cols[8]),
            "time": safe_extract_text(cols[9]),
            "location": safe_extract_text(cols[10]),
            "exam_code": safe_extract_text(cols[11], "a"),
        }

    elif row_type == "regular":
        return {
            "crn": safe_extract_text(cols[0], "b"),
            "course": safe_extract_text(cols[1], "font"),
            "title": safe_extract_text(cols[2]),
            "schedule_type": safe_extract_text(cols[3]),
            "modality": safe_extract_text(cols[4], "p"),
            "credit_hours": safe_extract_text(cols[5]),
            "capacity": safe_extract_text(cols[6]),
            "instructor": safe_extract_text(cols[7]),
            "days": safe_extract_text(cols[8]),
            "begin_time": safe_extract_text(cols[9]),
            "end_time": safe_extract_text(cols[10]),
            "location": safe_extract_text(cols[11]),
            "exam_code": safe_extract_text(cols[12], "a"),
        }

    logging.warning(f"Row type not recognized: {row_type}")
    return {}


def determine_meeting_times(
    days: Optional[str], begin_time: Optional[str], end_time: Optional[str] = None
) -> list:
    """Convert course meeting days and times into structured meeting time objects.

    Processes course schedule information and creates meeting time objects
    with day numbers and formatted times. Handles arranged schedules and
    converts day abbreviations to numeric values.

    Args:
        days (Optional[str]): Space-separated day abbreviations (e.g., "M W F")
        begin_time (Optional[str]): Start time in 12-hour format
        end_time (Optional[str]): End time in 12-hour format, defaults to begin_time

    Returns:
        list: List of meeting time dictionaries with day, begin_time, end_time,
              or ["ARR"] for arranged schedules
    """
    if not days or days == "(ARR)":
        return ["ARR"]

    # for async/arranged classes, begin and times are the same
    if end_time is None:
        end_time = begin_time

    formatted_begin_time = parse_time(begin_time)
    formatted_end_time = parse_time(end_time)

    meeting_times = []
    for day in days.split():
        meeting_time = {
            "day": DAY_MAPPING[day],
            "begin_time": formatted_begin_time,
            "end_time": formatted_end_time,
        }
        meeting_times.append(meeting_time)

    return meeting_times


def create_section_object(
    parsed_data: dict[str, Optional[str]], meeting_times: Optional[list[dict[str, Any]]]
) -> SectionData:
    """Create a standardized course section object from parsed data.

    Combines parsed course information and meeting times into a structured
    section object with consistent field names and data types.

    Args:
        parsed_data (dict[str, Optional[str]]): Dictionary of parsed course fields
        meeting_times (Optional[list[dict[str, Any]]]): List of meeting time objects

    Returns:
        SectionData: Structured course section object ready for JSON serialization
    """
    return {
        "crn": parsed_data.get("crn"),
        "course": parsed_data.get("course"),
        "title": parsed_data.get("title"),
        "schedule_type": parsed_data.get("schedule_type"),
        "modality": parsed_data.get("modality"),
        "credit_hours": parsed_data.get("credit_hours"),
        "capacity": parsed_data.get("capacity"),
        "instructor": parsed_data.get("instructor"),
        "meeting_times": meeting_times
        if meeting_times and len(meeting_times) > 0
        else None,
        "location": parsed_data.get("location"),
        "exam_code": parsed_data.get("exam_code"),
    }


# ======================================================================
# Row Processing (depend on data parsing functions)
# ======================================================================


def parse_additional_times_row(
    cols: list[Tag],
    course_sections_map: dict[str, list[dict[str, Any]]],
    curr_course: str,
    is_online: bool = False,
) -> None:
    """Parse and add additional meeting times to the most recent course section.

    Processes table rows marked with "* Additional Times *" and appends
    the meeting times to the previously parsed course section. Handles
    different column layouts for online vs in-person additional times.

    Args:
        cols (list[Tag]): List of table cell elements from the additional times row
        course_sections_map (dict[str, list[dict[str, Any]]]): Map of courses to sections
        curr_course (str): Current course code being processed
        is_online (bool): Whether this is an online course format

    Returns:
        None: Modifies the course_sections_map in place
    """
    if not curr_course or curr_course not in course_sections_map:
        logging.warning("No current course or not in sections map")
        return

    if not course_sections_map[curr_course]:
        logging.warning(
            f"No sections found to add additional time for course: {curr_course}"
        )
        return

    prev_section = course_sections_map[curr_course][-1]
    if "meeting_times" not in prev_section or prev_section["meeting_times"] is None:
        prev_section["meeting_times"] = []

    prev_section_meetings = prev_section["meeting_times"]

    if is_online and len(cols) == 9:
        days = safe_extract_text(cols[5])
        time_str = safe_extract_text(cols[6])
        meeting_times = determine_meeting_times(days, time_str)
    elif not is_online and len(cols) == 10:
        days = safe_extract_text(cols[5])
        begin_time = safe_extract_text(cols[6])
        end_time = safe_extract_text(cols[7])
        meeting_times = determine_meeting_times(days, begin_time, end_time)
        if meeting_times and meeting_times != ["ARR"] and len(meeting_times) > 0:
            meeting_times = [meeting_times[-1]]

    else:
        logging.warning(
            f"Invalid additional times row: columns={len(cols)}, is_online={is_online}"
        )
        return

    if meeting_times:
        prev_section_meetings.extend(meeting_times)


def process_subject_rows(rows: list[Tag]) -> CourseMap:
    """Process all table rows for a subject and extract course section data.

    Iterates through HTML table rows and identifies different row types
    (regular sections, arranged sections, additional times). Builds a
    comprehensive map of courses to their sections with all meeting times.

    Args:
        rows (list[Tag]): List of HTML table row elements to process

    Returns:
        CourseMap: Dictionary mapping course codes to lists of section objects
    """
    course_sections_map = defaultdict(list)
    curr_course = None

    for i, row in enumerate(rows):
        if not isinstance(row, Tag) or row is None:
            logging.warning(f"Row {i}: Invalid row type, skipping")
            continue

        cols = row.find_all("td")
        if not cols:
            logging.warning(f"Row {i}: No columns found, skipping")
            continue

        col_count = len(cols)
        logging.info(f"Row {i}: Processing row with {col_count} columns")

        if col_count == 9 and is_additional_times_row(cols, 9):
            logging.info("Scraping Additional Time row (Online)")

            parse_additional_times_row(
                cols, course_sections_map, curr_course, is_online=True
            )
            # we don't want to create a new section here
            continue

        elif col_count == 10 and is_additional_times_row(cols, 10):
            logging.info("Scraping Additional Time row (In Person)")
            parse_additional_times_row(
                cols, course_sections_map, curr_course, is_online=False
            )
            # we don't want to create a new section here
            continue

        parsed_data = None
        meeting_times = None

        # This is things like online async classes, research, independent study, internship, etc
        # All should be 'ARR' for times
        if col_count == 12:
            parsed_data = parse_new_section_data(cols, "arranged")
            if parsed_data:
                meeting_times = determine_meeting_times(
                    parsed_data.get("days"),
                    parsed_data.get("time"),
                )

        # Regular in person classes or sync online classes
        elif col_count == 13:
            parsed_data = parse_new_section_data(cols, "regular")
            if parsed_data:
                meeting_times = determine_meeting_times(
                    parsed_data.get("days"),
                    parsed_data.get("begin_time"),
                    parsed_data.get("end_time"),
                )

        # unrecognized row type
        else:
            logging.debug(
                f"Row {i}: Unrecognized row type with {col_count} columns, skipping"
            )
            continue

        if not parsed_data:
            logging.warning(f"Row {i}: Failed to parse section data, skipping")
            continue

        course = parsed_data.get("course")
        if not course:
            logging.warning(f"Row {i}: No course found in parsed data, skipping")
            continue

        curr_course = course
        section = create_section_object(parsed_data, meeting_times)
        if section:
            course_sections_map[curr_course].append(section)
        else:
            logging.warning(f"Row {i}: Failed to create section object")

    return course_sections_map


# ===========================================================================
# High Level Scraping (depend on row processing functions)
# ===========================================================================


class TimetableScraper:
    """Scrapes course and section data from the university timetable.

    This class provides methods to fetch, parse, and query timetable information
    for a specific academic term. It can retrieve subjects, scrape data for
    one or more subjects, and search for specific courses or sections.

    Attributes:
        term (str): The academic term to scrape (e.g., "202409").
        fetcher (TimetableFetcher): An instance of TimetableFetcher to handle
                                    HTTP requests.
    """

    def __init__(self, term: str) -> None:
        """Initializes the TimetableScraper for a specific term.

        Args:
            term (str): The academic term to scrape (e.g., "202409").
        """
        self.term: str = term
        self.fetcher: TimetableFetcher = TimetableFetcher(term)

    def get_subjects(self) -> list[str]:
        """Retrieves a list of all available subject codes for the term.

        Fetches the main timetable page and parses it to extract all unique
        subject abbreviations (e.g., 'CS', 'MATH', 'ENGL').

        Returns:
            list[str]: A list of unique subject codes. Returns an empty list
                       if fetching or parsing fails.
        """
        try:
            html = self.fetcher.fetch_html("%")
            if html is None:
                logging.warning("No HTML returned when retrieving all subjects")
                return []
        except Exception as e:
            logging.error(f"Failed to fetch HTML when retrieving all subjects: {e}")
            return []

        script_match = re.search(
            rf'case\s+["\']?{re.escape(self.term)}["\']?\s*:(.*?)break;',
            html,
            re.DOTALL,
        )
        if not script_match:
            logging.warning(
                "Could not find matching script when retrieving all subjects"
            )
            return []

        subjects = re.findall(
            r'new Option\(".*?",\s*"([A-Z0-9]+)"', script_match.group(1)
        )
        unique_subjects = list(dict.fromkeys(subjects))
        logging.info(f"Found {len(unique_subjects)} subjects for term {self.term}")

        return unique_subjects

    def scrape_subject(self, subject: str) -> CourseMap:
        """Scrapes all course data for a single subject.

        Fetches the timetable page for the given subject, parses the HTML table,
        and extracts details for all course sections offered under that subject.

        Args:
            subject (str): The subject code to scrape (e.g., 'CS').

        Returns:
            CourseMap: A dictionary mapping course codes to a list of their
                       section data. Returns an empty dictionary if the scrape fails.
        """
        logging.info(f"Starting scrape for subject: {subject}")

        try:
            html = self.fetcher.fetch_html(subject)
            if html is None:
                logging.warning(f"No HTML returned for subject: {subject}")
                return {}
        except Exception as e:
            logging.error(f"Failed to fetch HTML for subject {subject}: {e}")
            return {}

        try:
            soup = BeautifulSoup(html, "html.parser")
            section_table = soup.find("table", class_="dataentrytable")
        except Exception as e:
            logging.error(f"Failed to parse HTML for subject {subject}: {e}")
            return {}

        if not isinstance(section_table, Tag) or section_table is None:
            logging.debug(f"No section table found for subject: {subject}")
            return {}

        rows = section_table.find_all("tr")[1:]  # skip headers
        if not rows or len(rows) <= 1:
            logging.warning(f"No data rows found for subject: {subject}")
            return {}

        course_sections_map = process_subject_rows(rows)
        logging.info(
            f"Processed {len(course_sections_map)} courses for subject: {subject}"
        )
        return course_sections_map

    def scrape_multiple_subjects(self, subjects: list[str]) -> SubjectMap:
        """Scrapes course data for a list of subjects.

        Iterates through a list of subject codes and scrapes the data for each one,
        aggregating the results into a single map.

        Args:
            subjects (list[str]): A list of subject codes to scrape.

        Returns:
            SubjectMap: A dictionary mapping each subject code to its corresponding
                        CourseMap.
        """
        all_subjects_map: SubjectMap = {}

        for subject in subjects:
            course_sections_map = self.scrape_subject(subject)
            if course_sections_map:  # Only add if we got data
                all_subjects_map[subject] = course_sections_map

        return all_subjects_map

    def scrape_all_subjects(self) -> SubjectMap:
        """Scrapes course data for all available subjects in the term.

        First, it retrieves the list of all subjects, then scrapes the data
        for each subject.

        Returns:
            SubjectMap: A comprehensive map of all subjects and their courses
                        for the term.
        """
        subjects = self.get_subjects()
        if not subjects:
            logging.error(f"No subjects found for term: {self.term}")
            return {}
        logging.info(f"Found {len(subjects)} subjects to process")
        return self.scrape_multiple_subjects(subjects)

    def find_course(self, course_code: str) -> dict[str, CourseMap]:
        """Finds a specific course by its code across all subjects.

        This method is useful for searching for a course when the subject is
        unknown (e.g., cross-listed courses).

        Args:
            course_code (str): The course code to search for (e.g., "CS 1114").

        Returns:
            dict[str, CourseMap]: A dictionary where keys are subject codes
                                  that contain the course, and values are CourseMaps
                                  filtered to only that course.
        """
        subjects = self.get_subjects()
        results = {}

        for subject in subjects:
            course_map = self.scrape_subject(subject)
            for course, sections in course_map.items():
                if course_code.upper() in course.upper():
                    if subject not in results:
                        results[subject] = {}
                    results[subject][course] = sections

        return results

    def find_section_by_crn(self, crn: str) -> Optional[dict[str, Any]]:
        """Finds a specific course section by its CRN across all subjects.

        Scans all subjects and courses to find the single section that matches
        the given Course Registration Number (CRN).

        Args:
            crn (str): The 5-digit CRN of the section to find.

        Returns:
            Optional[dict[str, Any]]: A dictionary containing the subject, course,
                                      and section data if found, otherwise None.
        """
        subjects = self.get_subjects()

        for subject in subjects:
            course_map = self.scrape_subject(subject)
            for course, sections in course_map.items():
                for section in sections:
                    if section.get("crn") == crn:
                        return {
                            "subject": subject,
                            "course": course,
                            "section": section,
                        }
        return None

    def get_courses_for_subject(self, subject: str) -> list[str]:
        """Get the list of courses available for the specified subject.

        Args:
            subject (str): The subject code to retrieve courses for (e.g., 'CS')

        Returns:
            list[str]: A list of course codes for the specified subject
        """
        subject_all_caps = subject.upper()
        courses_with_sections = self.scrape_subject(subject_all_caps)
        courses_list = list(courses_with_sections.keys())
        return courses_list

    # NOTE: Should probably change this and other functions later to directly put the
    # specified course in the payload to the timetable in scraper.timetable_fetcher.
    # This implementation scrapes and returns a lot of unnecessary data (all courses and
    # sections for the specified subject)
    def get_all_sections_for_course(self, course: str) -> list[SectionData]:
        """Retrieves all sections for a specific course.

        Fetches all sections for a given course code by first scraping the
        entire subject and then filtering for the specific course.

        Args:
            course (str): The course identifier in "SUBJECT-####" format
                          (e.g., "CS-2114").

        Returns:
            list[SectionData]: A list of dictionaries, where each dictionary
                               represents a course section. Returns an empty
                               list if the course is not found.

        Raises:
            ValueError: If the course code does not match the expected
                        "SUBJECT-####" format.
        """
        # course = "CS-2114"
        course_pattern = re.compile(r"^[A-Za-z]+-\d{4}$")
        if not course_pattern.match(course):
            raise ValueError(
                f"Invalid course format: '{course}'. Expected format like 'CS-2114'."
            )

        subject, course_num = course.split("-")
        subject_all_caps = subject.upper()
        courses = self.scrape_subject(subject_all_caps)
        course_formatted = subject_all_caps + "-" + course_num
        course_sections = courses[course_formatted]
        return course_sections

    def close(self):
        """Closes the underlying HTTP session.

        It's important to call this method when done to release resources.
        """
        self.fetcher.close_session()
