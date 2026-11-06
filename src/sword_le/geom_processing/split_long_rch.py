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

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from shapely.ops import substring

import sword_le.geom_tool.generate_id as generate_id
import sword_le.geom_tool.save_metadata as save_metadata


def split_long_reaches(
    reaches_gdf: gpd.GeoDataFrame,
    utm_crs: str,
    max_length: float = 30000.0,
    long_reach_id: int = 1,
) -> tuple[gpd.GeoDataFrame, dict]:
    """
    Split SWORD reaches whose length exceeds a specified threshold.

    The workflow identifies reaches longer than the maximum allowed
    length and divides each of them into two shorter reaches at the
    midpoint of their geometry. New reach identifiers are generated
    for the resulting segments while preserving network connectivity
    information.

    Metadata describing the original reach, surrounding connectivity,
    generated reach identifiers, representative width information, and
    split locations are produced for each modified reach.

    Parameters
    ----------
    reaches_gdf : gpd.GeoDataFrame
        Input SWORD river network.
    utm_crs : str
        Projected coordinate reference system used for length
        calculations and geometric operations.
    max_length : float, default=30000.0
        Maximum allowed reach length in meters. Reaches exceeding
        this value are split.
    long_reach_id : int, default=1
        Identifier associated with the long-reach splitting operation.

    Returns
    -------
    tuple[gpd.GeoDataFrame, dict]
        A tuple containing:

        - The updated river network with long reaches replaced by
          newly generated reaches.
        - A metadata dictionary describing all performed split
          operations, including original reach identifiers,
          connectivity information, split locations, generated
          reach identifiers, and summary attributes.
    """
    output_rows = []

    existing_reach_ids = set(reaches_gdf["reach_id"].dropna().astype(str))

    long_reach_metadata = {
        "long_reach_id": long_reach_id,
        "replaced_reaches": [],
    }
    reaches_gdf = reaches_gdf.to_crs(utm_crs)

    for _, reach in reaches_gdf.iterrows():
        reach_id = int(reach["reach_id"])

        length = reach.geometry.length
        if length <= max_length:
            output_rows.append(reach.to_dict())

            continue

        midpoint = length / 2.0

        first = substring(
            reach.geometry,
            0,
            midpoint,
        )

        second = substring(
            reach.geometry,
            midpoint,
            length,
        )

        segments = [
            {
                "geometry": first,
                "has_obstruction": False,
            },
            {
                "geometry": second,
                "has_obstruction": False,
            },
        ]

        segments, new_reaches = generate_id.generate_reaches_id(
            upstream_reach_id=reach_id,
            segments=segments,
            existing_reach_ids=existing_reach_ids,
        )

        transformer = Transformer.from_crs(
            reaches_gdf.crs,
            "EPSG:4326",
            always_xy=True,
        )

        upstream_point = transformer.transform(*reach.geometry.coords[-1])

        downstream_point = transformer.transform(*reach.geometry.coords[0])

        external_upstream, external_downstream = (
            save_metadata.find_external_connectivity(
                reaches_gdf,
                [int(reach_id)],
            )
        )
        up_width = np.nan
        if external_upstream:
            subset = reaches_gdf.loc[
                reaches_gdf["reach_id"] == int(external_upstream[0]),
                "width",
            ]
            if not subset.empty:
                up_width = subset.iloc[0]

        dn_width = np.nan
        if external_downstream:
            subset = reaches_gdf.loc[
                reaches_gdf["reach_id"] == int(external_downstream[0]),
                "width",
            ]
            if not subset.empty:
                dn_width = subset.iloc[0]

        if np.isnan(up_width) and np.isnan(dn_width):
            mean_width = np.nan

        elif np.isnan(up_width):
            mean_width = dn_width

        elif np.isnan(dn_width):
            mean_width = up_width

        else:
            mean_width = ((up_width + dn_width) / 2) * 1.25

        long_reach_metadata["replaced_reaches"].append(
            {
                "old_reach_id": [int(reach_id)],
                "upstream_reaches": (external_upstream),
                "downstream_reaches": (external_downstream),
                "mean_width": mean_width,
                "upstream_point": list(upstream_point),
                "downstream_point": list(downstream_point),
                "new_reaches": [int(r["reach_id"]) for r in new_reaches],
            }
        )

        for segment in segments:
            row = {col: None for col in reaches_gdf.columns}

            row["geometry"] = segment["geometry"]

            row["reach_id"] = segment["reach_id"]

            output_rows.append(row)
    split_gdf = gpd.GeoDataFrame(
        output_rows,
        geometry="geometry",
        crs=utm_crs,
    )
    split_gdf["reach_id"] = split_gdf["reach_id"].astype(int)
    return (
        split_gdf,
        long_reach_metadata,
    )


def run_split_long_reaches(
    path_sword: str,
    path_output: str,
    max_length: float = 30000.0,
    long_reach_id: int = 1,
) -> tuple[gpd.GeoDataFrame, dict]:
    """
    Run long reach splitting workflow.
    """

    sword_gdf = gpd.read_file(
        path_sword,
    )

    utm_crs = sword_gdf.estimate_utm_crs()

    sword_gdf = sword_gdf.to_crs(
        utm_crs,
    )

    sword_gdf_out, metadata_json = split_long_reaches(
        reaches_gdf=sword_gdf,
        max_length=max_length,
        long_reach_id=long_reach_id,
        utm_crs=utm_crs,
    )

    output_dir = Path(path_output)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    sword_gdf_out.to_file(
        output_dir / "sword_long.gpkg",
        driver="GPKG",
    )

    with open(
        output_dir / "sword_long.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            metadata_json,
            f,
            indent=4,
        )

    return (
        sword_gdf_out,
        metadata_json,
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--path_sword",
        required=True,
    )

    parser.add_argument(
        "--path_output",
        required=True,
        help="Output directory",
    )

    parser.add_argument(
        "--max_length",
        type=float,
        default=30000.0,
    )

    parser.add_argument(
        "--long_reach_id",
        type=int,
        default=1,
    )

    args = parser.parse_args()

    run_split_long_reaches(
        path_sword=args.path_sword,
        path_output=args.path_output,
        max_length=args.max_length,
        long_reach_id=args.long_reach_id,
    )


if __name__ == "__main__":
    main()
