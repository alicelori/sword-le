import logging
import geopandas as gpd

logger = logging.getLogger("create_nodes")


def build_node(
    reach_id,
    node_order,
    point,
):
    """
    Create a node feature.
    """
    reach_type = reach_id[-1]

    return {
        "node_id": (f"{reach_id[:-1]}{node_order:03d}{reach_type}"),
        "reach_id": reach_id,
        "node_order": node_order,
        "geometry": point,
    }


def create_nodes_on_reach(
    segments,
    utm_crs,
    spacing=200.0,
):
    rows = []

    for segment in segments:
        reach_id = segment["reach_id"]
        geom = segment["geometry"]

        length = geom.length

        distances = []
        distance = 100.0

        while distance < length:
            distances.append(distance)
            distance += spacing

        node_ids = []

        # distances déjà triées aval -> amont
        for dist in distances:
            node_order = int((dist - 100.0) / spacing) + 1

            node = build_node(
                reach_id=reach_id,
                node_order=node_order,
                point=geom.interpolate(dist),
            )

            rows.append(node)
            node_ids.append(node["node_id"])

        segment["node_ids"] = node_ids

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs=utm_crs,
    )
