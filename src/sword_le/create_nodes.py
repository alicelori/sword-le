import logging
import geopandas as gpd

logger = logging.getLogger("create_nodes")


def build_node(
    reach_id,
    node_index,
    point,
):
    """
    Create a node feature.
    """

    reach_type = reach_id[-1]

    return {
        "node_id": (f"{reach_id[:-1]}{node_index:03d}{reach_type}"),
        "reach_id": reach_id,
        "geometry": point,
    }


def create_nodes_on_reach(
    segments,
    utm_crs,
    spacing=200.0,
):
    """
    Create nodes on replacement reaches.

    Parameters
    ----------
    segments : list[dict]

    utm_crs : CRS

    spacing : float
        Target node spacing in meters.

    Returns
    -------
    GeoDataFrame
    """

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

        for node_index, dist in enumerate(
            distances,
            start=1,
        ):
            rows.append(
                build_node(
                    reach_id=reach_id,
                    node_index=node_index,
                    point=geom.interpolate(dist),
                )
            )

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs=utm_crs,
    )
