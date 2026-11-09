"""
test_main.py
Unit tests for the metes and bounds description logic module.
Tests coordinate conversions, bearing calculations, and formatting functions.
"""

import csv
import sys
from types import SimpleNamespace
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
    describe_plss_corner,
    format_cartesian_corner_tie,
    format_traversal,
    get_nearest_calculated_corner,
    get_section_for_centerline_start,
    meters_to_us_feet,
    process_polyline,
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


class TestCalculatedCornerTie:
    """Tests for finding and describing the corner tie."""

    def test_format_cartesian_corner_tie_uses_north_and_east_offsets(self):
        result = format_cartesian_corner_tie(
            (1000.0, 2000.0),
            MockPoint(1091.44, 2152.4),
            "500640",
            (SimpleNamespace(centroid=MockPoint(2000.0, 2000.0)), "26", "T01S R01W", 12),
        )

        assert result == (
            "Beginning at the West 1/4 corner of Section 12, "
            "Salt Lake Base and Meridian T01S R01W; thence 500 ft north and "
            "300 ft east to the centerline's first vertex."
        )
        assert "583" not in result

    def test_format_cartesian_corner_tie_uses_south_and_west_offsets(self):
        result = format_cartesian_corner_tie(
            (1000.0, 2000.0),
            MockPoint(908.56, 1847.6),
            "540640",
            (SimpleNamespace(centroid=MockPoint(0.0, 0.0)), "30", "T02N R03E", 4),
        )

        assert "500 ft south and 300 ft west" in result
        assert "center 1/4 corner of Section 4" in result

    @pytest.mark.parametrize(
        ("point_label", "point_xy", "expected"),
        [
            ("500600", (0.0, 10.0), "NW corner"),
            ("500600", (10.0, 0.0), "SE corner"),
            ("540600", (0.0, 10.0), "North 1/4 corner"),
            ("540600", (0.0, -10.0), "South 1/4 corner"),
            ("500640", (-10.0, 0.0), "West 1/4 corner"),
            ("500640", (10.0, 0.0), "East 1/4 corner"),
            ("540640", (0.0, 0.0), "center 1/4 corner"),
            ("640", (-10.0, 0.0), "West 1/4 corner"),
        ],
    )
    def test_describe_plss_corner_uses_gcdb_point_id_and_section_centroid(self, point_label, point_xy, expected):
        section_geometry = SimpleNamespace(centroid=MockPoint(0.0, 0.0))

        assert describe_plss_corner(point_xy, point_label, section_geometry) == expected

    def test_describe_plss_corner_rejects_unrecognized_point_id(self):
        section_geometry = SimpleNamespace(centroid=MockPoint(0.0, 0.0))

        with pytest.raises(ValueError, match="six-digit point ID"):
            describe_plss_corner((0.0, 0.0), "invalid", section_geometry)

    @pytest.mark.parametrize(
        ("start", "next_point", "expected_section"),
        [
            (MockPoint(5.0, 5.0), MockPoint(6.0, 5.0), 2),
            (MockPoint(0.0, 5.0), MockPoint(1.0, 5.0), 2),
            (MockPoint(0.0, 5.0), MockPoint(-1.0, 5.0), 1),
            (MockPoint(0.0, 5.0), MockPoint(0.0, 6.0), 1),
        ],
    )
    def test_get_section_for_centerline_start_is_directional_and_deterministic(
        self, monkeypatch, start, next_point, expected_section
    ):
        class FakeSection:
            def __init__(self, min_x, max_x, section_number):
                self.min_x = min_x
                self.max_x = max_x
                self.section_number = section_number
                self.centroid = MockPoint((min_x + max_x) / 2, 0.0)

            def intersects(self, point_geometry):
                point = point_geometry.firstPoint
                return self.min_x <= point.X <= self.max_x and -100 <= point.Y <= 100

            def contains(self, point_geometry):
                point = point_geometry.firstPoint
                return self.min_x < point.X < self.max_x and -100 < point.Y < 100

        west_section = FakeSection(-10.0, 0.0, 1)
        east_section = FakeSection(0.0, 10.0, 2)
        section_rows = [
            (west_section, "26", "T01S R01W", 1),
            (east_section, "26", "T01S R01W", 2),
        ]

        class FakeCursor:
            def __init__(self, _layer, _fields, *, spatial_filter, **_kwargs):
                self.rows = [row for row in reversed(section_rows) if row[0].intersects(spatial_filter)]

            def __enter__(self):
                return iter(self.rows)

            def __exit__(self, *_args):
                return False

        fake_arcpy = SimpleNamespace(
            PointGeometry=lambda point, _sr: SimpleNamespace(firstPoint=point),
            Point=lambda x, y: MockPoint(x, y),
            da=SimpleNamespace(SearchCursor=FakeCursor),
        )
        monkeypatch.setitem(sys.modules, "arcpy", fake_arcpy)
        spatial_reference = SimpleNamespace(XYTolerance=0.001)
        centerline_path = [start, next_point]

        section = get_section_for_centerline_start(
            centerline_path,
            spatial_reference,
            "plss_sections",
            ["basemeridian", "label", "snum"],
        )

        assert section[3] == expected_section

    def test_get_section_for_boundary_following_line_uses_metadata_sort(self, monkeypatch):
        class FakeSection:
            def __init__(self, section_number):
                self.section_number = section_number
                self.centroid = MockPoint(0.0, 0.0)

            def intersects(self, _point_geometry):
                return True

            def contains(self, _point_geometry):
                return False

        section_rows = [
            (FakeSection(10), "26", "T01S R01W", 10),
            (FakeSection(2), "26", "T01S R01W", 2),
        ]

        class FakeCursor:
            def __init__(self, _layer, _fields, **_kwargs):
                self.rows = list(reversed(section_rows))

            def __enter__(self):
                return iter(self.rows)

            def __exit__(self, *_args):
                return False

        monkeypatch.setitem(
            sys.modules,
            "arcpy",
            SimpleNamespace(
                Point=MockPoint,
                PointGeometry=lambda point, _sr: SimpleNamespace(firstPoint=point),
                da=SimpleNamespace(SearchCursor=FakeCursor),
            ),
        )

        section = get_section_for_centerline_start(
            [MockPoint(0.0, 0.0), MockPoint(0.0, 10.0)],
            SimpleNamespace(XYTolerance=0.001),
            "plss_sections",
            ["basemeridian", "label", "snum"],
        )

        assert section[3] == 2

    def test_get_nearest_calculated_corner_filters_candidates(self, monkeypatch):
        calls = []
        existing_items = set()

        class FakeInsertCursor:
            def __init__(self, layer, fields):
                calls.append(("insert_cursor", layer, fields))

            def __enter__(self):
                return self

            def insertRow(self, row):
                calls.append(("insert_row", row))

            def __exit__(self, *_args):
                return False

        class FakeSearchCursor:
            def __init__(self, layer, fields, where_clause=None):
                calls.append(("search_cursor", layer, fields, where_clause))
                self.rows = [(42,)] if layer.startswith("memory/nearest_corner_") else [((3.0, 4.0), "nearest")]

            def __enter__(self):
                return iter(self.rows)

            def __exit__(self, *_args):
                return False

        def create_feature_class(workspace, name, geometry_type, spatial_reference):
            calls.append(("create_feature_class", workspace, name, geometry_type, spatial_reference))
            existing_items.add(f"{workspace}/{name}")

        def make_feature_layer(_points, name, where_clause):
            calls.append(("make_feature_layer", name, where_clause))
            existing_items.add(name)

        def generate_near_table(input_features, near_features, output_table, **kwargs):
            calls.append(("generate_near_table", input_features, near_features, output_table, kwargs))
            existing_items.add(output_table)

        def delete(item):
            calls.append(("delete", item))
            existing_items.remove(item)

        fake_arcpy = SimpleNamespace(
            PointGeometry=lambda point, _sr: point,
            Describe=lambda _layer: SimpleNamespace(OIDFieldName="OBJECTID"),
            Exists=lambda item: item in existing_items,
            management=SimpleNamespace(
                CreateFeatureclass=create_feature_class,
                MakeFeatureLayer=make_feature_layer,
                Delete=delete,
            ),
            analysis=SimpleNamespace(GenerateNearTable=generate_near_table),
            da=SimpleNamespace(InsertCursor=FakeInsertCursor, SearchCursor=FakeSearchCursor),
        )
        monkeypatch.setitem(sys.modules, "arcpy", fake_arcpy)

        spatial_reference = object()
        result = get_nearest_calculated_corner(MockPoint(3.0, 3.0), "plss_points", spatial_reference)

        assert result == ((3.0, 4.0), "nearest")
        candidate_layer, where_clause = next(call[1:3] for call in calls if call[0] == "make_feature_layer")
        assert candidate_layer.startswith("calculated_corner_candidates_")
        assert "pointlab LIKE '%00%00'" in where_clause
        assert "pointlab LIKE '%40%40'" in where_clause
        assert "pointlab LIKE '%00%40'" in where_clause
        assert "pointlab LIKE '%40%00'" in where_clause
        near_call = next(call for call in calls if call[0] == "generate_near_table")
        assert near_call[1].startswith("memory/centerline_start_")
        assert near_call[2] == candidate_layer
        assert near_call[4] == {"closest": "CLOSEST", "method": "PLANAR"}
        assert not existing_items

    def test_get_nearest_calculated_corner_raises_when_no_candidates(self, monkeypatch):
        existing_items = set()

        class FakeInsertCursor:
            def __init__(self, *_args):
                pass

            def __enter__(self):
                return self

            def insertRow(self, _row):
                return

            def __exit__(self, *_args):
                return False

        class FakeSearchCursor:
            def __init__(self, *_args):
                pass

            def __enter__(self):
                return iter([])

            def __exit__(self, *_args):
                return False

        def create_feature_class(workspace, name, *_args, **_kwargs):
            existing_items.add(f"{workspace}/{name}")

        def make_feature_layer(_points, name, _where_clause):
            existing_items.add(name)

        def generate_near_table(_input, _candidates, output_table, **_kwargs):
            existing_items.add(output_table)

        def delete(item):
            existing_items.remove(item)

        fake_arcpy = SimpleNamespace(
            PointGeometry=lambda point, _sr: point,
            Exists=lambda item: item in existing_items,
            management=SimpleNamespace(
                CreateFeatureclass=create_feature_class,
                MakeFeatureLayer=make_feature_layer,
                Delete=delete,
            ),
            analysis=SimpleNamespace(GenerateNearTable=generate_near_table),
            da=SimpleNamespace(InsertCursor=FakeInsertCursor, SearchCursor=FakeSearchCursor),
        )
        monkeypatch.setitem(sys.modules, "arcpy", fake_arcpy)

        with pytest.raises(ValueError, match="No calculated quarter"):
            get_nearest_calculated_corner(MockPoint(0.0, 0.0), "plss_points", object())
        assert not existing_items

    @pytest.mark.parametrize("start_on_boundary", [False, True])
    def test_process_polyline_prepends_corner_tie_and_keeps_centerline_start(self, monkeypatch, start_on_boundary):
        centerline_points = [MockPoint(1091.44, 2152.4), MockPoint(1191.44, 2152.4)]

        class FakeGeometry:
            def __init__(self, point):
                self.firstPoint = point

            def projectAs(self, _spatial_reference):
                return self

            def contains(self, _point):
                return True

        class FakeSection:
            centroid = MockPoint(2000.0, 2000.0)

            def intersects(self, _point):
                return True

            def contains(self, point):
                return not start_on_boundary or point.firstPoint.X > centerline_points[0].X + 0.01

        class FakePolyline:
            spatialReference = SimpleNamespace(XYTolerance=0.001)

            def __iter__(self):
                return iter([centerline_points])

        class FakeSegment:
            def __init__(self, points, _spatial_reference):
                self.firstPoint = points[0]
                self.lastPoint = points[-1]
                self.length = 100.0

        class FakeCursor:
            def __init__(self, layer, fields, **_kwargs):
                if layer == "intersected":
                    self.rows = [("26", "T01S R01W", 12)]
                elif fields == ["SHAPE@XY", "pointlab"]:
                    self.rows = [((1000.0, 2000.0), "500640")]
                elif layer.startswith("memory/nearest_corner_"):
                    self.rows = [(42,)]
                else:
                    self.rows = [(FakeSection(), "26", "T01S R01W", 12)]

            def __enter__(self):
                return iter(self.rows)

            def __exit__(self, *_args):
                return False

        class FakeInsertCursor:
            def __init__(self, *_args):
                pass

            def __enter__(self):
                return self

            def insertRow(self, _row):
                return

            def __exit__(self, *_args):
                return False

        temporary_items = set()

        def create_feature_class(workspace, name, *_args, **_kwargs):
            temporary_items.add(f"{workspace}/{name}")

        def make_feature_layer(_points, name, _where_clause):
            temporary_items.add(name)

        def generate_near_table(_input, _candidates, output_table, **_kwargs):
            temporary_items.add(output_table)

        def delete(item):
            temporary_items.remove(item)

        fake_arcpy = SimpleNamespace(
            Point=MockPoint,
            PointGeometry=lambda point, _spatial_reference: FakeGeometry(point),
            SpatialReference=lambda _wkid: object(),
            Array=list,
            Polyline=FakeSegment,
            analysis=SimpleNamespace(
                Intersect=lambda *_args, **_kwargs: "intersected",
                GenerateNearTable=generate_near_table,
            ),
            management=SimpleNamespace(
                CreateFeatureclass=create_feature_class,
                MakeFeatureLayer=make_feature_layer,
                Delete=delete,
            ),
            Describe=lambda _layer: SimpleNamespace(OIDFieldName="OBJECTID"),
            Exists=lambda item: item in temporary_items,
            da=SimpleNamespace(InsertCursor=FakeInsertCursor, SearchCursor=FakeCursor),
        )
        monkeypatch.setitem(sys.modules, "arcpy", fake_arcpy)

        result = process_polyline(FakePolyline(), "plss_sections", "plss_points", ["basemeridian", "label", "snum"])

        assert result["starting"] == dict(zip(("lat", "lon"), decimal_degrees_to_dms(centerline_points[0])))
        assert result["bearings"][0].startswith("Beginning at the West 1/4 corner of Section 12")
        assert "500 ft north and 300 ft east" in result["bearings"][0]
        assert result["bearings"][1].endswith("328.1 ft")


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

    def test_save_description_keeps_corner_tie_before_centerline_courses(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        bearings_folder = tmp_path / "bearings"
        bearings_folder.mkdir()
        description = cast(
            DescriptionDict,
            {
                "traversal": {"26-T01S R01W": [12]},
                "starting": {"lat": "40°45'30\"N", "lon": "111°52'15\"W"},
                "ending": {"lat": "40°46'00\"N", "lon": "111°53'00\"W"},
                "bearings": [
                    "Beginning at calculated PLSS corner NW1/4 of Section 12; thence 500 ft north and 300 ft east to the centerline's first vertex.",
                    "N45°30'15\"E 328.1 ft",
                ],
            },
        )

        save_description_to(description, "ROAD_001", str(csv_file), str(bearings_folder))

        with csv_file.open(encoding=ENCODING, newline=NEWLINE) as csv_file_handle:
            row = next(csv.DictReader(csv_file_handle))
        lines = (bearings_folder / "ROAD_001_bearings.txt").read_text(encoding=ENCODING).splitlines()

        assert row["starting"] == "Latitude: 40°45'30\"N and Longitude: 111°52'15\"W"
        assert lines[0].startswith("1. Beginning at calculated PLSS corner")
        assert lines[1] == "2. N45°30'15\"E 328.1 ft"

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
