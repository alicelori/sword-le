#!/usr/bin/env python3
# Copyright (c) 2026 CS GROUP France
#
# This file is part of the sword-le project:
#  https://github.com/csgroup-oss/sword-le
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def find_replaced_reaches(
    sword_gdf: gpd.GeoDataFrame,
    upstream_reach: pd.Series,
    downstream_reach: pd.Series,
    tolerance: float = 1e-5,
) -> list:
    """
    Identify all reaches belonging to the river
    section replaced by a geometry modification.

    The search starts from the downstream boundary
    reach and follows connected reaches until the
    upstream boundary reach is reached. All visited
    reach identifiers are considered part of the
    replaced section.
    """
    upstream_id = upstream_reach["reach_id"]

    current = downstream_reach

    replaced_ids = []
    visited = set()

    while True:
        current_id = current["reach_id"]

        if current_id in visited:
            break

        visited.add(current_id)
        replaced_ids.append(current_id)

        if current_id == upstream_id:
            break

        current_geom = current.geometry

        current_upstream_node = Point(current_geom.coords[-1])

        next_reach = None

        for _, candidate in sword_gdf.iterrows():
            candidate_id = candidate["reach_id"]

            if candidate_id in visited:
                continue

            candidate_geom = candidate.geometry

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
    upstream_reach: dict,
    downstream_reach: dict,
    output_dir: str | Path,
    replaced_reach_ids: list[int] | None = None,
) -> Path:
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
        "old_reach_id": replaced_reach_ids,
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


def build_metadata_json(
    upstream_reach: pd.Series,
    downstream_reach: pd.Series,
    replaced_reach_ids: list[int],
    replacement_id: int,
) -> dict:
    return {
        "replacement_id": int(replacement_id),
        "replaced_reaches": [
            {
                "upstream_point": list(upstream_reach.geometry.coords[-1]),
                "downstream_point": list(downstream_reach.geometry.coords[0]),
                "old_reach_id": [int(rid) for rid in replaced_reach_ids],
            }
        ],
    }


def build_obstruction_metadata(
    obstruction_id: int,
    impacted_reach_ids: list[int],
) -> dict:
    return {
        "obstruction_id": obstruction_id,
        "impacted_reach_ids": sorted(impacted_reach_ids),
    }


def add_new_reaches_to_json(
    json_file: str | Path,
    replacement_reaches: list[dict],
) -> None:
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
    json_file: str | Path,
    nodes_gdf: gpd.GeoDataFrame,
) -> None:
    """
    Add newly generated node information to a
    metadata JSON file.
    """
    json_file = Path(json_file)

    with json_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data["new_nodes"] = nodes_gdf[["node_id", "reach_id"]].to_dict("records")

    with json_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def add_connectivity_to_json(
    json_file: str | Path,
    connectivity: dict,
) -> None:
    """
    Add connectivity information to a metadata
    JSON file.
    """
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


def find_external_connectivity(
    sword_gdf: gpd.GeoDataFrame,
    replaced_reach_ids: list[int],
) -> tuple[list[int], list[int]]:
    """
    Find upstream and downstream reaches
    connected to the replaced group.
    """

    replaced_reach_ids = {str(rid) for rid in replaced_reach_ids}

    upstream_reaches = set()
    downstream_reaches = set()

    subset = sword_gdf[sword_gdf["reach_id"].astype(str).isin(replaced_reach_ids)]

    for _, reach in subset.iterrows():
        upstream_ids = [
            reach["rch_id_up_1"],
            reach["rch_id_up_2"],
            reach["rch_id_up_3"],
            reach["rch_id_up_4"],
        ]

        downstream_ids = [
            reach["rch_id_dn_1"],
            reach["rch_id_dn_2"],
            reach["rch_id_dn_3"],
            reach["rch_id_dn_4"],
        ]

        for rid in upstream_ids:
            if pd.isna(rid):
                continue

            rid = int(rid)

            if rid == 0:
                continue

            if str(rid) not in replaced_reach_ids:
                upstream_reaches.add(int(rid))

        for rid in downstream_ids:
            if pd.isna(rid):
                continue

            rid = int(rid)

            if rid == 0:
                continue

            if str(rid) not in replaced_reach_ids:
                downstream_reaches.add(int(rid))

    return (
        sorted(upstream_reaches),
        sorted(downstream_reaches),
    )
