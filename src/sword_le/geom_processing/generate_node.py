import logging
import geopandas as gpd
from pathlib import Path
import argparse
import json
import pandas as pd

logger = logging.getLogger("create_nodes")


def build_node(
    reach_id,
    node_order,
    point,
):
    """
    Create a node feature.
    """
    reach_type = str(reach_id)[-1]

    return {
        "node_id": (f"{str(reach_id)[:-1]}{node_order:03d}{reach_type}"),
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
        useful_length = length - 200.0

        if useful_length <= 0:
            continue

        n_intervals = max(1, round(useful_length / spacing))
        real_spacing = useful_length / n_intervals

        distances = [100.0 + i * real_spacing for i in range(n_intervals + 1)]

        node_ids = []

        for node_order, dist in enumerate(distances, start=1):
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

def rebuild_sword_nodes(
    sword_nodes_gdf: gpd.GeoDataFrame,
    new_nodes_gdf: gpd.GeoDataFrame,
    metadata_json: dict,
) -> gpd.GeoDataFrame:
    """
    Remove nodes from replaced reaches and add
    newly generated nodes.
    """

    old_reach_ids = []
    new_reach_ids = []

    for reach_info in metadata_json[
        "replaced_reaches"
    ]:

        old_reach_ids.extend(
            [
                str(r)
                for r in reach_info[
                    "replaced_reach_ids"
                ]
            ]
        )

        new_reach_ids.extend(
            [
                str(r)
                for r in reach_info[
                    "new_reaches"
                ]
            ]
        )

    # nodes conservées
    kept_nodes = sword_nodes_gdf[
        ~sword_nodes_gdf["reach_id"]
        .astype(str)
        .isin(old_reach_ids)
    ].copy()

    # ajout des nouvelles
    updated_nodes = pd.concat(
        [
            kept_nodes,
            new_nodes_gdf,
        ],
        ignore_index=True,
    )

    return gpd.GeoDataFrame(
        updated_nodes,
        geometry="geometry",
        crs=sword_nodes_gdf.crs,
    )

def update_node_metadata(
    metadata_json: dict,
    sword_nodes_gdf: gpd.GeoDataFrame,
    new_nodes_gdf: gpd.GeoDataFrame,
) -> dict:
    """
    Store removed and added node IDs for each replacement.
    """

    for reach_info in metadata_json[
        "replaced_reaches"
    ]:

        old_reach_ids = [
            str(r)
            for r in reach_info[
                "replaced_reach_ids"
            ]
        ]

        new_reach_ids = [
            str(r)
            for r in reach_info[
                "new_reaches"
            ]
        ]

        removed_node_ids = (
            sword_nodes_gdf[
                sword_nodes_gdf["reach_id"]
                .astype(str)
                .isin(old_reach_ids)
            ]["node_id"]
            .astype(int)
            .tolist()
        )

        added_node_ids = (
            new_nodes_gdf[
                new_nodes_gdf["reach_id"]
                .astype(str)
                .isin(new_reach_ids)
            ]["node_id"]
            .astype(int)
            .tolist()
        )

        reach_info[
            "removed_node_ids"
        ] = removed_node_ids

        reach_info[
            "added_node_ids"
        ] = added_node_ids

    return metadata_json

def run_create_nodes(
    path_sword: str,
    path_sword_node: str,
    path_metadata: str,
    path_output: str,
):
    """
    Create nodes on replacement reaches and rebuild
    the full SWORD nodes layer.
    """

    reaches_gdf = gpd.read_file(
        path_sword,
    )

    sword_nodes_gdf = gpd.read_file(
        path_sword_node,
    )

    with open(
        path_metadata,
        "r",
        encoding="utf-8",
    ) as f:
        metadata_json = json.load(f)

    reach_ids = []

    for reach_info in metadata_json[
        "replaced_reaches"
    ]:

        reach_ids.extend(
            [
                str(r)
                for r in reach_info[
                    "new_reaches"
                ]
            ]
        )

    subset = reaches_gdf[
        reaches_gdf["reach_id"]
        .astype(str)
        .isin(reach_ids)
    ].copy()

    if subset.empty:
        raise ValueError(
            "No replacement reaches found in SWORD."
        )

    original_crs = sword_nodes_gdf.crs

    utm_crs = subset.estimate_utm_crs()

    subset = subset.to_crs(
        utm_crs,
    )

    segments = subset[
        ["reach_id", "geometry"]
    ].to_dict(
        orient="records",
    )

    nodes_gdf = create_nodes_on_reach(
        segments=segments,
        utm_crs=utm_crs,
    )

    nodes_gdf = nodes_gdf.to_crs(
        original_crs,
    )

    metadata_json = update_node_metadata(
        metadata_json=metadata_json,
        sword_nodes_gdf=sword_nodes_gdf,
        new_nodes_gdf=nodes_gdf,
    )

    final_nodes_gdf = rebuild_sword_nodes(
        sword_nodes_gdf=sword_nodes_gdf,
        new_nodes_gdf=nodes_gdf,
        metadata_json=metadata_json,
    )
    final_nodes_gdf['node_id']= final_nodes_gdf['node_id'].astype(int)

    output_dir = Path(
        path_output,
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / f"{Path(path_sword).stem}_nodes.gpkg"
    )

    final_nodes_gdf.to_file(
        output_file,
        driver="GPKG",
    )

    metadata_file = (
        output_dir
        / Path(path_metadata).name
    )

    with open(
        metadata_file,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            metadata_json,
            f,
            indent=4,
        )

    return final_nodes_gdf


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--path_sword",
        required=True,
        help="Input SWORD GeoPackage",
    )

    parser.add_argument(
        "--path_sword_nodes",
        required=True,
        help="Input SWORD NODES GeoPackage",
    )

    parser.add_argument(
        "--path_metadata",
        required=True,
        help="Metadata JSON",
    )

    parser.add_argument(
        "--path_output",
        required=True,
        help="Output directory",
    )

    args = parser.parse_args()

    run_create_nodes(
        path_sword=args.path_sword,
        path_sword_node=args.path_sword_nodes,
        path_metadata=args.path_metadata,
        path_output=args.path_output,
    )

if __name__ == "__main__":
    main()