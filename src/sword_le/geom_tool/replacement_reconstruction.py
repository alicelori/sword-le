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

import logging
from collections import Counter
import pandas as pd

from shapely.geometry import (
    MultiLineString,
    MultiPoint,
    LineString,
    Point,
)
from shapely.ops import linemerge, split


def explode_lines(obj):

    if isinstance(obj, list):
        exploded = []

        for item in obj:
            exploded.extend(explode_lines(item))

        return exploded

    if isinstance(obj, dict):
        geom = obj["geometry"]

        if isinstance(geom, LineString):
            return [
                {
                    **obj,
                    "geometry": geom,
                }
            ]

        if isinstance(geom, MultiLineString):
            return [
                {
                    **obj,
                    "geometry": part,
                }
                for part in geom.geoms
            ]

    elif isinstance(obj, LineString):
        return [obj]

    elif isinstance(obj, MultiLineString):
        return list(obj.geoms)

    raise ValueError(f"Unsupported geometry type: {type(obj)}")


def build_corrected_network(
    upstream_part,
    replacement_part,
    downstream_part,
):
    """
    Assemble the corrected network from the
    upstream reach, replacement network and
    downstream reach.

    Parameters
    ----------
    upstream_part : LineString

    replacement_part : LineString | MultiLineString

    downstream_part : LineString

    Returns
    -------
    LineString | MultiLineString
        Corrected merged network.
    """

    logging.info("Building corrected network")

    lines = []

    lines.extend(explode_lines(upstream_part))

    lines.extend(explode_lines(replacement_part))

    lines.extend(explode_lines(downstream_part))

    logging.info(
        "Building network from %s line elements",
        len(lines),
    )

    return linemerge(MultiLineString(lines))


def find_connection_points(
    geom,
    tolerance=1e-5,
):
    """
    Find network connection nodes.

    A connection node is an endpoint touching
    another line of the network.

    Parameters
    ----------
    geom : LineString | MultiLineString

    tolerance : float

    Returns
    -------
    list[Point]
        Connection points.
    """

    logging.info("Searching connection points")

    lines = explode_lines(geom)

    connection_points = []

    for i, line1 in enumerate(lines):
        endpoints = [
            Point(line1.coords[0]),
            Point(line1.coords[-1]),
        ]

        for endpoint in endpoints:
            for j, line2 in enumerate(lines):
                if i == j:
                    continue

                if endpoint.distance(line2) < tolerance:
                    connection_points.append(endpoint)

                    break

    logging.info(
        "Found %s connection point(s)",
        len(connection_points),
    )

    return connection_points


def split_at_nodes(
    multiline,
    tolerance=1e-5,
):
    """
    Split a network at all detected connection
    points.

    Parameters
    ----------
    multiline : LineString | MultiLineString

    tolerance : float

    Returns
    -------
    list[LineString]
        Segments generated after splitting.
    """

    logging.info("Splitting network at connection points")

    nodes = find_connection_points(
        multiline,
        tolerance=tolerance,
    )

    if not nodes:
        logging.info("No connection points found")

        if multiline.geom_type == "LineString":
            return [multiline]

        return list(multiline.geoms)

    splitter = MultiPoint(nodes)

    segments = []

    for line in multiline.geoms:
        try:
            parts = split(
                line,
                splitter,
            )

            segments.extend(parts.geoms)

        except Exception:
            segments.append(line)

    logging.info(
        "Generated %s segments after split",
        len(segments),
    )

    return segments


def merge_non_pivot_segments(
    segments,
    precision=6,
):
    """
    Identify pivot nodes and merge connected
    segments.

    A pivot node is defined as a node whose
    degree is greater than 2.

    Parameters
    ----------
    segments : list[LineString]

    precision : int

    Returns
    -------
    tuple
        (
            merged_geometry,
            pivot_nodes,
        )
    """

    logging.info("Merging non-pivot segments")

    endpoints = []

    for line in segments:
        endpoints.append(
            (
                round(
                    line.coords[0][0],
                    precision,
                ),
                round(
                    line.coords[0][1],
                    precision,
                ),
            )
        )

        endpoints.append(
            (
                round(
                    line.coords[-1][0],
                    precision,
                ),
                round(
                    line.coords[-1][1],
                    precision,
                ),
            )
        )

    count = Counter(endpoints)

    pivot_nodes = [node for node, degree in count.items() if degree > 2]

    logging.info(
        "Detected %s pivot node(s)",
        len(pivot_nodes),
    )

    merged = linemerge(MultiLineString(segments))

    logging.info("Segment merging completed")

    return (
        merged,
        pivot_nodes,
    )

def get_upstream_network(
    reaches_gdf,
    start_reach_id,
):

    up_cols = sorted(
        [
            col
            for col in reaches_gdf.columns
            if col.startswith("rch_id_up_")
        ]
    )

    visited = set()
    to_visit = [int(start_reach_id)]

    while to_visit:
        reach_id = to_visit.pop()

        if reach_id in visited:
            continue

        visited.add(reach_id)

        row = reaches_gdf.loc[
            reaches_gdf["reach_id"] == int(reach_id)
        ]
        if row.empty:
            continue

        for col in up_cols:
            up_id = row[col].iloc[0]

            # 0 = pas de reach amont
            if pd.isna(up_id) or up_id == 0:
                continue

            up_id = int(up_id)

            if up_id not in visited:
                to_visit.append(up_id)

    return reaches_gdf.loc[
        reaches_gdf["reach_id"].isin(visited)
    ].copy()
 

def set_upstream_dist_out_to_zero(
    reaches_gdf,
    start_reach_id,
):
    upstream_gdf = get_upstream_network(
        reaches_gdf,
        start_reach_id,
    )
    reaches_gdf = reaches_gdf.copy()
    reaches_gdf.loc[
        reaches_gdf["reach_id"].isin(
            upstream_gdf["reach_id"]
        ),
        "dist_out",
    ] = 0

    reaches_gdf.loc[
            reaches_gdf["reach_id"].isin(
                upstream_gdf["reach_id"]
            ),
            "dist_out_dijkstra",
        ] = 0


    return reaches_gdf
