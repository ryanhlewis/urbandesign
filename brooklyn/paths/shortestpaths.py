"""
Complete Python script to:
1. Load the public housing, subway stations, and NYC street centerlines CSV files (with low_memory=False to handle mixed types).
2. Filter for Brooklyn public housing and subway stations.
3. Convert street centerlines to a graph.
4. Extract centroid coordinates for public housing polygons.
5. Find nearest street nodes for each housing location and subway station.
6. Compute shortest paths (using an optimized approach) from each housing location to the nearest subway station.
7. Save the resulting paths to a CSV.

Note: This script assumes:
    - public_housing.csv contains 'the_geom' (MULTIPOLYGON) and 'BOROUGH' columns.
    - subway_stations.csv contains 'GTFS Latitude', 'GTFS Longitude', 'Borough', etc.
    - nyc_centerlines.csv contains 'the_geom' (MULTILINESTRING), 'BOROCODE', etc.
    - The script is run in an environment with necessary libraries installed:
        pandas, numpy, shapely, networkx, scipy
"""

import math
import pandas as pd
import numpy as np
import networkx as nx
from shapely.wkt import loads
from shapely.geometry import MultiPolygon
from scipy.spatial import KDTree

def load_data():
    """Loads and returns the three main datasets: public housing, subway stations, and street centerlines."""
    # Use low_memory=False to avoid dtype warnings with large/mixed CSVs
    public_housing_df = pd.read_csv("public_housing.csv", low_memory=False)
    subway_stations_df = pd.read_csv("subway_stations.csv", low_memory=False)
    street_centerlines_df = pd.read_csv("nyc_centerlines.csv", low_memory=False)
    return public_housing_df, subway_stations_df, street_centerlines_df

def filter_brooklyn_data(public_housing_df, subway_stations_df, street_centerlines_df):
    """
    Filters the dataframes for Brooklyn public housing and subway stations,
    and for Brooklyn in the street centerlines (BOROCODE == 3).
    """
    # Filter for Brooklyn public housing by borough name
    # (This dataset uses the string 'BROOKLYN' in the 'BOROUGH' column)
    housing_bk = public_housing_df[public_housing_df["BOROUGH"].str.upper() == "BROOKLYN"].copy()
    
    # Filter for Brooklyn subway stations by 'Borough' == 'Bk'
    subway_bk = subway_stations_df[subway_stations_df["Borough"] == "Bk"].copy()
    
    # Filter street centerlines for BOROCODE = 3 (Brooklyn)
    streets_bk = street_centerlines_df[street_centerlines_df["BOROCODE"] == 3].copy()
    
    return housing_bk, subway_bk, streets_bk

def extract_centroid(wkt_str):
    """Extracts the centroid (lat, lon) from a MULTIPOLYGON string."""
    try:
        geometry = loads(wkt_str)
        if isinstance(geometry, MultiPolygon):
            c = geometry.centroid
            return (c.y, c.x)  # (Latitude, Longitude)
        # If it's not a MultiPolygon, try centroid anyway
        if geometry is not None:
            c = geometry.centroid
            return (c.y, c.x)
    except:
        pass
    return (None, None)

def build_street_graph(streets_bk):
    """
    Converts Brooklyn street centerlines into a NetworkX graph.
    Each segment in 'the_geom' (MULTILINESTRING) becomes edges in the graph.
    """
    G = nx.Graph()
    
    for _, row in streets_bk.iterrows():
        geom = row["the_geom"]
        if isinstance(geom, str) and geom.startswith("MULTILINESTRING"):
            multiline = loads(geom)
            # A MULTILINESTRING may contain multiple LineStrings
            for line in multiline.geoms:
                coords = list(line.coords)
                # add edges between consecutive points
                for i in range(len(coords) - 1):
                    # compute Euclidean distance between coords[i] and coords[i+1]
                    seg_length = math.dist(coords[i], coords[i+1])
                    G.add_edge(coords[i], coords[i+1], weight=seg_length)
    return G

def find_nearest_node(kd_tree, street_nodes, lat, lon):
    """Returns the nearest street node given a latitude and longitude."""
    # kd_tree.query expects (x, y) -> (longitude, latitude)
    _, idx = kd_tree.query((lon, lat))
    return tuple(street_nodes[idx])

def main():
    # 1. Load data
    public_housing_df, subway_stations_df, street_centerlines_df = load_data()
    
    # 2. Filter for Brooklyn
    housing_bk, subway_bk, streets_bk = filter_brooklyn_data(
        public_housing_df, subway_stations_df, street_centerlines_df
    )
    
    # 3. Build graph
    G = build_street_graph(streets_bk)
    
    # 4. Extract centroids for Brooklyn public housing
    housing_bk["centroid"] = housing_bk["the_geom"].apply(extract_centroid)
    # Split into latitude/longitude for clarity
    housing_bk["Latitude"] = housing_bk["centroid"].apply(lambda c: c[0])
    housing_bk["Longitude"] = housing_bk["centroid"].apply(lambda c: c[1])
    housing_bk.dropna(subset=["Latitude", "Longitude"], inplace=True)
    
    # 5. Prepare nearest node lookups
    #    Extract all street nodes from the graph and build a KDTree
    street_nodes = np.array(list(G.nodes()))
    kd_tree = KDTree(street_nodes)
    
    # 6. Find nearest street nodes for each housing location
    housing_bk["nearest_node"] = housing_bk.apply(
        lambda row: find_nearest_node(kd_tree, street_nodes, row["Latitude"], row["Longitude"]),
        axis=1
    )
    
    # 7. Find nearest street nodes for each subway station
    #    Note: Stations already have lat/lon columns in "GTFS Latitude" and "GTFS Longitude"
    subway_bk["nearest_node"] = subway_bk.apply(
        lambda row: find_nearest_node(kd_tree, street_nodes, row["GTFS Latitude"], row["GTFS Longitude"]),
        axis=1
    )
    
    # 8. Compute shortest paths using an optimized approach (A* plus KDTree for nearest stations)
    subway_nodes_arr = np.array(list(subway_bk["nearest_node"]))
    subway_kd_tree = KDTree(subway_nodes_arr)
    
    shortest_paths = []
    
    for _, housing in housing_bk.iterrows():
        housing_node = housing["nearest_node"]
        
        # Query 3 nearest subway station nodes
        _, nearest_indices = subway_kd_tree.query(housing_node, k=3)
        candidate_subway_nodes = subway_nodes_arr[nearest_indices]
        
        min_distance = float("inf")
        best_path = None
        best_subway_node = None
        
        for subway_node in candidate_subway_nodes:
            # Convert to tuple
            subway_node_tuple = tuple(subway_node)
            if nx.has_path(G, housing_node, subway_node_tuple):
                # Use A* for faster pathfinding
                path = nx.astar_path(G, housing_node, subway_node_tuple, weight="weight")
                # Sum the weights of edges in the path
                path_length = sum(
                    G[u][v]["weight"] for u, v in zip(path[:-1], path[1:])
                )
                if path_length < min_distance:
                    min_distance = path_length
                    best_path = path
                    best_subway_node = subway_node_tuple
        
        if best_path is not None:
            shortest_paths.append({
                "housing_development": housing["DEVELOPMEN"],
                "housing_node": housing_node,
                "subway_node": best_subway_node,
                "path_length": min_distance,
                "path_nodes": best_path
            })
    
    # 9. Convert to DataFrame and save to CSV
    results_df = pd.DataFrame(shortest_paths)
    results_df.to_csv("shortest_paths.csv", index=False)
    print("Shortest paths successfully saved to shortest_paths.csv.")

if __name__ == "__main__":
    main()
