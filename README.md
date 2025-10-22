# Meets without bounds

An ArcGIS python geoprocessing toolbox script tool for describing a polyline feature.

> [!Warning]
> No warranties or certification, express or implied, are provided for any and all road centerline descriptions provided by the Utah Geospatial Resource Center (UGRC). The following road centerline description has been compiled as a best effort service strictly for general purpose informational use and any interpretations made are the responsibility of the User.
>
> The State of Utah and County Governments, their elected officials, officers, employees, and agents assume no legal responsibilities for the information contained herein and shall have no liability for any damages, losses, costs, or expenses, including, but not limited to attorney's fees, arising from the use or misuses of the information provided herein. The User's use thereof shall constitute an agreement by the User to release The State of Utah and County Government, its elected officials, officers, employees, and agents from such liability.
>
> By using the information contained herein, the User is stating that the above Disclaimer has been read and that he/she has full understanding and is in agreement with the contents of this disclaimer. The road centerline information in this document was calculated and formatted using digital tools. The descriptions are NOT intended to be used for legal litigation, boundary disputes, or construction planning. These descriptions are for general reference or informational use only. Users interested in pursuing legal litigation and/or boundary disputes should consult an attorney or licensed surveyor, or both.

## Usage

> [!TIP]
> **First time using this tool?** Follow these three steps:
>
> 1. Download and extract from Releases
> 2. Connect to Open SGID for PLSS data
> 3. Add the toolbox to ArcGIS Pro

### Acquire the tool

1. Navigate to the [GitHub releases screen](https://github.com/agrc/metes-without-bounds/releases)
2. Download the `CenterlineTools.zip` asset from the latest release
3. Extract the zip file to a location in your ArcGIS Pro project (recommended: a registered project folder)
4. Keep the toolbox updated by running the `Update Centerline Tools` tool regularly

### Required data

The tool requires two inputs:

1. **Centerline layer**: A polyline feature layer with:
   - Projection: UTM NAD83 Zone 12N (EPSG:26912)
   - Exactly one feature selected

2. **PLSS Sections layer**: [PLSS Sections GCDB](https://gis.utah.gov/products/sgid/cadastre/plss-sections/) polygon layer from the Utah SGID with:
   - Projection: UTM NAD83 Zone 12N (EPSG:26912)
   - Fields: `basemeridian`, `label`, `snum`

**Recommended data source**: Use the [Open SGID](https://gis.utah.gov/documentation/sgid/#the-open-sgid-database) to access PLSS data. See [connection instructions](https://gis.utah.gov/documentation/sgid/open-sgid/) if needed. Browse to `cadastre > plss_sections_gcdb`.

### Running the tool

1. In ArcGIS Pro, open the **Catalog pane**
1. Right-click **Toolboxes** and select **Add Toolbox**
1. Navigate to the extracted `CenterlineTools.pyt` file and select it
1. Trust the code when prompted
1. Expand **CenterlineTools** in the Catalog pane
1. Double-click **Create Survey123 CSV** and choose a location to store the traversal information.
1. Click **Run**
1. Double-click **Centerline Describe** to open the tool
1. Select your parameters:
   - **Input Feature Layer**: Your centerline layer (with one feature selected)
   - **Unique ID Field**: The field containing the unique identifier for the selected feature
   - **PLSS Section Reference Layer**: The PLSS sections layer
   - **Survey123 Report CSV**: The CSV file created in step 6
   - **Bearing Output Destination Folder**: The folder where bearing text files will be saved
1. Click **Run**

### Troubleshooting

- **"No features found"**: Ensure exactly one feature is selected in your centerline layer
- **"Invalid projection"**: Both layers must use UTM NAD83 Zone 12N (EPSG:26912)
- **"Missing fields"**: Verify your PLSS layer is from the SGID `plss_sections_gcdb` table

## Development

1. Open the ArcGIS Pro project in the `/maps` folder
1. In VSCode, select the arcgispro-py3 environment or the mwb environment created below
1. Using the ArcGIS Pro Debugger extension, enable debugging
1. Using the ArcGIS Pro Debugger extension, attach to the ArcGIS Pro process
1. Set breakpoints in VSCode and execute the tool in ArcGIS Pro from the Toolbox area of the Catalog pane

### Toolbox Troubleshooting

1. **Code changes are not making their way into the toolbox**

   - Right-click the toolbox and choose **Refresh** or press <kbd>F5</kbd> with the toolbox selected.
   - If the changes are in an imported module, then caching is likely the issue. Use this code to reload:

   ```py
   import sys
   import importlib

   # Add the src directory to Python path if not already there
   src_path = r"C:\dev\metes-without-bounds\src"
   if src_path not in sys.path:
      sys.path.insert(0, src_path)

   # Reload the main module
   if 'main' in sys.modules:
      importlib.reload(sys.modules['main'])

   # Import the toolbox
   arcpy.ImportToolbox(f"{src_path}\CenterlineTools.pyt")
   ```

   - **Best practice**: Restart ArcGIS Pro to ensure all changes are picked up cleanly.

## Testing

1. Create a conda python virtual environment
   `conda create --name mwb python=3.11`
1. Activate the environment
   `activate mwb`
1. Install arcpy
   `conda install arcpy=3.5 -c esri`
1. Install development requirements
   `pip install -r requirements.dev.txt`
1. Run the tests
   `python -m pytest tests/test_main.py`
