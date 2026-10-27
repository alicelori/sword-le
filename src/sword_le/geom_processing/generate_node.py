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
    old_reach_ids: list,

) -> gpd.GeoDataFrame:
    """
    Remove nodes from replaced reaches and add
    newly generated nodes.
    """

    # nodes conservées
    kept_nodes = sword_nodes_gdf[
        ~sword_nodes_gdf["reach_id"]
        .astype(int)
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
    old_reach_ids = []
    new_reach_ids = []

    for category in [
        "replacements",
        "obstructions",
        "long_reaches",
    ]:
        for item in metadata_json.get(category, []):
            for reach_info in item["replaced_reaches"]:

                old_reach_ids.extend(
                    int(r)
                    for r in reach_info["old_reach_id"]
                )
                new_reach_ids.extend(
                    int(r)
                    for r in reach_info["new_reaches"]
                )
     
                
    removed_node_ids = (
        sword_nodes_gdf[
            sword_nodes_gdf["reach_id"]
            .astype(int)
            .isin(old_reach_ids)
        ]["node_id"]
        .astype(int)
        .tolist()
    )

    added_node_ids = (
        new_nodes_gdf[
            new_nodes_gdf["reach_id"]
            .astype(int)
            .isin(new_reach_ids)
        ]["node_id"]
        .astype(int)
        .tolist()
    )

    metadata_json[
        "removed_node_ids"
    ] = removed_node_ids

    metadata_json[
        "added_node_ids"
    ] = added_node_ids

    return metadata_json, old_reach_ids

def create_nodes_from_reaches(
    reaches_gdf: gpd.GeoDataFrame,
    sword_nodes_gdf: gpd.GeoDataFrame,
    metadata_json: dict,
) -> tuple[gpd.GeoDataFrame, dict]:
    """
    Create nodes on new reaches and rebuild the full
    SWORD nodes layer.
    """

    reach_ids = []

    for operation_type in [
        "replacements",
        "obstructions",
        "long_reaches",
    ]:
        for operation in metadata_json.get(operation_type, []):
            for reach_info in operation["replaced_reaches"]:
                reach_ids.extend(
                    reach_info["new_reaches"]
                )

    subset = reaches_gdf[
        reaches_gdf["reach_id"]
        .astype(int)
        .isin(reach_ids)
    ].copy()

    if subset.empty:
        raise ValueError(
            "No replacement reaches found in SWORD."
        )

    original_crs = sword_nodes_gdf.crs

    utm_crs = subset.estimate_utm_crs()

    subset = subset.to_crs(utm_crs)

    segments = subset[
        ["reach_id", "geometry"]
    ].to_dict(
        orient="records",
    )

    new_nodes_gdf = create_nodes_on_reach(
        segments=segments,
        utm_crs=utm_crs,
    )

    new_nodes_gdf = new_nodes_gdf.to_crs(
        original_crs,
    )

    metadata_json, old_reach_ids = (
        update_node_metadata(
            metadata_json=metadata_json,
            sword_nodes_gdf=sword_nodes_gdf,
            new_nodes_gdf=new_nodes_gdf,
        )
    )

    final_nodes_gdf = rebuild_sword_nodes(
        sword_nodes_gdf=sword_nodes_gdf,
        new_nodes_gdf=new_nodes_gdf,
        metadata_json=metadata_json,
        old_reach_ids=old_reach_ids,
    )

    final_nodes_gdf["node_id"] = (
        final_nodes_gdf["node_id"]
        .astype(int)
    )

    return final_nodes_gdf, metadata_json, reach_ids

def run_create_nodes(
    path_sword: str,
    path_sword_node: str,
    path_metadata: str,
    path_output: str,
) -> gpd.GeoDataFrame:

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

    final_nodes_gdf, metadata_json = (
        create_nodes_from_reaches(
            reaches_gdf=reaches_gdf,
            sword_nodes_gdf=sword_nodes_gdf,
            metadata_json=metadata_json,
        )
    )

    output_dir = Path(path_output)

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