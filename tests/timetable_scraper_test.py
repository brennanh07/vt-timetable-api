import pytest
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup, Tag
import json
from collections import defaultdict
from typing import cast

from scraper.timetable_scraper import (
    TimetableScraper,
    parse_time,
    safe_extract_text,
    is_additional_times_row,
    parse_new_section_data,
    determine_meeting_times,
    create_section_object,
    parse_additional_times_row,
    process_subject_rows,
    DAY_MAPPING,
)


@pytest.fixture
def mock_fetcher():
    with patch("scraper.timetable_fetcher.TimetableFetcher") as mock:
        fetcher_instance = Mock()
        mock.return_value = fetcher_instance
        yield fetcher_instance


@pytest.fixture
def scraper(mock_fetcher):
    return TimetableScraper("202509")


@pytest.fixture
def sample_html():
    return """
            <tr>
              <td valign="middle" bgcolor="white" class="dedefault">
                <p class="centeraligntext"></p><a href="javascript:flexibleWindow(&quot;HZSKVTSC.P_ProcComments?CRN=83488&amp;TERM=09&amp;YEAR=2025&amp;SUBJ=CS&amp;CRSE=2114&amp;history=N&quot;,&quot;new_win&quot;,&quot;800&quot;,&quot;800&quot;,&quot;300&quot;,&quot;300&quot;,&quot;no&quot;,&quot;no&quot;,&quot;yes&quot;,&quot;no&quot;)"><b style="font-size:12px;">83488</b></a>&#160;
              </td>
              <td class="deleft" style="background-color:WHITE">
                <font size="1">CS-2114</font>
              </td>
              <td class="deleft" style="background-color:WHITE">
                Softw Des &amp; Data Structures
              </td>
              <td style="text-align:center;font-size:10px;background:WHITE;" class="dedefault">
                <p class="centeraligntext"></p>L
              </td>
              <td style="text-align:center;font-size:10px;background:WHITE;" class="dedefault">
                <p class="centeraligntext">
                  Face-to-Face Instruction
                </p>
              </td>
              <td style="text-align:center;font-size:10px;background:WHITE;" class="dedefault">
                <p class="centeraligntext"></p>3
              </td>
              <td class="dedefault" style="text-align:center;font-size:10px;background:WHITE;">
                35
              </td>
              <td class="deleft" style="background-color:WHITE">
                N/A
              </td>
              <td class="dedefault" style="font-size:10px;background-color:WHITE">
                T R
              </td>
              <td class="deright" style="font-size:10px;background-color:WHITE">
                9:30AM
              </td>
              <td class="deright" style="font-size:10px;background-color:WHITE">
                10:20AM
              </td>
              <td class="deleft" style="font-size:10px;background-color:WHITE">
                GOODW 190
              </td>
              <td style="font-size:9px;color:red;background-color:WHITE;" class="dedefault">
                <a href="javascript:openWindow(&quot;HZSKVTSC.P_ProcExamTime?CRN=83488&amp;SUBJECT=CS&amp;CRSE_NUM=2114&amp;TERM=09&amp;YEAR=2025&amp;EXAMNUM=XXX&quot;)">CTE</a>
              </td>
            </tr>
           """


# =====================
# Helper Function Tests
# =====================


class TestParseTime:
    """Tests time parsing funcitonality"""

    @pytest.mark.parametrize(
        "input_time,expected",
        [
            ("09:00AM", "09:00"),
            ("12:00PM", "12:00"),
            ("01:30PM", "13:30"),
            ("12:00AM", "00:00"),
            ("11:59PM", "23:59"),
            ("----- (ARR) -----", "ARR"),
            (None, "ARR"),
            ("", "ARR"),
        ],
    )
    def test_parse_time_formats(self, input_time, expected):
        assert parse_time(input_time) == expected


class TestSafeExtractText:
    """Tests SAFE text extract from HTTML table elements helper function"""

    def test_safe_extract_null_element(self):
        assert safe_extract_text(element=None) is None  # type: ignore

    def test_safe_extract_not_tag_type(self):
        assert safe_extract_text(element="not a tag") is None  # type: ignore

    def test_safe_extract_no_selector(self):
        # Arrange
        html = '<td class="deleft" style="background-color:WHITE">Softw Des &amp; Data Structures</td>'
        soup = BeautifulSoup(html, "html.parser")
        td_tag = soup.find("td")

        # Act
        extracted_text = safe_extract_text(td_tag)  # type: ignore

        # Assert
        assert extracted_text == "Softw Des & Data Structures"

    def test_safe_extract_with_selector(self):
        # Arrange
        html = '<td class="deleft" style="background-color:WHITE"><font size="1">CS-2114</font></td>'
        soup = BeautifulSoup(html, "html.parser")
        td_tag = soup.find("td")

        # Act
        extracted_text = safe_extract_text(td_tag, selector="font")  # type: ignore

        # Assert
        assert extracted_text == "CS-2114"

    def test_safe_extract_selector_not_found(self):
        # Arrange
        html = '<td class="deleft" style="background-color:WHITE"><font size="1">CS-2114</font></td>'
        soup = BeautifulSoup(html, "html.parser")
        td_tag = soup.find("td")

        # Act
        extracted_text = safe_extract_text(td_tag, selector="b")  # type: ignore

        # Assert
        assert extracted_text is None


class TestIsAdditionalTimesRow:
    """Tests helper function that checks if input row is an additional times row"""

    def test_is_additional_times_row_empty_list(self):
        """Test with empty list"""
        assert is_additional_times_row([], 13) is False

    def test_is_additional_times_row_wrong_length(self):
        """Test with wrong expected length"""
        cols = [Mock() for _ in range(10)]
        assert is_additional_times_row(cols, 13) is False  # type: ignore

    def test_is_additional_times_row_none_col_four(self):
        """Tests when column 4 is None"""
        cols = [Mock() for _ in range(13)]
        cols[4] = None  # type: ignore
        assert is_additional_times_row(cols, 13) is False  # type: ignore

    def test_is_additional_times_row_no_b_element(self):
        """Tests when column 4 has no <b> element"""
        cols = [Mock() for _ in range(13)]
        cols[4].find.return_value = None
        assert is_additional_times_row(cols, 13) is False  # type: ignore

    def test_is_additional_times_row_wrong_text(self):
        """Tests when <b> element has wrong text"""
        cols = [Mock() for _ in range(13)]
        b_mock = Mock()
        b_mock.get_text.return_value = "Some Other Text"
        cols[4].find.return_value = b_mock
        assert is_additional_times_row(cols, 13) is False  # type: ignore

    def test_is_additional_times_row_correct_marker(self):
        """Test when row has correct additional times marker"""
        cols = [Mock() for _ in range(13)]
        b_mock = Mock()
        b_mock.get_text.return_value = "* Additional Times *"
        cols[4].find.return_value = b_mock
        assert is_additional_times_row(cols, 13) is True  # type: ignore


class TestParseNewSectionData:
    """Tests for parse_new_section_data function"""

    def test_parse_arranged_section_data(self):
        """Test parsing arranged section data with 12 columns"""
        # Arrange
        html = """
        <tr>
            <td><b>12345</b></td>
            <td><font>CS-1064</font></td>
            <td>Intro to Programming</td>
            <td>L</td>
            <td><p>Online</p></td>
            <td>3</td>
            <td>100</td>
            <td>John Doe</td>
            <td>(ARR)</td>
            <td>-----</td>
            <td>Online</td>
            <td><a>CTE</a></td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        cols = soup.find("tr").find_all("td")  # type: ignore

        # Act
        result = parse_new_section_data(cols, "arranged")  # type: ignore

        # Assert
        expected = {
            "crn": "12345",
            "course": "CS-1064",
            "title": "Intro to Programming",
            "schedule_type": "L",
            "modality": "Online",
            "credit_hours": "3",
            "capacity": "100",
            "instructor": "John Doe",
            "days": "(ARR)",
            "time": "-----",
            "location": "Online",
            "exam_code": "CTE",
        }
        assert result == expected

    def test_parse_regular_section_data(self):
        """Test parsing regular section data with 13 columns"""
        # Arrange
        html = """
        <tr>
            <td><b>83488</b></td>
            <td><font>CS-2114</font></td>
            <td>Softw Des & Data Structures</td>
            <td>L</td>
            <td><p>Face-to-Face Instruction</p></td>
            <td>3</td>
            <td>35</td>
            <td>N/A</td>
            <td>T R</td>
            <td>9:30AM</td>
            <td>10:20AM</td>
            <td>GOODW 190</td>
            <td><a>CTE</a></td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        cols = soup.find("tr").find_all("td")  # type: ignore

        # Act
        result = parse_new_section_data(cols, "regular")  # type: ignore

        # Assert
        expected = {
            "crn": "83488",
            "course": "CS-2114",
            "title": "Softw Des & Data Structures",
            "schedule_type": "L",
            "modality": "Face-to-Face Instruction",
            "credit_hours": "3",
            "capacity": "35",
            "instructor": None,
            "days": "T R",
            "begin_time": "9:30AM",
            "end_time": "10:20AM",
            "location": "GOODW 190",
            "exam_code": "CTE",
        }
        assert result == expected

    def test_parse_section_data_invalid_row_type(self):
        """Test parsing with invalid row type returns empty dict"""
        # Arrange
        html = "<tr><td>test</td></tr>"
        soup = BeautifulSoup(html, "html.parser")
        cols = soup.find("tr").find_all("td")  # type:ignore

        # Act
        result = parse_new_section_data(cols, "invalid_type")  # type: ignore

        # Assert
        assert result == {}

    def test_parse_section_data_with_none_values(self):
        """Test parsing when some elements are missing or None"""
        # Arrange
        html = """
        <tr>
            <td></td>
            <td><font></font></td>
            <td></td>
            <td></td>
            <td><p></p></td>
            <td></td>
            <td></td>
            <td></td>
            <td></td>
            <td></td>
            <td></td>
            <td></td>
            <td><a></a></td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        cols = soup.find("tr").find_all("td")  # type: ignore

        # Act
        result = parse_new_section_data(cols, "regular")  # type: ignore

        # Assert
        assert result is not None
        assert all(value is None or value == "" for value in result.values())

    def test_parse_arranged_section_with_missing_selectors(self):
        """Test arranged section parsing when specific selectors are missing"""
        # Arrange
        html = """
        <tr>
            <td>12345</td>
            <td>CS-1064</td>
            <td>Intro to Programming</td>
            <td>L</td>
            <td>Online</td>
            <td>3</td>
            <td>100</td>
            <td>John Doe</td>
            <td>(ARR)</td>
            <td>-----</td>
            <td>Online</td>
            <td>CTE</td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        cols = soup.find("tr").find_all("td")  # type: ignore

        # Act
        result = parse_new_section_data(cols, "arranged")  # type: ignore

        # Assert
        expected = {
            "crn": None,  # No <b> tag
            "course": None,  # No <font> tag
            "title": "Intro to Programming",
            "schedule_type": "L",
            "modality": None,  # No <p> tag
            "credit_hours": "3",
            "capacity": "100",
            "instructor": "John Doe",
            "days": "(ARR)",
            "time": "-----",
            "location": "Online",
            "exam_code": None,  # No <a> tag
        }
        assert result == expected

    def test_parse_regular_section_with_missing_selectors(self):
        """Test regular section parsing when specific selectors are missing"""
        # Arrange
        html = """
        <tr>
            <td>83488</td>
            <td>CS-2114</td>
            <td>Softw Des & Data Structures</td>
            <td>L</td>
            <td>Face-to-Face Instruction</td>
            <td>3</td>
            <td>35</td>
            <td>N/A</td>
            <td>T R</td>
            <td>9:30AM</td>
            <td>10:20AM</td>
            <td>GOODW 190</td>
            <td>CTE</td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        cols = soup.find("tr").find_all("td")  # type: ignore

        # Act
        result = parse_new_section_data(cols, "regular")  # type: ignore

        # Assert
        expected = {
            "crn": None,  # No <b> tag
            "course": None,  # No <font> tag
            "title": "Softw Des & Data Structures",
            "schedule_type": "L",
            "modality": None,  # No <p> tag
            "credit_hours": "3",
            "capacity": "35",
            "instructor": None,
            "days": "T R",
            "begin_time": "9:30AM",
            "end_time": "10:20AM",
            "location": "GOODW 190",
            "exam_code": None,  # No <a> tag
        }
        assert result == expected

    @patch("scraper.timetable_scraper.logging")
    def test_parse_section_data_logs_warning_for_invalid_type(self, mock_logging):
        """Test that invalid row type triggers warning log"""
        # Arrange
        html = "<tr><td>test</td></tr>"
        soup = BeautifulSoup(html, "html.parser")
        cols = soup.find("tr").find_all("td")  # type: ignore

        # Act
        parse_new_section_data(cols, "invalid_type")  # type: ignore

        # Assert
        mock_logging.warning.assert_called_once_with(
            "Row type not recognized: invalid_type"
        )

    def test_parse_section_data_with_special_characters(self):
        """Test parsing section data with HTML entities and special characters"""
        # Arrange
        html = """
        <tr>
            <td><b>12345</b></td>
            <td><font>MATH-1225</font></td>
            <td>Calculus I &amp; II</td>
            <td>L</td>
            <td><p>Hybrid</p></td>
            <td>4</td>
            <td>25</td>
            <td>Dr. Smith &amp; Dr. Jones</td>
            <td>M W F</td>
            <td>8:00AM</td>
            <td>8:50AM</td>
            <td>MATH 101</td>
            <td><a>FTE</a></td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        cols = soup.find("tr").find_all("td")  # type: ignore

        # Act
        result = parse_new_section_data(cols, "regular")  # type: ignore

        # Assert
        assert result["title"] == "Calculus I & II"  # type: ignore
        assert result["instructor"] == "Dr. Smith & Dr. Jones"  # type: ignore


class TestDetermineMeetingTimes:
    def test_determine_meeting_times_null_days(self):
        """Tests determine meeting times with null days input"""
        # Arrange
        days = None
        begin_time = "10:00AM"
        end_time = "10:50AM"

        # Act
        meeting_times: list = determine_meeting_times(days, begin_time, end_time)

        # Assert
        assert meeting_times == ["ARR"]

    def test_determine_meeting_times_arranged_days(self):
        """Tests determine meeting times with ARR days input"""
        # Arrange
        days = "(ARR)"
        begin_time = "10:00AM"
        end_time = "10:50AM"

        # Act
        meeting_times: list = determine_meeting_times(days, begin_time, end_time)

        # Assert
        assert meeting_times == ["ARR"]

    def test_determine_meeting_times_no_end_time(self):
        """Tests determine meeting times with a section with no end time
        (represents online/research/etc type of section)"""
        # Arrange
        days = "M"
        begin_time = "10:00AM"
        end_time = None

        # Act
        meeting_times: list = determine_meeting_times(days, begin_time, end_time)

        # Assert
        assert meeting_times == [
            {
                "day": 1,
                "begin_time": "10:00",
                "end_time": "10:00",
            },
        ]

    def test_determine_meeting_times_one_day(self):
        """Tests determine meeting times with a in-person section with one day"""
        # Arrange
        days = "M"
        begin_time = "10:00AM"
        end_time = "10:50AM"

        # Act
        meeting_times: list = determine_meeting_times(days, begin_time, end_time)

        # Assert
        assert meeting_times == [
            {
                "day": 1,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
        ]

    def test_determine_meeting_times_two_days(self):
        """Tests determine meeting times with a in-person section with one day"""
        # Arrange
        days = "M W"
        begin_time = "10:00AM"
        end_time = "10:50AM"

        # Act
        meeting_times: list = determine_meeting_times(days, begin_time, end_time)

        # Assert
        assert meeting_times == [
            {
                "day": 1,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
            {
                "day": 3,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
        ]

    def test_determine_meeting_times_three_days(self):
        """Tests determine meeting times with a in-person section with one day"""
        # Arrange
        days = "M W F"
        begin_time = "10:00AM"
        end_time = "10:50AM"

        # Act
        meeting_times: list = determine_meeting_times(days, begin_time, end_time)

        # Assert
        assert meeting_times == [
            {
                "day": 1,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
            {
                "day": 3,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
            {
                "day": 5,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
        ]


class TestCreateSectionObject:
    def test_create_section_object_inperson(self):
        # Arrange
        parsed_data = {
            "crn": "87084",
            "course": "CS-2114",
            "title": "Software Design",
            "schedule_type": "L",
            "modality": "Face-to-Face Instruction",
            "credit_hours": "3",
            "capacity": "35",
            "instructor": None,
            "days": "T R",
            "begin_time": "9:30AM",
            "end_time": "10:20AM",
            "location": "GOODW 190",
            "exam_code": "CTE",
        }
        meeting_times = [
            {
                "day": 1,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
            {
                "day": 3,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
            {
                "day": 5,
                "begin_time": "10:00",
                "end_time": "10:50",
            },
        ]

        # Act
        section_obj = create_section_object(parsed_data, meeting_times)

        # Assert
        assert section_obj == {
            "crn": "87084",
            "course": "CS-2114",
            "title": "Software Design",
            "schedule_type": "L",
            "modality": "Face-to-Face Instruction",
            "credit_hours": "3",
            "capacity": "35",
            "instructor": None,
            "meeting_times": [
                {
                    "day": 1,
                    "begin_time": "10:00",
                    "end_time": "10:50",
                },
                {
                    "day": 3,
                    "begin_time": "10:00",
                    "end_time": "10:50",
                },
                {
                    "day": 5,
                    "begin_time": "10:00",
                    "end_time": "10:50",
                },
            ],
            "location": "GOODW 190",
            "exam_code": "CTE",
        }

    def test_create_section_object_arranged(self):
        # Arrange
        parsed_data = {
            "crn": "87084",
            "course": "CS-2114",
            "title": "Software Design",
            "schedule_type": "L",
            "modality": "Face-to-Face Instruction",
            "credit_hours": "3",
            "capacity": "35",
            "instructor": None,
            "days": "T R",
            "begin_time": "(ARR)",
            "location": "GOODW 190",
            "exam_code": "CTE",
        }
        meeting_times = ["ARR"]

        # Act
        section_obj = create_section_object(parsed_data, meeting_times)  # type: ignore

        # Assert
        assert section_obj == {
            "crn": "87084",
            "course": "CS-2114",
            "title": "Software Design",
            "schedule_type": "L",
            "modality": "Face-to-Face Instruction",
            "credit_hours": "3",
            "capacity": "35",
            "instructor": None,
            "meeting_times": ["ARR"],
            "location": "GOODW 190",
            "exam_code": "CTE",
        }


class TestParseAdditionalTimesRow:
    @pytest.fixture(autouse=True)
    def setup(self):
        html = """
        <tr>
        <td class="dedefault" style="border-right-width:0px;border-top-width:1px;">&nbsp;</td>
        <td class="dedefault" style="border-right-width:0px;border-top-width:1px;">&nbsp;</td>
        <td class="dedefault" style="border-right-width:0px;border-top-width:1px;">&nbsp;</td>
        <td class="dedefault" style="border-right-width:0px;border-top-width:1px;">&nbsp;</td>
        <td colspan="4" class="dedefault" style="background-color:WHITE;"><b class="blue_msg">* Additional Times *</b></td>
        <td class="dedefault" style="font-size:10px;background-color:WHITE">F      </td>
        <td class="deright" style="font-size:10px;background-color:WHITE">12:20PM</td>
        <td class="deright" style="font-size:10px;background-color:WHITE">2:50PM</td>
        <td class="deleft" style="font-size:10px;background-color:WHITE">CLMS 170</td>
        <td class="dedefault" style="border-top-width:0px;background-color:WHITE">&nbsp;</td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.cols = cast(list[Tag], soup.find("tr").find_all("td"))  # type: ignore

        self.course_sections_map = {
            "CS-2114": [
                {
                    "crn": "83488",
                    "course": "CS-2114",
                    "title": "Softw Des & Data Structures",
                    "schedule_type": "L",
                    "modality": "Face-to-Face Instruction",
                    "credit_hours": "3",
                    "capacity": "35",
                    "instructor": None,
                    "meeting_times": [
                        {"day": 2, "begin_time": "09:30", "end_time": "10:20"},
                        {"day": 4, "begin_time": "09:30", "end_time": "10:20"},
                        # {"day": 1, "begin_time": "14:30", "end_time": "17:00"},
                    ],
                    "location": "GOODW 190",
                    "exam_code": "CTE",
                },
            ]
        }

        self.curr_course = "CS-2114"

    @patch("scraper.timetable_scraper.logging")
    def test_parse_additional_times_row_null_curr_course(self, mock_logging):
        """Tests the parse additional times row func with no curr course"""
        # Arrange
        curr_course = None
        is_online = False

        # Act
        parse_additional_times_row(
            self.cols,
            self.course_sections_map,
            curr_course,  # type: ignore
            is_online,
        )

        # Assert
        mock_logging.warning.assert_called_once_with(
            "No current course or not in sections map"
        )

    @patch("scraper.timetable_scraper.logging")
    def test_parse_additional_times_row_curr_course_not_found(self, mock_logging):
        """Tests the parse additional times row func with no curr course"""
        # Arrange
        curr_course = "MATH-1225"
        is_online = False

        # Act
        parse_additional_times_row(
            self.cols,
            self.course_sections_map,
            curr_course,  # type: ignore
            is_online,
        )

        # Assert
        mock_logging.warning.assert_called_once_with(
            "No current course or not in sections map"
        )

    @patch("scraper.timetable_scraper.logging")
    def test_parse_additional_times_row_null_course_sections_map(self, mock_logging):
        """Tests the parse additional times row func with no curr course"""
        # Arrange
        self.course_sections_map["CS-2114"] = None  # type: ignore
        is_online = False

        # Act
        parse_additional_times_row(
            self.cols,
            self.course_sections_map,  # type: ignore
            self.curr_course,
            is_online,
        )

        # Assert
        mock_logging.warning.assert_called_once_with(
            "No sections found to add additional time for course: CS-2114"
        )
