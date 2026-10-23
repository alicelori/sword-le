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
import pandas as pd
import sword_le.geom_tool.priority_rep_geom as pr_geom

import sword_le.geom_processing.replace_rch_geometry as rep_geometry 
import sword_le.geom_processing.split_long_rch as split_long 
import sword_le.geom_processing.split_obstr as split_obs

def process_sword_network(
    path_sword: str,
    path_output: str,
    max_length,
    path_replacement_csv: str | None = None,
    path_obstruction_csv: str | None = None,
):
    """
    Full SWORD processing workflow.
    """
    output_dir = Path(path_output)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    sword_gdf = gpd.read_file(
        path_sword,
    )

    utm_crs = sword_gdf.estimate_utm_crs()

    metadata = {}

    #
    # Geometry replacements
    #

    if path_replacement_csv is not None:

        replacement_order = (
            pr_geom.build_replacement_priority(
                sword_gdf=sword_gdf,
                replacement_csv=path_replacement_csv,
            )
        )

        replacement_metadata = []

        for replacement in replacement_order:

            replacement_gdf = gpd.read_file(
                replacement["path_replacement"]
            )
    
            sword_gdf, current_metadata = (
                rep_geometry.replace_reach_geometry(
                    sword_gdf=sword_gdf,
                    replacement_gdf=replacement_gdf,
                    replacement_id=replacement[
                        "replacement_id"
                    ],
                )
            )

            replacement_metadata.append(
                current_metadata
            )

        metadata["replacement"] = (
            replacement_metadata
        )

    #
    # Obstructions
    #

    if path_obstruction_csv is not None:

        obs_df = pd.read_csv(
            path_obstruction_csv
        )

        obstruction_gdf = (
            gpd.GeoDataFrame(
                obs_df,
                geometry=gpd.points_from_xy(
                    obs_df["Longitude"],
                    obs_df["Latitude"],
                ),
                crs="EPSG:4326",
            )
            .to_crs(
                utm_crs
            )
        )
        sword_gdf = sword_gdf.to_crs(
            utm_crs,
        )
        sword_gdf, obstruction_metadata = (
            split_obs.split_on_obstructions(
                reaches_gdf=sword_gdf,
                obstruction_gdf=obstruction_gdf,
                utm_crs=utm_crs
            )
        )

        metadata["obstruction"] = (
            obstruction_metadata
        )

    #
    # Long reaches
    #
    sword_gdf = sword_gdf.to_crs(utm_crs)
    sword_gdf, long_reach_metadata = (
        split_long.split_long_reaches(
            reaches_gdf=sword_gdf,
            max_length=max_length,
            utm_crs=utm_crs
        )
    )

    metadata["long_reach"] = (
        long_reach_metadata
    )

    #
    # Outputs
    #

    sword_gdf.to_file(
        output_dir / "sword_processed.gpkg",
        driver="GPKG",
    )

    with open(
        output_dir / "metadata.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            metadata,
            f,
            indent=4,
        )

    return (
        sword_gdf,
        metadata,
    )


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Apply SWORD geometry replacements, "
            "obstruction splitting and long reach splitting."
        )
    )

    parser.add_argument(
        "--path_sword",
        required=True,
        help="Input SWORD GPKG.",
    )

    parser.add_argument(
        "--path_output",
        required=True,
        help="Output directory.",
    )

    parser.add_argument(
        "--path_replacement_csv",
        default=None,
        help=(
            "CSV containing replacement geometries."
        ),
    )

    parser.add_argument(
        "--path_obstruction_csv",
        default=None,
        help=(
            "CSV containing obstruction points."
        ),
    )

    parser.add_argument(
        "--max_length",
        type=float,
        default=20000.0,
        help=(
            "Maximum reach length in meters "
            "before splitting."
        ),
    )

    args = parser.parse_args()

    process_sword_network(
        path_sword=args.path_sword,
        path_output=args.path_output,
        max_length=args.max_length,
        path_replacement_csv=(
            args.path_replacement_csv
        ),
        path_obstruction_csv=(
            args.path_obstruction_csv
        ),
    )


if __name__ == "__main__":
    main()