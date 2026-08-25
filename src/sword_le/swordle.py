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

"""Main functions of swordle"""

import logging
import math
from collections import Counter, deque
import matplotlib.pyplot as plt
import numpy as np
import pyproj

from geopy.distance import distance, lonlat
from shapely.geometry import (
    MultiLineString,
    MultiPoint,
    LineString,
    Point,
    mapping,
    shape,
)
from shapely.ops import linemerge, snap, split, transform, unary_union

logger = logging.getLogger("swordle")


def create_nodes(reaches, default_attributes, spacing=200.0):
    """Create nodes on every reaches in a list

    Arguments
    ---------
        reaches : list
            List of reaches
            (dictionaries following the Python geo protocol, as in a fiona.Collection)
        spacing : float
            Prescribed spacing between nodes
            (the actual spacing will differ to ensure equal spacing between nodes)

    Returns
    -------
        nodes : list
            List of nodes
            (dictionaries following the Python geo protocol, as in a fiona.Collection)

    """

    # Loop on features in reaches to extract segments
    # Segments are tuples
    # (LineString, feature index in the source, index of the LineString in the source geometry)
    segments = []
    for feature_index, feature in enumerate(reaches):
        # Retrieve geometry of the feature
        geometry = shape(feature["geometry"])

        # Retrieve reach id
        reach_id = feature["properties"]["reach_id"]

        if geometry.geom_type == "MultiLineString":
            # Extract LineStrings of a MultiLineString object
            for index, geom in enumerate(geometry.geoms):
                segments.append((geom, feature_index, index, reach_id))

        elif geometry.geom_type == "LineString":
            # Store LineString
            segments.append((geometry, feature_index, 0, reach_id))

        else:
            raise RuntimeError(f"Cannot process geometry of type {geometry.geom_type}")

    # Loop on segments to create nodes
    nodes = []
    reach_nodes_count_dict = {}
    for segment in segments:
        # Retrieve objects from the tuple
        geometry, feature_index, _, reach_id = segment
        reach_type = int(reach_id[-1])

        # Compute length (in meters) of the linestring using geopy.distance.distance
        coords = list(geometry.coords)
        lon1, lat1 = coords[0]
        dist = 0.0
        for lon2, lat2 in coords[1:]:
            dist += distance(lonlat(lon1, lat1), lonlat(lon2, lat2)).meters
            lon1, lat1 = lon2, lat2

        # Compute number of nodes
        nnodes = int(math.floor(dist / spacing))

        # Compute actual spacing
        actual_spacing = dist / float(nnodes)

        # Initialise next node dist to 0.5 * actual_spacing
        next_node_dist = 0.5 * actual_spacing

        # Initialise current distance and node_index to zero
        dist = 0.0
        node_index = 0

        # Retrieve coordinates of the first node in the geometry
        lon1, lat1 = coords[0]

        # Loop on remaining points in the geometry
        for lon2, lat2 in coords[1:]:
            # Compute distance increment between current Point2 and Point1
            ddist = distance(lonlat(lon1, lat1), lonlat(lon2, lat2)).meters

            if dist + ddist >= next_node_dist:
                # Create a new node as dist + ddist >= next_node_dist
                alpha = (next_node_dist - dist) / ddist
                lon = lon1 + alpha * (lon2 - lon1)
                lat = lat1 + alpha * (lat2 - lat1)
                # new_node_geometry = Point(
                #    (lon, lat)
                # )
                new_node = {
                    "geometry": mapping(Point((lon, lat))),
                    "properties": default_attributes.copy(),
                }
                node_index += 1
                new_node["properties"]["node_id"] = (
                    f"{reach_id[:-1]}{node_index:04d}{reach_type}"
                )
                nodes.append(new_node)
                # nodes.append(new_node(Point((lon, lat)), feature_index, subindex, len(nodes)+1))

                # Increment next_node_dist
                next_node_dist += actual_spacing

            # Increment current distance
            dist += ddist

            # Pass Point2 coordinates to Point 1 for the next loop iteration
            lon1, lat1 = lon2, lat2

        logger.info("Created %i nodes on segment %i", nnodes, feature_index)

        if reach_id not in reach_nodes_count_dict:
            reach_nodes_count_dict[reach_id] = node_index
        else:
            reach_nodes_count_dict[reach_id] += node_index

    # Set nodes counts
    for feature in reaches:
        reach_id = feature["properties"]["reach_id"]
        feature["properties"]["n_nodes"] = reach_nodes_count_dict[reach_id]

    return nodes


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


def are_connected(
    line1,
    line2,
    tolerance=1e-5,
):
    """
    Check whether two reaches are connected.

    Connectivity is evaluated using reach
    endpoints and endpoint-to-line distances.

    Parameters
    ----------
    line1 : LineString
        First reach.

    line2 : LineString
        Second reach.

    tolerance : float, optional
        Distance tolerance used to determine
        connectivity.

    Returns
    -------
    bool
        True if the reaches are connected,
        False otherwise.
    """

    logging.debug("Checking connectivity between two reaches")

    endpoints1 = [
        Point(line1.coords[0]),
        Point(line1.coords[-1]),
    ]

    endpoints2 = [
        Point(line2.coords[0]),
        Point(line2.coords[-1]),
    ]

    for p1 in endpoints1:
        if p1.distance(line2) < tolerance:
            return True

        for p2 in endpoints2:
            if p1.distance(p2) < tolerance:
                return True

    return False


def find_intersected_reaches(
    sword_features,
    replacement_features,
):
    """
    Find all SWORD reaches intersecting the
    replacement network.

    Parameters
    ----------
    sword_features : list[dict]
        SWORD GeoJSON features.

    replacement_features : list[dict]
        Replacement GeoJSON features.

    Returns
    -------
    list[dict]
        Intersected SWORD reaches.
    """

    logging.info("Searching for intersected SWORD reaches")

    intersected_reaches = []

    for sword_feature in sword_features:
        sword_geom = shape(sword_feature["geometry"])

        for replacement_feature in replacement_features:
            replacement_geom = shape(replacement_feature["geometry"])

            if sword_geom.intersects(replacement_geom):
                intersected_reaches.append(sword_feature)

                break

    logging.info(
        "Found %s intersected reaches",
        len(intersected_reaches),
    )

    return intersected_reaches


def find_upstream_downstream_reaches(
    intersected_reaches,
):
    """
    Identify upstream and downstream reaches
    among intersected reaches.

    Upstream reach is the feature with the
    maximum dist_out value.

    Downstream reach is the feature with the
    minimum dist_out value.

    Parameters
    ----------
    intersected_reaches : list[dict]

    Returns
    -------
    tuple(dict, dict)
        upstream_reach,
        downstream_reach
    """

    logging.info("Finding upstream and downstream reaches")

    upstream_reach = max(
        intersected_reaches,
        key=lambda f: f["properties"]["dist_out"],
    )

    downstream_reach = min(
        intersected_reaches,
        key=lambda f: f["properties"]["dist_out"],
    )

    logging.info("Selected upstream and downstream reaches")

    return (
        upstream_reach,
        downstream_reach,
    )


def find_upstream_intersection_point(
    upstream_reach,
    replacement_features,
):
    """
    Find the upstream-most intersection point
    between the upstream reach and the
    replacement network.

    Parameters
    ----------
    upstream_reach : dict
        SWORD reach.

    replacement_features : list[dict]
        Replacement GeoJSON features.

    Returns
    -------
    Point
        Upstream intersection point.
    """

    logging.info("Searching upstream intersection point")

    reach_geom = shape(upstream_reach["geometry"])

    points = []

    for replacement_feature in replacement_features:
        replacement_geom = shape(replacement_feature["geometry"])

        inter = reach_geom.intersection(replacement_geom)

        if inter.is_empty:
            continue

        if inter.geom_type == "Point":
            points.append(inter)

        elif inter.geom_type == "MultiPoint":
            points.extend(inter.geoms)

    if not points:
        raise ValueError("No upstream intersection point found.")

    point = max(
        points,
        key=lambda p: reach_geom.project(p),
    )

    logging.info(
        "Upstream intersection located at (%s, %s)",
        point.x,
        point.y,
    )

    return point


def trim_replacement_between_points(
    replacement_features,
    upstream_point,
    downstream_point,
):
    """
    Trim the replacement network between the upstream
    and downstream intersection points.

    The line intersecting the upstream point is trimmed
    after the intersection. The line intersecting the
    downstream point is trimmed before the intersection.
    Intermediate replacement lines are preserved.

    Parameters
    ----------
    replacement_features : list[dict]
        Replacement GeoJSON features.

    upstream_point : Point
        Upstream intersection point.

    downstream_point : Point
        Downstream intersection point.

    Returns
    -------
    MultiLineString
        Trimmed replacement network.
    """

    logging.info("Trimming replacement network between intersection points")

    lines = []

    for feature in replacement_features:
        geom = shape(feature["geometry"])

        lines.extend(explode_lines(geom))

    output_lines = []

    for line in lines:
        touches_upstream = line.distance(upstream_point) < 1e-8

        touches_downstream = line.distance(downstream_point) < 1e-8

        if touches_upstream and touches_downstream:
            line = snap(
                line,
                upstream_point,
                1e-5,
            )

            line = snap(
                line,
                downstream_point,
                1e-5,
            )

            parts = list(
                split(
                    line,
                    upstream_point,
                ).geoms
            )

            middle_parts = []

            for part in parts:
                for subpart in split(
                    part,
                    downstream_point,
                ).geoms:
                    if (
                        subpart.distance(upstream_point) < 1e-8
                        and subpart.distance(downstream_point) < 1e-8
                    ):
                        middle_parts.append(subpart)

            output_lines.extend(middle_parts)

            continue

        if touches_upstream:
            output_lines.append(
                keep_upstream_part(
                    {"geometry": line.__geo_interface__},
                    upstream_point,
                )
            )

            continue

        if touches_downstream:
            output_lines.append(
                keep_downstream_part(
                    {"geometry": line.__geo_interface__},
                    downstream_point,
                )
            )

            continue

        output_lines.append(line)

    logging.info(
        "Generated %s replacement line(s) after trimming",
        len(output_lines),
    )

    return MultiLineString(output_lines)


def insert_pivot_points(
    replacement_geom,
    upstream_point,
    downstream_point,
    tolerance=1e-5,
):

    lines = explode_lines(replacement_geom)

    result_lines = []

    for line in lines:
        line = snap(
            line,
            upstream_point,
            tolerance,
        )

        line = snap(
            line,
            downstream_point,
            tolerance,
        )

        parts = [line]

        for pivot in (
            upstream_point,
            downstream_point,
        ):
            new_parts = []

            for part in parts:
                try:
                    if part.distance(pivot) < tolerance:
                        split_result = split(
                            part,
                            pivot,
                        )

                        new_parts.extend(split_result.geoms)

                    else:
                        new_parts.append(part)

                except Exception:
                    new_parts.append(part)

            parts = new_parts

        result_lines.extend(parts)

    return MultiLineString(result_lines)


def find_downstream_intersection_point(
    downstream_reach,
    replacement_features,
):

    reach_geom = shape(downstream_reach["geometry"])

    points = []

    for replacement_feature in replacement_features:
        replacement_geom = shape(replacement_feature["geometry"])

        inter = reach_geom.intersection(replacement_geom)

        if inter.is_empty:
            continue

        if inter.geom_type == "Point":
            points.append(inter)

        elif inter.geom_type == "MultiPoint":
            points.extend(inter.geoms)

    if not points:
        raise ValueError("No downstream intersection point found.")

    return min(
        points,
        key=lambda p: reach_geom.project(p),
    )


def keep_upstream_part(
    reach,
    intersection_point,
):
    """
    Split a reach at the intersection point and
    keep the upstream portion.

    Parameters
    ----------
    reach : dict
        Reach feature.

    intersection_point : Point
        Split location.

    Returns
    -------
    LineString
        Upstream reach segment.
    """

    logging.info("Keeping upstream reach segment")

    geom = shape(reach["geometry"])

    geom = snap(
        geom,
        intersection_point,
        1e-5,
    )

    parts = list(
        split(
            geom,
            intersection_point,
        ).geoms
    )

    upstream_point = Point(geom.coords[-1])

    result = min(
        parts,
        key=lambda g: g.distance(upstream_point),
    )

    logging.info(
        "Upstream segment length: %s",
        result.length,
    )

    return result


def keep_downstream_part(
    reach,
    intersection_point,
):
    """
    Split a reach at the intersection point and
    keep the downstream portion.

    Parameters
    ----------
    reach : dict
        Reach feature.

    intersection_point : Point
        Split location.

    Returns
    -------
    LineString
        Downstream reach segment.
    """

    logging.info("Keeping downstream reach segment")

    geom = shape(reach["geometry"])

    geom = snap(
        geom,
        intersection_point,
        1e-5,
    )

    parts = list(
        split(
            geom,
            intersection_point,
        ).geoms
    )

    downstream_point = Point(geom.coords[0])

    result = min(
        parts,
        key=lambda g: g.distance(
            downstream_point,
        ),
    )

    logging.info(
        "Downstream segment length: %s",
        result.length,
    )

    return result


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


def same_point(
    p1,
    p2,
    precision=10,
):
    return round(p1[0], precision) == round(p2[0], precision) and round(
        p1[1], precision
    ) == round(p2[1], precision)


def orient_reaches_downstream_to_upstream(
    segments,
    downstream_reach,
):
    """
    Orient replacement reaches from downstream
    to upstream.

    Parameters
    ----------
    segments : list[dict]

    downstream_reach : dict

    Returns
    -------
    list[dict]
    """

    if not segments:
        return []

    downstream_geom = shape(downstream_reach["geometry"])

    downstream_point = tuple(downstream_geom.coords[0])

    remaining = list(segments)

    oriented = []

    points_to_process = deque([downstream_point])

    while points_to_process:
        current_point = points_to_process.popleft()

        matched = []

        for i, segment in enumerate(remaining):
            geom = shape(segment["geometry"])

            start_point = tuple(geom.coords[0])

            end_point = tuple(geom.coords[-1])

            if same_point(
                start_point,
                current_point,
            ):
                matched.append(
                    (
                        i,
                        {
                            **segment,
                            "geometry": geom,
                        },
                    )
                )

            elif same_point(
                end_point,
                current_point,
            ):
                matched.append(
                    (
                        i,
                        {
                            **segment,
                            "geometry": LineString(list(geom.coords)[::-1]),
                        },
                    )
                )

        for i, segment in sorted(
            matched,
            key=lambda x: x[0],
            reverse=True,
        ):
            remaining.pop(i)

            oriented.append(segment)

            points_to_process.append(tuple(segment["geometry"].coords[-1]))

    if remaining:
        print(f"{len(remaining)} segments non orientés :")

        for segment in remaining:
            geom = shape(segment["geometry"])

            print(
                tuple(geom.coords[0]),
                "->",
                tuple(geom.coords[-1]),
            )

        raise RuntimeError(f"{len(remaining)} reach(es) could not be oriented.")

    return oriented
