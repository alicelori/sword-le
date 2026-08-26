import geopandas as gpd
from shapely.geometry import shape


def rebuild_sword_network(
    sword_features,
    replaced_ids,
    final_geometry,
    crs="EPSG:4326",
):
    """
    Rebuild a SWORD layer by removing features belonging
    to replaced reaches and appending replacement features.
    """

    rows = []

    # Existing SWORD features
    for feature in sword_features:
        properties = dict(feature["properties"])

        reach_id = properties.get("reach_id")

        if reach_id in replaced_ids:
            continue

        properties["geometry"] = shape(feature["geometry"])

        rows.append(properties)

    # Accept either a GeoDataFrame or a list of dicts
    if isinstance(final_geometry, gpd.GeoDataFrame):
        final_geometry = final_geometry.to_dict("records")
    # Collect all columns
    all_columns = set()

    for row in rows:
        all_columns.update(row.keys())

    for feature in final_geometry:
        all_columns.update(feature.keys())

    # Append replacement features
    for feature in final_geometry:
        row = {col: None for col in all_columns}
        row.update(feature)
        rows.append(row)

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs=crs,
    )
