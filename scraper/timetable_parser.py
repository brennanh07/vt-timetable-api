from bs4 import BeautifulSoup, Tag
import json
from timetable_fetcher import TimetableFetcher
import re
from collections import defaultdict
from typing import Any, Optional
import logging

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
        Optional[str]: Extracted text content, or None if extractino fails or
                       text is empty/invalid
    """
    if not element or not isinstance(element, Tag):
        return None

    if selector:
        found = element.find(selector)
        if not found:
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
    if not cols or len(cols) != expected_length:
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
        if not isinstance(cols, list):
            logging.warning(f"Row {i}: Not a list, skipping")
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


def fetch_subjects(term: str, fetcher: TimetableFetcher) -> list[str]:
    """Fetch all available subject codes for a given academic term.

    Retrieves the timetable page and extracts subject codes from JavaScript
    that populates the subject dropdown menu. Uses regex to find all subject
    codes associated with the specified term.

    Args:
        term (str): Academic term code (e.g., "202509" for Fall 2025)
        fetcher (TimetableFetcher): TimetableFetcher instance for making HTTP requests

    Returns:
        list[str]: List of unique subject codes available for the term,
                   empty list if fetch or parsing fails
    """
    try:
        html = fetcher.fetch_html("%")
        if html is None:
            logging.warning("No HTML returned when retrieving all subjects")
            return []
    except Exception as e:
        logging.error(f"Failed to fetch HTML when retrieving all subjects: {e}")
        return []

    try:
        script_match = re.search(
            rf'case\s+["\']?{re.escape(term)}["\']?\s*:(.*?)break;', html, re.DOTALL
        )
        if not script_match:
            logging.warning(
                "Could not find matching script when retrieving all subjects"
            )
            return []

        # Extract all subject codes from new Option() calls
        subjects = re.findall(
            r'new Option\(".*?",\s*"([A-Z0-9]+)"', script_match.group(1)
        )
        unique_subjects = list(dict.fromkeys(subjects))  # remove duplicates

        logging.info(f"Found {len(unique_subjects)} subjects for term {term}")
        return unique_subjects
    except Exception as e:
        logging.error(f"Failed to parse subjects from HTML for term {term}: {e}")
        return []


def scrape_subjects(subjects: list[str], fetcher: TimetableFetcher) -> str:
    """Scrape comprehensive course data for specified subjects.

    Iterates through subject codes and extracts detailed course information
    including sections, meeting times, instructors, location, etc.
    Returns structured data ready for JSON serialization.

    Args:
        subjects (list[str]): List of subjects
        fetcher (TimetableFetcher): TimetableFetcher object

    Returns:
        str: JSON string of all sections for all courses in subjects list
    """
    if not subjects or not fetcher:
        return "{}"

    all_subjects_map: SubjectMap = {}

    for subject in subjects:
        logging.info(f"Starting scrape for subject: {subject}")

        try:
            html = fetcher.fetch_html(subject)
            if html is None:
                logging.warning(f"No HTML returned for subject: {subject}")
                continue
        except Exception as e:
            logging.error(f"Failed ot fetch HTML for subject {subject}: {e}")
            continue

        try:
            soup = BeautifulSoup(html, "html.parser")
            section_table = soup.find("table", class_="dataentrytable")
        except Exception as e:
            logging.error(f"Failed to parse HTML for subject {subject}: {e}")
            continue

        if not isinstance(section_table, Tag):
            logging.debug(f"Section table is not of type Tag for subject: {subject}")
            continue
        if section_table is None:
            logging.debug(f"Section table is null for subject: {subject}")
            continue

        rows = section_table.find_all("tr")[1:]  # skip headers
        if not rows or len(rows) <= 1:
            logging.warning(f"No data rows were found for subject: {subject}")
            continue

        course_sections_map = process_subject_rows(rows)
        all_subjects_map[subject] = course_sections_map
        logging.info(
            f"Processed {len(course_sections_map)} courses for subject: {subject}"
        )

    try:
        return json.dumps(all_subjects_map, indent=2)
    except Exception as e:
        logging.error(f"Failed to serialize results to JSON: {e}")
        return "{}"


# ===========================================================================
# Main Orchestration (depends on everything)
# ===========================================================================


def main(term: str, output_file: str) -> bool:
    """Main function to orchestrate the course scraping process.

    Args:
        term: The academic term to scrape for (e.g. "202509" for Fall 2025)
        output_file: The output JSON file name

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logging.info(f"Starting course scraper for term: {term}")

        fetcher = TimetableFetcher(term)

        logging.info("Fetching subjects...")
        subjects = fetch_subjects(term, fetcher)

        if not subjects:
            logging.error(f"No subjects found for term: {term}")
            return False

        logging.info(f"Found {len(subjects)} subjects to process")

        logging.info("Starting scraping process...")
        json_output = scrape_subjects(subjects, fetcher)

        if json_output == "{}":
            logging.error("Scraping returned empty results")
            return False

        with open(output_file, "w") as f:
            f.write(json_output)

        logging.info(f"Successfully wrote results to {output_file}")
        return True

    except Exception as e:
        logging.error(f"Main function failed: {e}")
        return False
    finally:
        if fetcher:
            fetcher.close_session()


# ===================================================================
# Main Entry Point
# ===================================================================


if __name__ == "__main__":
    success = main("202509", "sections.json")
    if success:
        print("Course scraping completed successfully")
    else:
        print("Course scraping failed. Check parse.log for details")
