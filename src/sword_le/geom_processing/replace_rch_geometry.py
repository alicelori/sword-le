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
import argparse
from pathlib import Path
import json

import sword_le.geom_tool.generate_id as generate_id 
import sword_le.geom_tool.save_metadata as save_metadata
import sword_le.geom_tool.reach_intersection as rch_int
import sword_le.geom_tool.replacement_reconstruction as rep_build
import sword_le.geom_tool.final_geometry_reconstruction as geom_build

def replace_reach_geometry(
    sword_gdf: gpd.GeoDataFrame,
    replacement_gdf: gpd.GeoDataFrame,
    replacement_id: int = 0,
) -> tuple[gpd.GeoDataFrame, dict]:

    intersected_reaches = rch_int.find_intersected_reaches(
        sword_gdf,
        replacement_gdf,
    )

    upstream_reach, downstream_reach = (
        rch_int.find_upstream_downstream_reaches(
            intersected_reaches,
        )
    )

    replaced_reach_ids = save_metadata.find_replaced_reaches(
        sword_gdf,
        upstream_reach,
        downstream_reach,
    )

    metadata_json = save_metadata.build_metadata_json(
        upstream_reach,
        downstream_reach,
        replaced_reach_ids,
        replacement_id,
    )

    upstream_pt = rch_int.find_upstream_intersection_point(
        upstream_reach,
        replacement_gdf,
    )

    downstream_pt = rch_int.find_downstream_intersection_point(
        downstream_reach,
        replacement_gdf,
    )

    upstream_part = rch_int.keep_upstream_part(
        upstream_reach,
        upstream_pt,
    )

    downstream_part = rch_int.keep_downstream_part(
        downstream_reach,
        downstream_pt,
    )

    replacement_part = rch_int.trim_replacement_between_points(
        replacement_gdf,
        upstream_pt,
        downstream_pt,
    )

    replacement_part = rch_int.insert_pivot_points(
        replacement_part,
        upstream_pt,
        downstream_pt,
    )

    final_geometry = rep_build.build_corrected_network(
        upstream_part,
        replacement_part,
        downstream_part,
    )

    segments = rep_build.split_at_nodes(
        final_geometry,
        tolerance=1e-5,
    )

    segments, pivot_nodes = (
        rep_build.merge_non_pivot_segments(
            segments,
        )
    )

    segments = rep_build.explode_lines(
        segments,
    )
    
    utm_crs = gpd.GeoDataFrame(
        geometry=segments,
        crs="EPSG:4326",
    ).estimate_utm_crs()

    segments = [
        geom_build.reproject_geometry(
            seg,
            "EPSG:4326",
            utm_crs
        )
        for seg in segments
    ]

    segments = [
        geom_build.resample_line(
            line,
            30
        )
        for line in segments
    ]

    segments = [
        geom_build.reproject_geometry(
            seg,
            utm_crs,
            "EPSG:4326"
        )
        for seg in segments
    ]


    existing_reach_ids = set(
        sword_gdf["reach_id"]
        .dropna()
        .astype(str)
    )

    segments_for_id = [
        {
            "geometry": segment,
            "has_obstruction": False,
        }
        for segment in segments
    ]

    segments_for_id, new_reaches = (
        generate_id.generate_reaches_id(
            upstream_reach_id=(
                upstream_reach["reach_id"]
            ),
            segments=segments_for_id,
            existing_reach_ids=(
                existing_reach_ids
            ),
        )
    )
    external_upstream, external_downstream = (
        save_metadata.find_external_connectivity(
            sword_gdf,
            replaced_reach_ids,
        )
    )

    upstream_width = float(upstream_reach["width"])
    downstream_width = float(downstream_reach["width"])

    mean_width = (
        (upstream_width + downstream_width) / 2
    ) * 1.25
    metadata_json["replaced_reaches"][0]["mean_width"] = float(mean_width)

    metadata_json[
        "replaced_reaches"
    ][0]["upstream_reaches"] = (
        external_upstream
    )

    metadata_json[
        "replaced_reaches"
    ][0]["downstream_reaches"] = (
        external_downstream
    )
    metadata_json[
        "replaced_reaches"
    ][0]["new_reaches"] = [
        int(reach["reach_id"])
        for reach in new_reaches
    ]

    sword_gdf_out = (
        geom_build.rebuild_sword_network(
            sword_gdf=sword_gdf,
            replaced_ids=replaced_reach_ids,
            final_geometry=segments_for_id,
        )
    )
    for reach_id in external_upstream:
        sword_gdf_out = rep_build.set_upstream_dist_out_to_zero(
            sword_gdf_out,
            int(reach_id),
        )
    
    sword_gdf_out["reach_id"] = sword_gdf_out["reach_id"].astype(int)
  
    return (
        sword_gdf_out,
        metadata_json,
    )


def run_replace_reach_geometry(
    path_sword: str,
    path_replacement: str,
    path_output: str,
    replacement_id: int = 1,
):
    """
    Run reach replacement workflow from file paths.
    """

    sword_gdf = gpd.read_file(
        path_sword,
    )

    replacement_gdf = gpd.read_file(
        path_replacement,
    )

    sword_gdf_out, metadata_json = (
        replace_reach_geometry(
            sword_gdf=sword_gdf,
            replacement_gdf=replacement_gdf,
            replacement_id=replacement_id,
        )
    )

    output_dir = Path(path_output)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    sword_gdf_out.to_file(
        output_dir / "sword_replace.gpkg",
        driver="GPKG",
    )

    with open(
        output_dir / "sword_replace.json",
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
        "--path_replacement",
        required=True,
    )

    parser.add_argument(
        "--path_output",
        required=True,
        help="Output directory",
    )

    parser.add_argument(
        "--replacement_id",
        type=int,
        default=1,
    )

    args = parser.parse_args()

    run_replace_reach_geometry(
        path_sword=args.path_sword,
        path_replacement=args.path_replacement,
        path_output=args.path_output,
        replacement_id=args.replacement_id,
    )


if __name__ == "__main__":
    main()