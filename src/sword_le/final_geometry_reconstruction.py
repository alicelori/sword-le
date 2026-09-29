#!/usr/bin/env python3
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

import geopandas as gpd
from shapely.geometry import shape


def rebuild_sword_network(
    sword_features,
    replaced_ids,
    final_geometry,
    crs="EPSG:4326",
):
    """
    Rebuild a SWORD layer by removing features belonging
    to replaced reaches and appending replacement features.
    """

    rows = []

    # Existing SWORD features
    for feature in sword_features:
        properties = dict(feature["properties"])

        reach_id = properties.get("reach_id")

        if reach_id in replaced_ids:
            continue

        properties["geometry"] = shape(feature["geometry"])

        rows.append(properties)

    # Accept either a GeoDataFrame or a list of dicts
    if isinstance(final_geometry, gpd.GeoDataFrame):
        final_geometry = final_geometry.to_dict("records")
    # Collect all columns
    all_columns = set()

    for row in rows:
        all_columns.update(row.keys())

    for feature in final_geometry:
        all_columns.update(feature.keys())

    # Append replacement features
    for feature in final_geometry:
        row = {col: None for col in all_columns}
        row.update(feature)
        rows.append(row)

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs=crs,
    )
