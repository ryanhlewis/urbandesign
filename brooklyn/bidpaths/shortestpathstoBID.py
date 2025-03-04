import math
import json
import pandas as pd
import numpy as np
import networkx as nx
from shapely.wkt import loads as load_wkt
from shapely.geometry import shape
from scipy.spatial import KDTree

def load_data():
    """
    Loads public housing, subway stations, and NYC street centerlines CSV files.
    """
    housing_df = pd.read_csv("public_housing.csv", low_memory=False)
    subway_df = pd.read_csv("subway_stations.csv", low_memory=False)
    streets_df = pd.read_csv("nyc_centerlines.csv", low_memory=False)
    return housing_df, subway_df, streets_df

def load_bid_data():
    """
    Loads BID data from a geojson file and computes each BID’s centroid.
    Filters for Brooklyn bids (if property 'F_ALL_BI_1' equals 'Brooklyn').
    """
    with open("fultoncourtmetro.geojson") as f:
        bid_geojson = json.load(f)
    bids = []
    for feature in bid_geojson["features"]:
        props = feature["properties"]
        geom = shape(feature["geometry"])
        centroid = geom.centroid
        # Only include Brooklyn bids (assuming the property holds the borough info)
        if str(props.get("F_ALL_BI_1")).upper() == "BROOKLYN":
            bids.append({
                "BID_name": props.get("F_ALL_BI_2"),
                "centroid": (centroid.y, centroid.x),
                "Latitude": centroid.y,
                "Longitude": centroid.x,
                "properties": props
            })
    bids_df = pd.DataFrame(bids)
    return bids_df

def filter_brooklyn(housing_df, subway_df, streets_df):
    """
    Filters the dataframes for Brooklyn data.
    - Housing: 'BOROUGH' equals 'BROOKLYN'
    - Subway: 'Borough' equals 'Bk'
    - Streets: 'BOROCODE' equals 3
    """
    housing_bk = housing_df[housing_df["BOROUGH"].str.upper() == "BROOKLYN"].copy()
    subway_bk = subway_df[subway_df["Borough"] == "Bk"].copy()
    streets_bk = streets_df[streets_df["BOROCODE"] == 3].copy()
    return housing_bk, subway_bk, streets_bk

def extract_centroid(wkt_str):
    """
    Extracts the centroid (latitude, longitude) from a WKT geometry string.
    """
    try:
        geom = load_wkt(wkt_str)
        centroid = geom.centroid
        return (centroid.y, centroid.x)
    except Exception:
        return (None, None)

def build_graph(streets_bk):
    """
    Converts Brooklyn street centerlines (assumed as WKT MULTILINESTRING) into a NetworkX graph.
    Each consecutive pair of points becomes an edge with Euclidean weight.
    """
    G = nx.Graph()
    for _, row in streets_bk.iterrows():
        geom = row["the_geom"]
        if isinstance(geom, str) and geom.startswith("MULTILINESTRING"):
            multiline = load_wkt(geom)
            for line in multiline.geoms:
                coords = list(line.coords)
                for i in range(len(coords) - 1):
                    seg_length = math.dist(coords[i], coords[i+1])
                    G.add_edge(coords[i], coords[i+1], weight=seg_length)
    return G

def find_nearest(street_nodes, kd_tree, lat, lon):
    """
    Given a latitude and longitude, returns the nearest street node from the KDTree.
    Note: KDTree is built with (lon, lat) tuples.
    """
    _, idx = kd_tree.query((lon, lat))
    return tuple(street_nodes[idx])

def main():
    # 1. Load CSV and geojson data
    housing_df, subway_df, streets_df = load_data()
    bids_df = load_bid_data()
    
    # 2. Filter datasets for Brooklyn
    housing_bk, subway_bk, streets_bk = filter_brooklyn(housing_df, subway_df, streets_df)
    
    # 3. Build the street network graph
    G = build_graph(streets_bk)
    
    # 4. Build a KDTree for street nodes lookup
    street_nodes = np.array(list(G.nodes()))
    kd_tree = KDTree(street_nodes)
    
    # 5. Process public housing: extract centroid and assign nearest street node.
    housing_bk["centroid"] = housing_bk["the_geom"].apply(extract_centroid)
    housing_bk["Latitude"] = housing_bk["centroid"].apply(lambda c: c[0])
    housing_bk["Longitude"] = housing_bk["centroid"].apply(lambda c: c[1])
    housing_bk.dropna(subset=["Latitude", "Longitude"], inplace=True)
    housing_bk["nearest_node"] = housing_bk.apply(
        lambda row: find_nearest(street_nodes, kd_tree, row["Latitude"], row["Longitude"]), axis=1
    )
    
    # 6. Process subway stations: assign nearest street node.
    subway_bk["nearest_node"] = subway_bk.apply(
        lambda row: find_nearest(street_nodes, kd_tree, row["GTFS Latitude"], row["GTFS Longitude"]), axis=1
    )
    
    # 7. For each BID, assign the nearest street node using its centroid.
    bids_df["nearest_node"] = bids_df.apply(
        lambda row: find_nearest(street_nodes, kd_tree, row["Latitude"], row["Longitude"]), axis=1
    )
    
    # 8. Compute shortest paths from each housing location to its nearest BID.
    housing_paths = []
    for _, h_row in housing_bk.iterrows():
        h_node = h_row["nearest_node"]
        best_bid = None
        best_path = None
        best_length = float("inf")
        # Since there are few BID points, try each one.
        for _, bid_row in bids_df.iterrows():
            bid_node = bid_row["nearest_node"]
            if nx.has_path(G, h_node, bid_node):
                try:
                    path = nx.astar_path(G, h_node, bid_node, weight="weight")
                    length = sum(G[u][v]["weight"] for u, v in zip(path[:-1], path[1:]))
                    if length < best_length:
                        best_length = length
                        best_path = path
                        best_bid = bid_row["BID_name"]
                except nx.NetworkXNoPath:
                    continue
        if best_path is not None:
            housing_paths.append({
                "housing_development": h_row.get("DEVELOPMEN", "Unknown"),
                "nearest_bid": best_bid,
                "housing_node": h_node,
                "path_length": best_length,
                "path_nodes": best_path
            })
    
    # 9. Compute shortest paths from each subway station to its nearest BID.
    subway_paths = []
    for _, s_row in subway_bk.iterrows():
        s_node = s_row["nearest_node"]
        best_bid = None
        best_path = None
        best_length = float("inf")
        for _, bid_row in bids_df.iterrows():
            bid_node = bid_row["nearest_node"]
            if nx.has_path(G, s_node, bid_node):
                try:
                    path = nx.astar_path(G, s_node, bid_node, weight="weight")
                    length = sum(G[u][v]["weight"] for u, v in zip(path[:-1], path[1:]))
                    if length < best_length:
                        best_length = length
                        best_path = path
                        best_bid = bid_row["BID_name"]
                except nx.NetworkXNoPath:
                    continue
        if best_path is not None:
            subway_paths.append({
                "station": s_row.get("Station", "Unknown"),
                "nearest_bid": best_bid,
                "subway_node": s_node,
                "path_length": best_length,
                "path_nodes": best_path
            })
    
    # 10. Save the resulting paths to CSV files.
    housing_paths_df = pd.DataFrame(housing_paths)
    subway_paths_df = pd.DataFrame(subway_paths)
    housing_paths_df.to_csv("housing_to_bid_paths.csv", index=False)
    subway_paths_df.to_csv("subway_to_bid_paths.csv", index=False)
    
    print("Paths successfully saved to 'housing_to_bid_paths.csv' and 'subway_to_bid_paths.csv'.")

if __name__ == "__main__":
    main()
