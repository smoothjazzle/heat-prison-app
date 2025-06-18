import streamlit as st
import geopandas as gpd
import matplotlib.pyplot as plt
import xarray as xr
import pandas as pd
import numpy as np
from shapely.geometry import Point
from io import BytesIO
import requests

st.set_page_config(layout="wide")
st.title("Arizona Prison Heatmap Viewer")

# Load Daymet file lookup table
index_df = pd.read_csv("Daymet_Tile-Year_File_IDs.csv")

# Sidebar inputs
years = sorted(index_df['year'].unique())
tiles = sorted(index_df['tile'].unique())

selected_year = st.sidebar.selectbox("Select Year", years)
selected_tiles = st.sidebar.multiselect("Select Daymet Tiles", tiles, default=tiles)

# Load shapefiles
prisons = gpd.read_file("Prison_Boundaries/Prison_Boundaries.shp").to_crs(epsg=3857)
prisons["buffer_5km"] = prisons.geometry.buffer(5000)
prison_buffers = prisons.set_geometry("buffer_5km")

cities = gpd.read_file("tl_2021_04_place/tl_2021_04_place.shp")
cities = cities.to_crs(epsg=3857)
cities = cities.nlargest(25, 'ALAND')
cities['geometry'] = cities.centroid

# Function to download NetCDF from Google Drive
@st.cache_data(show_spinner=False)
def fetch_nc_file(file_id):
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url)
    response.raise_for_status()
    return xr.open_dataset(BytesIO(response.content))

# Aggregate data
all_lats, all_lons, all_temps = [], [], []

for tile in selected_tiles:
    match = index_df[(index_df['tile'] == tile) & (index_df['year'] == selected_year)]
    if not match.empty:
        file_id = match.iloc[0]['file_id']
        try:
            ds = fetch_nc_file(file_id)
            tmax = ds['tmax'].isel(time=0).values
            lats = ds['lat'].values
            lons = ds['lon'].values

            flat_temps = tmax.ravel()
            flat_lats = lats.ravel()
            flat_lons = lons.ravel()
            valid_mask = flat_temps != -9999

            all_lats.append(flat_lats[valid_mask])
            all_lons.append(flat_lons[valid_mask])
            all_temps.append(flat_temps[valid_mask])
        except Exception as e:
            st.warning(f"Could not load tile {tile} for year {selected_year}: {e}")

# Plotting
if all_lats:
    flat_lats = np.concatenate(all_lats)
    flat_lons = np.concatenate(all_lons)
    flat_temps = np.concatenate(all_temps)

    points = gpd.GeoDataFrame(
        {'tmax': flat_temps},
        geometry=[Point(xy) for xy in zip(flat_lons, flat_lats)],
        crs="EPSG:4326"
    ).to_crs(epsg=3857)

    fig, ax = plt.subplots(figsize=(14, 14))
    ax.set_aspect('equal')

    points.plot(ax=ax, column='tmax', cmap='hot', markersize=1, alpha=0.5, zorder=1)
    prison_buffers.plot(ax=ax, edgecolor='blue', linewidth=2, label='Prison Buffers', zorder=3)
    prisons.plot(ax=ax, color='black', alpha=0.8, label='Prison Buildings', zorder=4)
    cities.plot(ax=ax, color='white', edgecolor='black', markersize=20, label='Cities', zorder=5)

    for _, row in cities.iterrows():
        ax.text(row.geometry.x, row.geometry.y, row["NAME"], fontsize=6, ha='center', color='black', zorder=6)

    for _, row in prisons.iterrows():
        centroid = row.geometry.centroid
        ax.text(centroid.x, centroid.y, row['NAME'], fontsize=6, ha='center', color='white', zorder=7)

    ax.set_title(f"Daymet Tmax ({selected_year}) with Arizona Prisons and Cities", fontsize=14)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend()
    st.pyplot(fig)
else:
    st.info("No data loaded for the selected tiles and year.")
