#!/usr/bin/env python
# * coding: utf8 *
"""
test_main.py
Unit tests for the metes and bounds description logic module.
Tests coordinate conversions, bearing calculations, and formatting functions.
"""

import csv
from typing import cast

import pytest

from src.main import (
    ENCODING,
    FIELD_NAMES,
    MODE_APPEND,
    MODE_WRITE,
    NEWLINE,
    QUOTE_CHAR,
    DescriptionDict,
    calculate_grid_bearing,
    csv_has_header,
    decimal_degrees_to_dms,
    format_traversal,
    get_disclaimer,
    meters_to_us_feet,
    save_description_to,
)


class MockPoint:
    """Mock point object for testing without arcpy dependency."""

    def __init__(self, x, y):
        self.X = x
        self.Y = y


class TestMetersToUSFeet:
    """Tests for meters to US Survey Feet conversion."""

    def test_meters_to_us_feet_basic(self):
        """Test basic meter to feet conversion."""
        # 1 meter = 3937/1200 US Survey Feet ≈ 3.280833333
        result = meters_to_us_feet(1.0)
        assert result == 3.3

    def test_meters_to_us_feet_100_meters(self):
        """Test conversion of 100 meters."""
        result = meters_to_us_feet(100.0)
        expected = round(100 * 3937 / 1200, 1)
        assert result == expected
        assert result == 328.1

    def test_meters_to_us_feet_zero(self):
        """Test conversion of zero meters."""
        result = meters_to_us_feet(0.0)
        assert result == 0.0

    def test_meters_to_us_feet_decimal(self):
        """Test conversion with decimal input."""
        result = meters_to_us_feet(10.5)
        expected = round(10.5 * 3937 / 1200, 1)
        assert result == expected

    def test_meters_to_us_feet_rounding(self):
        """Test that result is rounded to 1 decimal place."""
        result = meters_to_us_feet(1.23456)
        assert isinstance(result, float)
        # Check that it has at most 1 decimal place
        assert result == round(result, 1)


class TestDDToDMS:
    """Tests for decimal degrees to DMS conversion."""

    def test_dd_to_dms_north_west(self):
        """Test conversion of coordinates in NW quadrant (typical Utah)."""
        point = MockPoint(-111.8710, 40.7588)
        lat_dms, lon_dms = decimal_degrees_to_dms(point)

        # Check latitude (North)
        assert lat_dms.endswith(f"{QUOTE_CHAR}N")
        assert "40°" in lat_dms
        assert "45'" in lat_dms

        # Check longitude (West)
        assert lon_dms.endswith(f"{QUOTE_CHAR}W")
        assert "111°" in lon_dms
        assert "52'" in lon_dms

    def test_dd_to_dms_south_east(self):
        """Test conversion of coordinates in SE quadrant."""
        point = MockPoint(151.2093, -33.8688)  # Sydney, Australia
        lat_dms, lon_dms = decimal_degrees_to_dms(point)

        # Check latitude (South)
        assert lat_dms.endswith(f"{QUOTE_CHAR}S")
        assert "33°" in lat_dms

        # Check longitude (East)
        assert lon_dms.endswith(f"{QUOTE_CHAR}E")
        assert "151°" in lon_dms

    def test_dd_to_dms_zero_coordinates(self):
        """Test conversion of point at origin (0, 0)."""
        point = MockPoint(0.0, 0.0)
        lat_dms, lon_dms = decimal_degrees_to_dms(point)

        # At 0,0, should be N and E (zero is treated as positive: >= 0)
        assert lat_dms.endswith(f"{QUOTE_CHAR}N")
        assert lon_dms.endswith(f"{QUOTE_CHAR}E")
        assert "0°00'" in lat_dms
        assert "0°00'" in lon_dms

    def test_dd_to_dms_precision(self):
        """Test that seconds are formatted to 5 decimal places."""
        point = MockPoint(-111.5, 40.5)
        lat_dms, lon_dms = decimal_degrees_to_dms(point)

        # Check format includes decimal in seconds
        # Format should be degrees°minutes'seconds.xxxxx"direction
        assert "." in lat_dms
        assert "." in lon_dms


class TestCalculateGridBearing:
    """Tests for grid bearing calculation."""

    def test_calculate_grid_bearing_north(self):
        """Test bearing calculation for due north direction."""
        start = MockPoint(100.0, 100.0)
        end = MockPoint(100.0, 200.0)  # Due north
        distance = 100.0

        bearing = calculate_grid_bearing(start, end, distance)

        # Due north should be N 0° E or similar
        assert bearing.startswith("N")
        assert "0°0'0" in bearing or "N0°0'0" in bearing
        assert " ft" in bearing

    def test_calculate_grid_bearing_east(self):
        """Test bearing calculation for due east direction."""
        start = MockPoint(100.0, 100.0)
        end = MockPoint(200.0, 100.0)  # Due east
        distance = 100.0

        bearing = calculate_grid_bearing(start, end, distance)

        # Due east should be N 90° E or S 90° E
        assert "90°0'0" in bearing
        assert "E " in bearing
        assert " ft" in bearing

    def test_calculate_grid_bearing_northeast_45(self):
        """Test bearing calculation for 45-degree northeast direction."""
        start = MockPoint(0.0, 0.0)
        end = MockPoint(100.0, 100.0)  # 45° NE
        distance = 141.42  # sqrt(100^2 + 100^2)

        bearing = calculate_grid_bearing(start, end, distance)

        # 45° NE should be N 45° E
        assert bearing.startswith("N")
        assert "45°" in bearing
        assert bearing.endswith(" ft")
        assert "E " in bearing.split("°")[1]  # E should appear after degrees

    def test_calculate_grid_bearing_southeast(self):
        """Test bearing calculation for southeast direction."""
        start = MockPoint(100.0, 100.0)
        end = MockPoint(150.0, 50.0)  # Southeast (positive X, negative Y)
        distance = 70.71

        bearing = calculate_grid_bearing(start, end, distance)

        # SE quadrant should have S and E
        assert bearing.startswith("S")
        assert "E " in bearing
        assert " ft" in bearing

    def test_calculate_grid_bearing_southwest(self):
        """Test bearing calculation for southwest direction."""
        start = MockPoint(100.0, 100.0)
        end = MockPoint(50.0, 50.0)  # Southwest
        distance = 70.71

        bearing = calculate_grid_bearing(start, end, distance)

        # SW quadrant should have S and W
        assert bearing.startswith("S")
        assert "W " in bearing
        assert " ft" in bearing

    def test_calculate_grid_bearing_northwest(self):
        """Test bearing calculation for northwest direction."""
        start = MockPoint(100.0, 100.0)
        end = MockPoint(50.0, 150.0)  # Northwest (negative X, positive Y)
        distance = 70.71

        bearing = calculate_grid_bearing(start, end, distance)

        # NW quadrant should have N and W
        assert bearing.startswith("N")
        assert "W " in bearing
        assert " ft" in bearing

    def test_calculate_grid_bearing_distance_conversion(self):
        """Test that distance is properly converted to US Survey Feet."""
        start = MockPoint(0.0, 0.0)
        end = MockPoint(0.0, 100.0)
        distance_meters = 100.0

        bearing = calculate_grid_bearing(start, end, distance_meters)

        # 100 meters = 328.1 feet
        assert "328.1 ft" in bearing

    def test_calculate_grid_bearing_format(self):
        """Test that bearing follows correct DMS format."""
        start = MockPoint(0.0, 0.0)
        end = MockPoint(50.0, 86.6)  # Approximately 60° north
        distance = 100.0

        bearing = calculate_grid_bearing(start, end, distance)

        # Should contain degree, minute, second symbols
        assert "°" in bearing
        assert "'" in bearing
        assert QUOTE_CHAR in bearing or "''" in bearing


class TestFormatTraversal:
    """Tests for PLSS section traversal formatting."""

    def test_format_traversal_salt_lake_meridian(self):
        """Test formatting with Salt Lake Base and Meridian."""
        traversal = {"26-T01S R01W": [1, 2, 3]}

        result = format_traversal(traversal)

        assert "Salt Lake Base and Meridian T01S R01W" in result
        assert result["Salt Lake Base and Meridian T01S R01W"] == [1, 2, 3]

    def test_format_traversal_uintah_meridian(self):
        """Test formatting with Uintah Special Meridian."""
        traversal = {"30-T02N R03E": [10, 11]}

        result = format_traversal(traversal)

        assert "Uintah Special Meridian T02N R03E" in result
        assert result["Uintah Special Meridian T02N R03E"] == [10, 11]

    def test_format_traversal_removes_duplicates(self):
        """Test that duplicate section numbers are removed."""
        traversal = {"26-T01S R01W": [1, 2, 2, 3, 1]}

        result = format_traversal(traversal)

        sections = result["Salt Lake Base and Meridian T01S R01W"]
        assert sections == [1, 2, 3]
        assert len(sections) == 3

    def test_format_traversal_sorts_sections(self):
        """Test that section numbers are sorted."""
        traversal = {"26-T01S R01W": [5, 2, 8, 1, 3]}

        result = format_traversal(traversal)

        sections = result["Salt Lake Base and Meridian T01S R01W"]
        assert sections == [1, 2, 3, 5, 8]

    def test_format_traversal_multiple_townships(self):
        """Test formatting with multiple townships."""
        traversal = {
            "26-T01S R01W": [1, 2],
            "26-T02N R03E": [15, 14],
            "30-T03S R02W": [20, 19, 20],
        }

        result = format_traversal(traversal)

        assert len(result) == 3
        assert result["Salt Lake Base and Meridian T01S R01W"] == [1, 2]
        assert result["Salt Lake Base and Meridian T02N R03E"] == [14, 15]
        assert result["Uintah Special Meridian T03S R02W"] == [19, 20]

    def test_format_traversal_empty_input(self):
        """Test formatting with empty input."""
        traversal = {}

        result = format_traversal(traversal)

        assert result == {}

    def test_format_traversal_single_section(self):
        """Test formatting with single section."""
        traversal = {"26-T01S R01W": [5]}

        result = format_traversal(traversal)

        assert result["Salt Lake Base and Meridian T01S R01W"] == [5]

    def test_format_traversal_unknown_meridian(self):
        """Test formatting with unknown base meridian code."""
        traversal = {"99-T05N R04E": [7, 8, 9]}

        result = format_traversal(traversal)

        assert "Unknown Meridian T05N R04E" in result
        assert result["Unknown Meridian T05N R04E"] == [7, 8, 9]


class TestGetDisclaimer:
    """Tests for disclaimer text."""

    def test_get_disclaimer_returns_string(self):
        """Test that disclaimer returns a string."""
        result = get_disclaimer()
        assert isinstance(result, str)

    def test_get_disclaimer_is_multiline(self):
        """Test that disclaimer is formatted with multiple lines/paragraphs."""
        result = get_disclaimer()

        # Should contain newlines for paragraph breaks
        assert "\n" in result


class TestCSVHasHeader:
    """Tests for CSV header detection."""

    def test_csv_has_header_with_matching_header(self, tmp_path):
        """Test that function returns True when header matches."""
        csv_file = tmp_path / "test.csv"

        # Write CSV with matching header
        with csv_file.open("w", newline=NEWLINE, encoding=ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=FIELD_NAMES)
            writer.writeheader()
            writer.writerow({"id": "1", "starting": "start", "ending": "end", "traversal": "path"})

        result = csv_has_header(csv_file, FIELD_NAMES)
        assert result is True

    def test_csv_has_header_with_non_matching_header(self, tmp_path):
        """Test that function returns False when header doesn't match."""
        csv_file = tmp_path / "test.csv"
        actual_fieldnames = ["name", "value", "type"]

        # Write CSV with different header
        with csv_file.open("w", newline=NEWLINE, encoding=ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=actual_fieldnames)
            writer.writeheader()

        result = csv_has_header(csv_file, FIELD_NAMES)
        assert result is False

    def test_csv_has_header_with_missing_file(self, tmp_path):
        """Test that function returns False when file doesn't exist."""
        csv_file = tmp_path / "nonexistent.csv"

        result = csv_has_header(csv_file, FIELD_NAMES)
        assert result is False

    def test_csv_has_header_with_empty_file(self, tmp_path):
        """Test that function returns False when CSV file is empty."""
        csv_file = tmp_path / "empty.csv"
        csv_file.touch()  # Create empty file

        result = csv_has_header(csv_file, FIELD_NAMES)
        assert result is False

    def test_csv_has_header_with_partial_match(self, tmp_path):
        """Test that function returns False when header partially matches."""
        csv_file = tmp_path / "test.csv"
        actual_fieldnames = ["id", "starting", "ending"]  # Missing one field

        # Write CSV with partial header
        with csv_file.open("w", newline=NEWLINE, encoding=ENCODING) as f:
            writer = csv.DictWriter(f, fieldnames=actual_fieldnames)
            writer.writeheader()

        result = csv_has_header(csv_file, FIELD_NAMES)
        assert result is False

    def test_csv_has_header_with_different_order(self, tmp_path):
        """Test that function returns False when header fields are in different order."""
        csv_file = tmp_path / "test.csv"
        actual_fieldnames = ["starting", "id", "traversal", "ending"]  # Different order

        # Write CSV with reordered header
        with csv_file.open("w", newline=NEWLINE, encoding=ENCODING) as f:
            writer = csv.writer(f)
            writer.writerow(actual_fieldnames)

        result = csv_has_header(csv_file, FIELD_NAMES)
        assert result is False

    def test_csv_has_header_with_extra_fields(self, tmp_path):
        """Test that function returns False when header has extra fields."""
        csv_file = tmp_path / "test.csv"
        actual_fieldnames = ["id", "starting", "ending", "traversal", "extra"]

        # Write CSV with extra field
        with csv_file.open("w", newline=NEWLINE, encoding=ENCODING) as f:
            writer = csv.writer(f)
            writer.writerow(actual_fieldnames)

        result = csv_has_header(csv_file, FIELD_NAMES)
        assert result is False

    def test_csv_has_header_with_single_field(self, tmp_path):
        """Test that function works with single field header."""
        csv_file = tmp_path / "test.csv"
        expected_fieldnames = ["id"]

        # Write CSV with single field
        with csv_file.open("w", newline=NEWLINE, encoding=ENCODING) as f:
            writer = csv.writer(f)
            writer.writerow(expected_fieldnames)

        result = csv_has_header(csv_file, expected_fieldnames)
        assert result is True

    def test_csv_has_header_with_data_as_first_row(self, tmp_path):
        """Test that function returns False when first row is data, not header."""
        csv_file = tmp_path / "test.csv"

        # Write CSV without header (data only)
        with csv_file.open("w", newline=NEWLINE, encoding=ENCODING) as f:
            writer = csv.writer(f)
            writer.writerow(["001", "start_value", "end_value", "path_value"])

        result = csv_has_header(csv_file, FIELD_NAMES)
        assert result is False


class TestConstants:
    """Tests for module-level constants."""

    def test_constants_values(self):
        """Test that constants have the correct values."""
        assert MODE_APPEND == "a"
        assert MODE_WRITE == "w"
        assert ENCODING == "utf-8"
        assert NEWLINE == ""
        assert QUOTE_CHAR == '"'


class TestSaveDescriptionTo:
    """Tests for save_description_to function."""

    def test_save_description_creates_csv_with_header(self, tmp_path):
        """Test that function creates CSV file with proper header."""
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()

        description = cast(
            DescriptionDict,
            {
                "traversal": {"26-T01S R01W": [1, 2]},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": ["N45°30'15\"E 328.1 ft"],
            },
        )

        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))

        # Check CSV was created
        assert csv_file.exists()

        # Check header and data
        with csv_file.open(encoding=ENCODING, newline=NEWLINE) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["id"] == "ROAD_001"
        assert "40°45'30" in rows[0]["starting"]
        assert "Salt Lake Base and Meridian T01S R01W: Sections 1, 2" in rows[0]["traversal"]

    def test_save_description_appends_without_duplicate_header(self, tmp_path):
        """Test that function appends to existing CSV without duplicate header."""
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()

        description = cast(
            DescriptionDict,
            {
                "traversal": {"26-T01S R01W": [1]},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": ["N45°30'15\"E 328.1 ft"],
            },
        )

        # Save twice
        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))
        save_description_to(description, "ROAD_002", str(csv_file), str(bearings_folder))

        # Check that there are 2 data rows and only 1 header
        with csv_file.open(encoding=ENCODING, newline=NEWLINE) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["id"] == "ROAD_001"
        assert rows[1]["id"] == "ROAD_002"

    def test_save_description_formats_traversal_with_pipe_separator(self, tmp_path):
        """Test that multiple townships are separated with pipe character."""
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()

        description = cast(
            DescriptionDict,
            {
                "traversal": {"26-T01S R01W": [1, 2], "30-T02N R03E": [15, 14]},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": ["N45°30'15\"E 328.1 ft"],
            },
        )

        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))

        with csv_file.open(encoding=ENCODING, newline=NEWLINE) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Check traversal contains both townships separated by pipe
        traversal = rows[0]["traversal"]
        assert " | " in traversal
        assert "Salt Lake Base and Meridian T01S R01W: Sections 1, 2" in traversal
        assert "Uintah Special Meridian T02N R03E: Sections 14, 15" in traversal

    def test_save_description_creates_bearings_file(self, tmp_path):
        """Test that bearings file is created with correct content."""
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()

        description = cast(
            DescriptionDict,
            {
                "traversal": {"26-T01S R01W": [1]},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": ["N45°30'15\"E 328.1 ft", "N50°20'10\"E 250.3 ft"],
            },
        )

        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))

        bearings_file = bearings_folder / "ROAD_001_bearings.txt"
        assert bearings_file.exists()

        content = bearings_file.read_text(encoding=ENCODING)
        assert "1. N45°30'15" in content
        assert "2. N50°20'10" in content

    def test_save_description_creates_disclaimer_file(self, tmp_path):
        """Test that disclaimer file is created."""
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()

        description = cast(
            DescriptionDict,
            {
                "traversal": {"26-T01S R01W": [1]},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": ["N45°30'15\"E 328.1 ft"],
            },
        )

        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))

        disclaimer_file = bearings_folder / "disclaimer.txt"
        assert disclaimer_file.exists()

        content = disclaimer_file.read_text(encoding=ENCODING)
        assert "Disclaimer" in content
        assert "UGRC" in content

    def test_save_description_with_empty_bearings(self, tmp_path):
        """Test that function handles empty bearings list."""
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()

        description = cast(
            DescriptionDict,
            {
                "traversal": {"26-T01S R01W": [1]},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": [],
            },
        )

        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))

        # Should still create files
        assert csv_file.exists()
        bearings_file = bearings_folder / "ROAD_001_bearings.txt"
        assert bearings_file.exists()

        # Bearings file should be empty (or just have newlines)
        content = bearings_file.read_text(encoding=ENCODING)
        assert content == "" or content.strip() == ""

    def test_save_description_with_empty_traversal(self, tmp_path):
        """Test that function handles empty traversal dict."""
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()

        description = cast(
            DescriptionDict,
            {
                "traversal": {},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": ["N45°30'15\"E 328.1 ft"],
            },
        )

        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))

        with csv_file.open(encoding=ENCODING, newline=NEWLINE) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Traversal should be empty string
        assert rows[0]["traversal"] == ""

    def test_save_description_sections_sorted_and_formatted(self, tmp_path):
        """Test that section numbers are sorted and comma-separated."""
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()

        description = cast(
            DescriptionDict,
            {
                "traversal": {"26-T01S R01W": [5, 2, 8, 1, 3]},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": [],
            },
        )

        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))

        with csv_file.open(encoding=ENCODING, newline=NEWLINE) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Should be sorted: 1, 2, 3, 5, 8
        assert "Sections 1, 2, 3, 5, 8" in rows[0]["traversal"]


# Run tests with pytest if this file is executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
