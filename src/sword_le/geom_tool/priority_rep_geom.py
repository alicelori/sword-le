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

import geopandas as gpd
import pandas as pd
import sword_le.geom_tool.reach_intersection as rch_int

def build_replacement_priority(
    sword_gdf: gpd.GeoDataFrame,
    replacement_csv: str,
):
    """
    Build replacement execution order based on
    upstream dist_out.

    Parameters
    ----------
    sword_gdf : GeoDataFrame
        SWORD network in projected CRS.

    replacement_csv : str
        CSV containing:
        - replacement_id
        - path_replacement

    Returns
    -------
    list[dict]
        Replacement descriptors sorted from
        upstream to downstream.
    """

    replacement_df = pd.read_csv(
        replacement_csv
    )

    replacements = []

    for _, row in replacement_df.iterrows():

        replacement_gdf = gpd.read_file(
            row["path_replacement"]
        )

        if (
            replacement_gdf.crs
            != sword_gdf.crs
        ):
            replacement_gdf = (
                replacement_gdf.to_crs(
                    sword_gdf.crs
                )
            )

        intersected_reaches = (
            rch_int.find_intersected_reaches(
                sword_gdf,
                replacement_gdf,
            )
        )

        if intersected_reaches.empty:

            raise ValueError(
                "No intersected reaches found for "
                f"{row['path_replacement']}"
            )

        upstream_reach, _ = (
            rch_int.find_upstream_downstream_reaches(
                intersected_reaches,
            )
        )

        replacements.append(
            {
                "replacement_id": row[
                    "replacement_id"
                ],
                "path_replacement": row[
                    "path_replacement"
                ],
                "reach_id": upstream_reach[
                    "reach_id"
                ],
                "dist_out": upstream_reach[
                    "dist_out"
                ],
            }
        )

    replacements = sorted(
        replacements,
        key=lambda x: x["dist_out"],
        reverse=True,
    )

    return replacements