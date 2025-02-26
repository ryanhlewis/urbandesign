# Brooklyn Paths Visualizer

Computes shortest paths from Brooklyn public housing to subway stations using NYC street centerlines. Then, we perform a heatmap on these paths to find areas of potential high activity. Run the Python script to generate the CSV, then open `index.html` to view the visualization with Deck.gl and MapLibre GL.

## Data Sources

- **Street Centerlines**: [NYC Centerlines](https://data.cityofnewyork.us/api/views/inkn-q76z/rows.csv?date=20250225&accessType=DOWNLOAD)
- **Public Housing**: [NYC Public Housing](https://data.cityofnewyork.us/api/views/phvi-damg/rows.csv?accessType=DOWNLOAD)
- **Subway Stations**: [NYC Subway Stations](https://data.ny.gov/api/views/39hk-dx4f/rows.csv?accessType=DOWNLOAD)

## Usage

1. Run `python shortestpaths.py` to compute the shortest paths.
2. Open `index.html` in a browser to explore the results.