# Meets without bounds

An ArcGIS python geoprocessing toolbox script tool for describing a polyline feature.

> [!Warning]
> No warranties or certification, express or implied, are provided for any and all road centerline descriptions provided by the Utah Geospatial Resource Center (UGRC). The following road centerline description has been compiled as a best effort service strictly for general purpose informational use and any interpretations made are the responsibility of the User.
>
> The State of Utah and County Governments, their elected officials, officers, employees, and agents assume no legal responsibilities for the information contained herein and shall have no liability for any damages, losses, costs, or expenses, including, but not limited to attorney's fees, arising from the use or misuses of the information provided herein. The User's use thereof shall constitute an agreement by the User to release The State of Utah and County Government, its elected officials, officers, employees, and agents from such liability.
>
> By using the information contained herein, the User is stating that the above Disclaimer has been read and that he/she has full understanding and is in agreement with the contents of this disclaimer. The road centerline information in this document was calculated and formatted using digital tools. The descriptions are NOT intended to be used for legal litigation, boundary disputes, or construction planning. These descriptions are for general reference or informational use only. Users interested in pursuing legal litigation and/or boundary disputes should consult an attorney or licensed surveyor, or both.

## Development

1. Open the ArcGIS Pro project in the `/maps` folder
1. In VSCode, select the arcgispro-py3 environment or the mwb environment created below
1. Using the ArcGIS Pro Debugger extension, enable debugging
1. Using the ArcGIS Pro Debugger extension, attach to the ArcGIS Pro process
1. Set breakpoints in VSCode and execute the tool in ArcGIS Pro from the Toolbox area of the Catalog pane

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
