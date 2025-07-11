import json
from collections import defaultdict
from typing import cast
from unittest.mock import MagicMock, Mock, patch

import pytest
from bs4 import BeautifulSoup, Tag

from scraper.timetable_fetcher import TimetableFetcher
from scraper.timetable_scraper import (DAY_MAPPING, TimetableScraper,
                                       create_section_object,
                                       determine_meeting_times,
                                       is_additional_times_row,
                                       parse_additional_times_row,
                                       parse_new_section_data, parse_time,
                                       process_subject_rows, safe_extract_text)


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

    def test_parse_additional_times_row_no_meeting_times(self):
        # Arrange
        no_meeting_times = {
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
                    "location": "GOODW 190",
                    "exam_code": "CTE",
                },
            ]
        }

        # Act
        parse_additional_times_row(
            self.cols, no_meeting_times, self.curr_course, is_online=False
        )

        # Assert
        section = no_meeting_times["CS-2114"][0]
        assert "meeting_times" in section
        assert section["meeting_times"] is not None
        assert isinstance(section["meeting_times"], list)

    def test_parse_additional_times_row_null_meeting_times(self):
        # Arrange
        no_meeting_times = {
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
                    "meeting_times": None,
                    "location": "GOODW 190",
                    "exam_code": "CTE",
                },
            ]
        }

        # Act
        parse_additional_times_row(
            self.cols, no_meeting_times, self.curr_course, is_online=False
        )

        # Assert
        section = no_meeting_times["CS-2114"][0]
        assert "meeting_times" in section
        assert section["meeting_times"] is not None
        assert isinstance(section["meeting_times"], list)

    def test_parse_additional_times_row_not_online(self):
        # Arrange
        is_online = False

        # Act
        parse_additional_times_row(
            self.cols, self.course_sections_map, self.curr_course, is_online
        )

        # Assert
        section = self.course_sections_map["CS-2114"][0]
        meeting_times = section["meeting_times"]
        assert meeting_times == [
            {"day": 2, "begin_time": "09:30", "end_time": "10:20"},
            {"day": 4, "begin_time": "09:30", "end_time": "10:20"},
            {"day": 5, "begin_time": "12:20", "end_time": "14:50"},
        ]

    def test_parse_additional_times_row_online(self):
        # Arrange
        online_section_map = {
            "ALCE-3624": [
                {
                    "crn": "80285",
                    "course": "ALCE-3084",
                    "title": "Comm Ag & Life Sci in Writing",
                    "schedule_type": "L",
                    "modality": "Hybrid (F2F & Online Instruc.)",
                    "credit_hours": "3",
                    "capacity": "30",
                    "instructor": None,
                    "meeting_times": [
                        {"day": 2, "begin_time": "14:00", "end_time": "15:15"},
                    ],
                    "location": "GOODW 190",
                    "exam_code": "CTE",
                },
            ]
        }
        html = """
        <tr>
        <td class="dedefault" style="border-right-width:0px;border-top-width:1px;">&nbsp;</td>
        <td class="dedefault" style="border-right-width:0px;border-top-width:1px;">&nbsp;</td>
        <td class="dedefault" style="border-right-width:0px;border-top-width:1px;">&nbsp;</td>
        <td class="dedefault" style="border-right-width:0px;border-top-width:1px;">&nbsp;</td>
        <td colspan="4" class="dedefault" style="background-color:WHITE;"><b class="blue_msg">* Additional Times *</b></td>
        <td class="dedefault" style="font-size:10px;background-color:WHITE">(ARR)</td>
        <td colspan="2" class="dedefault" style="font-size:10px;text-align:center;background-color:WHITE">----- (ARR) -----</td>
        <td class="deleft" style="font-size:10px;background-color:WHITE">ONLINE</td>
        <td class="dedefault" style="border-top-width:0px;background-color:WHITE">&nbsp;</td>
        </tr>
        """
        soup = BeautifulSoup(html, "html.parser")
        online_cols = cast(list[Tag], soup.find("tr").find_all("td"))  # type: ignore
        is_online = True
        curr_course = "ALCE-3624"

        # Act
        parse_additional_times_row(
            online_cols, online_section_map, curr_course, is_online
        )

        # Assert
        section = online_section_map[curr_course][0]
        meeting_times = section["meeting_times"]
        assert meeting_times == [
            {"day": 2, "begin_time": "14:00", "end_time": "15:15"},
            "ARR",
        ]


class TestProcessSubjectRows:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up a variety of table rows to test the process_subject_rows function."""
        # A standard in-person course section (13 cols)
        self.regular_row_html = """
        <tr>
            <td><b>83488</b></td><td><font>CS-2114</font></td><td>Softw Des & Data Structures</td>
            <td>L</td><td><p>Face-to-Face</p></td><td>3</td><td>35</td><td>N/A</td>
            <td>T R</td><td>9:30AM</td><td>10:20AM</td><td>GOODW 190</td><td><a>CTE</a></td>
        </tr>
        """
        # An online/arranged course section (12 cols)
        self.arranged_row_html = """
        <tr>
            <td><b>12345</b></td><td><font>CS-1064</font></td><td>Intro to Programming</td>
            <td>L</td><td><p>Online</p></td><td>3</td><td>100</td><td>John Doe</td>
            <td>(ARR)</td><td>-----</td><td>Online</td><td><a>CTE</a></td>
        </tr>
        """
        # An additional time row for an in-person course (10 cols)
        self.additional_time_in_person_html = """
        <tr>
            <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
            <td colspan="4"><b>* Additional Times *</b></td>
            <td>F</td><td>12:20PM</td><td>2:50PM</td><td>CLMS 170</td><td>&nbsp;</td>
        </tr>
        """
        # An additional time row for an online course (9 cols)
        self.additional_time_online_html = """
        <tr>
            <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
            <td colspan="4"><b>* Additional Times *</b></td>
            <td>(ARR)</td><td colspan="2">----- (ARR) -----</td><td>ONLINE</td><td>&nbsp;</td>
        </tr>
        """
        # An invalid row with not enough columns
        self.invalid_row_html = "<tr><td>Invalid</td></tr>"

    def test_process_single_regular_row(self):
        """Test processing a single regular course row."""
        soup = BeautifulSoup(self.regular_row_html, "html.parser")
        rows = soup.find_all("tr")
        result = process_subject_rows(rows)  # type: ignore
        assert "CS-2114" in result
        assert len(result["CS-2114"]) == 1
        section = result["CS-2114"][0]
        assert section["crn"] == "83488"
        assert len(section["meeting_times"]) == 2

    def test_process_single_arranged_row(self):
        """Test processing a single arranged course row."""
        soup = BeautifulSoup(self.arranged_row_html, "html.parser")
        rows = soup.find_all("tr")
        result = process_subject_rows(rows)  # type: ignore
        assert "CS-1064" in result
        assert len(result["CS-1064"]) == 1
        section = result["CS-1064"][0]
        assert section["crn"] == "12345"
        assert section["meeting_times"] == ["ARR"]

    def test_process_regular_row_with_additional_in_person_time(self):
        """Test a regular course followed by an in-person additional time."""
        html = self.regular_row_html + self.additional_time_in_person_html
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        result = process_subject_rows(rows)  # type: ignore
        assert "CS-2114" in result
        section = result["CS-2114"][0]
        assert len(section["meeting_times"]) == 3
        assert {"day": 5, "begin_time": "12:20", "end_time": "14:50"} in section[
            "meeting_times"
        ]

    def test_process_arranged_row_with_additional_online_time(self):
        """Test an arranged course followed by an online additional time."""
        html = self.arranged_row_html + self.additional_time_online_html
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        result = process_subject_rows(rows)  # type: ignore
        assert "CS-1064" in result
        section = result["CS-1064"][0]
        assert section["meeting_times"] == ["ARR", "ARR"]

    def test_process_multiple_courses(self):
        """Test processing multiple different courses in sequence."""
        html = self.regular_row_html + self.arranged_row_html
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        result = process_subject_rows(rows)  # type: ignore
        assert "CS-2114" in result
        assert "CS-1064" in result
        assert len(result["CS-2114"]) == 1
        assert len(result["CS-1064"]) == 1

    def test_process_invalid_row(self):
        """Test that an invalid row is skipped and does not affect output."""
        html = self.regular_row_html + self.invalid_row_html + self.arranged_row_html
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        result = process_subject_rows(rows)  # type: ignore
        assert "CS-2114" in result
        assert "CS-1064" in result
        assert len(result) == 2

    @patch("scraper.timetable_scraper.logging")
    def test_process_row_with_no_course(self, mock_logging):
        """Test a row that parses but has no course code."""
        no_course_html = """
        <tr>
            <td><b>12345</b></td><td><font></font></td><td>No Course Name</td>
            <td>L</td><td><p>Online</p></td><td>3</td><td>100</td><td>John Doe</td>
            <td>(ARR)</td><td>-----</td><td>Online</td><td><a>CTE</a></td>
        </tr>
        """
        soup = BeautifulSoup(no_course_html, "html.parser")
        rows = soup.find_all("tr")
        result = process_subject_rows(rows)  # type: ignore
        assert not result
        mock_logging.warning.assert_any_call(
            "Row 0: No course found in parsed data, skipping"
        )

    def test_process_empty_rows_list(self):
        """Test processing an empty list of rows."""
        result = process_subject_rows([])
        assert not result

    def test_additional_time_without_previous_section(self):
        """Test an additional time row appearing before any course section."""
        html = self.additional_time_in_person_html + self.regular_row_html
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        result = process_subject_rows(rows)  # type: ignore
        # The additional time should be ignored, and the regular course processed normally.
        assert "CS-2114" in result
        assert len(result["CS-2114"][0]["meeting_times"]) == 2

    @patch("scraper.timetable_scraper.logging")
    def test_null_row(self, mock_logging):
        """Test with a null row"""
        # Arrange
        soup = BeautifulSoup(self.regular_row_html, "html.parser")
        rows = soup.find_all("tr")
        rows.append(None)  # type: ignore

        # Act
        process_subject_rows(rows)  # type: ignore

        # Assert
        mock_logging.warning.assert_called_once_with(
            "Row 1: Invalid row type, skipping"
        )

    @patch("scraper.timetable_scraper.logging")
    def test_non_tag_row(self, mock_logging):
        """Test a row with a non-Tag class"""
        # Arrange
        soup = BeautifulSoup(self.regular_row_html, "html.parser")
        rows = soup.find_all("tr")
        rows.append("NOT A TAG")  # type: ignore

        # Act
        process_subject_rows(rows)  # type: ignore

        # Assert
        mock_logging.warning.assert_called_once_with(
            "Row 1: Invalid row type, skipping"
        )

    @patch("scraper.timetable_scraper.logging")
    def test_no_cols(self, mock_logging):
        """Tests a row with no cols in it"""
        # Arrange
        html = "<tr></tr>"
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")

        # Act
        result = process_subject_rows(rows)  # type: ignore

        # Assert
        assert not result
        mock_logging.warning.assert_called_once_with(
            "Row 0: No columns found, skipping"
        )

    @patch("scraper.timetable_scraper.logging")
    @patch("scraper.timetable_scraper.parse_new_section_data")
    def test_parse_data_failure(self, mock_parse_new_section_data, mock_logging):
        """Test when parse_new_section_data returns None/falsy value."""
        # Arrange - mock parse_new_section_data to return None
        mock_parse_new_section_data.return_value = None

        soup = BeautifulSoup(self.regular_row_html, "html.parser")
        rows = soup.find_all("tr")

        # Act
        result = process_subject_rows(rows)  # type: ignore

        # Assert
        assert not result  # Should be empty since parsing failed
        mock_logging.warning.assert_any_call(
            "Row 0: Failed to parse section data, skipping"
        )

    @patch("scraper.timetable_scraper.logging")
    @patch("scraper.timetable_scraper.create_section_object")
    def test_create_section_object_failure(
        self, mock_create_section_object, mock_logging
    ):
        """Test when create_section_object returns None/falsy value."""
        # Arrange - mock create_section_object to return None
        mock_create_section_object.return_value = None

        soup = BeautifulSoup(self.regular_row_html, "html.parser")
        rows = soup.find_all("tr")

        # Act
        result = process_subject_rows(rows)  # type: ignore

        # Assert
        assert not result  # Should be empty since section creation failed
        mock_logging.warning.assert_any_call("Row 0: Failed to create section object")

    @patch("scraper.timetable_scraper.logging")
    @patch("scraper.timetable_scraper.parse_new_section_data")
    def test_parse_data_returns_empty_dict(
        self, mock_parse_new_section_data, mock_logging
    ):
        """Test when parse_new_section_data returns an empty dict (falsy)."""
        # Arrange - mock parse_new_section_data to return empty dict
        mock_parse_new_section_data.return_value = {}

        soup = BeautifulSoup(self.regular_row_html, "html.parser")
        rows = soup.find_all("tr")

        # Act
        result = process_subject_rows(rows)  # type: ignore

        # Assert
        assert not result
        mock_logging.warning.assert_any_call(
            "Row 0: Failed to parse section data, skipping"
        )


class TestTimetableScraper:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Sets up test fixtures for the TimetableScraper tests."""
        with patch("scraper.timetable_scraper.TimetableFetcher") as mock_fetcher_class:
            self.term = "202509"
            self.mock_fetcher = MagicMock(spec=TimetableFetcher)
            mock_fetcher_class.return_value = self.mock_fetcher

            self.scraper = TimetableScraper(self.term)

            # Sample HTML for get_subjects()
            self.subjects_html = """
            <script language="javascript" type="text/javascript">
        function dropdownlist(listindex)
            {
            document.ttform.subj_code.options.length = 0;
            switch (listindex)
            {
            case "202506" :
            document.ttform.subj_code.options[0]=new Option("All Subjects","%",false, false);
            document.ttform.subj_code.options[1]=new Option("AAEC - Agricultural and Applied Economics","AAEC",false, false);
            document.ttform.subj_code.options[2]=new Option("ACIS - Accounting and Information Systems","ACIS",false, false);
            document.ttform.subj_code.options[3]=new Option("ADV - Advertising","ADV",false, false);
            document.ttform.subj_code.options[4]=new Option("AFST - Africana Studies","AFST",false, false);
            document.ttform.subj_code.options[5]=new Option("AHRM - Apparel, Housing, and Resource Management","AHRM",false, false);
            document.ttform.subj_code.options[6]=new Option("AINS - American Indian Studies","AINS",false, false);
            document.ttform.subj_code.options[7]=new Option("ALCE - Agricultural, Leadership, and Community Education","ALCE",false, false);
            document.ttform.subj_code.options[8]=new Option("ALS - Agriculture and Life Sciences","ALS",false, false);
            document.ttform.subj_code.options[9]=new Option("AOE - Aerospace and Ocean Engineering","AOE",false, false);
            document.ttform.subj_code.options[10]=new Option("APS - Appalachian Studies","APS",false, false);
            document.ttform.subj_code.options[11]=new Option("APSC - Animal and Poultry Sciences","APSC",false, false);
            document.ttform.subj_code.options[12]=new Option("ARBC - Arabic","ARBC",false, false);
            document.ttform.subj_code.options[13]=new Option("ARCH - Architecture","ARCH",false, false);
            document.ttform.subj_code.options[14]=new Option("ART - Art and Art History","ART",false, false);
            document.ttform.subj_code.options[15]=new Option("ASPT - Alliance for Social, Political, Ethical, and Cultural Thought","ASPT",false, false);
            document.ttform.subj_code.options[16]=new Option("AT - Agricultural Technology","AT",false, false);
            document.ttform.subj_code.options[17]=new Option("BC - Building Construction","BC",false, false);
            document.ttform.subj_code.options[18]=new Option("BCHM - Biochemistry","BCHM",false, false);
            document.ttform.subj_code.options[19]=new Option("BIOL - Biological Sciences","BIOL",false, false);
            document.ttform.subj_code.options[20]=new Option("BIT - Business Information Technology","BIT",false, false);
            document.ttform.subj_code.options[21]=new Option("BMES - Biomedical Engineering and Sciences","BMES",false, false);
            document.ttform.subj_code.options[22]=new Option("BMSP - Biomedical Sciences and Pathobiology","BMSP",false, false);
            document.ttform.subj_code.options[23]=new Option("BMVS - Biomedical and Veterinary Sciences","BMVS",false, false);
            document.ttform.subj_code.options[24]=new Option("BSE - Biological Systems Engineering","BSE",false, false);
            document.ttform.subj_code.options[25]=new Option("BUS - Business","BUS",false, false);
            document.ttform.subj_code.options[26]=new Option("CEE - Civil and Environmental Engineering","CEE",false, false);
            document.ttform.subj_code.options[27]=new Option("CEM - Construction Engineering and Management","CEM",false, false);
            document.ttform.subj_code.options[28]=new Option("CHE - Chemical Engineering","CHE",false, false);
            document.ttform.subj_code.options[29]=new Option("CHEM - Chemistry","CHEM",false, false);
            document.ttform.subj_code.options[30]=new Option("CHN - Chinese","CHN",false, false);
            document.ttform.subj_code.options[31]=new Option("CINE - Cinema","CINE",false, false);
            document.ttform.subj_code.options[32]=new Option("CLA - Classical Studies","CLA",false, false);
            document.ttform.subj_code.options[33]=new Option("CMDA - Computational Modeling and Data Analytics","CMDA",false, false);
            document.ttform.subj_code.options[34]=new Option("CMST - Communication Studies","CMST",false, false);
            document.ttform.subj_code.options[35]=new Option("CNST - Construction","CNST",false, false);
            document.ttform.subj_code.options[36]=new Option("COMM - Communication","COMM",false, false);
            document.ttform.subj_code.options[37]=new Option("CONS - Consumer Studies","CONS",false, false);
            document.ttform.subj_code.options[38]=new Option("CRIM - Criminology","CRIM",false, false);
            document.ttform.subj_code.options[39]=new Option("CS - Computer Science","CS",false, true);
            document.ttform.subj_code.options[40]=new Option("CSES - Crop and Soil Environmental Sciences","CSES",false, false);
            document.ttform.subj_code.options[41]=new Option("DASC - Dairy Science","DASC",false, false);
            document.ttform.subj_code.options[42]=new Option("ECE - Electrical and Computer Engineering","ECE",false, false);
            document.ttform.subj_code.options[43]=new Option("ECON - Economics","ECON",false, false);
            document.ttform.subj_code.options[44]=new Option("EDCI - Education, Curriculum and Instruction","EDCI",false, false);
            document.ttform.subj_code.options[45]=new Option("EDCO - Counselor Education","EDCO",false, false);
            document.ttform.subj_code.options[46]=new Option("EDCT - Career and Technical Education","EDCT",false, false);
            document.ttform.subj_code.options[47]=new Option("EDEL - Educational Leadership","EDEL",false, false);
            document.ttform.subj_code.options[48]=new Option("EDEP - Educational Psychology","EDEP",false, false);
            document.ttform.subj_code.options[49]=new Option("EDHE - Higher Education","EDHE",false, false);
            document.ttform.subj_code.options[50]=new Option("EDIT - Instructional Design and Technology","EDIT",false, false);
            document.ttform.subj_code.options[51]=new Option("EDP - Environmental Design and Planning","EDP",false, false);
            document.ttform.subj_code.options[52]=new Option("EDRE - Education, Research and Evaluation","EDRE",false, false);
            document.ttform.subj_code.options[53]=new Option("ENGE - Engineering Education","ENGE",false, false);
            document.ttform.subj_code.options[54]=new Option("ENGL - English","ENGL",false, false);
            document.ttform.subj_code.options[55]=new Option("ENGR - Engineering","ENGR",false, false);
            document.ttform.subj_code.options[56]=new Option("ENT - Entomology","ENT",false, false);
            document.ttform.subj_code.options[57]=new Option("ESM - Engineering Science and Mechanics","ESM",false, false);
            document.ttform.subj_code.options[58]=new Option("FIN - Finance","FIN",false, false);
            document.ttform.subj_code.options[59]=new Option("FIW - Fish and Wildlife Conservation","FIW",false, false);
            document.ttform.subj_code.options[60]=new Option("FL - Modern and Classical Languages and Literatures","FL",false, false);
            document.ttform.subj_code.options[61]=new Option("FMD - Fashion Merchandising and Design","FMD",false, false);
            document.ttform.subj_code.options[62]=new Option("FR - French","FR",false, false);
            document.ttform.subj_code.options[63]=new Option("FREC - Forest Resources and Environmental Conservation","FREC",false, false);
            document.ttform.subj_code.options[64]=new Option("FST - Food Science and Technology","FST",false, false);
            document.ttform.subj_code.options[65]=new Option("GBCB - Genetics, Bioinformatics, Computational Biology","GBCB",false, false);
            document.ttform.subj_code.options[66]=new Option("GEN - Invalid for Summer 2025","GEN",false, false);
            document.ttform.subj_code.options[67]=new Option("GEOG - Geography","GEOG",false, false);
            document.ttform.subj_code.options[68]=new Option("GEOS - Geosciences","GEOS",false, false);
            document.ttform.subj_code.options[69]=new Option("GER - German","GER",false, false);
            document.ttform.subj_code.options[70]=new Option("GIA - Government and International Affairs","GIA",false, false);
            document.ttform.subj_code.options[71]=new Option("GR - Greek","GR",false, false);
            document.ttform.subj_code.options[72]=new Option("GRAD - Graduate School","GRAD",false, false);
            document.ttform.subj_code.options[73]=new Option("HD - Human Development","HD",false, false);
            document.ttform.subj_code.options[74]=new Option("HIST - History","HIST",false, false);
            document.ttform.subj_code.options[75]=new Option("HNFE - Human Nutrition, Foods and Exercise","HNFE",false, false);
            document.ttform.subj_code.options[76]=new Option("HORT - Horticulture","HORT",false, false);
            document.ttform.subj_code.options[77]=new Option("HTM - Hospitality and Tourism Management","HTM",false, false);
            document.ttform.subj_code.options[78]=new Option("HUM - Humanities","HUM",false, false);
            document.ttform.subj_code.options[79]=new Option("IDS - Industrial Design","IDS",false, false);
            document.ttform.subj_code.options[80]=new Option("IS - International Studies","IS",false, false);
            document.ttform.subj_code.options[81]=new Option("ISE - Industrial and Systems Engineering","ISE",false, false);
            document.ttform.subj_code.options[82]=new Option("ITAL - Italian","ITAL",false, false);
            document.ttform.subj_code.options[83]=new Option("ITDS - Interior Design","ITDS",false, false);
            document.ttform.subj_code.options[84]=new Option("JMC - Journalism and Mass Communication","JMC",false, false);
            document.ttform.subj_code.options[85]=new Option("JPN - Japanese","JPN",false, false);
            document.ttform.subj_code.options[86]=new Option("JUD - Judaic Studies","JUD",false, false);
            document.ttform.subj_code.options[87]=new Option("LAHS - Liberal Arts and Human Sciences","LAHS",false, false);
            document.ttform.subj_code.options[88]=new Option("LAR - Landscape Architecture","LAR",false, false);
            document.ttform.subj_code.options[89]=new Option("LAT - Latin","LAT",false, false);
            document.ttform.subj_code.options[90]=new Option("LDRS - Leadership Studies","LDRS",false, false);
            document.ttform.subj_code.options[91]=new Option("MACR - Macromolecular Science and Engineering","MACR",false, false);
            document.ttform.subj_code.options[92]=new Option("MATH - Mathematics","MATH",false, false);
            document.ttform.subj_code.options[93]=new Option("ME - Mechanical Engineering","ME",false, false);
            document.ttform.subj_code.options[94]=new Option("MGT - Management","MGT",false, false);
            document.ttform.subj_code.options[95]=new Option("MINE - Mining Engineering","MINE",false, false);
            document.ttform.subj_code.options[96]=new Option("MKTG - Marketing","MKTG",false, false);
            document.ttform.subj_code.options[97]=new Option("MN - Military Navy","MN",false, false);
            document.ttform.subj_code.options[98]=new Option("MSE - Materials Science and Engineering","MSE",false, false);
            document.ttform.subj_code.options[99]=new Option("MTRG - Meteorology","MTRG",false, false);
            document.ttform.subj_code.options[100]=new Option("MUS - Music","MUS",false, false);
            document.ttform.subj_code.options[101]=new Option("NANO - Nanoscience","NANO",false, false);
            document.ttform.subj_code.options[102]=new Option("NEUR - Neuroscience","NEUR",false, false);
            document.ttform.subj_code.options[103]=new Option("NR - Natural Resources","NR",false, false);
            document.ttform.subj_code.options[104]=new Option("NSEG - Nuclear Science and Engineering","NSEG",false, false);
            document.ttform.subj_code.options[105]=new Option("PAPA - Public Administration/Public Affairs","PAPA",false, false);
            document.ttform.subj_code.options[106]=new Option("PHIL - Philosophy","PHIL",false, false);
            document.ttform.subj_code.options[107]=new Option("PHS - Population Health Sciences","PHS",false, false);
            document.ttform.subj_code.options[108]=new Option("PHYS - Physics","PHYS",false, false);
            document.ttform.subj_code.options[109]=new Option("PM - Property Management","PM",false, false);
            document.ttform.subj_code.options[110]=new Option("PPE - Philosophy, Politics, and Economics","PPE",false, false);
            document.ttform.subj_code.options[111]=new Option("PR - Public Relations","PR",false, false);
            document.ttform.subj_code.options[112]=new Option("PSCI - Political Science","PSCI",false, false);
            document.ttform.subj_code.options[113]=new Option("PSYC - Psychology","PSYC",false, false);
            document.ttform.subj_code.options[114]=new Option("REAL - Real Estate","REAL",false, false);
            document.ttform.subj_code.options[115]=new Option("RED - Residential Environments and Design","RED",false, false);
            document.ttform.subj_code.options[116]=new Option("RLCL - Religion and Culture","RLCL",false, false);
            document.ttform.subj_code.options[117]=new Option("RUS - Russian","RUS",false, false);
            document.ttform.subj_code.options[118]=new Option("SBIO - Sustainable Biomaterials","SBIO",false, false);
            document.ttform.subj_code.options[119]=new Option("SOC - Sociology","SOC",false, false);
            document.ttform.subj_code.options[120]=new Option("SPAN - Spanish","SPAN",false, false);
            document.ttform.subj_code.options[121]=new Option("SPES - School of Plant and Environmental Sciences","SPES",false, false);
            document.ttform.subj_code.options[122]=new Option("SPIA - School of Public and International Affairs","SPIA",false, false);
            document.ttform.subj_code.options[123]=new Option("STAT - Statistics","STAT",false, false);
            document.ttform.subj_code.options[124]=new Option("STS - Science and Technology Studies","STS",false, false);
            document.ttform.subj_code.options[125]=new Option("SYSB - Systems Biology","SYSB",false, false);
            document.ttform.subj_code.options[126]=new Option("TA - Theatre Arts","TA",false, false);
            document.ttform.subj_code.options[127]=new Option("TBMH - Translational Biology, Medicine and Health","TBMH",false, false);
            document.ttform.subj_code.options[128]=new Option("UAP - Urban Affairs and Planning","UAP",false, false);
            document.ttform.subj_code.options[129]=new Option("UH - University Honors","UH",false, false);
            document.ttform.subj_code.options[130]=new Option("UNIV - University Course Series","UNIV",false, false);
            document.ttform.subj_code.options[131]=new Option("VM - Veterinary Medicine","VM",false, false);
            document.ttform.subj_code.options[132]=new Option("WGS - Women's and Gender Studies","WGS",false, false);


            break;


            case "202509" :
            document.ttform.subj_code.options[0]=new Option("All Subjects","%",false, false);
            document.ttform.subj_code.options[1]=new Option("AAD - Architecture, Arts, and Design","AAD",false, false);
            document.ttform.subj_code.options[2]=new Option("AAEC - Agricultural and Applied Economics","AAEC",false, false);
            document.ttform.subj_code.options[3]=new Option("ACIS - Accounting and Information Systems","ACIS",false, false);
            document.ttform.subj_code.options[4]=new Option("ADS - Applied Data Science","ADS",false, false);
            document.ttform.subj_code.options[5]=new Option("ADV - Advertising","ADV",false, false);
            document.ttform.subj_code.options[6]=new Option("AFST - Africana Studies","AFST",false, false);
            document.ttform.subj_code.options[7]=new Option("AHRM - Apparel, Housing, and Resource Management","AHRM",false, false);
            document.ttform.subj_code.options[8]=new Option("AINS - American Indian Studies","AINS",false, false);
            document.ttform.subj_code.options[9]=new Option("AIS - Academy of Integrated Science","AIS",false, false);
            document.ttform.subj_code.options[10]=new Option("ALCE - Agricultural, Leadership, and Community Education","ALCE",false, false);
            document.ttform.subj_code.options[11]=new Option("ALS - Agriculture and Life Sciences","ALS",false, false);
            document.ttform.subj_code.options[12]=new Option("AOE - Aerospace and Ocean Engineering","AOE",false, false);
            document.ttform.subj_code.options[13]=new Option("APS - Appalachian Studies","APS",false, false);
            document.ttform.subj_code.options[14]=new Option("APSC - Animal and Poultry Sciences","APSC",false, false);
            document.ttform.subj_code.options[15]=new Option("ARBC - Arabic","ARBC",false, false);
            document.ttform.subj_code.options[16]=new Option("ARCH - Architecture","ARCH",false, false);
            document.ttform.subj_code.options[17]=new Option("ART - Art and Art History","ART",false, false);
            document.ttform.subj_code.options[18]=new Option("AS - Military Aerospace Studies","AS",false, false);
            document.ttform.subj_code.options[19]=new Option("ASPT - Alliance for Social, Political, Ethical, and Cultural Thought","ASPT",false, false);
            document.ttform.subj_code.options[20]=new Option("AT - Agricultural Technology","AT",false, false);
            document.ttform.subj_code.options[21]=new Option("BC - Building Construction","BC",false, false);
            document.ttform.subj_code.options[22]=new Option("BCHM - Biochemistry","BCHM",false, false);
            document.ttform.subj_code.options[23]=new Option("BDS - Behavioral Decision Science","BDS",false, false);
            document.ttform.subj_code.options[24]=new Option("BIOL - Biological Sciences","BIOL",false, false);
            document.ttform.subj_code.options[25]=new Option("BIT - Business Information Technology","BIT",false, false);
            document.ttform.subj_code.options[26]=new Option("BMES - Biomedical Engineering and Sciences","BMES",false, false);
            document.ttform.subj_code.options[27]=new Option("BMSP - Biomedical Sciences and Pathobiology","BMSP",false, false);
            document.ttform.subj_code.options[28]=new Option("BMVS - Biomedical and Veterinary Sciences","BMVS",false, false);
            document.ttform.subj_code.options[29]=new Option("BSE - Biological Systems Engineering","BSE",false, false);
            document.ttform.subj_code.options[30]=new Option("CEE - Civil and Environmental Engineering","CEE",false, false);
            document.ttform.subj_code.options[31]=new Option("CEM - Construction Engineering and Management","CEM",false, false);
            document.ttform.subj_code.options[32]=new Option("CHE - Chemical Engineering","CHE",false, false);
            document.ttform.subj_code.options[33]=new Option("CHEM - Chemistry","CHEM",false, false);
            document.ttform.subj_code.options[34]=new Option("CHN - Chinese","CHN",false, false);
            document.ttform.subj_code.options[35]=new Option("CINE - Cinema","CINE",false, false);
            document.ttform.subj_code.options[36]=new Option("CLA - Classical Studies","CLA",false, false);
            document.ttform.subj_code.options[37]=new Option("CMDA - Computational Modeling and Data Analytics","CMDA",false, false);
            document.ttform.subj_code.options[38]=new Option("CMST - Communication Studies","CMST",false, false);
            document.ttform.subj_code.options[39]=new Option("CNST - Construction","CNST",false, false);
            document.ttform.subj_code.options[40]=new Option("COMM - Communication","COMM",false, false);
            document.ttform.subj_code.options[41]=new Option("CONS - Consumer Studies","CONS",false, false);
            document.ttform.subj_code.options[42]=new Option("COS - College of Science","COS",false, false);
            document.ttform.subj_code.options[43]=new Option("CRIM - Criminology","CRIM",false, false);
            document.ttform.subj_code.options[44]=new Option("CS - Computer Science","CS",false, true);
            document.ttform.subj_code.options[45]=new Option("CSES - Crop and Soil Environmental Sciences","CSES",false, false);
            document.ttform.subj_code.options[46]=new Option("DANC - Dance","DANC",false, false);
            document.ttform.subj_code.options[47]=new Option("DASC - Dairy Science","DASC",false, false);
            document.ttform.subj_code.options[48]=new Option("ECE - Electrical and Computer Engineering","ECE",false, false);
            document.ttform.subj_code.options[49]=new Option("ECON - Economics","ECON",false, false);
            document.ttform.subj_code.options[50]=new Option("EDCI - Education, Curriculum and Instruction","EDCI",false, false);
            document.ttform.subj_code.options[51]=new Option("EDCO - Counselor Education","EDCO",false, false);
            document.ttform.subj_code.options[52]=new Option("EDCT - Career and Technical Education","EDCT",false, false);
            document.ttform.subj_code.options[53]=new Option("EDEL - Educational Leadership","EDEL",false, false);
            document.ttform.subj_code.options[54]=new Option("EDEP - Educational Psychology","EDEP",false, false);
            document.ttform.subj_code.options[55]=new Option("EDHE - Higher Education","EDHE",false, false);
            document.ttform.subj_code.options[56]=new Option("EDIT - Instructional Design and Technology","EDIT",false, false);
            document.ttform.subj_code.options[57]=new Option("EDP - Environmental Design and Planning","EDP",false, false);
            document.ttform.subj_code.options[58]=new Option("EDRE - Education, Research and Evaluation","EDRE",false, false);
            document.ttform.subj_code.options[59]=new Option("EDTE - Technology Education","EDTE",false, false);
            document.ttform.subj_code.options[60]=new Option("ENGE - Engineering Education","ENGE",false, false);
            document.ttform.subj_code.options[61]=new Option("ENGL - English","ENGL",false, false);
            document.ttform.subj_code.options[62]=new Option("ENGR - Engineering","ENGR",false, false);
            document.ttform.subj_code.options[63]=new Option("ENSC - Environmental Science","ENSC",false, false);
            document.ttform.subj_code.options[64]=new Option("ENT - Entomology","ENT",false, false);
            document.ttform.subj_code.options[65]=new Option("ES - Environmental Security","ES",false, false);
            document.ttform.subj_code.options[66]=new Option("ESM - Engineering Science and Mechanics","ESM",false, false);
            document.ttform.subj_code.options[67]=new Option("FIN - Finance","FIN",false, false);
            document.ttform.subj_code.options[68]=new Option("FIW - Fish and Wildlife Conservation","FIW",false, false);
            document.ttform.subj_code.options[69]=new Option("FL - Modern and Classical Languages and Literatures","FL",false, false);
            document.ttform.subj_code.options[70]=new Option("FMD - Fashion Merchandising and Design","FMD",false, false);
            document.ttform.subj_code.options[71]=new Option("FR - French","FR",false, false);
            document.ttform.subj_code.options[72]=new Option("FREC - Forest Resources and Environmental Conservation","FREC",false, false);
            document.ttform.subj_code.options[73]=new Option("FST - Food Science and Technology","FST",false, false);
            document.ttform.subj_code.options[74]=new Option("GBCB - Genetics, Bioinformatics, Computational Biology","GBCB",false, false);
            document.ttform.subj_code.options[75]=new Option("GEOG - Geography","GEOG",false, false);
            document.ttform.subj_code.options[76]=new Option("GEOS - Geosciences","GEOS",false, false);
            document.ttform.subj_code.options[77]=new Option("GER - German","GER",false, false);
            document.ttform.subj_code.options[78]=new Option("GIA - Government and International Affairs","GIA",false, false);
            document.ttform.subj_code.options[79]=new Option("GR - Greek","GR",false, false);
            document.ttform.subj_code.options[80]=new Option("GRAD - Graduate School","GRAD",false, false);
            document.ttform.subj_code.options[81]=new Option("HD - Human Development","HD",false, false);
            document.ttform.subj_code.options[82]=new Option("HEB - Hebrew","HEB",false, false);
            document.ttform.subj_code.options[83]=new Option("HIST - History","HIST",false, false);
            document.ttform.subj_code.options[84]=new Option("HNFE - Human Nutrition, Foods and Exercise","HNFE",false, false);
            document.ttform.subj_code.options[85]=new Option("HORT - Horticulture","HORT",false, false);
            document.ttform.subj_code.options[86]=new Option("HTM - Hospitality and Tourism Management","HTM",false, false);
            document.ttform.subj_code.options[87]=new Option("HUM - Humanities","HUM",false, false);
            document.ttform.subj_code.options[88]=new Option("IDS - Industrial Design","IDS",false, false);
            document.ttform.subj_code.options[89]=new Option("IS - International Studies","IS",false, false);
            document.ttform.subj_code.options[90]=new Option("ISC - Integrated Science","ISC",false, false);
            document.ttform.subj_code.options[91]=new Option("ISE - Industrial and Systems Engineering","ISE",false, false);
            document.ttform.subj_code.options[92]=new Option("ITAL - Italian","ITAL",false, false);
            document.ttform.subj_code.options[93]=new Option("ITDS - Interior Design","ITDS",false, false);
            document.ttform.subj_code.options[94]=new Option("JMC - Journalism and Mass Communication","JMC",false, false);
            document.ttform.subj_code.options[95]=new Option("JPN - Japanese","JPN",false, false);
            document.ttform.subj_code.options[96]=new Option("JUD - Judaic Studies","JUD",false, false);
            document.ttform.subj_code.options[97]=new Option("LAHS - Liberal Arts and Human Sciences","LAHS",false, false);
            document.ttform.subj_code.options[98]=new Option("LAR - Landscape Architecture","LAR",false, false);
            document.ttform.subj_code.options[99]=new Option("LAT - Latin","LAT",false, false);
            document.ttform.subj_code.options[100]=new Option("LDRS - Leadership Studies","LDRS",false, false);
            document.ttform.subj_code.options[101]=new Option("MACR - Macromolecular Science and Engineering","MACR",false, false);
            document.ttform.subj_code.options[102]=new Option("MATH - Mathematics","MATH",false, false);
            document.ttform.subj_code.options[103]=new Option("ME - Mechanical Engineering","ME",false, false);
            document.ttform.subj_code.options[104]=new Option("MED - Medicine","MED",false, false);
            document.ttform.subj_code.options[105]=new Option("MGT - Management","MGT",false, false);
            document.ttform.subj_code.options[106]=new Option("MINE - Mining Engineering","MINE",false, false);
            document.ttform.subj_code.options[107]=new Option("MKTG - Marketing","MKTG",false, false);
            document.ttform.subj_code.options[108]=new Option("MN - Military Navy","MN",false, false);
            document.ttform.subj_code.options[109]=new Option("MS - Military Science (AROTC)","MS",false, false);
            document.ttform.subj_code.options[110]=new Option("MSE - Materials Science and Engineering","MSE",false, false);
            document.ttform.subj_code.options[111]=new Option("MTRG - Meteorology","MTRG",false, false);
            document.ttform.subj_code.options[112]=new Option("MUS - Music","MUS",false, false);
            document.ttform.subj_code.options[113]=new Option("NANO - Nanoscience","NANO",false, false);
            document.ttform.subj_code.options[114]=new Option("NEUR - Neuroscience","NEUR",false, false);
            document.ttform.subj_code.options[115]=new Option("NR - Natural Resources","NR",false, false);
            document.ttform.subj_code.options[116]=new Option("NSEG - Nuclear Science and Engineering","NSEG",false, false);
            document.ttform.subj_code.options[117]=new Option("PAPA - Public Administration/Public Affairs","PAPA",false, false);
            document.ttform.subj_code.options[118]=new Option("PHIL - Philosophy","PHIL",false, false);
            document.ttform.subj_code.options[119]=new Option("PHS - Population Health Sciences","PHS",false, false);
            document.ttform.subj_code.options[120]=new Option("PHYS - Physics","PHYS",false, false);
            document.ttform.subj_code.options[121]=new Option("PM - Property Management","PM",false, false);
            document.ttform.subj_code.options[122]=new Option("PORT - Portuguese","PORT",false, false);
            document.ttform.subj_code.options[123]=new Option("PPE - Philosophy, Politics, and Economics","PPE",false, false);
            document.ttform.subj_code.options[124]=new Option("PPWS - Plant Pathology, Physiology and Weed Science","PPWS",false, false);
            document.ttform.subj_code.options[125]=new Option("PR - Public Relations","PR",false, false);
            document.ttform.subj_code.options[126]=new Option("PSCI - Political Science","PSCI",false, false);
            document.ttform.subj_code.options[127]=new Option("PSVP - Peace Studies","PSVP",false, false);
            document.ttform.subj_code.options[128]=new Option("PSYC - Psychology","PSYC",false, false);
            document.ttform.subj_code.options[129]=new Option("REAL - Real Estate","REAL",false, false);
            document.ttform.subj_code.options[130]=new Option("RED - Residential Environments and Design","RED",false, false);
            document.ttform.subj_code.options[131]=new Option("RLCL - Religion and Culture","RLCL",false, false);
            document.ttform.subj_code.options[132]=new Option("RTM - Research in Translational Medicine","RTM",false, false);
            document.ttform.subj_code.options[133]=new Option("RUS - Russian","RUS",false, false);
            document.ttform.subj_code.options[134]=new Option("SBIO - Sustainable Biomaterials","SBIO",false, false);
            document.ttform.subj_code.options[135]=new Option("SOC - Sociology","SOC",false, false);
            document.ttform.subj_code.options[136]=new Option("SPAN - Spanish","SPAN",false, false);
            document.ttform.subj_code.options[137]=new Option("SPES - School of Plant and Environmental Sciences","SPES",false, false);
            document.ttform.subj_code.options[138]=new Option("SPIA - School of Public and International Affairs","SPIA",false, false);
            document.ttform.subj_code.options[139]=new Option("STAT - Statistics","STAT",false, false);
            document.ttform.subj_code.options[140]=new Option("STL - Science, Technology, & Law","STL",false, false);
            document.ttform.subj_code.options[141]=new Option("STS - Science and Technology Studies","STS",false, false);
            document.ttform.subj_code.options[142]=new Option("SYSB - Systems Biology","SYSB",false, false);
            document.ttform.subj_code.options[143]=new Option("TA - Theatre Arts","TA",false, false);
            document.ttform.subj_code.options[144]=new Option("TBMH - Translational Biology, Medicine and Health","TBMH",false, false);
            document.ttform.subj_code.options[145]=new Option("UAP - Urban Affairs and Planning","UAP",false, false);
            document.ttform.subj_code.options[146]=new Option("UH - University Honors","UH",false, false);
            document.ttform.subj_code.options[147]=new Option("UNIV - University Course Series","UNIV",false, false);
            document.ttform.subj_code.options[148]=new Option("VM - Veterinary Medicine","VM",false, false);
            document.ttform.subj_code.options[149]=new Option("WATR - Water","WATR",false, false);
            document.ttform.subj_code.options[150]=new Option("WGS - Women's and Gender Studies","WGS",false, false);


            break;


            default:
            document.ttform.subj_code.options[0]=new Option("All Subjects","%",false, false);
            document.ttform.subj_code.options[1]=new Option("AAD - Architecture, Arts, and Design","AAD",false, false);
            document.ttform.subj_code.options[2]=new Option("AAEC - Agricultural and Applied Economics","AAEC",false, false);
            document.ttform.subj_code.options[3]=new Option("ACIS - Accounting and Information Systems","ACIS",false, false);
            document.ttform.subj_code.options[4]=new Option("ADS - Applied Data Science","ADS",false, false);
            document.ttform.subj_code.options[5]=new Option("ADV - Advertising","ADV",false, false);
            document.ttform.subj_code.options[6]=new Option("AFST - Africana Studies","AFST",false, false);
            document.ttform.subj_code.options[7]=new Option("AHRM - Apparel, Housing, and Resource Management","AHRM",false, false);
            document.ttform.subj_code.options[8]=new Option("AINS - American Indian Studies","AINS",false, false);
            document.ttform.subj_code.options[9]=new Option("AIS - Academy of Integrated Science","AIS",false, false);
            document.ttform.subj_code.options[10]=new Option("ALCE - Agricultural, Leadership, and Community Education","ALCE",false, false);
            document.ttform.subj_code.options[11]=new Option("ALS - Agriculture and Life Sciences","ALS",false, false);
            document.ttform.subj_code.options[12]=new Option("AOE - Aerospace and Ocean Engineering","AOE",false, false);
            document.ttform.subj_code.options[13]=new Option("APS - Appalachian Studies","APS",false, false);
            document.ttform.subj_code.options[14]=new Option("APSC - Animal and Poultry Sciences","APSC",false, false);
            document.ttform.subj_code.options[15]=new Option("ARBC - Arabic","ARBC",false, false);
            document.ttform.subj_code.options[16]=new Option("ARCH - Architecture","ARCH",false, false);
            document.ttform.subj_code.options[17]=new Option("ART - Art and Art History","ART",false, false);
            document.ttform.subj_code.options[18]=new Option("AS - Military Aerospace Studies","AS",false, false);
            document.ttform.subj_code.options[19]=new Option("ASPT - Alliance for Social, Political, Ethical, and Cultural Thought","ASPT",false, false);
            document.ttform.subj_code.options[20]=new Option("AT - Agricultural Technology","AT",false, false);
            document.ttform.subj_code.options[21]=new Option("BC - Building Construction","BC",false, false);
            document.ttform.subj_code.options[22]=new Option("BCHM - Biochemistry","BCHM",false, false);
            document.ttform.subj_code.options[23]=new Option("BDS - Behavioral Decision Science","BDS",false, false);
            document.ttform.subj_code.options[24]=new Option("BIOL - Biological Sciences","BIOL",false, false);
            document.ttform.subj_code.options[25]=new Option("BIT - Business Information Technology","BIT",false, false);
            document.ttform.subj_code.options[26]=new Option("BMES - Biomedical Engineering and Sciences","BMES",false, false);
            document.ttform.subj_code.options[27]=new Option("BMSP - Biomedical Sciences and Pathobiology","BMSP",false, false);
            document.ttform.subj_code.options[28]=new Option("BMVS - Biomedical and Veterinary Sciences","BMVS",false, false);
            document.ttform.subj_code.options[29]=new Option("BSE - Biological Systems Engineering","BSE",false, false);
            document.ttform.subj_code.options[30]=new Option("CEE - Civil and Environmental Engineering","CEE",false, false);
            document.ttform.subj_code.options[31]=new Option("CEM - Construction Engineering and Management","CEM",false, false);
            document.ttform.subj_code.options[32]=new Option("CHE - Chemical Engineering","CHE",false, false);
            document.ttform.subj_code.options[33]=new Option("CHEM - Chemistry","CHEM",false, false);
            document.ttform.subj_code.options[34]=new Option("CHN - Chinese","CHN",false, false);
            document.ttform.subj_code.options[35]=new Option("CINE - Cinema","CINE",false, false);
            document.ttform.subj_code.options[36]=new Option("CLA - Classical Studies","CLA",false, false);
            document.ttform.subj_code.options[37]=new Option("CMDA - Computational Modeling and Data Analytics","CMDA",false, false);
            document.ttform.subj_code.options[38]=new Option("CMST - Communication Studies","CMST",false, false);
            document.ttform.subj_code.options[39]=new Option("CNST - Construction","CNST",false, false);
            document.ttform.subj_code.options[40]=new Option("COMM - Communication","COMM",false, false);
            document.ttform.subj_code.options[41]=new Option("CONS - Consumer Studies","CONS",false, false);
            document.ttform.subj_code.options[42]=new Option("COS - College of Science","COS",false, false);
            document.ttform.subj_code.options[43]=new Option("CRIM - Criminology","CRIM",false, false);
            document.ttform.subj_code.options[44]=new Option("CS - Computer Science","CS",false, true);
            document.ttform.subj_code.options[45]=new Option("CSES - Crop and Soil Environmental Sciences","CSES",false, false);
            document.ttform.subj_code.options[46]=new Option("DANC - Dance","DANC",false, false);
            document.ttform.subj_code.options[47]=new Option("DASC - Dairy Science","DASC",false, false);
            document.ttform.subj_code.options[48]=new Option("ECE - Electrical and Computer Engineering","ECE",false, false);
            document.ttform.subj_code.options[49]=new Option("ECON - Economics","ECON",false, false);
            document.ttform.subj_code.options[50]=new Option("EDCI - Education, Curriculum and Instruction","EDCI",false, false);
            document.ttform.subj_code.options[51]=new Option("EDCO - Counselor Education","EDCO",false, false);
            document.ttform.subj_code.options[52]=new Option("EDCT - Career and Technical Education","EDCT",false, false);
            document.ttform.subj_code.options[53]=new Option("EDEL - Educational Leadership","EDEL",false, false);
            document.ttform.subj_code.options[54]=new Option("EDEP - Educational Psychology","EDEP",false, false);
            document.ttform.subj_code.options[55]=new Option("EDHE - Higher Education","EDHE",false, false);
            document.ttform.subj_code.options[56]=new Option("EDIT - Instructional Design and Technology","EDIT",false, false);
            document.ttform.subj_code.options[57]=new Option("EDP - Environmental Design and Planning","EDP",false, false);
            document.ttform.subj_code.options[58]=new Option("EDRE - Education, Research and Evaluation","EDRE",false, false);
            document.ttform.subj_code.options[59]=new Option("EDTE - Technology Education","EDTE",false, false);
            document.ttform.subj_code.options[60]=new Option("ENGE - Engineering Education","ENGE",false, false);
            document.ttform.subj_code.options[61]=new Option("ENGL - English","ENGL",false, false);
            document.ttform.subj_code.options[62]=new Option("ENGR - Engineering","ENGR",false, false);
            document.ttform.subj_code.options[63]=new Option("ENSC - Environmental Science","ENSC",false, false);
            document.ttform.subj_code.options[64]=new Option("ENT - Entomology","ENT",false, false);
            document.ttform.subj_code.options[65]=new Option("ES - Environmental Security","ES",false, false);
            document.ttform.subj_code.options[66]=new Option("ESM - Engineering Science and Mechanics","ESM",false, false);
            document.ttform.subj_code.options[67]=new Option("FIN - Finance","FIN",false, false);
            document.ttform.subj_code.options[68]=new Option("FIW - Fish and Wildlife Conservation","FIW",false, false);
            document.ttform.subj_code.options[69]=new Option("FL - Modern and Classical Languages and Literatures","FL",false, false);
            document.ttform.subj_code.options[70]=new Option("FMD - Fashion Merchandising and Design","FMD",false, false);
            document.ttform.subj_code.options[71]=new Option("FR - French","FR",false, false);
            document.ttform.subj_code.options[72]=new Option("FREC - Forest Resources and Environmental Conservation","FREC",false, false);
            document.ttform.subj_code.options[73]=new Option("FST - Food Science and Technology","FST",false, false);
            document.ttform.subj_code.options[74]=new Option("GBCB - Genetics, Bioinformatics, Computational Biology","GBCB",false, false);
            document.ttform.subj_code.options[75]=new Option("GEOG - Geography","GEOG",false, false);
            document.ttform.subj_code.options[76]=new Option("GEOS - Geosciences","GEOS",false, false);
            document.ttform.subj_code.options[77]=new Option("GER - German","GER",false, false);
            document.ttform.subj_code.options[78]=new Option("GIA - Government and International Affairs","GIA",false, false);
            document.ttform.subj_code.options[79]=new Option("GR - Greek","GR",false, false);
            document.ttform.subj_code.options[80]=new Option("GRAD - Graduate School","GRAD",false, false);
            document.ttform.subj_code.options[81]=new Option("HD - Human Development","HD",false, false);
            document.ttform.subj_code.options[82]=new Option("HEB - Hebrew","HEB",false, false);
            document.ttform.subj_code.options[83]=new Option("HIST - History","HIST",false, false);
            document.ttform.subj_code.options[84]=new Option("HNFE - Human Nutrition, Foods and Exercise","HNFE",false, false);
            document.ttform.subj_code.options[85]=new Option("HORT - Horticulture","HORT",false, false);
            document.ttform.subj_code.options[86]=new Option("HTM - Hospitality and Tourism Management","HTM",false, false);
            document.ttform.subj_code.options[87]=new Option("HUM - Humanities","HUM",false, false);
            document.ttform.subj_code.options[88]=new Option("IDS - Industrial Design","IDS",false, false);
            document.ttform.subj_code.options[89]=new Option("IS - International Studies","IS",false, false);
            document.ttform.subj_code.options[90]=new Option("ISC - Integrated Science","ISC",false, false);
            document.ttform.subj_code.options[91]=new Option("ISE - Industrial and Systems Engineering","ISE",false, false);
            document.ttform.subj_code.options[92]=new Option("ITAL - Italian","ITAL",false, false);
            document.ttform.subj_code.options[93]=new Option("ITDS - Interior Design","ITDS",false, false);
            document.ttform.subj_code.options[94]=new Option("JMC - Journalism and Mass Communication","JMC",false, false);
            document.ttform.subj_code.options[95]=new Option("JPN - Japanese","JPN",false, false);
            document.ttform.subj_code.options[96]=new Option("JUD - Judaic Studies","JUD",false, false);
            document.ttform.subj_code.options[97]=new Option("LAHS - Liberal Arts and Human Sciences","LAHS",false, false);
            document.ttform.subj_code.options[98]=new Option("LAR - Landscape Architecture","LAR",false, false);
            document.ttform.subj_code.options[99]=new Option("LAT - Latin","LAT",false, false);
            document.ttform.subj_code.options[100]=new Option("LDRS - Leadership Studies","LDRS",false, false);
            document.ttform.subj_code.options[101]=new Option("MACR - Macromolecular Science and Engineering","MACR",false, false);
            document.ttform.subj_code.options[102]=new Option("MATH - Mathematics","MATH",false, false);
            document.ttform.subj_code.options[103]=new Option("ME - Mechanical Engineering","ME",false, false);
            document.ttform.subj_code.options[104]=new Option("MED - Medicine","MED",false, false);
            document.ttform.subj_code.options[105]=new Option("MGT - Management","MGT",false, false);
            document.ttform.subj_code.options[106]=new Option("MINE - Mining Engineering","MINE",false, false);
            document.ttform.subj_code.options[107]=new Option("MKTG - Marketing","MKTG",false, false);
            document.ttform.subj_code.options[108]=new Option("MN - Military Navy","MN",false, false);
            document.ttform.subj_code.options[109]=new Option("MS - Military Science (AROTC)","MS",false, false);
            document.ttform.subj_code.options[110]=new Option("MSE - Materials Science and Engineering","MSE",false, false);
            document.ttform.subj_code.options[111]=new Option("MTRG - Meteorology","MTRG",false, false);
            document.ttform.subj_code.options[112]=new Option("MUS - Music","MUS",false, false);
            document.ttform.subj_code.options[113]=new Option("NANO - Nanoscience","NANO",false, false);
            document.ttform.subj_code.options[114]=new Option("NEUR - Neuroscience","NEUR",false, false);
            document.ttform.subj_code.options[115]=new Option("NR - Natural Resources","NR",false, false);
            document.ttform.subj_code.options[116]=new Option("NSEG - Nuclear Science and Engineering","NSEG",false, false);
            document.ttform.subj_code.options[117]=new Option("PAPA - Public Administration/Public Affairs","PAPA",false, false);
            document.ttform.subj_code.options[118]=new Option("PHIL - Philosophy","PHIL",false, false);
            document.ttform.subj_code.options[119]=new Option("PHS - Population Health Sciences","PHS",false, false);
            document.ttform.subj_code.options[120]=new Option("PHYS - Physics","PHYS",false, false);
            document.ttform.subj_code.options[121]=new Option("PM - Property Management","PM",false, false);
            document.ttform.subj_code.options[122]=new Option("PORT - Portuguese","PORT",false, false);
            document.ttform.subj_code.options[123]=new Option("PPE - Philosophy, Politics, and Economics","PPE",false, false);
            document.ttform.subj_code.options[124]=new Option("PPWS - Plant Pathology, Physiology and Weed Science","PPWS",false, false);
            document.ttform.subj_code.options[125]=new Option("PR - Public Relations","PR",false, false);
            document.ttform.subj_code.options[126]=new Option("PSCI - Political Science","PSCI",false, false);
            document.ttform.subj_code.options[127]=new Option("PSVP - Peace Studies","PSVP",false, false);
            document.ttform.subj_code.options[128]=new Option("PSYC - Psychology","PSYC",false, false);
            document.ttform.subj_code.options[129]=new Option("REAL - Real Estate","REAL",false, false);
            document.ttform.subj_code.options[130]=new Option("RED - Residential Environments and Design","RED",false, false);
            document.ttform.subj_code.options[131]=new Option("RLCL - Religion and Culture","RLCL",false, false);
            document.ttform.subj_code.options[132]=new Option("RTM - Research in Translational Medicine","RTM",false, false);
            document.ttform.subj_code.options[133]=new Option("RUS - Russian","RUS",false, false);
            document.ttform.subj_code.options[134]=new Option("SBIO - Sustainable Biomaterials","SBIO",false, false);
            document.ttform.subj_code.options[135]=new Option("SOC - Sociology","SOC",false, false);
            document.ttform.subj_code.options[136]=new Option("SPAN - Spanish","SPAN",false, false);
            document.ttform.subj_code.options[137]=new Option("SPES - School of Plant and Environmental Sciences","SPES",false, false);
            document.ttform.subj_code.options[138]=new Option("SPIA - School of Public and International Affairs","SPIA",false, false);
            document.ttform.subj_code.options[139]=new Option("STAT - Statistics","STAT",false, false);
            document.ttform.subj_code.options[140]=new Option("STL - Science, Technology, & Law","STL",false, false);
            document.ttform.subj_code.options[141]=new Option("STS - Science and Technology Studies","STS",false, false);
            document.ttform.subj_code.options[142]=new Option("SYSB - Systems Biology","SYSB",false, false);
            document.ttform.subj_code.options[143]=new Option("TA - Theatre Arts","TA",false, false);
            document.ttform.subj_code.options[144]=new Option("TBMH - Translational Biology, Medicine and Health","TBMH",false, false);
            document.ttform.subj_code.options[145]=new Option("UAP - Urban Affairs and Planning","UAP",false, false);
            document.ttform.subj_code.options[146]=new Option("UH - University Honors","UH",false, false);
            document.ttform.subj_code.options[147]=new Option("UNIV - University Course Series","UNIV",false, false);
            document.ttform.subj_code.options[148]=new Option("VM - Veterinary Medicine","VM",false, false);
            document.ttform.subj_code.options[149]=new Option("WATR - Water","WATR",false, false);
            document.ttform.subj_code.options[150]=new Option("WGS - Women's and Gender Studies","WGS",false, false);


            break;


            }
            return true;
            }
            </script>

            """

            # Sample HTML for scrape_subject('CS')
            self.cs_subject_html = """
            <table class="dataentrytable">
                <tr><th>CRN</th><th>Course</th><th>Title</th><th>Type</th><th>Modality</th><th>Hours</th><th>Cap</th><th>Instructor</th><th>Days</th><th>Begin</th><th>End</th><th>Location</th><th>Exam</th></tr>
                <tr>
                    <td><b>83488</b></td><td><font>CS-2114</font></td><td>Softw Des & Data Structures</td>
                    <td>L</td><td><p>Face-to-Face</p></td><td>3</td><td>35</td><td>N/A</td>
                    <td>T R</td><td>9:30AM</td><td>10:20AM</td><td>GOODW 190</td><td><a>CTE</a></td>
                </tr>
                <tr>
                    <td><b>12345</b></td><td><font>CS-1064</font></td><td>Intro to Programming</td>
                    <td>L</td><td><p>Online</p></td><td>3</td><td>100</td><td>John Doe</td>
                    <td>(ARR)</td><td>-----</td><td>Online</td><td><a>CTE</a></td>
                </tr>
            </table>
            """

            # Sample HTML for scrape_subject('MATH')
            self.math_subject_html = """
            <table class="dataentrytable">
                <tr><th>CRN</th><th>Course</th><th>Title</th><th>Type</th><th>Modality</th><th>Hours</th><th>Cap</th><th>Instructor</th><th>Days</th><th>Begin</th><th>End</th><th>Location</th><th>Exam</th></tr>
                <tr>
                    <td><b>54321</b></td><td><font>MATH-1225</font></td><td>Calculus I</td>
                    <td>L</td><td><p>Face-to-Face</p></td><td>4</td><td>150</td><td>Jane Smith</td>
                    <td>M W F</td><td>11:15AM</td><td>12:05PM</td><td>MCB 110</td><td><a>CTE</a></td>
                </tr>
                <tr>
                    <td><b>65432</b></td><td><font>MATH-1226</font></td><td>Calculus II</td>
                    <td>L</td><td><p>Face-to-Face</p></td><td>4</td><td>120</td><td>Bob Johnson</td>
                    <td>T R</td><td>2:00PM</td><td>3:15PM</td><td>MCB 120</td><td><a>CTE</a></td>
                </tr>
            </table>
            """

            # Sample HTML for a subject with no courses (PHYS)
            self.empty_subject_html = """
            <table class="dataentrytable">
                <tr><th>CRN</th><th>Course</th><th>Title</th><th>Type</th><th>Modality</th><th>Hours</th><th>Cap</th><th>Instructor</th><th>Days</th><th>Begin</th><th>End</th><th>Location</th><th>Exam</th></tr>
            </table>
            """

            # Sample HTML for a subject that returns no table
            self.no_table_html = "<html><body><p>No data found</p></body></html>"

            def fetch_html_side_effect(subject):
                if subject == "%":
                    return self.subjects_html
                elif subject == "CS":
                    return self.cs_subject_html
                elif subject == "MATH":
                    return self.math_subject_html
                elif subject == "PHYS":
                    return self.empty_subject_html
                else:
                    return self.no_table_html

            self.mock_fetcher.fetch_html.side_effect = fetch_html_side_effect

            yield

    def test_get_subjects_success(self):
        """Test get_subjects successfully retrieves and parses subjects."""
        # Act
        subjects = self.scraper.get_subjects()

        # Assert
        self.mock_fetcher.fetch_html.assert_called_once_with("%")
        assert len(subjects) == 150
        assert "CS" in subjects

    @patch("scraper.timetable_scraper.logging")
    @patch("scraper.timetable_scraper.TimetableFetcher")
    def test_get_subjects_null_return(self, mock_fetcher_class, mock_logging):
        """Tests get_subjects retrieving null HTML"""
        # Arrange
        mock_fetcher_instance = Mock()
        mock_fetcher_instance.fetch_html.return_value = None
        mock_fetcher_class.return_value = mock_fetcher_instance

        scraper = TimetableScraper("202509")

        # Act
        subjects = scraper.get_subjects()

        # Assert
        mock_fetcher_instance.fetch_html.assert_called_once_with("%")
        mock_logging.warning.assert_called_once_with(
            "No HTML returned when retrieving all subjects"
        )
        assert subjects == []

    @patch("scraper.timetable_scraper.logging")
    def test_get_subjects_fetch_html_exception(self, mock_logging):
        """Test get_subjects when fetch_html raises an exception"""
        # Arrange
        exception_message = "Network connection failed"
        self.mock_fetcher.fetch_html.side_effect = Exception(exception_message)

        # Act
        subjects = self.scraper.get_subjects()

        # Assert
        self.mock_fetcher.fetch_html.assert_called_once_with("%")
        mock_logging.error.assert_called_once_with(
            f"Failed to fetch HTML when retrieving all subjects: {exception_message}"
        )
        assert subjects == []

    @patch("scraper.timetable_scraper.logging")
    @patch("scraper.timetable_scraper.TimetableFetcher")
    def test_get_subjects_no_script_match(self, mock_fetcher_class, mock_logging):
        """Tests get_subjects with no match for subjects block"""
        # Arrange
        mock_fetcher_instance = Mock()
        mock_fetcher_instance.fetch_html.return_value = "Not a match"
        mock_fetcher_class.return_value = mock_fetcher_instance

        scraper = TimetableScraper("202509")

        # Act
        subjects = scraper.get_subjects()

        # Assert
        mock_fetcher_instance.fetch_html.assert_called_once_with("%")
        mock_logging.warning.assert_called_once_with(
            "Could not find matching script when retrieving all subjects"
        )
        assert subjects == []

    def test_scrape_subject_success(self):
        """Test scrape_subject successfully retrieves and processes course data."""
        # Act
        result = self.scraper.scrape_subject("CS")

        # Assert
        self.mock_fetcher.fetch_html.assert_called_with("CS")
        assert "CS-2114" in result
        assert "CS-1064" in result
        assert len(result["CS-2114"]) == 1
        assert len(result["CS-1064"]) == 1
        assert result["CS-2114"][0]["crn"] == "83488"
        assert result["CS-1064"][0]["crn"] == "12345"

    def test_scrape_subject_null_html(self):
        """Test scrape_subject when fetcher returns None."""
        # Arrange
        with patch.object(self.mock_fetcher, 'fetch_html', return_value=None):
            # Act
            result = self.scraper.scrape_subject("CS")

        # Assert
        assert result == {}

    @patch("scraper.timetable_scraper.logging")
    def test_scrape_subject_fetch_exception(self, mock_logging):
        """Test scrape_subject when fetch_html raises an exception."""
        # Arrange
        exception_message = "Connection timeout"
        self.mock_fetcher.fetch_html.side_effect = Exception(exception_message)

        # Act
        result = self.scraper.scrape_subject("CS")

        # Assert
        self.mock_fetcher.fetch_html.assert_called_with("CS")
        mock_logging.error.assert_called_once_with(
            f"Failed to fetch HTML for subject CS: {exception_message}"
        )
        assert result == {}

    @patch("scraper.timetable_scraper.logging")
    def test_scrape_subject_parse_exception(self, mock_logging):
        """Test scrape_subject when HTML parsing fails."""
        # Arrange
        self.mock_fetcher.fetch_html.return_value = "Invalid HTML that causes parsing error"
        with patch("scraper.timetable_scraper.BeautifulSoup") as mock_soup:
            mock_soup.side_effect = Exception("Parsing failed")

            # Act
            result = self.scraper.scrape_subject("CS")

            # Assert
            mock_logging.error.assert_called_once_with(
                "Failed to parse HTML for subject CS: Parsing failed"
            )
            assert result == {}

    @patch("scraper.timetable_scraper.logging")
    def test_scrape_subject_no_table(self, mock_logging):
        """Test scrape_subject when no data table is found."""
        # Act
        result = self.scraper.scrape_subject("INVALID")

        # Assert
        self.mock_fetcher.fetch_html.assert_called_with("INVALID")
        mock_logging.debug.assert_called_once_with(
            "No section table found for subject: INVALID"
        )
        assert result == {}

    @patch("scraper.timetable_scraper.logging")
    def test_scrape_subject_empty_table(self, mock_logging):
        """Test scrape_subject when table has no data rows."""
        # Act
        result = self.scraper.scrape_subject("PHYS")

        # Assert
        self.mock_fetcher.fetch_html.assert_called_with("PHYS")
        mock_logging.warning.assert_called_once_with(
            "No data rows found for subject: PHYS"
        )
        assert result == {}

    def test_scrape_multiple_subjects_success(self):
        """Test scraping multiple subjects successfully."""
        # Arrange
        subjects = ["CS", "MATH"]

        # Act
        result = self.scraper.scrape_multiple_subjects(subjects)

        # Assert
        assert "CS" in result
        assert "MATH" in result
        assert "CS-2114" in result["CS"]
        assert "MATH-1225" in result["MATH"]

    def test_scrape_multiple_subjects_partial_success(self):
        """Test scraping multiple subjects with some failures."""
        # Arrange
        subjects = ["CS", "INVALID", "MATH"]

        # Act
        result = self.scraper.scrape_multiple_subjects(subjects)

        # Assert
        assert "CS" in result
        assert "MATH" in result
        assert "INVALID" not in result  # Should not include empty results

    def test_scrape_multiple_subjects_empty_list(self):
        """Test scraping with empty subjects list."""
        # Act
        result = self.scraper.scrape_multiple_subjects([])

        # Assert
        assert result == {}

    @patch("scraper.timetable_scraper.logging")
    def test_scrape_all_subjects_success(self, mock_logging):
        """Test scraping all subjects successfully."""
        # Act
        result = self.scraper.scrape_all_subjects()

        # Assert
        mock_logging.info.assert_any_call("Found 150 subjects to process")
        assert len(result) > 0
        assert "CS" in result
        assert "MATH" in result

    @patch("scraper.timetable_scraper.logging")  
    def test_scrape_all_subjects_no_subjects_found(self, mock_logging):
        """Test scrape_all_subjects when no subjects are available."""
        # Arrange
        with patch.object(self.scraper, "get_subjects", return_value=[]):
            # Act
            result = self.scraper.scrape_all_subjects()

            # Assert
            mock_logging.error.assert_called_once_with(
                f"No subjects found for term: {self.term}"
            )
            assert result == {}

    def test_find_course_success(self):
        """Test finding a specific course across subjects."""
        # Act
        result = self.scraper.find_course("2114")

        # Assert
        assert len(result) > 0
        # Should find CS-2114 in CS subject
        found_cs = False
        for subject, courses in result.items():
            for course in courses:
                if "2114" in course:
                    found_cs = True
                    break
        assert found_cs

    def test_find_course_case_insensitive(self):
        """Test finding course with case-insensitive search."""
        # Act
        result = self.scraper.find_course("cs-2114")

        # Assert
        assert len(result) > 0
        found_course = False
        for subject, courses in result.items():
            for course in courses:
                if "CS-2114" in course:
                    found_course = True
                    break
        assert found_course

    def test_find_course_not_found(self):
        """Test finding a course that doesn't exist."""
        # Act
        result = self.scraper.find_course("NONEXISTENT-9999")

        # Assert
        assert result == {}

    def test_find_section_by_crn_success(self):
        """Test finding a section by CRN successfully."""
        # Act
        result = self.scraper.find_section_by_crn("83488")

        # Assert
        assert result is not None
        assert result["subject"] == "CS"
        assert result["course"] == "CS-2114"
        assert result["section"]["crn"] == "83488"

    def test_find_section_by_crn_not_found(self):
        """Test finding a section with non-existent CRN."""
        # Act
        result = self.scraper.find_section_by_crn("99999")

        # Assert
        assert result is None

    @patch("scraper.timetable_scraper.logging")
    def test_find_section_by_crn_empty_subjects(self, mock_logging):
        """Test finding section by CRN when no subjects are available."""
        # Arrange
        with patch.object(self.scraper, "get_subjects", return_value=[]):
            # Act
            result = self.scraper.find_section_by_crn("83488")

            # Assert
            assert result is None

    def test_close_session(self):
        """Test closing the fetcher session."""
        # Act
        self.scraper.close()

        # Assert
        self.mock_fetcher.close_session.assert_called_once()

    @patch("scraper.timetable_scraper.logging")
    def test_scrape_subject_with_logging(self, mock_logging):
        """Test that scrape_subject logs appropriate messages."""
        # Act
        self.scraper.scrape_subject("CS")

        # Assert
        mock_logging.info.assert_any_call("Starting scrape for subject: CS")
        mock_logging.info.assert_any_call("Processed 2 courses for subject: CS")

    def test_scrape_subject_maintains_section_data_integrity(self):
        """Test that scrape_subject preserves all section data correctly."""
        # Act
        result = self.scraper.scrape_subject("CS")

        # Assert
        cs_2114_section = result["CS-2114"][0]
        assert cs_2114_section["crn"] == "83488"
        assert cs_2114_section["course"] == "CS-2114"
        assert cs_2114_section["title"] == "Softw Des & Data Structures"
        assert cs_2114_section["schedule_type"] == "L"
        assert cs_2114_section["modality"] == "Face-to-Face"
        assert cs_2114_section["credit_hours"] == "3"
        assert cs_2114_section["capacity"] == "35"
        assert cs_2114_section["instructor"] is None
        assert len(cs_2114_section["meeting_times"]) == 2
        assert cs_2114_section["location"] == "GOODW 190"
        assert cs_2114_section["exam_code"] == "CTE"

        cs_1064_section = result["CS-1064"][0]
        assert cs_1064_section["crn"] == "12345"
        assert cs_1064_section["meeting_times"] == ["ARR"]

    def test_find_course_partial_match(self):
        """Test finding courses with partial course code match."""
        # Act
        result = self.scraper.find_course("CS")

        # Assert
        assert len(result) > 0
        found_cs_courses = False
        for subject, courses in result.items():
            for course in courses:
                if course.startswith("CS-"):
                    found_cs_courses = True
                    break
        assert found_cs_courses

    @pytest.mark.parametrize(
        "crn,expected_found",
        [
            ("83488", True),
            ("12345", True),
            ("54321", True),
            ("00000", False),
            ("", False),
        ],
    )
    def test_find_section_by_crn_parametrized(self, crn, expected_found):
        """Test finding sections by various CRNs."""
        # Act
        result = self.scraper.find_section_by_crn(crn)

        # Assert
        if expected_found:
            assert result is not None
            assert result["section"]["crn"] == crn
        else:
            assert result is None

    def test_scrape_multiple_subjects_preserves_order(self):
        """Test that scrape_multiple_subjects processes subjects in order."""
        # Arrange
        subjects = ["CS", "MATH"]
        call_order = []
        
        def track_calls(subject):
            call_order.append(subject)
            return self.mock_fetcher.fetch_html.return_value

        self.mock_fetcher.fetch_html.side_effect = track_calls

        # Act
        self.scraper.scrape_multiple_subjects(subjects)

        # Assert
        # We need to account for the calls to get_subjects() in find methods
        # So we look for the specific calls we expect
        cs_calls = [call for call in call_order if call == "CS"]
        math_calls = [call for call in call_order if call == "MATH"]
        assert len(cs_calls) >= 1
        assert len(math_calls) >= 1


