#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
Output (shapefiles) :
 - test_rep_masked_out.shp
 - test_rep_masked_in.shp
 - test_src_masked_out.shp
 - test_points.shp
 - test_src_up_reach.shp
 - test_src_dw_reach.shp
 - test_rep_keeped.shp
 - test_src_keeped.shp
 - test_new_up_reach.shp
 - test_new_dw_reach.shp
 - test_complete.shp
"""

import argparse
import json
import logging
import os
import sys

import fiona
from shapely.geometry import mapping, shape

from sword_le import swordle

# ========================================================================================
# Utility functions for saving ESRI shapefiles
# ========================================================================================


def ensure_dir(path: str):
    """Create dir"""
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def load_first_geometry(shp_path: str):
    """Load the first feature geometry from a shapefile (ex: polygon mask)."""
    with fiona.open(shp_path, "r") as src:
        for feat in src:
            return shape(feat["geometry"])
    raise ValueError(f"No geometry found in {shp_path}")


def read_default_attributes(json_path: str) -> dict:
    """Read default attributes."""
    with open(json_path, "r", encoding="utf-8") as fin:
        return json.load(fin)


def _extract_geom_and_props(feature):
    """
    Return (geometry_mapping, properties) from heterogeneous input :
      - dict Fiona (Feature ou geometry)
      - objet avec __geo_interface__ (Feature ou geometry)
      - Shapely geometry
    """
    # Dict Fiona
    if isinstance(feature, dict):
        if feature.get("type") == "Feature" and "geometry" in feature:
            geom_mapping = feature["geometry"]
            props = feature.get("properties", {})
        elif "geometry" in feature:
            geom_mapping = feature["geometry"]
            props = feature.get("properties", {})
        else:
            # Mapping direct geometry
            geom_mapping = feature
            props = {}
        return mapping(shape(geom_mapping)), props

    # Object GeoPython with __geo_interface__
    if hasattr(feature, "__geo_interface__"):
        gi = feature.__geo_interface__
        if gi.get("type") == "Feature":
            geom_mapping = gi["geometry"]
            props = gi.get("properties", {})
        else:
            geom_mapping = gi
            props = getattr(feature, "properties", {})
        return mapping(shape(geom_mapping)), props

    # Shapely Geometry
    try:
        return mapping(feature), getattr(feature, "properties", {})
    except Exception as exc:
        raise TypeError(
            f"Unsupported feature type for Fiona writing: {type(feature)}"
        ) from exc


def adapt_feature(feature, schema, default_attributes):
    """
    Adapt a feature to the output schema/CRS :
      - normalized geometry (mapping GeoJSON)
      - properties restricted to schema keys, filled with default values
    """
    geom, props_src = _extract_geom_and_props(feature)
    props_out = {
        key: props_src.get(key, default_attributes.get(key, None))
        for key in schema["properties"].keys()
    }
    return {"geometry": geom, "properties": props_out}


def _geom_equals(a, b, tol: float = 0.0) -> bool:
    """
    Compare geometric equality between two non-identical features
    - tol: Tolerance for equals_exact (0.0 by défaut), fallback to topological equals.
    """
    try:
        ga, _ = _extract_geom_and_props(a)
        gb, _ = _extract_geom_and_props(b)
        sa = shape(ga)
        sb = shape(gb)
        return sa.equals_exact(sb, tol) or sa.equals(sb)
    except Exception:
        return False


def write_features(path, features, schema, crs, default_attributes):
    """Write a list of features to a shapefile according to a given schema/CRS."""
    ensure_dir(os.path.dirname(path))
    with fiona.open(
        path, "w", driver="ESRI Shapefile", crs=crs, schema=schema
    ) as fout:
        for feature in features:
            fout.write(adapt_feature(feature, schema, default_attributes))


# ========================================================================================
# Pipeline principal
# ========================================================================================


def run_pipeline(
    mask_path: str,
    sword_path: str,
    logic: str,
    replacement_path: str,
    default_attr_path: str,
    results_dir: str,
):
    """Run pipeline"""
    logger = logging.getLogger("swordle_prod")

    # Preparation
    ensure_dir(results_dir)
    logger.info("Result dir: %s", results_dir)

    # Load data
    logger.info("Loading mask: %s", mask_path)
    mask = load_first_geometry(mask_path)

    logger.info("Loading source (SWORD reaches): %s", sword_path)
    src = fiona.open(sword_path, "r")

    logger.info("Loading replacement (TOPAGE): %s", replacement_path)
    rep = fiona.open(replacement_path, "r")
    logger.info("Element replacement: %d", len(rep))

    logger.info("Loading default attributes: %s", default_attr_path)
    default_attributes = read_default_attributes(default_attr_path)

    # ========================================================================================
    # 1 - Selection via mask
    # ========================================================================================
    logger.info("Selection of reaches outside the mask on the source (SWORD)")
    src_masked_out = swordle.select_reaches_using_mask(src, mask, where="out")

    logger.info("Selection in/out on the replacement layer (TOPAGE)")
    rep_masked_in = swordle.select_reaches_using_mask(
        rep, mask, where="in", crs=rep.crs
    )
    rep_masked_out = swordle.select_reaches_using_mask(
        rep, mask, where="out", crs=rep.crs
    )

    logger.info("Apply default attributes on the replacement layer (in/out)")
    rep_masked_in = swordle.apply_default_attributes(
        rep_masked_in, default_attributes
    )
    rep_masked_out = swordle.apply_default_attributes(
        rep_masked_out, default_attributes
    )

    # ========================================================================================
    # 2 - Adjustment to mask boundaries
    # ========================================================================================
    logger.info("Search for upstream/downstream reaches to be corrected")
    if logic == "1":
        logic_func = swordle.find_upstream_downstream_reaches_using_mask_logic1

    else:
        logic_func = swordle.find_upstream_downstream_reaches_using_mask_logic2

    logger.info("Use of %s logic for upstream/downstream selection.", logic)

    src_upstream_reach, src_downstream_reach = logic_func(src_masked_out, mask)

    logger.info("Search intersection points near mask")
    upstream_intersection_point = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_upstream_reach, mask
        )
    )
    downstream_intersection_point = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_downstream_reach, mask
        )
    )

    logger.info("Correct upstream/downstream reaches with intersection points")
    upstream_reach = swordle.correct_reach_using_intersection_point(
        rep=rep_masked_out,
        src_reach=src_upstream_reach,
        intersection_point=upstream_intersection_point,
        mask=mask,
    )
    downstream_reach = swordle.correct_reach_using_intersection_point(
        rep=rep_masked_out,
        src_reach=src_downstream_reach,
        intersection_point=downstream_intersection_point,
        mask=mask,
    )

    # ========================================================================================
    # 3 - Adjustment of replacement reaches inside the mask (confluences)
    # ========================================================================================
    logger.info(
        "Adjustment of replacement reaches inside the mask (confluences)"
    )
    rectified_rep_features, upstream_reach, downstream_reach = (
        swordle.adjust_reaches_with_confluence_using_mask(
            rep_masked_in, upstream_reach, downstream_reach, mask
        )
    )

    # Default attributes on final objects
    rectified_rep_features = swordle.apply_default_attributes(
        rectified_rep_features, default_attributes
    )
    upstream_reach["properties"] = default_attributes
    downstream_reach["properties"] = default_attributes

    # ========================================================================================
    # 4 - Save
    # ========================================================================================
    logger.info("Writting output shapefiles")

    # We use the source schema/CRS as a basis for standardization
    src_schema = src.schema
    src_crs = src.crs

    # Selection files
    write_features(
        os.path.join(results_dir, "test_rep_masked_out.shp"),
        rep_masked_out,
        src_schema,
        src_crs,
        default_attributes,
    )
    write_features(
        os.path.join(results_dir, "test_rep_masked_in.shp"),
        rep_masked_in,
        src_schema,
        src_crs,
        default_attributes,
    )
    write_features(
        os.path.join(results_dir, "test_src_masked_out.shp"),
        src_masked_out,
        src_schema,
        src_crs,
        default_attributes,
    )

    # Intersection points
    points_schema = {"geometry": "Point", "properties": {}}
    with fiona.open(
        os.path.join(results_dir, "test_points.shp"),
        "w",
        driver="ESRI Shapefile",
        crs=src_crs,
        schema=points_schema,
    ) as fout:
        fout.write(
            {"geometry": mapping(upstream_intersection_point), "properties": {}}
        )
        fout.write(
            {
                "geometry": mapping(downstream_intersection_point),
                "properties": {},
            }
        )

    # Individuals reaches
    write_features(
        os.path.join(results_dir, "test_src_up_reach.shp"),
        [src_upstream_reach],
        src_schema,
        src_crs,
        default_attributes,
    )
    write_features(
        os.path.join(results_dir, "test_src_dw_reach.shp"),
        [src_downstream_reach],
        src_schema,
        src_crs,
        default_attributes,
    )
    write_features(
        os.path.join(results_dir, "test_rep_keeped.shp"),
        rectified_rep_features,
        src_schema,
        src_crs,
        default_attributes,
    )

    # Source reaches kept (excluding upstream/downstream)
    src_keeped = [
        f
        for f in src_masked_out
        if not (
            _geom_equals(f, src_upstream_reach)
            or _geom_equals(f, src_downstream_reach)
        )
    ]
    write_features(
        os.path.join(results_dir, "test_src_keeped.shp"),
        src_keeped,
        src_schema,
        src_crs,
        default_attributes,
    )

    # Corrected reaches
    write_features(
        os.path.join(results_dir, "test_new_up_reach.shp"),
        [upstream_reach],
        src_schema,
        src_crs,
        default_attributes,
    )
    write_features(
        os.path.join(results_dir, "test_new_dw_reach.shp"),
        [downstream_reach],
        src_schema,
        src_crs,
        default_attributes,
    )

    # Complete shapefile
    complete_path = os.path.join(results_dir, "test_complete.shp")
    with fiona.open(
        complete_path,
        "w",
        driver="ESRI Shapefile",
        crs=src_crs,
        schema=src_schema,
    ) as fout:
        fout.write(
            adapt_feature(upstream_reach, src_schema, default_attributes)
        )
        fout.write(
            adapt_feature(downstream_reach, src_schema, default_attributes)
        )
        for feature in src_keeped:
            fout.write(adapt_feature(feature, src_schema, default_attributes))
        for feature in rectified_rep_features:
            fout.write(adapt_feature(feature, src_schema, default_attributes))

    logger.info(
        "Processing completed successfully => Results generated in the directory : %s",
        results_dir,
    )


def build_arg_parser():
    """Build argument parser"""
    p = argparse.ArgumentParser(
        description="SWORDLE pipeline (Selection, SWORD correction, and shapefile export)"
    )
    p.add_argument("--mask", required=True, help="Shapefile mask (polygone)")
    p.add_argument("--sword", required=True, help="Shapefile SWORD (reaches)")
    p.add_argument(
        "--logic",
        required=False,
        choices=["1", "2"],
        default="2",
        help="Choice of logic for upstream/downstream selection (1 or 2). Default : 2.",
    )
    p.add_argument(
        "--replacement", required=True, help="Shapefile replacement (TOPAGE)"
    )
    p.add_argument(
        "--default-attributes",
        required=True,
        help="JSON default attributes",
    )
    p.add_argument(
        "--results", required=True, help="Output folder for shapefiles."
    )
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
    for label, path in [
        ("mask", args.mask),
        ("sword", args.sword),
        ("replacement", args.replacement),
        ("default-attributes", args.default_attributes),
    ]:
        if not os.path.exists(path):
            logging.error(
                "The specified path for --%s doesn't exist : %s", label, path
            )
            sys.exit(1)

    try:
        run_pipeline(
            mask_path=args.mask,
            sword_path=args.sword,
            logic=args.logic,
            replacement_path=args.replacement,
            default_attr_path=args.default_attributes,
            results_dir=args.results.rstrip(os.sep) + os.sep,
        )
    except Exception as e:
        logging.exception("Pipeline failed : %s", str(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
