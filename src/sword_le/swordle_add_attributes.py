#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) CS GROUP 2026
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
Adding reach_len, x, and y to the corrected SWORD's features.

Author : Abderrahmane AICHE (CS GROUP)

Version : Python  3.10

Description:
    This script reads an input shapefile (the output of the pipeline: swordle_prod_upgrade.py),
    identifies features whose properties are all None,
    computes the length of the segment (reach_len) in meters for these features,
    and then adds the x and y coordinates of the midpoint of the reach.
    Finally, it writes a new output shapefile with the modifications.

Generated output (shapefiles):
    - An output shapefile containing updated features (reach_len, x, y)
      for the corrected reaches in SWORD.

"""

import argparse
import logging

import fiona
from shapely.geometry import LineString

from sword_le import swordle


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Adding reach_len, x, and y to the corrected SWORD's features."
    )
    parser.add_argument("--file", required=True, help="Input shapefile")
    parser.add_argument("--outputfile", required=True, help="Ouput shapefile")
    return parser.parse_args()


def main():
    """Main entry point of the program."""
    args = parse_args()
    input_file = args.file
    output_file = args.outputfile
    logger = logging.getLogger("swordle_add_attributes")

    # Step 1 — Select features where all properties are None
    features_none = []
    with fiona.open(input_file, "r") as src:
        for feat in src:
            props = feat["properties"]
            if all(v is None for v in props.values()):
                features_none.append(feat)

    logger.info(
        "%s reaches where all properties are None", {len(features_none)}
    )

    # Step 2 — Add reach_len
    updated_features = []
    for feat in features_none:
        # Calcul via swordle
        reach_len = swordle.compute_reach_length(feat)  # metres
        props = dict(feat.properties)
        props["reach_len"] = reach_len

        # Keep the geometry as it is
        new_feat = fiona.Feature(
            id=feat.id, geometry=feat.geometry, properties=props
        )
        updated_features.append(new_feat)

    # Step 3 — Add x and y starting from the midpoint (reach_len / 2)
    updated_features1 = []
    for feat in updated_features:
        geom = feat.geometry
        # Reconstruct the LineString from coordinates :
        coords = geom["coordinates"]
        line = LineString(coords)

        reach_len = feat.properties.get("reach_len")
        if reach_len is None:
            # If reach_len could not be calculated
            continue

        mid_point = line.interpolate(reach_len / 2.0)

        props = dict(feat.properties)
        props["x"] = float(mid_point.x)
        props["y"] = float(mid_point.y)

        updated_features1.append(
            fiona.Feature(id=feat.id, geometry=geom, properties=props)
        )

    # Index by id
    updated_by_id = {f.id: f for f in updated_features1}

    # Step 4 — Writing :
    with fiona.open(input_file, "r") as src:
        schema = src.schema.copy()
        crs = src.crs
        driver = src.driver

        with fiona.open(
            output_file, "w", driver=driver, crs=crs, schema=schema
        ) as dst:
            for feature in src:
                # If the feature has been updated, the modified version is written.
                if feature.id in updated_by_id:
                    dst.write(updated_by_id[feature.id])
                else:
                    # Otherwise, it is left unchanged
                    dst.write(feature)
    logger.info(
        "File updated with new properties of the corrected reaches : %s",
        {output_file},
    )


if __name__ == "__main__":
    main()
