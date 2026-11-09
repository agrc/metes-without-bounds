"""
Centerline description logic module.

This module contains the core business logic for processing road centerlines
and generating descriptions. It includes functions for:
- Coordinate projection and conversion
- Decimal degrees to DMS format conversion
- Grid bearing calculations
- Distance conversions
- PLSS section traversal formatting
- Writing the results to files

These functions are designed to be unit testable and are imported by the
ArcGIS Python Toolbox (CenterlineTools.pyt) for use in geoprocessing tools.
"""

import csv
import math
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

# Type aliases for arcpy types (arcpy doesn't provide type stubs)
# Using Any here is intentional - these are duck-typed arcpy objects
ArcPyPoint = Any  # arcpy.Point with X, Y attributes
ArcPySpatialReference = Any  # arcpy.SpatialReference
ArcPyPolyline = Any  # arcpy.Polyline geometry
ArcPyFeatureLayer = Any  # arcpy feature layer or path


class CoordinateDict(TypedDict):
    """Dictionary containing lat/lon coordinates in DMS format."""

    lat: str
    lon: str


class DescriptionDict(TypedDict):
    """Dictionary containing centerline description data."""

    traversal: dict[str, list[int]]
    starting: CoordinateDict
    ending: CoordinateDict
    bearings: list[str]


MODE_APPEND = "a"
MODE_WRITE = "w"
ENCODING = "utf-8"
NEWLINE = ""
QUOTE_CHAR = '"'
FIELD_NAMES = ["id", "starting", "ending", "traversal"]
CORNER_WHERE_CLAUSE = (
    "pointlab LIKE '%00%00' OR pointlab LIKE '%40%40' OR pointlab LIKE '%00%40' OR pointlab LIKE '%40%00'"
)


def project_point(point: ArcPyPoint, source_spatial_reference: ArcPySpatialReference) -> ArcPyPoint:
    """Projects a point from one spatial reference system to WGS 84.

    Transforms a point's coordinates from its source spatial reference
    (e.g., UTM NAD83 Zone 12N) to a target spatial reference (e.g., WGS84).

    Args:
        point: The point to project with X and Y coordinates (arcpy.Point)
        source_spatial_reference: The spatial reference of the input point

    Returns:
        The projected point with coordinates in the target spatial reference
    """
    import arcpy

    target_spatial_reference = arcpy.SpatialReference(4326)  #: WGS 1984

    point_geometry = arcpy.PointGeometry(point, source_spatial_reference)
    projected_point = point_geometry.projectAs(target_spatial_reference)

    return projected_point.firstPoint


def decimal_degrees_to_dms(point: ArcPyPoint) -> tuple[str, str]:
    """Converts decimal degrees to degrees, minutes, and seconds (DMS) format.

    Transforms geographic coordinates from decimal degrees (DD) to the traditional
    DMS notation with cardinal directions. The output includes degrees (°), minutes ('),
    and seconds (") with directional indicators (N/S for latitude, E/W for longitude).
    Seconds are formatted to 5 decimal places for high precision.

    Args:
        point: A point with X (longitude) and Y (latitude) coordinates in decimal degrees

    Returns:
        tuple[str, str]: A tuple of (latitude_dms, longitude_dms) where:
            - latitude_dms: Formatted string like "40°45'30.12345"N"
            - longitude_dms: Formatted string like "111°52'15.67890"W"

    Example:
        >>> point = type('Point', (), {'X': -111.8710, 'Y': 40.7588})()
        >>> lat, lon = dd_to_dms(point)
        >>> print(lat)  # "40°45'31.68000"N"
        >>> print(lon)  # "111°52'15.60000"W"
    """
    latitude = abs(point.Y)
    longitude = abs(point.X)

    # Convert latitude
    positive_latitude = point.Y >= 0
    lat_minutes, lat_seconds = divmod(latitude * 3600, 60)
    lat_degrees, lat_minutes = divmod(lat_minutes, 60)
    lat_degrees = int(lat_degrees)
    lat_minutes = int(lat_minutes)
    lat_direction = "N" if positive_latitude else "S"
    lat_dms = f"{lat_degrees}°{lat_minutes:02d}'{lat_seconds:02.5f}{QUOTE_CHAR}{lat_direction}"

    # Convert longitude
    positive_longitude = point.X >= 0
    lon_minutes, lon_seconds = divmod(longitude * 3600, 60)
    lon_degrees, lon_minutes = divmod(lon_minutes, 60)
    lon_degrees = int(lon_degrees)
    lon_minutes = int(lon_minutes)
    lon_direction = "E" if positive_longitude else "W"
    lon_dms = f"{lon_degrees}°{lon_minutes:02d}'{lon_seconds:02.5f}{QUOTE_CHAR}{lon_direction}"

    return lat_dms, lon_dms


def calculate_grid_bearing(start_point: ArcPyPoint, end_point: ArcPyPoint, distance_meters: float) -> str:
    """Calculates grid bearing between two points in a projected coordinate system.

    Computes the bearing using Cartesian mathematics on projected coordinates
    (e.g., UTM NAD83 Zone 12N), expressing the result as a quadrant bearing
    with cardinal directions (N/S and E/W). The bearing represents the acute
    angle from either North or South toward East or West.

    The method:
    1. Calculates azimuth (0-360° clockwise from North) using atan2
    2. Converts azimuth to quadrant bearing (acute angle from N/S)
    3. Formats as DMS (degrees, minutes, seconds) with cardinal directions
    4. Converts distance from meters to US Survey Feet

    Args:
        start_point: Starting point with X and Y in projected coordinates (e.g., UTM meters)
        end_point: Ending point with X and Y in projected coordinates (e.g., UTM meters)
        distance_meters (float): Distance between points in meters

    Returns:
        str: Bearing formatted as quadrant bearing with distance in US Survey Feet.
            Format: "{N|S}{degrees}°{minutes}'{seconds}"{E|W} {distance} ft"
            Example: "N45°30'15"E 328.1 ft"

    Example:
        >>> start = type('Point', (), {'X': 424500.0, 'Y': 4515000.0})()
        >>> end = type('Point', (), {'X': 424600.0, 'Y': 4515100.0})()
        >>> bearing = calculate_grid_bearing(start, end, 141.42)
        >>> print(bearing)  # "N45°0'0"E 464.4 ft"
    """
    delta_x = end_point.X - start_point.X
    delta_y = end_point.Y - start_point.Y

    # Calculate azimuth (0-360° from North clockwise) using atan2
    # atan2(x, y) gives angle from north (0°) going clockwise
    azimuth_rad = math.atan2(delta_x, delta_y)
    azimuth = math.degrees(azimuth_rad)
    azimuth = (azimuth + 360) % 360  # Normalize to 0-360

    # Convert azimuth to bearing (acute angle from N/S)
    if 0 <= azimuth < 90:
        # NE quadrant
        angle = azimuth
        y_direction = "N"
        x_direction = "E"
    elif 90 <= azimuth < 180:
        # SE quadrant
        angle = 180 - azimuth
        y_direction = "S"
        x_direction = "E"
    elif 180 <= azimuth < 270:
        # SW quadrant
        angle = azimuth - 180
        y_direction = "S"
        x_direction = "W"
    else:  # 270 <= azimuth < 360
        # NW quadrant
        angle = 360 - azimuth
        y_direction = "N"
        x_direction = "W"

    # Convert angle to DMS
    degrees = int(angle)
    minutes_float = (angle - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60)

    distance_feet = meters_to_us_feet(distance_meters)

    bearing = f"{y_direction}{degrees}°{minutes}'{seconds}{QUOTE_CHAR}{x_direction} {distance_feet} ft"

    return bearing


def meters_to_us_feet(meters: float) -> float:
    """Convert meters to US Survey Feet using the official conversion factor.

    Uses the conversion factor established by the Mendenhall Order of 1893,
    which defines 1 meter as exactly 3937/1200 US Survey Feet. This is the
    standard conversion used in surveying in the United States.

    Args:
        meters (float): Distance in meters to convert

    Returns:
        float: Distance in US Survey Feet, rounded to 1 decimal place
    """
    return round(meters * 3937 / 1200, 1)


def format_traversal(traversal_dict: dict[str, list[int]]) -> dict[str, list[int]]:
    """Formats PLSS section traversal data into human-readable form.

    Processes the raw traversal dictionary to create a formatted output that:
    - Removes duplicate section numbers
    - Sorts section numbers in ascending order
    - Expands base meridian codes to full names
    - Combines base meridian with township/range designations

    Args:
        traversal_dict (dict): Dictionary mapping "{meridian_code}-{township_range}"
            keys to lists of section numbers. For example:
            {"26-T01S R01W": [1, 2, 1], "27-T02N R03E": [15, 14]}

    Returns:
        dict: Formatted dictionary with expanded meridian names as keys and sorted,
            unique section numbers as values. For example:
            {"Salt Lake Base and Meridian T01S R01W": [1, 2],
             "Uintah Special Meridian T02N R03E": [14, 15]}

    Note:
        - Base meridian code "26" maps to "Salt Lake Base and Meridian"
        - Base meridian code "30" maps to "Uintah Special Meridian"
        - All other codes default to "Unknown Meridian"
    """
    formatted = {}
    for key, sections in traversal_dict.items():
        unique_sections = sorted(set(sections))
        base_meridian, township_range = key.split("-")
        formatted[f"{_format_base_meridian(base_meridian)} {township_range}"] = unique_sections

    return formatted


def _format_base_meridian(base_meridian: str) -> str:
    if base_meridian == "26":
        return "Salt Lake Base and Meridian"
    if base_meridian == "30":
        return "Uintah Special Meridian"
    return "Unknown Meridian"


def get_selected_polyline(feature_layer: ArcPyFeatureLayer, unique_id: str) -> tuple[ArcPyPolyline, str] | None:
    """Retrieves the first selected polyline and unique id from a feature layer.

    Args:
        feature_layer: The feature layer to read from (arcpy layer or path)
        unique_id (str): The field name of the unique identifier for the feature

    Returns:
        tuple: (polyline, id) if a feature is found, or None if no features found
    """
    import arcpy

    with arcpy.da.SearchCursor(feature_layer, ["SHAPE@", unique_id]) as search_cursor:
        return next(search_cursor, None)


def get_plss_traversal(
    polyline: ArcPyPolyline, plss_sections: ArcPyFeatureLayer, plss_schema: list[str]
) -> dict[str, list[int]]:
    """Intersects a polyline with PLSS sections to determine traversal.

    Performs a spatial intersection between a polyline and PLSS sections layer
    to identify which sections the polyline passes through. Returns a dictionary
    mapping township/range designations to the section numbers traversed.

    Args:
        polyline: The polyline geometry to intersect (arcpy.Polyline)
        plss_sections: The PLSS sections feature layer or path to intersect with
        plss_schema (list): List of field names to read ["basemeridian", "label", "snum"]

    Returns:
        dict: Dictionary mapping "{meridian_code}-{township_range}" keys to lists
            of section numbers. For example:
            {"26-T01S R01W": [1, 2, 3], "27-T02N R03E": [15, 14]}

    Example:
        >>> traversal = get_plss_traversal(polyline, sections_layer, ["basemeridian", "label", "snum"])
        >>> print(traversal)  # {"26-T01S R01W": [1, 2, 1]}
    """
    import arcpy

    traversal = {}

    intersected = arcpy.analysis.Intersect(
        [plss_sections, polyline],
        "memory/sections",
        join_attributes="NO_FID",
    )

    with arcpy.da.SearchCursor(intersected, plss_schema) as intersect_cursor:
        for base_meridian, label, section in intersect_cursor:
            traversal.setdefault(f"{base_meridian}-{label}", []).append(section)

    return traversal


def get_nearest_calculated_corner(
    point: ArcPyPoint,
    plss_points: ArcPyFeatureLayer,
    spatial_reference: ArcPySpatialReference,
) -> tuple[tuple[float, float], str]:
    """Finds the nearest eligible calculated PLSS corner using ArcGIS proximity tools."""
    import arcpy

    unique_id = uuid4().hex
    start_name = f"centerline_start_{unique_id}"
    start_feature = f"memory/{start_name}"
    near_table = f"memory/nearest_corner_{unique_id}"
    candidate_layer = f"calculated_corner_candidates_{unique_id}"
    temporary_data = []
    temporary_layers = []

    try:
        temporary_data.append(start_feature)
        arcpy.management.CreateFeatureclass("memory", start_name, "POINT", spatial_reference=spatial_reference)

        with arcpy.da.InsertCursor(start_feature, ["SHAPE@"]) as cursor:
            cursor.insertRow([arcpy.PointGeometry(point, spatial_reference)])

        arcpy.management.MakeFeatureLayer(plss_points, candidate_layer, CORNER_WHERE_CLAUSE)
        temporary_layers.append(candidate_layer)

        temporary_data.append(near_table)
        arcpy.analysis.GenerateNearTable(
            start_feature,
            candidate_layer,
            near_table,
            closest="CLOSEST",
            method="PLANAR",
        )

        with arcpy.da.SearchCursor(near_table, ["NEAR_FID"]) as cursor:
            nearest_row = next(cursor, None)

        if nearest_row is None or nearest_row[0] == -1:
            raise ValueError("No calculated quarter or quarter-quarter corners were found in the PLSS points layer.")

        oid_field = arcpy.Describe(plss_points).OIDFieldName
        where_clause = f"{oid_field} = {nearest_row[0]}"
        with arcpy.da.SearchCursor(plss_points, ["SHAPE@XY", "pointlab"], where_clause=where_clause) as cursor:
            nearest_corner = next(cursor, None)

        if nearest_corner is None:
            raise ValueError("The nearest calculated corner could not be read from the PLSS points layer.")

        return nearest_corner
    finally:
        for temporary_item in reversed(temporary_layers + temporary_data):
            if arcpy.Exists(temporary_item):
                arcpy.management.Delete(temporary_item)


def get_section_at_point(
    point_geometry: ArcPyPoint, plss_sections: ArcPyFeatureLayer, plss_schema: list[str]
) -> tuple[ArcPyPoint, str, str, int]:
    """Gets the section containing the centerline's first vertex."""
    import arcpy

    with arcpy.da.SearchCursor(
        plss_sections,
        ["SHAPE@", *plss_schema],
        spatial_filter=point_geometry,
        spatial_relationship="INTERSECTS",
    ) as cursor:
        for geometry, base_meridian, label, section in cursor:
            if geometry.contains(point_geometry):
                return geometry, base_meridian, label, section

    raise ValueError("The centerline's first vertex is not inside a PLSS section polygon.")


def describe_plss_corner(point_xy: tuple[float, float], point_label: str, section_geometry: ArcPyPoint) -> str:
    """Describes a GCDB point ID as a corner relative to a PLSS section.

    The point ID's first and last three digits encode its X and Y positions.
    Their trailing 00/40 markers distinguish section corners, quarter corners,
    and the section center.
    """
    point_label = str(point_label).strip()
    if point_label.isdigit() and len(point_label) < 6:
        point_label = point_label.zfill(6)
    if len(point_label) != 6 or not point_label.isdigit():
        raise ValueError(f"Unable to interpret GCDB point label {point_label!r} as a six-digit point ID.")

    x_position = point_label[1:3]
    y_position = point_label[4:6]
    centroid = section_geometry.centroid
    east = point_xy[0] > centroid.X
    north = point_xy[1] > centroid.Y

    if x_position == "00" and y_position == "00":
        return f"{'N' if north else 'S'}{'E' if east else 'W'} corner"
    if x_position == "40" and y_position == "00":
        return f"{'North' if north else 'South'} 1/4 corner"
    if x_position == "00" and y_position == "40":
        return f"{'East' if east else 'West'} 1/4 corner"
    if x_position == "40" and y_position == "40":
        return "center 1/4 corner"

    raise ValueError(f"GCDB point label {point_label!r} does not identify a standard PLSS corner.")


def format_cartesian_corner_tie(
    corner_xy: tuple[float, float],
    centerline_start: ArcPyPoint,
    point_label: str,
    section: tuple[ArcPyPoint, str, str, int],
) -> str:
    """Formats north/south and east/west offsets from a calculated corner."""
    section_geometry, base_meridian, township_range, section_number = section
    formatted_township = next(iter(format_traversal({f"{base_meridian}-{township_range}": [section_number]})))
    corner_name = describe_plss_corner(corner_xy, point_label, section_geometry)
    tie = f"Beginning at the {corner_name} of Section {section_number}, {formatted_township}; thence "

    delta_x = centerline_start.X - corner_xy[0]
    delta_y = centerline_start.Y - corner_xy[1]
    offsets = []

    if delta_y:
        direction = "north" if delta_y > 0 else "south"
        distance = meters_to_us_feet(abs(delta_y))
        offsets.append(f"{distance:g} ft {direction}")

    if delta_x:
        direction = "east" if delta_x > 0 else "west"
        distance = meters_to_us_feet(abs(delta_x))
        offsets.append(f"{distance:g} ft {direction}")

    if not offsets:
        return f"{tie}the centerline begins at this corner."

    return f"{tie}{' and '.join(offsets)} to the centerline's first vertex."


def process_polyline(
    polyline: ArcPyPolyline,
    plss_sections: ArcPyFeatureLayer,
    plss_points: ArcPyFeatureLayer,
    plss_schema: list[str],
) -> DescriptionDict:
    """Processes a polyline to generate centerline description data.

    Analyzes a polyline geometry and generates comprehensive centerline
    description information including PLSS section traversals, the nearest
    calculated corner tie, start/end coordinates in DMS format, and
    bearing/distance data for each centerline segment. Coordinates are
    automatically projected to WGS84 for DMS output.

    Args:
        polyline: The polyline geometry to process (arcpy.Polyline)
        plss_sections: The PLSS sections feature layer or path to intersect with
        plss_points: The calculated PLSS corner point layer
        plss_schema (list): List of field names from PLSS sections ["basemeridian", "label", "snum"]

    Returns:
        dict: Dictionary containing:
            - "traversal": Dict mapping PLSS township keys to section number lists
            - "starting": Centerline's first vertex coordinates in DMS format (WGS84)
            - "ending": Dict with "lat" and "lon" in DMS format (WGS84)
            - "bearings": Corner tie followed by centerline bearing strings with distances

    Example:
        >>> result = process_polyline(polyline, sections_layer, points_layer, ["basemeridian", "label", "snum"])
        >>> print(result["starting"]["lat"])  # "40°45'30.12345"N"
        >>> print(result["bearings"][0])  # Beginning-at-corner tie description
    """
    import arcpy

    result: DescriptionDict = {
        "traversal": {},
        "starting": {"lat": "", "lon": ""},
        "ending": {"lat": "", "lon": ""},
        "bearings": [],
    }

    result["traversal"] = get_plss_traversal(polyline, plss_sections, plss_schema)

    first_path = next((path for path in polyline if len(path)), None)
    if first_path is None:
        raise ValueError("The selected centerline has no vertices.")

    first_point = first_path[0]
    nearest_corner, point_label = get_nearest_calculated_corner(
        first_point,
        plss_points,
        polyline.spatialReference,
    )
    start_point_geometry = arcpy.PointGeometry(first_point, polyline.spatialReference)
    try:
        start_section = get_section_at_point(start_point_geometry, plss_sections, plss_schema)
    except ValueError:
        if len(first_path) < 2:
            raise

        next_point = first_path[1]
        delta_x = next_point.X - first_point.X
        delta_y = next_point.Y - first_point.Y
        segment_length = math.hypot(delta_x, delta_y)
        if not segment_length:
            raise

        probe_distance = min(0.1, segment_length / 2)
        probe_point = arcpy.Point(
            first_point.X + delta_x / segment_length * probe_distance,
            first_point.Y + delta_y / segment_length * probe_distance,
        )
        probe_geometry = arcpy.PointGeometry(probe_point, polyline.spatialReference)
        start_section = get_section_at_point(probe_geometry, plss_sections, plss_schema)

    projected_start = project_point(first_point, polyline.spatialReference)
    start_lat, start_lon = decimal_degrees_to_dms(projected_start)
    result["starting"] = {"lat": start_lat, "lon": start_lon}
    result["bearings"].append(format_cartesian_corner_tie(nearest_corner, first_point, point_label, start_section))

    for path in polyline:
        last_point = None
        for index, point in enumerate(path):
            projected_point = project_point(point, polyline.spatialReference)
            lat_dms, lon_dms = decimal_degrees_to_dms(projected_point)

            if index == 0:
                last_point = point
                continue
            elif index == len(path) - 1:
                result["ending"] = {"lat": lat_dms, "lon": lon_dms}

            if index > 0:
                segment = arcpy.Polyline(
                    arcpy.Array([last_point, point]),
                    polyline.spatialReference,
                )

                grid_bearing = calculate_grid_bearing(segment.firstPoint, segment.lastPoint, segment.length)
                result["bearings"].append(grid_bearing)

                last_point = point

    return result


def csv_has_header(csv_path: Path, expected_fieldnames: list[str]) -> bool:
    """Checks if a CSV file has the expected header row.

    Reads the first line of a CSV file and compares it with the expected
    field names to determine if the header is present.

    Args:
        csv_path (Path): Path object to the CSV file
        expected_fieldnames (list): List of expected field names

    Returns:
        bool: True if the header is present and matches, False otherwise
    """
    try:
        with csv_path.open(encoding=ENCODING, newline=NEWLINE) as rf:
            first_row = next(csv.reader(rf))
            return first_row == expected_fieldnames
    except (StopIteration, FileNotFoundError):
        return False


def save_description_to(description: DescriptionDict, unique_id: str, survey123: str, bearings: str) -> None:
    """Saves centerline description data to CSV and a bearing file.

    Appends description data to a file ready to be imported to Survey123 CSV and writes bearing
    information to a separate text file. The CSV contains summary information
    while detailed bearing data is stored in a text file.

    Args:
        description (dict): Description dictionary containing:
            - 'traversal': Dict mapping meridian/township keys to section lists
            - 'starting': Dict with 'lat' and 'lon' in DMS format
            - 'ending': Dict with 'lat' and 'lon' in DMS format
            - 'bearings': List of bearing strings
        unique_id (str): Unique identifier for this centerline feature
        survey123 (str): Path to the CSV file to append data to
        bearings (str): Path to the folder where bearing text files are written

    Returns:
        None

    Raises:
        Exception: If file operations fail (CSV write or bearing file write)

    Example:
        >>> desc = {
        ...     'traversal': {'26-T01S R01W': [1, 2]},
        ...     'starting': {'lat': '40°45\'30"N', 'lon': '111°52\'15"W'},
        ...     'ending': {'lat': '40°46\'00"N', 'lon': '111°53\'00"W'},
        ...     'bearings': ['N45°30\'15"E 328.1 ft', 'N50°20\'10"E 250.3 ft']
        ... }
        >>> save_description_to(desc, 'ROAD_001', '/path/to/output.csv', '/path/to/bearings')
        # Creates CSV row with traversal: "Salt Lake Base and Meridian T01S R01W: Sections 1, 2"
    """
    starting_text = f"Latitude: {description['starting']['lat']} and Longitude: {description['starting']['lon']}"
    ending_text = f"Latitude: {description['ending']['lat']} and Longitude: {description['ending']['lon']}"

    formatted_traversal = format_traversal(description["traversal"])
    traversal_lines = []

    for meridian_township, sections in formatted_traversal.items():
        sections_text = ", ".join(str(s) for s in sections)
        traversal_lines.append(f"{meridian_township}: Sections {sections_text}")

    traversal = " | ".join(traversal_lines)

    csv_path = Path(survey123)

    needs_header = not csv_has_header(csv_path, FIELD_NAMES)

    with csv_path.open(MODE_APPEND, newline=NEWLINE, encoding=ENCODING) as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELD_NAMES)

        if needs_header:
            writer.writeheader()

        writer.writerow(
            {
                "id": unique_id,
                "starting": starting_text,
                "ending": ending_text,
                "traversal": traversal,
            }
        )

    bearings_folder = Path(bearings)
    bearings_file = bearings_folder / f"{unique_id}_bearings.txt"

    with bearings_file.open(MODE_WRITE, encoding=ENCODING) as f:
        lines = (f"{i}. {bearing}\n" for i, bearing in enumerate(description["bearings"], 1))
        f.writelines(lines)
