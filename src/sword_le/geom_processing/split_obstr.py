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
import pandas as pd
import argparse
from pathlib import Path
import json
from pyproj import Transformer

import sword_le.geom_tool.obs_function as obs
import sword_le.geom_tool.save_metadata as save_metadata
import sword_le.geom_tool.generate_id as generate_id 

def split_on_obstructions(
    reaches_gdf: gpd.GeoDataFrame,
    obstruction_gdf: gpd.GeoDataFrame,
    buffer_distance: float = 10.0,
    cut_distance: float = 200.0,
    obstruction_id: int = 1,
):
    """
    Split SWORD reaches around obstruction points.

    Only reaches with T = 1 (last digit of the
    reach_id) are eligible for splitting.
    Reaches already associated with an obstruction
    (T = 4) are preserved unchanged.

    Parameters
    ----------
    reaches_gdf : geopandas.GeoDataFrame
        Input SWORD reach network in a projected CRS
        (typically UTM). Distances are assumed to be
        expressed in meters.

    obstruction_gdf : geopandas.GeoDataFrame
        Obstruction point locations in the same CRS
        as reaches_gdf.

    buffer_distance : float, optional
        Search distance used to identify obstructions
        associated with a reach, in meters.

    cut_distance : float, optional
        Distance removed upstream and downstream from
        the obstruction location, in meters.

    obstruction_id : int, optional
        Unique identifier of the obstruction processing
        operation.

    Returns
    -------
    split_gdf : geopandas.GeoDataFrame
        Updated reach network.

        Unaffected reaches are preserved unchanged.

        Reaches impacted by obstructions are removed
        and replaced by new segments generated from
        the split operation.

        Newly created reaches receive generated
        reach identifiers.

    obstruction_metadata : dict
        Metadata describing the obstruction
        processing, including:

        - obstruction_id
        - old reach identifiers
        - newly generated reach identifiers

    Notes
    -----
    The obstruction segment receives T = 4 in its
    generated reach identifier.

    Segments located upstream and downstream of the
    obstruction receive T = 1.

    Generated reach identifiers are checked against
    existing reach identifiers to avoid collisions.
    """

    if reaches_gdf.crs != obstruction_gdf.crs:
        raise ValueError(
            "reaches_gdf and obstruction_gdf must use the same CRS."
        )

    if reaches_gdf.crs.is_geographic:
        raise ValueError(
            "Projected CRS required (e.g. UTM)."
        )

    output_rows = []

    existing_reach_ids = set(
        reaches_gdf["reach_id"]
        .dropna()
        .astype(str)
    )

    obstruction_metadata = {
        "obstruction_id": obstruction_id,
        "replaced_reaches": [],
    }

    for _, reach in reaches_gdf.iterrows():

        reach_id = str(reach["reach_id"])

        if reach_id[-1] != "1":

            output_rows.append(
                reach.to_dict()
            )

            continue

        nearby_obstructions = obs.get_obstructions_on_reach(
            reach.geometry,
            obstruction_gdf,
            buffer_distance,
        )

        current_segments = [
            {
                "geometry": reach.geometry,
                "has_obstruction": False,
            }
        ]

        split_occurred = False

        for obstruction in nearby_obstructions.geometry:

            next_segments = []

            for seg_data in current_segments:

                seg = seg_data["geometry"]

                obstruction_buffer = obstruction.buffer(
                    buffer_distance
                )

                if not seg.intersects(
                    obstruction_buffer
                ):
                    next_segments.append(
                        seg_data
                    )
                    continue

                split_occurred = True

                next_segments.extend(
                    obs.split_segment_at_obstruction(
                        seg,
                        obstruction,
                        cut_distance,
                    )
                )

            current_segments = next_segments

        if not split_occurred:
            output_rows.append(
                reach.to_dict()
            )
            continue

        segments_for_id, new_reaches = (
            generate_id.generate_reaches_id(
                upstream_reach_id=reach_id,
                segments=current_segments,
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
        external_upstream, external_downstream = (
            save_metadata.find_external_connectivity(
                reaches_gdf,
                [int(reach_id)],
            )
        )

        mean_width = float(
            reaches_gdf.loc[
                reaches_gdf["reach_id"] == int(reach_id),
                "width",
            ].mean()
        )

        obstruction_metadata[
            "replaced_reaches"
        ].append(
            {
                "replaced_reach_ids": [
                    int(reach_id)
                ],
                "upstream_reaches": (
                    external_upstream
                ),
                "downstream_reaches": (
                    external_downstream
                ),
                "width": mean_width,
                "upstream_point": list(
                    upstream_point
                ),
                "downstream_point": list(
                    downstream_point
                ),
                "new_reaches": [
                    int(
                        r["reach_id"]
                    )
                    for r in new_reaches
                ],
            }
        )


        for segment in segments_for_id:

            row = {
                col: None
                for col in reaches_gdf.columns
            }

            row["geometry"] = segment["geometry"]
            row["reach_id"] = segment["reach_id"]

            output_rows.append(row)

    split_gdf = gpd.GeoDataFrame(
        output_rows,
        geometry="geometry",
        crs="4326",
    )

    return (
        split_gdf,
        obstruction_metadata,
    )


def run_split_on_obstructions(
    path_sword: str,
    path_obstruction_csv: str,
    path_output: str,
    obstruction_id: int = 1,
):
    """
    Run obstruction splitting workflow from file paths.
    """

    sword_gdf = gpd.read_file(
        path_sword,
    )

    utm_crs = sword_gdf.estimate_utm_crs()

    sword_gdf = sword_gdf.to_crs(
        utm_crs,
    )

    obs_df = pd.read_csv(
        path_obstruction_csv,
    )

    obstruction_gdf = gpd.GeoDataFrame(
        obs_df,
        geometry=gpd.points_from_xy(
            obs_df["Longitude"],
            obs_df["Latitude"],
        ),
        crs="EPSG:4326",
    ).to_crs(
        utm_crs,
    )

    sword_gdf_out, metadata_json = (
        split_on_obstructions(
            reaches_gdf=sword_gdf,
            obstruction_gdf=obstruction_gdf,
            obstruction_id=obstruction_id,
        )
    )

    output_dir = Path(path_output)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    sword_gdf_out.to_file(
        output_dir / "sword_obstruction.gpkg",
        driver="GPKG",
    )

    with open(
        output_dir / "sword_obstruction.json",
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
        "--path_obstruction_csv",
        required=True,
    )

    parser.add_argument(
        "--path_output",
        required=True,
        help="Output directory",
    )

    parser.add_argument(
        "--obstruction_id",
        type=int,
        default=1,
    )

    args = parser.parse_args()

    run_split_on_obstructions(
        path_sword=args.path_sword,
        path_obstruction_csv=args.path_obstruction_csv,
        path_output=args.path_output,
        obstruction_id=args.obstruction_id,
    )


if __name__ == "__main__":
    main()