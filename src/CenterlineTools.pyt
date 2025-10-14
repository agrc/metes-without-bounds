# -*- coding: utf-8 -*-

import arcpy

from main import format_traversal, get_disclaimer, get_selected_polyline, process_polyline


class Toolbox:
    def __init__(self):
        """Initializes the CenterlineTools Python Toolbox for ArcGIS.

        Defines the toolbox properties and registers the tools contained within it.
        This toolbox provides geospatial tools for generating
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

        The tool generates descriptions for road centerlines by:
        - Calculating PLSS section traversals
        - Converting coordinates to DMS format
        - Computing grid bearings and distances in US Survey Feet
        """
        self.label = "Centerline Describe"
        self.description = get_disclaimer() + "\nAn ArcGIS geoprocessing tool for describing a polyline feature."
        self.canRunInBackground = False
        self.required_wkid = 26912  #: UTM NAD83 Zone 12 North
        self.plss_schema = ["basemeridian", "label", "snum"]

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
        """Process polyline to generate descriptions.

        Reads polyline geometry, intersects them with SGID section
        reference data, and calculates:
        - Section traversals (which PLSS sections are crossed)
        - Starting and ending coordinates in DMS format
        - Grid bearing and distance for each segment in us survey feet
        """
        polyline = get_selected_polyline(parameters[0].value)
        if polyline is None:
            messages.addErrorMessage("No features found in the selected layer.")

            return

        result = process_polyline(
            polyline,
            parameters[1].value,
            self.plss_schema,
        )

        messages.addMessage(get_disclaimer())
        messages.addMessage("\nTraversal:")

        traversal = format_traversal(result["traversal"])
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
