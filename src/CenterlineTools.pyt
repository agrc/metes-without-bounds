# -*- coding: utf-8 -*-

__version__ = "1.0.1"  # x-release-please-version

import csv
import os
import zipfile
from io import BytesIO
from pathlib import Path

import arcpy
import requests
from packaging import version

from main import (
    ENCODING,
    FIELD_NAMES,
    MODE_WRITE,
    NEWLINE,
    csv_has_header,
    get_selected_polyline,
    process_polyline,
    save_description_to,
)

SURVEY_FILENAME = "survey123_data.csv"


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

        self.tools = [Survey123Export, CenterlineDescribe, Update]


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
        self.description = "An ArcGIS geoprocessing tool for describing a polyline feature."
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

        unique_id = arcpy.Parameter(
            displayName="Unique ID Field",
            name="in_unique_id",
            datatype="Field",
            parameterType="Required",
            direction="Input",
        )

        unique_id.parameterDependencies = ["in_features"]  # pyright: ignore[reportAttributeAccessIssue]
        unique_id.filter.list = ["String", "Text"]  # pyright: ignore[reportOptionalMemberAccess]

        plss_sections = arcpy.Parameter(
            displayName="PLSS Section Reference Layer",
            name="in_plss",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
        )

        plss_sections.filter.list = ["Polygon"]  # pyright: ignore[reportOptionalMemberAccess]

        survey123_csv = arcpy.Parameter(
            displayName="Survey123 Report CSV",
            name="in_survey123_csv",
            datatype="DEFile",
            parameterType="Required",
            direction="Input",
        )

        survey123_csv.filter.list = ["csv"]  # pyright: ignore[reportOptionalMemberAccess]

        bearing_destination = arcpy.Parameter(
            displayName="Bearing Output Destination Folder",
            name="in_bearing_destination",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )

        return [input_data, unique_id, plss_sections, survey123_csv, bearing_destination]

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
        parameter. This method is called after internal validation.
        """
        # Access parameters by name for clarity and maintainability
        params = {p.name: p for p in parameters}

        self._validate_centerline(params["in_features"])
        self._validate_plss(params["in_plss"])
        self._validate_survey123_csv(params["in_survey123_csv"])

        return

    def execute(self, parameters, messages):
        """Process polyline to generate descriptions.

        Reads polyline geometry, intersects them with SGID section
        reference data, and calculates:
        - Section traversals (which PLSS sections are crossed)
        - Starting and ending coordinates in DMS format
        - Grid bearing and distance for each segment in us survey feet
        """
        # Access parameters by name for clarity and maintainability
        params = {p.name: p for p in parameters}

        selected_row = get_selected_polyline(params["in_features"].value, params["in_unique_id"].valueAsText)

        if selected_row is None:
            messages.addErrorMessage("No features found in the selected layer.")

            return

        polyline, id = selected_row

        result = process_polyline(
            polyline,
            params["in_plss"].value,
            self.plss_schema,
        )

        messages.addMessage(f"\nSaving Survey123 results to {params['in_survey123_csv'].valueAsText}...")
        messages.addMessage(
            f"Saving bearing results to {Path(params['in_bearing_destination'].valueAsText) / f'{id}_bearings.txt'}..."
        )

        save_description_to(
            result, id, params["in_survey123_csv"].valueAsText, params["in_bearing_destination"].valueAsText
        )

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
        params = {p.name: p for p in parameters}

        if not params["in_bearing_destination"].value:
            return

        folder = Path(params["in_bearing_destination"].valueAsText)

        if folder.exists():
            os.startfile(str(folder))

        return

    def _validate_centerline(self, parameter) -> None:
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

    def _validate_plss(self, parameter) -> None:
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

    def _validate_survey123_csv(self, parameter) -> None:
        """Validates the Survey123 CSV input parameter.

        Ensures the selected file is a valid CSV file.

        Args:
            parameter (arcpy.Parameter): The input file parameter to validate
        """
        if not parameter.value:
            return

        parameter.clearMessage()

        csv_path = Path(parameter.valueAsText)

        if not csv_has_header(csv_path, FIELD_NAMES):
            parameter.setErrorMessage("The Survey123 file does not have the required header values.")

        return


class Survey123Export:
    def __init__(self):
        """Initializes the Survey123 Export geoprocessing tool.

        This tool creates an empty CSV file with the required header fields
        for storing centerline description results that will be used with
        Survey123 forms.
        """
        self.label = "Create Survey123 CSV"
        self.description = "Create the CSV file required by the centerline describe tool"
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Return the parameter definition for this tool.

        This tool requires a single parameter:

        - `parent_folder` (DEFolder, Required): The destination folder where
          the Survey123 CSV file will be created.

        Returns:
            list[arcpy.Parameter]: A list containing the folder parameter.
        """

        destination = arcpy.Parameter(
            displayName="CSV Destination Parent Folder",
            name="parent_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )

        return [destination]

    def isLicensed(self):
        """Tool is always licensed.

        Returns:
            bool: Always returns True
        """
        return True

    def updateParameters(self, parameters):
        """No parameters to update.

        Args:
            parameters (list): Empty list

        Returns:
            None
        """
        return

    def updateMessages(self, parameters):
        """No parameter validation needed.

        Args:
            parameters (list): Empty list

        Returns:
            None
        """
        if not parameters[0].value:
            parameters[0].clearMessage()

            return

        folder = Path(parameters[0].valueAsText)
        csv_path = folder / SURVEY_FILENAME

        if csv_path.exists():
            parameters[0].setWarningMessage("The Survey123 file exists in this folder and will be overwritten.")

        return

    def execute(self, parameters, messages):
        """Creates a CSV file with the required header for Survey123 integration.

        Generates a new CSV file with columns for id, starting coordinates,
        ending coordinates, and PLSS section traversal data. The file will be
        used to store centerline description results.

        Args:
            parameters (list): Tool parameters containing the destination folder
            messages: ArcGIS messages object for user feedback
        """
        folder = Path(parameters[0].valueAsText)
        csv_path = folder / SURVEY_FILENAME

        with csv_path.open(MODE_WRITE, newline=NEWLINE, encoding=ENCODING) as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=FIELD_NAMES)
            writer.writeheader()

    def postExecute(self, parameters):
        """No post-execution operations needed.

        Args:
            parameters (list): Empty list

        Returns:
            None
        """
        return


class Update:
    def __init__(self):
        """Initializes the Update Centerline Tools geoprocessing tool.

        This tool checks for updates to the CenterlineTools toolbox from the
        GitHub repository and downloads/installs the latest version if available.
        """
        self.label = "Update Centerline Tools"
        self.description = "Check for and install updates to the CenterlineTools toolbox from GitHub."
        self.canRunInBackground = False

    def getParameterInfo(self):
        """No parameters required for this tool.

        Returns:
            list: Empty list as no parameters are needed
        """
        return []

    def isLicensed(self):
        """Tool is always licensed.

        Returns:
            bool: Always returns True
        """
        return True

    def updateParameters(self, parameters):
        """No parameters to update.

        Args:
            parameters (list): Empty list

        Returns:
            None
        """
        return

    def updateMessages(self, parameters):
        """No parameter validation needed.

        Args:
            parameters (list): Empty list

        Returns:
            None
        """
        return

    def execute(self, parameters, messages):
        """Check for updates and install if available.

        Queries the GitHub API for the latest release, compares versions,
        and downloads/installs the update if a newer version is available.

        Args:
            parameters (list): Empty list (no parameters)
            messages: ArcGIS messages object for user feedback
        """
        repo_owner = "agrc"
        repo_name = "metes-without-bounds"
        current_version = __version__

        messages.addMessage("Checking for updates...")

        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

        try:
            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            release_data = response.json()

            latest_tag = release_data["tag_name"]
            latest_version = latest_tag.lstrip("v")
            release_notes = release_data.get("body", "No release notes available.")

            if version.parse(latest_version) <= version.parse(current_version):
                messages.addMessage(f"✅ The current version, {current_version}, is still the latest version.")

                return

            messages.addMessage(f"🎉 New version available: {latest_version}")
            messages.addMessage("\n\nRelease Notes:")
            messages.addMessage("-" * 50)
            messages.addMessage(release_notes)
            messages.addMessage("-" * 50)

            asset_url = None
            for asset in release_data.get("assets", []):
                if asset["name"] == "CenterlineTools.zip":
                    asset_url = asset["browser_download_url"]
                    break

            if not asset_url:
                messages.addErrorMessage("❌ Could not find assets in the latest release.")

                return

            download_response = requests.get(asset_url, timeout=30)
            download_response.raise_for_status()
            zip_data = BytesIO(download_response.content)

            messages.addMessage("Installing update...")

            install_dir = Path(__file__).parent
            allowed_files = {"main.py", "CenterlineTools.pyt"}

            with zipfile.ZipFile(zip_data) as zip_ref:
                for file_info in zip_ref.filelist:
                    filename = file_info.filename

                    if filename not in allowed_files:
                        continue

                    target_path = install_dir / filename

                    # Prevent zip slip attacks - ensure target_path is within install_dir
                    try:
                        target_path.resolve().relative_to(install_dir.resolve())
                    except ValueError:
                        messages.addErrorMessage(f"Security Error: Invalid file path in zip: {filename}")
                        return

                    messages.addMessage(f"  Updating {filename}")

                    # Extract the file
                    with zip_ref.open(filename) as source:
                        target_path.write_bytes(source.read())

            messages.addMessage(f"\n\n✅ Successfully updated to version {latest_version}.")
            messages.addMessage("ℹ️ You must restart ArcGIS Pro to use the new version.")

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                messages.addErrorMessage("No releases have been published yet for this tool.")
            else:
                messages.addErrorMessage(f"HTTP Error: {e.response.status_code} - {e.response.reason}")
        except requests.exceptions.ConnectionError:
            messages.addErrorMessage("Network connection error. Please check your internet connection.")
        except requests.exceptions.Timeout:
            messages.addErrorMessage("Request timed out. Please try again later.")
        except requests.exceptions.RequestException as e:
            messages.addErrorMessage(f"Request error: {str(e)}")
        except zipfile.BadZipFile:
            messages.addErrorMessage("Downloaded file is not a valid zip archive.")
        except Exception as e:
            messages.addErrorMessage(f"Unexpected error: {str(e)}")

    def postExecute(self, parameters):
        """No post-execution operations needed.

        Args:
            parameters (list): Empty list

        Returns:
            None
        """
        return
