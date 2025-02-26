import re
import geopandas as gpd
import pandas as pd
from tqdm import tqdm

tqdm.pandas()

def normalize_address(addr):
    if not addr or not isinstance(addr, str):
        return ""
    addr = addr.lower()
    addr = re.sub(r'\bst\b', 'street', addr)
    addr = re.sub(r'\bave\b', 'avenue', addr)
    addr = re.sub(r'\broad\b', 'road', addr)
    addr = re.sub(r'[^\w\s]', '', addr)
    return re.sub(r'\s+', ' ', addr).strip()

# Load the MapPLUTO shapefile
gdf = gpd.read_file("nyc_mappluto_24v4_shp.zip")
print("Unique Borough values in shapefile:", gdf["Borough"].unique())

# Filter for Brooklyn (shapefile uses 'BK')
gdf = gdf[gdf["Borough"].str.upper() == "BK"].copy()
print("Number of Brooklyn lots in shapefile:", len(gdf))

# Rename to avoid duplicate column conflict
gdf.rename(columns={"Borough": "Borough_shp"}, inplace=True)

# Normalize the Address field
gdf['norm_address'] = gdf['Address'].progress_apply(normalize_address)

# Load the DOB CSV
df = pd.read_csv("DOB_Brooklyn_New_Buildings_by_Construction_Date_20250223.csv")
print("Unique BOROUGH values in CSV:", df["BOROUGH"].unique())

# Filter for Brooklyn in the CSV
brooklyn_df = df[df["BOROUGH"].str.upper() == "BROOKLYN"].copy().reset_index(drop=True)
print("Number of Brooklyn rows in DOB CSV:", len(brooklyn_df))

# Rename the CSV borough column to avoid conflicts
brooklyn_df.rename(columns={"BOROUGH": "DOB_Borough"}, inplace=True)

# Construct and normalize address from CSV fields
brooklyn_df['constructed_address'] = brooklyn_df.apply(
    lambda row: f"{row['House #']} {row['Street Name']}",
    axis=1
)
brooklyn_df['norm_address'] = brooklyn_df['constructed_address'].progress_apply(normalize_address)

# Merge the shapefile and CSV on the normalized address
merged_df = gdf.merge(
    brooklyn_df,
    on='norm_address',
    suffixes=('', '_dob')
)
print("Number of merged rows:", len(merged_df))
print("Merged columns:", merged_df.columns)

# (Optional) Convert numeric fields to string if needed
for col in merged_df.columns:
    if col != "geometry" and pd.api.types.is_numeric_dtype(merged_df[col]):
         merged_df[col] = merged_df[col].astype(str)

# Save as GeoPackage
output_file = "matched_shapefile.gpkg"
merged_df.to_file(output_file, driver="GPKG")
print(f"Saved merged file as '{output_file}' with {len(merged_df)} rows.")
