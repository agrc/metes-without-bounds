#!/usr/bin/env python
# * coding: utf8 *
"""
Centerline description logic module.

This module contains the core business logic for processing road centerlines
and generating descriptions. It includes functions for:
- Coordinate projection and conversion
- Decimal degrees to DMS format conversion
- Grid bearing calculations
- Distance conversions
- PLSS section traversal formatting
- Legal disclaimer text

These functions are designed to be unit testable and are imported by the
ArcGIS Python Toolbox (CenterlineTools.pyt) for use in geoprocessing tools.
"""

import csv
import math
from os import linesep
from pathlib import Path

MODE_APPEND = "a"
MODE_WRITE = "w"
ENCODING = "utf-8"
NEWLINE = ""
QUOTE_CHAR = '"'


def project_point(point, source_spatial_reference):
    """Projects a point from one spatial reference system to WGS 84.

    Transforms a point's coordinates from its source spatial reference
    (e.g., UTM NAD83 Zone 12N) to a target spatial reference (e.g., WGS84).
    This is commonly used to convert between projected coordinate systems
    and geographic coordinate systems for latitude/longitude calculations.

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


def decimal_degrees_to_dms(point):
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


def calculate_grid_bearing(start_point, end_point, distance_meters):
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
    seconds = int(round(((minutes_float - minutes) * 60)))

    distance_feet = meters_to_us_feet(distance_meters)

    bearing = f"{y_direction}{degrees}°{minutes}'{seconds}{QUOTE_CHAR}{x_direction} {distance_feet} ft"

    return bearing


def meters_to_us_feet(meters):
    """Convert meters to US Survey Feet using the official conversion factor.

    Uses the conversion factor established by the Mendenhall Order of 1893,
    which defines 1 meter as exactly 3937/1200 US Survey Feet. This is the
    standard conversion used in surveying and legal land descriptions in the
    United States.

    Args:
        meters (float): Distance in meters to convert

    Returns:
        float: Distance in US Survey Feet, rounded to 1 decimal place
    """
    return round(meters * 3937 / 1200, 1)


def format_traversal(traversal_dict):
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

        if base_meridian == "26":
            base_meridian = "Salt Lake Base and Meridian"
        elif base_meridian == "30":
            base_meridian = "Uintah Special Meridian"
        else:
            base_meridian = "Unknown Meridian"

        formatted[f"{base_meridian} {township_range}"] = unique_sections

    return formatted


def get_disclaimer():
    """Returns the legal disclaimer text for road centerline descriptions.

    Provides a comprehensive disclaimer that informs users about the limitations
    and proper use of the generated road centerline descriptions. The disclaimer
    is displayed at the beginning of the tool's output and included in the tool
    description.

    The disclaimer covers:
    - No warranties or certifications provided by UGRC
    - Liability limitations for the State of Utah and County Governments
    - User agreement and acceptance of terms
    - Limitations on legal use (not for litigation or boundary disputes)
    - Recommendation to consult attorneys or licensed surveyors for legal matters

    Returns:
        str: Multi-paragraph disclaimer text formatted for display in ArcGIS
            geoprocessing tool messages and descriptions

    Note:
        This disclaimer is required for all road centerline descriptions to protect
        the state of Utah and contributing agencies from legal liability related to
        the use or misuse of automatically generated centerline descriptions.
    """
    return """Disclaimer

No warranties or certification, express or implied, are provided for any and all road centerline descriptions provided by the Utah Geospatial Resource Center (UGRC). The following road centerline description has been compiled as a best effort service strictly for general purpose informational use and any interpretations made are the responsibility of the User.

The state of Utah and County Governments, their elected officials, officers, employees, and agents assume no legal responsibilities for the information contained herein and shall have no liability for any damages, losses, costs, or expenses, including, but not limited to attorney's fees, arising from the use or misuses of the information provided herein. The User's use thereof shall constitute an agreement by the User to release The State of Utah and County Government, its elected officials, officers, employees, and agents from such liability.

By using the information contained herein, the User is stating that the above Disclaimer has been read and that he/she has full understanding and is in agreement with the contents of this disclaimer. The road centerline information in this document was calculated and formatted using digital tools. The descriptions are NOT intended to be used for legal litigation, boundary disputes, or construction planning. These descriptions are for general reference or informational use only. Users interested in pursuing legal litigation and/or boundary disputes should consult an attorney or licensed surveyor, or both.
"""


def get_selected_polyline(feature_layer, unique_id):
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


def get_plss_traversal(polyline, plss_sections, plss_schema):
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

    # Intersect polyline with PLSS sections to determine traversal
    intersected = arcpy.analysis.Intersect(
        [plss_sections, polyline],
        "memory/sections",
        join_attributes="NO_FID",
    )

    with arcpy.da.SearchCursor(intersected, plss_schema) as intersect_cursor:
        for base_meridian, label, section in intersect_cursor:
            traversal.setdefault(f"{base_meridian}-{label}", []).append(section)

    return traversal


def process_polyline(polyline, plss_sections, plss_schema):
    """Processes a polyline to generate metes and bounds description data.

    Analyzes a polyline geometry and generates comprehensive metes and bounds
    description information including PLSS section traversals, start/end coordinates
    in DMS format, and bearing/distance data for each segment. Coordinates are
    automatically projected to WGS84 for DMS output.

    Args:
        polyline: The polyline geometry to process (arcpy.Polyline)
        plss_sections: The PLSS sections feature layer or path to intersect with
        plss_schema (list): List of field names from PLSS sections ["basemeridian", "label", "snum"]

    Returns:
        dict: Dictionary containing:
            - "traversal": Dict mapping PLSS township keys to section number lists
            - "starting": Dict with "lat" and "lon" in DMS format (WGS84)
            - "ending": Dict with "lat" and "lon" in DMS format (WGS84)
            - "bearings": List of bearing strings with distances

    Example:
        >>> result = process_polyline(polyline, sections_layer, ["basemeridian", "label", "snum"])
        >>> print(result["starting"]["lat"])  # "40°45'30.12345"N"
        >>> print(result["bearings"][0])  # "N45°30'15"E 328.1 ft"
    """
    import arcpy

    result = {"traversal": {}, "starting": "", "ending": "", "bearings": []}

    result["traversal"] = get_plss_traversal(polyline, plss_sections, plss_schema)

    for path in polyline:
        last_point = None
        for index, point in enumerate(path):
            projected_point = project_point(point, polyline.spatialReference)
            lat_dms, lon_dms = decimal_degrees_to_dms(projected_point)

            if index == 0:
                result["starting"] = {"lat": lat_dms, "lon": lon_dms}
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


def csv_has_header(csv_path, expected_fieldnames):
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


def save_description_to(description, unique_id, survey123, bearings):
    """Saves centerline description data to CSV and bearing files.

    Appends description data to a Survey123 CSV file and writes bearing
    information to a separate text file. The CSV contains summary information
    while detailed bearing data is stored in individual text files.

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
    fieldnames = ["id", "starting", "ending", "traversal"]

    # Check for header before opening file
    needs_header = not csv_has_header(csv_path, fieldnames)

    with csv_path.open(MODE_APPEND, newline=NEWLINE, encoding=ENCODING) as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

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
        lines = (f"{i}. {bearing}{linesep}" for i, bearing in enumerate(description["bearings"], 1))
        f.writelines(lines)

    disclaimer = bearings_folder / "disclaimer.txt"
    with disclaimer.open(MODE_WRITE, encoding=ENCODING) as f:
        f.write(get_disclaimer())
