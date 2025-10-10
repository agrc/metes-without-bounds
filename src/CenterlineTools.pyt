# -*- coding: utf-8 -*-

import math

import arcpy


class Toolbox:
    def __init__(self):
        """Initializes the CenterlineTools Python Toolbox for ArcGIS.

        Defines the toolbox properties and registers the tools contained within it.
        This toolbox provides geospatial tools for generating metes and bounds
        descriptions of road centerlines, including PLSS section traversals,
        coordinate conversions, and bearing calculations.

        The toolbox name displayed in ArcGIS is derived from the .pyt filename.
        Tools are automatically discovered and made available in ArcGIS Pro
        when the toolbox is added.
        """
        self.label = "CenterlineTools"
        self.alias = "centerlinetools"

        self.tools = [CenterlineDescribe]


class CenterlineDescribe:
    def __init__(self):
        """Initializes the Centerline Describe geoprocessing tool.

        Sets up the tool's properties, configuration, and constants used throughout
        the tool's execution. This includes the tool label, description, spatial
        reference systems, PLSS schema, and ArcGIS environment settings.

        The tool generates metes and bounds descriptions for road centerlines by:
        - Calculating PLSS section traversals
        - Converting coordinates to DMS format
        - Computing grid bearings and distances in US Survey Feet
        """
        self.label = "Centerline Describe"
        self.description = self._get_disclaimer() + "\nAn ArcGIS geoprocessing tool for describing a polyline feature."
        self.canRunInBackground = False
        self.required_wkid = 26912  #: UTM NAD83 Zone 12 North
        self.target_sr = arcpy.SpatialReference(4326)  #: WGS 1984
        self.plss_schema = ["basemeridian", "label", "snum"]
        self.quote_char = '"'

        arcpy.env.overwriteOutput = True
        arcpy.env.overwriteOutputOptions = "Truncate"

    def isLicensed(self):
        """Determines if the tool is licensed to execute.

        This method is called by ArcGIS to check whether the tool has the necessary
        licenses or extensions to run. It allows tools to perform custom license
        checks for ArcGIS extensions (e.g., Spatial Analyst, 3D Analyst) or other
        software dependencies.

        This tool does not require any special licenses beyond a basic ArcGIS
        installation, so it always returns True.

        Returns:
            bool: True if the tool is licensed and can execute, False otherwise
        """
        return True

    def getParameterInfo(self):
        """Defines the input parameters for the geoprocessing tool.

        Creates and configures the parameter objects that appear in the tool's
        dialog box in ArcGIS. This tool requires two input parameters:

        1. Input Feature Layer: A polyline layer representing the road centerline
           - Must have exactly one feature selected
           - Must use UTM NAD83 Zone 12 North projection (EPSG:26912)

        2. PLSS Section Reference Layer: A polygon layer containing the SGID PLSS section data
           - Must contain fields: basemeridian, label, snum
           - Must use UTM NAD83 Zone 12 North projection (EPSG:26912)

        Returns:
            list[arcpy.Parameter]: A list of two Parameter objects:
                - parameters[0]: Input polyline feature layer
                - parameters[1]: PLSS section polygon reference layer

        Note:
            Parameters are validated in the updateMessages() method to ensure
            proper spatial reference and schema requirements are met.
        """
        input_data = arcpy.Parameter(
            displayName="Input Feature Layer",
            name="in_features",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )

        input_data.filter.list = ["Polyline"]  # pyright: ignore[reportOptionalMemberAccess]

        plss_sections = arcpy.Parameter(
            displayName="PLSS Section Reference Layer",
            name="in_plss",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )

        plss_sections.filter.list = ["Polygon"]  # pyright: ignore[reportOptionalMemberAccess]

        return [input_data, plss_sections]

    def updateParameters(self, parameters):
        """Updates parameter values and properties dynamically based on user input.

        This method is called by ArcGIS whenever a parameter value changes in the
        tool dialog. It allows for dynamic parameter behavior such as:
        - Setting default values based on other parameters
        - Modifying parameter properties (enabled/disabled, visible/hidden)
        - Updating filter lists or value lists
        - Calculating derived parameter values

        Currently, this tool does not require any dynamic parameter updates,
        so the method simply returns without modification.

        Args:
            parameters (list[arcpy.Parameter]): List of tool parameters that can
                be inspected and modified. Changes are reflected in the tool dialog.

        Returns:
            None

        Note:
            This method is called before updateMessages() in the parameter
            validation lifecycle.
        """

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        self._validate_centerline(parameters[0])
        self._validate_plss(parameters[1])

        return

    def execute(self, parameters, messages):
        """Process polyline to generate metes descriptions.

        Reads polyline geometry, intersects them with section
        reference data, and calculates:
        - Section traversals (which PLSS sections are crossed)
        - Starting and ending coordinates in DMS format
        - Grid bearing and distance for each segment in us survey feet
        """
        with arcpy.da.SearchCursor(
            parameters[0].value,
            ["SHAPE@"],
        ) as search_cursor:
            for (polyline,) in search_cursor:
                result = {"traversal": {}, "starting": "", "ending": "", "bearings": []}
                intersected = arcpy.analysis.Intersect(
                    [parameters[1].value, polyline],
                    "memory/sections",
                    join_attributes="NO_FID",
                )

                with arcpy.da.SearchCursor(intersected, self.plss_schema) as intersect_cursor:
                    for base_meridian, label, section in intersect_cursor:
                        result["traversal"].setdefault(f"{base_meridian}-{label}", []).append(section)

                for path in polyline:
                    last_point = None
                    for index, point in enumerate(path):
                        projected_point = self._project_point(point, polyline.spatialReference, self.target_sr)
                        lat_dms, lon_dms = self._dd_to_dms(projected_point)

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
                            grid_bearing = self._calculate_grid_bearing(
                                segment.firstPoint, segment.lastPoint, segment.length
                            )

                            last_point = point

                            result["bearings"].append(grid_bearing)

                messages.addMessage(self._get_disclaimer())
                traversal = self._format_traversal(result["traversal"])
                messages.addMessage("\nTraversal:")
                for key, sections in traversal.items():
                    term = "Sections" if len(sections) > 1 else "Section"
                    messages.addMessage(f"  {key}: {term} {', '.join(map(str, sections))}")

                messages.addMessage("\nStarting:")
                messages.addMessage(f"  Latitude: {result['starting']['lat']}")
                messages.addMessage(f"  Longitude: {result['starting']['lon']}")

                messages.addMessage("\nEnding:")
                messages.addMessage(f"  Latitude: {result['ending']['lat']}")
                messages.addMessage(f"  Longitude: {result['ending']['lon']}")

                messages.addMessage("\nBearings:")
                for i, bearing in enumerate(result["bearings"], 1):
                    messages.addMessage(f"  {i}. {bearing}")

    def postExecute(self, parameters):
        """Performs cleanup or post-processing after tool execution completes.

        This method is called by ArcGIS after the execute() method finishes and
        any output datasets have been processed and added to the map display.
        It provides an opportunity to perform additional operations such as:
        - Setting layer symbology or properties
        - Adding custom metadata
        - Cleaning up temporary files
        - Logging completion information

        Currently, this tool does not require any post-execution operations as
        it outputs results as text messages rather than creating spatial datasets.

        Args:
            parameters (list): List of parameter objects passed to the tool,
                same as provided to execute() and updateParameters() methods

        Returns:
            None
        """
        return

    def _project_point(self, point, source_spatial_reference, target_spatial_reference):
        """Projects a point from one spatial reference system to another.

        Transforms a point's coordinates from its source spatial reference
        (e.g., UTM NAD83 Zone 12N) to a target spatial reference (e.g., WGS84).
        This is commonly used to convert between projected coordinate systems
        and geographic coordinate systems for latitude/longitude calculations.

        Args:
            point (arcpy.Point): The point to project with X and Y coordinates
            source_spatial_reference (arcpy.SpatialReference): The spatial reference
                of the input point
            target_spatial_reference (arcpy.SpatialReference): The desired spatial
                reference for the output point

        Returns:
            arcpy.Point: The projected point with coordinates in the target spatial reference
        """
        point_geometry = arcpy.PointGeometry(point, source_spatial_reference)
        projected_point = point_geometry.projectAs(target_spatial_reference)

        return projected_point.firstPoint

    def _dd_to_dms(self, point):
        """Converts decimal degrees to degrees, minutes, and seconds (DMS) format.

        Transforms geographic coordinates from decimal degrees (DD) to the traditional
        DMS notation with cardinal directions. The output includes degrees (°), minutes ('),
        and seconds (") with directional indicators (N/S for latitude, E/W for longitude).
        Seconds are formatted to 5 decimal places for high precision.

        Args:
            point (arcpy.Point): A point with X (longitude) and Y (latitude) coordinates
                in decimal degrees

        Returns:
            tuple[str, str]: A tuple of (latitude_dms, longitude_dms) where:
                - latitude_dms: Formatted string like "40°45'30.12345"N"
                - longitude_dms: Formatted string like "111°52'15.67890"W"

        Example:
            >>> point = arcpy.Point(-111.8710, 40.7588)
            >>> lat, lon = self.dd_to_dms(point)
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
        lat_dms = f"{lat_degrees}°{lat_minutes:02d}'{lat_seconds:02.5f}{self.quote_char}{lat_direction}"

        # Convert longitude
        positive_longitude = point.X >= 0
        lon_minutes, lon_seconds = divmod(longitude * 3600, 60)
        lon_degrees, lon_minutes = divmod(lon_minutes, 60)
        lon_degrees = int(lon_degrees)
        lon_minutes = int(lon_minutes)
        lon_direction = "E" if positive_longitude else "W"
        lon_dms = f"{lon_degrees}°{lon_minutes:02d}'{lon_seconds:02.5f}{self.quote_char}{lon_direction}"

        return lat_dms, lon_dms

    def _calculate_grid_bearing(self, start_point, end_point, distance_meters):
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
            start_point (arcpy.Point): Starting point with X and Y in projected
                coordinates (e.g., UTM meters)
            end_point (arcpy.Point): Ending point with X and Y in projected
                coordinates (e.g., UTM meters)
            distance_meters (float): Distance between points in meters

        Returns:
            str: Bearing formatted as quadrant bearing with distance in US Survey Feet.
                Format: "{N|S}{degrees}°{minutes}'{seconds}"{E|W} {distance} ft"
                Example: "N45°30'15"E 328.1 ft"

        Example:
            >>> start = arcpy.Point(424500.0, 4515000.0)  # UTM coordinates
            >>> end = arcpy.Point(424600.0, 4515100.0)
            >>> bearing = self._calculate_grid_bearing(start, end, 141.42)
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
        seconds = round(((minutes_float - minutes) * 60))

        distance_feet = self._meters_to_us_feet(distance_meters)

        bearing = f"{y_direction}{degrees}°{minutes}'{seconds:02d}{self.quote_char}{x_direction} {distance_feet} ft"

        return bearing

    def _meters_to_us_feet(self, meters):
        """Convert meters to US Survey Feet using the official conversion factor.

        Uses the conversion factor established by the Mendenhall Order of 1893,
        which defines 1 meter as exactly 3937/1200 US Survey Feet. This is the
        standard conversion used in surveying and legal land descriptions in the
        United States.

        Args:
            meters: Distance in meters to convert

        Returns:
            float: Distance in US Survey Feet, rounded to 1 decimal place
        """
        return round(meters * 3937 / 1200, 1)

    def _format_traversal(self, traversal_dict):
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
            - All other codes default to "Uintah Special Meridian"
        """
        formatted = {}
        for key, sections in traversal_dict.items():
            unique_sections = sorted(set(sections))
            base_meridian, township_range = key.split("-")

            if base_meridian == "26":
                base_meridian = "Salt Lake Base and Meridian"
            else:
                base_meridian = "Uintah Special Meridian"

            formatted[f"{base_meridian} {township_range}"] = unique_sections

        return formatted

    def _get_disclaimer(self):
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
            the State of Utah and contributing agencies from legal liability related to
            the use or misuse of automatically generated centerline descriptions.
        """
        return """Disclaimer

No warranties or certification, express or implied, are provided for any and all road centerline descriptions provided by the Utah Geospatial Resource Center (UGRC). The following road centerline description has been compiled as a best effort service strictly for general purpose informational use and any interpretations made are the responsibility of the User.

The State of Utah and County Governments, their elected officials, officers, employees, and agents assume no legal responsibilities for the information contained herein and shall have no liability for any damages, losses, costs, or expenses, including, but not limited to attorney's fees, arising from the use or misuses of the information provided herein. The User's use thereof shall constitute an agreement by the User to release The State of Utah and County Government, its elected officials, officers, employees, and agents from such liability.

By using the information contained herein, the User is stating that the above Disclaimer has been read and that he/she has full understanding and is in agreement with the contents of this disclaimer. The road centerline information in this document was calculated and formatted using digital tools. The descriptions are NOT intended to be used for legal litigation, boundary disputes, or construction planning. These descriptions are for general reference or informational use only. Users interested in pursuing legal litigation and/or boundary disputes should consult an attorney or licensed surveyor, or both.
"""

    def _validate_centerline(self, parameter):
        """Validates the centerline input parameter.

        Ensures the selected feature layer:
        - Uses the UTM NAD83 Zone 12 North projection (EPSG:26912)
        - Has exactly one feature selected

        Args:
            parameter (arcpy.Parameter): The input feature layer parameter to validate
        """
        if not parameter.value:
            return

        errors = []
        centerline = parameter.valueAsText
        parameter.clearMessage()

        metadata = arcpy.da.Describe(centerline)
        sr = metadata["spatialReference"]
        selection = metadata["FIDSet"]

        if sr.factoryCode != self.required_wkid:
            errors.append(
                f"This parameter requires the layer projection to be UTM NAD83 Zone 12N. Select a different feature layer or project the data.\n\nFound: {sr.name}"
            )

        if selection:
            selection_count = len(selection)

            if selection_count != 1:
                errors.append(
                    f"This parameter requires one selected feature per run. Select one feature and try again.\n\nFound: {selection_count}"
                )
        else:
            errors.append(
                "This parameter requires one selected feature per run. Select one feature and try again.\n\nFound: No selection"
            )

        if errors:
            numbered_errors = "\n\n".join(f"{i + 1}. {msg}" for i, msg in enumerate(errors))
            parameter.setErrorMessage("details\n\n" + numbered_errors)
        else:
            parameter.clearMessage()

    def _validate_plss(self, parameter):
        """Validates the PLSS section input parameter.

        Ensures the selected feature layer:
        - Uses the UTM NAD83 Zone 12 North projection (EPSG:26912)
        - Has the correct schema elements

        Args:
            parameter (arcpy.Parameter): The input feature layer parameter to validate
        """
        if not parameter.value:
            return

        errors = []
        plss_sections = parameter.valueAsText
        parameter.clearMessage()

        metadata = arcpy.da.Describe(plss_sections)
        sr = metadata["spatialReference"]

        if sr.factoryCode != self.required_wkid:
            errors.append(
                f"This parameter requires the layer projection to be UTM NAD83 Zone 12N. Select a different feature layer or project the data.\n\nFound: {sr.name}"
            )

        fields = {f.name.lower() for f in metadata["fields"]}
        missing_fields = [f for f in self.plss_schema if f not in fields]

        if missing_fields:
            missing_list = "\n".join(f"   - {f}" for f in sorted(missing_fields))
            errors.append(
                f"This parameter requires the selected PLSS layer to have fields from the SGID Sections dataset.\n\nMissing fields:\n{missing_list}"
            )

        if errors:
            numbered_errors = "\n\n".join(f"{i + 1}. {msg}" for i, msg in enumerate(errors))
            parameter.setErrorMessage("details\n\n" + numbered_errors)
        else:
            parameter.clearMessage()

        return
