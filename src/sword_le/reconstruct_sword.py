import geopandas as gpd
from shapely.geometry import shape


def rebuild_sword_network(
    sword_features,
    replaced_ids,
    final_geometry,
):
    """
    Rebuild network by removing replaced reaches
    and inserting replacement segments.
    """

    rows = []

    # Keep unreplaced SWORD reaches
    for feature in sword_features:
        properties = dict(feature["properties"])

        reach_id = properties["reach_id"]

        if reach_id in replaced_ids:
            continue

        properties["geometry"] = shape(feature["geometry"])

        properties["source"] = "sword"

        if "has_obstruction" not in properties:
            properties["has_obstruction"] = False

        rows.append(properties)

    # Retrieve all existing columns
    all_columns = set()

    for row in rows:
        all_columns.update(row.keys())

    # Add replacement reaches
    for segment in final_geometry:
        row = {col: None for col in all_columns}

        row.update(
            {
                "reach_id": segment["reach_id"],
                "T": segment["T"],
                "source": "replacement",
                "has_obstruction": segment["has_obstruction"],
                "geometry": segment["geometry"],
            }
        )

        rows.append(row)

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs="EPSG:4326",
    )
