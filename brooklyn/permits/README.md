# Permit Viewer

This project visualizes NYC building permits alongside PLUTO spatial data.

## Data Downloads

1. **DOB Permit Data**: [Download](https://data.cityofnewyork.us/Housing-Development/DOB-Permit-Issuance/ipu4-2q9a)
2. **MapPLUTO Data**: [Download](https://hub.arcgis.com/datasets/DCP::mappluto-1/explore?location=40.693461%2C-73.992769%2C18.65)
3. **Borough Boundaries**: [Download](https://boundaries.beta.nyc/?map=cd)

## Instructions

1. **Run `creator.py`**: Intersects permit addresses with PLUTO spatial data.
2. **Export to GeoJSON**: Use QGIS with the borough boundaries file.
3. **Extract by Location**: In QGIS, filter the borough boundary to `BoroCode` 302.

Follow these steps to analyze and visualize the data effectively. 