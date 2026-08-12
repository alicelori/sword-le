from geopy.distance import distance, lonlat
from shapely.geometry import Point
import math
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
    geometry,
    reach_id,
    spacing=200.0,
):
    """
    Create nodes on a single reach.

    Parameters
    ----------
    geometry : LineString

    reach_id : str

    spacing : float
        Target spacing between nodes in meters.

    Returns
    -------
    list[dict]
        Generated nodes.
    """

    nodes = []

    coords = list(geometry.coords)

    lon1, lat1 = coords[0]

    reach_length = 0.0

    for lon2, lat2 in coords[1:]:
        reach_length += distance(
            lonlat(lon1, lat1),
            lonlat(lon2, lat2),
        ).meters

        lon1, lat1 = lon2, lat2

    nnodes = int(math.floor(reach_length / spacing))

    if nnodes == 0:
        return nodes

    actual_spacing = reach_length / float(nnodes)

    next_node_dist = 0.5 * actual_spacing

    current_dist = 0.0

    node_index = 0

    lon1, lat1 = coords[0]

    for lon2, lat2 in coords[1:]:
        ddist = distance(
            lonlat(lon1, lat1),
            lonlat(lon2, lat2),
        ).meters

        while current_dist + ddist >= next_node_dist:
            alpha = (next_node_dist - current_dist) / ddist

            lon = lon1 + alpha * (lon2 - lon1)

            lat = lat1 + alpha * (lat2 - lat1)

            node_index += 1

            nodes.append(
                build_node(
                    reach_id=reach_id,
                    node_index=node_index,
                    point=Point(
                        lon,
                        lat,
                    ),
                )
            )

            next_node_dist += actual_spacing

        current_dist += ddist

        lon1, lat1 = lon2, lat2

    logger.info(
        "Created %s node(s) on reach %s",
        len(nodes),
        reach_id,
    )

    return nodes


def create_nodes_on_replacement_reaches(
    segments,
    spacing=200.0,
):
    """
    Create nodes on replacement reaches.
    """

    rows = []

    for segment in segments:
        rows.extend(
            create_nodes_on_reach(
                geometry=segment["geometry"],
                reach_id=segment["reach_id"],
                spacing=spacing,
            )
        )

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs="EPSG:4326",
    )
