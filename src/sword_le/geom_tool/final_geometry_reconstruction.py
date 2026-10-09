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
import pandas as pd

import numpy as np
from shapely import line_interpolate_point
from shapely.geometry import LineString
from pyproj import Transformer
from shapely.ops import transform


def resample_line(line, step):
    distances = np.arange(0, line.length, step)
    distances = np.append(distances, line.length)

    return LineString([line_interpolate_point(line, d).coords[0] for d in distances])


def reproject_geometry(
    geom,
    source_crs,
    target_crs,
):
    transformer = Transformer.from_crs(
        source_crs,
        target_crs,
        always_xy=True,
    )

    return transform(
        transformer.transform,
        geom,
    )

def rebuild_sword_network(
    sword_gdf,
    replaced_ids,
    final_geometry,
):

    remaining = sword_gdf.loc[
        ~sword_gdf["reach_id"].isin(replaced_ids)
    ].copy()

    if not isinstance(final_geometry, gpd.GeoDataFrame):

        first = final_geometry[0]

        if hasattr(first, "geom_type"):
            final_geometry = gpd.GeoDataFrame(
                geometry=final_geometry,
                crs=sword_gdf.crs,
            )

        else:
            final_geometry = gpd.GeoDataFrame(
                final_geometry,
                crs=sword_gdf.crs,
            )

    return gpd.GeoDataFrame(
        pd.concat(
            [remaining, final_geometry],
            ignore_index=True,
            sort=False,
        ),
        geometry="geometry",
        crs=sword_gdf.crs,
    )