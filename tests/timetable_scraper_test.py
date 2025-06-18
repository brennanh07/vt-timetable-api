import pytest
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup, Tag
import json
from collections import defaultdict

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
