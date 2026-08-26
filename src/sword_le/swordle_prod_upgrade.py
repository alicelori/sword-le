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

"""
Author : Abderrahmane AICHE (CS GROUP)
Date : 23/01/2026
''Adjusting script for new logic functions : find_upstream_downstream_reaches_using_mask''

Version : Python  3.10

Description :
SWORDLE pipeline (Selection, SWORD correction, and shapefile export).
Output (gpkg) :
sword.gpkg
"""

import argparse
import json
import logging
import os
import sys
import fiona
import geopandas as gpd
from pathlib import Path
from sword_le import swordle
from generate_id import generate_reaches_id
from save_metadata import (
    find_replaced_reaches,
    save_boundary_reaches,
    add_new_reaches_to_json,
)
from sword_segmentation import (
    split_long_lines,
    cut_at_obstructions,
    load_obstructions,
    merge_short_reaches,
)
from create_nodes import create_nodes_on_reach
from reconstruct_sword import rebuild_sword_network
from tools.geom_utils import resample_line
# ========================================================================================
# Utility functions for saving ESRI shapefiles
# ========================================================================================


def ensure_dir(path: str):
    """Create dir"""
    if path and not Path(path).is_dir():
        Path(path).mkdir(parents=True, exist_ok=True)


def read_default_attributes(json_path: str) -> dict:
    """Read default attributes."""
    with open(json_path, encoding="utf-8") as fin:
        return json.load(fin)


# ========================================================================================
# Pipeline principal
# ========================================================================================


def run_pipeline(
    sword_path: str,
    replacement_path: str,
    obstruction_path: str,
    results_dir: str,
):
    """Run pipeline"""
    logger = logging.getLogger("swordle_prod")

    # Preparation
    ensure_dir(results_dir)
    logger.info("Result dir: %s", results_dir)

    logger.info("Loading source (SWORD reaches): %s", sword_path)
    src = fiona.open(sword_path, "r")

    logger.info("Loading replacement (TOPAGE): %s", replacement_path)
    rep = fiona.open(replacement_path, "r")
    logger.info("Element replacement: %d", len(rep))

    intersected_reaches = swordle.find_intersected_reaches(
        src,
        rep,
    )
    (
        upstream_reach,
        downstream_reach,
    ) = swordle.find_upstream_downstream_reaches(
        intersected_reaches,
    )
    replaced_reach_ids = find_replaced_reaches(src, upstream_reach, downstream_reach)
    metadata_json = save_boundary_reaches(
        upstream_reach, downstream_reach, results_dir, replaced_reach_ids
    )

    upstream_intersection_point = swordle.find_upstream_intersection_point(
        upstream_reach,
        rep,
    )

    downstream_intersection_point = swordle.find_downstream_intersection_point(
        downstream_reach,
        rep,
    )

    upstream_part = swordle.keep_upstream_part(
        upstream_reach,
        upstream_intersection_point,
    )

    downstream_part = swordle.keep_downstream_part(
        downstream_reach,
        downstream_intersection_point,
    )

    replacement_part = swordle.trim_replacement_between_points(
        rep,
        upstream_intersection_point,
        downstream_intersection_point,
    )

    replacement_part = swordle.insert_pivot_points(
        replacement_part,
        upstream_intersection_point,
        downstream_intersection_point,
    )
    final_geometry = swordle.build_corrected_network(
        upstream_part,
        replacement_part,
        downstream_part,
    )

    segments = swordle.split_at_nodes(
        final_geometry,
        tolerance=1e-5,
    )
    segments, pivot_nodes = swordle.merge_non_pivot_segments(segments)

    segments = swordle.explode_lines(segments)

    utm_crs = gpd.GeoDataFrame(
        geometry=segments,
        crs="EPSG:4326",
    ).estimate_utm_crs()

    segments = [
        swordle.reproject_geometry(seg, "EPSG:4326", utm_crs) for seg in segments
    ]
    segments = [resample_line(line, 30) for line in segments]

    if obstruction_path and Path(obstruction_path).exists():
        logger.info(
            "Loading obstruction database: %s",
            obstruction_path,
        )

        obstruction_points = load_obstructions(obstruction_path, utm_crs)

        segments = cut_at_obstructions(
            segments,
            obstruction_points,
        )

    else:
        logger.info("No obstruction database found. Skipping obstruction processing.")

    segments = split_long_lines(segments)
    segments = merge_short_reaches(
        segments,
        pivot_nodes,
    )
    segments = swordle.explode_lines(segments)

    segments, new_reaches = generate_reaches_id(
        upstream_reach["properties"]["reach_id"],
        segments,
    )
    add_new_reaches_to_json(
        metadata_json,
        new_reaches,
    )

    nodes_gdf = create_nodes_on_reach(segments, utm_crs, spacing=200.0)

    segments = [
        {
            **seg,
            "geometry": swordle.reproject_geometry(
                seg["geometry"],
                utm_crs,
                "EPSG:4326",
            ),
        }
        for seg in segments
    ]

    segments = swordle.orient_reaches_downstream_to_upstream(
        segments,
        downstream_reach,
    )

    nodes_gdf.to_file(
        Path(results_dir) / "replacement_nodes.gpkg",
        driver="GPKG",
    )

    gdf = rebuild_sword_network(
        sword_features=src,
        replaced_ids=replaced_reach_ids,
        final_geometry=segments,
    )

    gdf.to_file(
        Path(results_dir) / "sword.gpkg",
        driver="GPKG",
    )

    logger.info(
        "Processing completed successfully => Results generated in the directory : %s",
        results_dir,
    )


def build_arg_parser():
    """Build argument parser"""
    p = argparse.ArgumentParser(
        description="SWORDLE pipeline (Selection, SWORD correction, and shapefile export)"
    )
    p.add_argument("--sword", required=True, help="Shapefile SWORD (reaches)")
    p.add_argument(
        "--obs_bd",
        required=False,
        default=None,
        help="Give obstruction database",
    )
    p.add_argument(
        "--replacement", required=True, help="Shapefile replacement (TOPAGE)"
    )
    p.add_argument("--results", required=True, help="Output folder for shapefiles.")
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Niveau de log (défaut: INFO).",
    )
    return p


def main():
    """Main function"""
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # Check paths
    for label, path in (
        ("sword", args.sword),
        ("replacement", args.replacement),
    ):
        if not Path(path).exists():
            logging.error("The specified path for --%s doesn't exist : %s", label, path)
            sys.exit(1)

    try:
        run_pipeline(
            sword_path=args.sword,
            replacement_path=args.replacement,
            obstruction_path=args.obs_bd,
            results_dir=args.results.rstrip(os.sep) + os.sep,
        )
    except Exception as e:
        logging.exception("Pipeline failed : %s", str(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
