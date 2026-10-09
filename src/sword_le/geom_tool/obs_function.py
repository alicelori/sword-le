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

def get_obstructions_on_reach(
    reach_geom,
    obstruction_gdf,
    buffer_distance,
):
    """
    Return only obstruction points located
    on or very close to a reach.
    """

    reach_buffer = reach_geom.buffer(
        buffer_distance
    )

    idx = list(
        obstruction_gdf.sindex.intersection(
            reach_buffer.bounds
        )
    )

    candidates = obstruction_gdf.iloc[idx]

    return candidates.loc[
        candidates.intersects(
            reach_buffer
        )
    ]


from shapely.ops import linemerge, substring


def split_segment_at_obstruction(
    seg,
    obstruction,
    cut_distance,
    min_length=150.0,
):

    distance_along = seg.project(
        obstruction
    )

    start_cut = max(
        0.0,
        distance_along - cut_distance,
    )

    end_cut = min(
        seg.length,
        distance_along + cut_distance,
    )

    before = substring(
        seg,
        0,
        start_cut,
    )

    middle = substring(
        seg,
        start_cut,
        end_cut,
    )

    after = substring(
        seg,
        end_cut,
        seg.length,
    )

    if (
        before.length > 0
        and before.length < min_length
        and middle.length > 0
    ):
        middle = linemerge(
            [before, middle]
        )
        before = None

    if (
        after.length > 0
        and after.length < min_length
        and middle.length > 0
    ):
        middle = linemerge(
            [middle, after]
        )
        after = None

    output = []

    if (
        before is not None
        and before.length > 0
    ):
        output.append(
            {
                "geometry": before,
                "has_obstruction": False,
            }
        )

    if (
        middle is not None
        and middle.length > 0
    ):
        output.append(
            {
                "geometry": middle,
                "has_obstruction": True,
            }
        )

    if (
        after is not None
        and after.length > 0
    ):
        output.append(
            {
                "geometry": after,
                "has_obstruction": False,
            }
        )

    return output