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

from shapely.ops import substring
import geopandas as gpd
from pathlib import Path
import json 
from pyproj import Transformer
import sword_le.geom_tool.generate_id as generate_id 

def split_long_reaches(
    reaches_gdf: gpd.GeoDataFrame,
    max_length: float = 30000.0,
    long_reach_id: int = 1,
):
    """
    Split reaches longer than max_length.

    Parameters
    ----------
    reaches_gdf : GeoDataFrame

    max_length : float, optional
        Maximum allowed reach length in meters.

    Returns
    -------
    split_gdf : GeoDataFrame

    long_reach_metadata : dict
    """

    output_rows = []

    existing_reach_ids = set(
        reaches_gdf["reach_id"]
        .dropna()
        .astype(str)
    )

    long_reach_metadata = {
        "long_reach_id": long_reach_id,
        "replaced_reaches": [],
    }

    for _, reach in reaches_gdf.iterrows():

        reach_id = str(
            reach["reach_id"]
        )

        length = reach.geometry.length

        if length <= max_length:

            output_rows.append(
                reach.to_dict()
            )

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

        segments, new_reaches = (
            generate_id.generate_reaches_id(
                upstream_reach_id=reach_id,
                segments=segments,
                existing_reach_ids=existing_reach_ids,
            )
        )

        transformer = Transformer.from_crs(
            reaches_gdf.crs,
            "EPSG:4326",
            always_xy=True,
        )

        upstream_point = transformer.transform(
            *reach.geometry.coords[-1]
        )

        downstream_point = transformer.transform(
            *reach.geometry.coords[0]
        )

        long_reach_metadata[
            "replaced_reaches"
        ].append(
            {
                "old_reach_id": reach_id,
                "upstream_point": list(upstream_point),
                "downstream_point": list(downstream_point),
                "new_reaches": [
                    r["reach_id"]
                    for r in new_reaches
                ],
            }
        )

        for segment in segments:

            row = {
                col: None
                for col in reaches_gdf.columns
            }

            row["geometry"] = (
                segment["geometry"]
            )

            row["reach_id"] = (
                segment["reach_id"]
            )

            output_rows.append(row)

    split_gdf = gpd.GeoDataFrame(
        output_rows,
        geometry="geometry",
        crs="4326",
    )

    return (
        split_gdf,
        long_reach_metadata,
    )


def run_split_long_reaches(
    path_sword: str,
    path_output: str,
    max_length: float = 30000.0,
    long_reach_id: int = 1,
):
    """
    Run long reach splitting workflow from file paths.
    """

    sword_gdf = gpd.read_file(
        path_sword,
    )

    utm_crs = sword_gdf.estimate_utm_crs()

    sword_gdf = sword_gdf.to_crs(
        utm_crs,
    )

    sword_gdf_out, metadata_json = (
        split_long_reaches(
            reaches_gdf=sword_gdf,
            max_length=max_length,
            long_reach_id=long_reach_id,
        )
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

import argparse


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
