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
from shapely.geometry import (
    MultiLineString,
    Point,
    shape,
)
from shapely.ops import snap, split
import replacement_reconstruction as rep


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

        lines.extend(rep.explode_lines(geom))

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

    lines = rep.explode_lines(replacement_geom)

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
