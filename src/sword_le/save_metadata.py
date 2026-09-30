import json
from pathlib import Path
from shapely.geometry import shape
from shapely.geometry import Point


def find_replaced_reaches(
    sword_features,
    upstream_reach,
    downstream_reach,
    tolerance=1e-5,
):
    """
    Find all reach IDs located between the
    downstream and upstream reaches.

    The search follows the network by moving
    from one connected reach to the next.

    Parameters
    ----------
    sword_features : list[dict]

    upstream_reach : dict

    downstream_reach : dict

    tolerance : float

    Returns
    -------
    list
        Reach IDs located between downstream
        and upstream reaches (included).
    """

    upstream_id = upstream_reach["properties"]["reach_id"]

    current = downstream_reach

    replaced_ids = []

    visited = set()

    while True:
        current_id = current["properties"]["reach_id"]

        if current_id in visited:
            break

        visited.add(current_id)

        replaced_ids.append(current_id)

        if current_id == upstream_id:
            break

        current_geom = shape(current["geometry"])

        current_upstream_node = Point(current_geom.coords[-1])

        next_reach = None

        for candidate in sword_features:
            candidate_id = candidate["properties"]["reach_id"]

            if candidate_id in visited:
                continue

            candidate_geom = shape(candidate["geometry"])

            candidate_nodes = [
                Point(candidate_geom.coords[0]),
                Point(candidate_geom.coords[-1]),
            ]

            if any(
                current_upstream_node.distance(node) < tolerance
                for node in candidate_nodes
            ):
                next_reach = candidate
                break

        if next_reach is None:
            break

        current = next_reach

    return replaced_ids


def save_boundary_reaches(
    upstream_reach,
    downstream_reach,
    output_dir,
    replaced_reach_ids=None,
):
    """
    Save upstream/downstream reach IDs and
    replaced reach IDs to a JSON file.

    Parameters
    ----------
    upstream_reach : dict
        Upstream SWORD feature.

    downstream_reach : dict
        Downstream SWORD feature.

    output_dir : str | Path
        Output directory.

    replaced_reach_ids : list, optional
        IDs of replaced reaches.

    Returns
    -------
    Path
        Path to the generated JSON file.
    """

    if replaced_reach_ids is None:
        replaced_reach_ids = []

    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = {
        "upstream_reach_id": (upstream_reach["properties"]["reach_id"]),
        "downstream_reach_id": (downstream_reach["properties"]["reach_id"]),
        "replaced_reach_ids": replaced_reach_ids,
    }

    output_file = output_dir / "boundary_reaches.json"

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
        )

    return output_file


def add_new_reaches_to_json(
    json_file,
    replacement_reaches,
):
    """
    Add newly generated reaches to the
    metadata JSON.
    """

    json_file = Path(json_file)

    with json_file.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    data["new_reaches"] = [
        {
            "reach_id": r["reach_id"],
            "T": r["T"],
        }
        for r in replacement_reaches
    ]

    with json_file.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
        )


def add_new_nodes_to_json(
    json_file,
    nodes_gdf,
):
    json_file = Path(json_file)

    with json_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data["new_nodes"] = nodes_gdf[["node_id", "reach_id"]].to_dict("records")

    with json_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def add_connectivity_to_json(
    json_file,
    connectivity,
):
    json_file = Path(json_file)

    with json_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data["connectivity"] = connectivity

    with json_file.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False,
        )
