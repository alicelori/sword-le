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

"""Main functions of swordle"""

import logging
import math

import matplotlib.pyplot as plt
import numpy as np
import pyproj
from geopy.distance import distance, lonlat
from shapely.geometry import MultiLineString, Point, mapping, shape
from shapely.ops import linemerge, snap, split, transform, unary_union

logger = logging.getLogger("swordle")


def select_reaches_using_mask(src, mask, where="in", crs=None):
    """Remove or keep reaches and reaches portions that are in the mask

    Arguments
    ---------
        src : fiona.Collection
            Source layer
        mask : shapely.geometry.Polygon
            Polygon of the selection area
        inside : str
            'in' to keep reaches and portions inside, 'out' to keep reaches and portions outside,
            'sin' to keep reaches strictly inside, 'sout' to keep reaches strictly outside

    Returns
    -------
        selected_features : list
            List of selected features (whole reaches or remaining portions).

    """

    # Create emtpy list of selected features
    selected_features = []

    # Set up reprojection is necessary
    reproject = None
    if crs is not None:
        src_crs = pyproj.CRS.from_user_input(crs)
        target_crs = pyproj.CRS.from_epsg(4326)

        if src_crs != target_crs:
            reproject = pyproj.Transformer.from_crs(
                src_crs, target_crs, always_xy=True
            ).transform

    # Loop on features in source
    nfeaturescut = 0
    for feature in src:

        # Retrieve feature geometry and reproject if needed
        geometry = shape(feature["geometry"])
        if reproject is not None:
            geometry = transform(reproject, geometry)

        if geometry.intersects(mask):

            # Geometry intersects the mask
            if where == "in":

                # Cut the geometry to keep inside portion (using intersection method of Shapely)
                inside_part = geometry.intersection(mask)
                if not inside_part.is_empty:
                    kept_portion = {
                        "geometry": mapping(inside_part),
                        "properties": feature["properties"],
                    }
                    kept_portion["properties"]["cut"] = True
                    selected_features.append(kept_portion)
                    nfeaturescut += 1

            # Keep outside portion
            elif where == "out":

                outside_part = geometry.difference(mask)
                if outside_part.is_empty:
                    continue

                mask_boundary_intersection = geometry.intersection(
                    mask.boundary
                )

                # Touches boundary at one point only
                if mask_boundary_intersection.geom_type == "Point":
                    kept_portion = {
                        "geometry": mapping(outside_part),
                        "properties": feature["properties"],
                    }
                    selected_features.append(kept_portion)
                    nfeaturescut += 1

                # Reach crosses the mask entirely
                elif mask_boundary_intersection.geom_type == "MultiPoint":

                    points = list(mask_boundary_intersection.geoms)
                    if len(points) != 2:
                        raise ValueError(
                            "More than 2 intersection points between 'mask' boundary and 'src'"
                        )

                    geometry = snap(
                        geometry, mask_boundary_intersection, tolerance=1e-5
                    )  # in degrees => EPSG:4326
                    splitted_geometries = split(
                        geometry, mask_boundary_intersection
                    )

                    for sp_geometry in splitted_geometries.geoms:
                        # Correct condition: keep ONLY parts outside the mask
                        if not sp_geometry.intersects(mask):
                            kept_portion = {
                                "geometry": mapping(sp_geometry),
                                "properties": feature["properties"],
                            }
                            selected_features.append(kept_portion)
                            nfeaturescut += 1

        elif mask.covers(geometry):

            # Geometry lies entirely inside the mask
            if where in ("in", "sin"):

                # Keep source geometry
                selected_features.append(feature)

        else:

            # Geometry lies entirely outside the mask
            if where in ("out", "sout"):

                selected_features.append(feature)

    logger.info(
        "  - Selected %s portions %s cut",
        len(selected_features),
        nfeaturescut,
    )

    return selected_features


def find_upstream_downstream_reaches_using_mask_logic1(src_outmasked, mask):
    """Determines the two reaches of the source upstream and dowtream
    of the mask

    Arguments
    ---------
        src_outmasked : fiona.Collection
            Reaches located outside of 'mask'
        mask : shapely.geometry.Polygon
            Polygon of the selection area

    Returns
    -------
        src_upstream_reach : shapely.geometry.linestring.LineString
            First upstream src_upstream_reach next to the 'mask'
        downstream_reach : shapely.geometry.linestring.LineString
            First downstream src_upstream_reach next to the 'mask'

    """

    # Selecting reachs touching the mask : upstream and downstream reaches
    src_selected_reaches = []
    for feature in src_outmasked:

        # Retrieve feature geometry
        geometry = shape(feature["geometry"])

        # Catching the two src reaches touching the mask
        if geometry.intersects(mask.exterior.buffer(0.001)):
            src_selected_reaches.append(feature)

    logger.info(
        "Upstream and downstream reaches : %i reaches selected",
        len(src_selected_reaches),
    )

    # Check that there is only 2 reaches : downstream and upstream
    if len(src_selected_reaches) == 2:

        src_upstream_reach, _ = (
            None,
            None,
        )

        # Assigning 'downstream' or 'upstream' name to reaches according to 'dist_out' parameter
        if (
            src_selected_reaches[0]["properties"]["dist_out"]
            > src_selected_reaches[1]["properties"]["dist_out"]
        ):
            src_upstream_reach = src_selected_reaches[0]
            src_downstream_reach = src_selected_reaches[1]

        elif (
            src_selected_reaches[0]["properties"]["dist_out"]
            < src_selected_reaches[1]["properties"]["dist_out"]
        ):
            src_upstream_reach = src_selected_reaches[1]
            src_downstream_reach = src_selected_reaches[0]

        else:
            raise ValueError(
                "'dist_out' parameter is the same for the two selected reaches."
            )

    else:
        raise ValueError(
            "Incorrect buffer value : algorithm must select 2 reaches."
        )

    return src_upstream_reach, src_downstream_reach


def find_upstream_downstream_reaches_using_mask_logic2(src_masked_out, mask):
    """Determines the two reaches of the source upstream and downstream
    of the mask

    Arguments
    ---------
        src_masked_out : fiona.Collection
            Reaches located outside of 'mask'
        mask : shapely.geometry.Polygon
            Polygon of the selection area

    Returns
    -------
        src_upstream_reach : shapely.geometry.linestring.LineString
            First upstream src_upstream_reach next to the 'mask'
        downstream_reach : shapely.geometry.linestring.LineString
            First downstream src_upstream_reach next to the 'mask'

    """

    distances = [
        mask.distance(shape(feature["geometry"])) for feature in src_masked_out
    ]
    reaches_dist_to_mask = dict(zip(distances, src_masked_out))

    sorted_distances = sorted(reaches_dist_to_mask.keys())

    # Getting the four reaches closest to the mask, for the nearest to the most far
    reach_1 = reaches_dist_to_mask[sorted_distances[0]]
    reach_2 = reaches_dist_to_mask[sorted_distances[1]]
    reach_3 = reaches_dist_to_mask[sorted_distances[2]]
    reach_4 = reaches_dist_to_mask[sorted_distances[3]]

    # Finding which reach is upstream or downstream
    # between reach_3 and reach_4 (Checking 'reach_id' parameter)
    if reach_3["properties"]["reach_id"] < reach_4["properties"]["reach_id"]:
        far_upstream_reach = reach_4
        _ = reach_3
    elif reach_3["properties"]["reach_id"] > reach_4["properties"]["reach_id"]:
        far_upstream_reach = reach_3
        _ = reach_4

    else:
        raise ValueError(
            "'reach_id' parameter is the same for 'reach_3' and 'reach_4' features"
        )

    # Finding which reach is upstream or downstream between reach_1 and reach_2
    if shape(reach_1["geometry"]).distance(
        shape(far_upstream_reach["geometry"])
    ) < shape(reach_2["geometry"]).distance(
        shape(far_upstream_reach["geometry"])
    ):
        upstream_reach = reach_1
        downstream_reach = reach_2

    elif shape(reach_1["geometry"]).distance(
        shape(far_upstream_reach["geometry"])
    ) > shape(reach_2["geometry"]).distance(
        shape(far_upstream_reach["geometry"])
    ):
        upstream_reach = reach_2
        downstream_reach = reach_1

    else:
        raise ValueError(
            "'reach_1' and 'reach_2' are at the same distance from 'far_upstream_reach'"
        )

    return upstream_reach, downstream_reach


def get_number_of_reaches_connected_to_mask(src, mask):
    """Returns the number of src reaches connected to the mask

    Arguments
    ---------
        src : fiona.Collection
            Source data
        mask : shapely.geometry.Polygon
            Polygon of the selection area

    Returns
    -------
        n_src_reaches : int
            Number of reaches connected to the mask
    """

    n_src_reaches = 0

    for feature in src:

        geometry = shape(feature["geometry"])
        if geometry.intersects(mask.boundary):

            intersection = geometry.intersection(mask.boundary)
            logger.info("> geometry is %s", geometry.geom_type)
            logger.info("> mask boundary is %s", mask.boundary.geom_type)
            if intersection.geom_type == "Point":
                logger.info("Point")
                n_src_reaches += 1
            elif intersection.geom_type == "MultiPoint":
                logger.info("MultiPoint")
                n_src_reaches += len(intersection.geoms)
            else:
                raise ValueError(f"{intersection.geom_type} is not supported")

    return n_src_reaches


def get_matching_src_rep_reaches_using_mask(src, rep, mask, n_src_reaches):
    """Returns pairs of reaches (1 replacement reach associated with 1 source reach)

    Arguments
    ---------
        src : fiona.Collection
            Source reaches out of the mask

        rep : fiona.Collection
            Replacement reaches out of the mask

        mask : shapely.geometry.Polygon
            Polygon of the selection area

        n_src_reaches : int
            Number of reaches from src connected to mask boundary

    Returns
    -------
        pairs : list
            List of pairs of 'src' and 'rep' reaches, [[src_feature, rep_feature]...]
    """

    pairs = []

    # Sort src features by distance to the mask
    distances = [mask.distance(shape(feature["geometry"])) for feature in src]
    reaches_dist_to_mask = dict(zip(distances, src))

    sorted_distances = sorted(reaches_dist_to_mask.keys())

    for index in range(n_src_reaches):

        # Source feature connected to mask boundary
        src_feature = reaches_dist_to_mask[sorted_distances[index]]

        rep_distances = [
            shape(rep_feature["geometry"]).distance(
                shape(src_feature["geometry"])
            )
            for rep_feature in rep
        ]
        src_rep_distances_dict = dict(zip(rep_distances, rep))

        rep_feature = src_rep_distances_dict[min(rep_distances)]

        pairs.append([src_feature, rep_feature])

    return pairs


def find_closest_intersection_point_to_the_mask(
    rep_masked_out, src_reach, mask
):
    """Gives the closest intersection point to the mask between 'src_reach' and 'rep_masked_out'

    Arguments
    ---------
        rep_masked_out : fiona.Collection
            Reaches from replacement data located outside of 'mask'
        src_reach : shapely.geometry.LineString
            Reach located
        mask : shapely.geometry.Polygon
            Polygon of the selection area

    Returns
    -------
        intersection_point : shapely.geometry.Point
            Intersection Point between 'src_reach' and 'rep_masked_out'.
            In case of multiple points, 'intersection_point' is the closest point to the mask.

    """

    intersection = None

    for feature in rep_masked_out:

        if shape(src_reach["geometry"]).intersects(shape(feature["geometry"])):
            intersection = shape(src_reach["geometry"]).intersection(
                shape(feature["geometry"])
            )

    # Multiple points intersection
    if intersection.geom_type == "MultiPoint":
        intersection_points = list(intersection.geoms)
        distances = [point.distance(mask) for point in intersection_points]

        intersection_points_dict = dict(zip(distances, intersection_points))
        intersection_point = intersection_points_dict[min(distances)]

    # Unique point intersection
    elif intersection.geom_type == "Point":
        intersection_point = intersection

    # No intersection or wrong type of geometry
    else:
        raise ValueError(f"Type {intersection.geom_type} is not supported.")

    return intersection_point


def correct_reach_using_intersection_point(
    rep, src_reach, intersection_point, mask
):
    """Corrects 'src_reach' to fit 'rep' data at the edge of the mask

    Arguments
    ---------
        rep : fiona.Collection
            Replacement data out of the 'mask'
        src_reach : shapely.geometry.(Multi)LineString
            Reach to correct
        intersection_point : shapely.geometry.Point
            Intersectoion point between 'reach' and 'rep' data
        mask : shapely.geometry.Polygon
            Polygon of the selection area

    Returns
    -------
        new_reach : shapely.geometry.MultiLineString
            Corrected reach, fitting with 'rep' data inside of the 'mask'
    """

    # rep_reach = None

    # Retrieving 'src_reach' geometry
    src_reach_geometry = shape(src_reach["geometry"])

    # Selecting rep reach geometry that intersects 'src_reach'
    for feature in rep:
        if src_reach_geometry.intersects(shape(feature["geometry"])):
            rep_reach_geometry = shape(feature["geometry"])

    # Splitting 'src_reach' and selected rep reach with 'intersection_point'
    # A too large tolerance value interrupts code
    # when intersection point is near the end of the line.
    # (tol=0.1 fails for the roi "ile de la cité")
    rep_reach_geometry = snap(
        rep_reach_geometry, intersection_point, tolerance=1e-5
    )  # in degrees => EPSG:4326
    src_reach_geometry = snap(
        src_reach_geometry, intersection_point, tolerance=1e-5
    )  # in degrees => EPSG:4326

    rep_reach_1, rep_reach_2 = split(
        rep_reach_geometry, intersection_point
    ).geoms
    src_reach_1, src_reach_2 = split(
        src_reach_geometry, intersection_point
    ).geoms

    # Computing the new reach geometry as sum of :
    # - rep reach part that is close to the mask
    # - src reach part that is far from the mask
    rep_distances = [
        r.centroid.distance(mask.centroid) for r in [rep_reach_1, rep_reach_2]
    ]
    rep_dict = dict(zip(rep_distances, [rep_reach_1, rep_reach_2]))

    src_distances = [
        s.centroid.distance(mask.centroid) for s in [src_reach_1, src_reach_2]
    ]
    src_dict = dict(zip(src_distances, [src_reach_1, src_reach_2]))

    new_reach_geometry = MultiLineString(
        get_lines_list(src_dict[max(src_distances)])
        + get_lines_list(rep_dict[min(rep_distances)])
    )
    new_reach_geometry = linemerge(new_reach_geometry)
    logger.info("NEW GEOM: new_reach_geometry")

    # Final corrected reach
    new_reach = {"geometry": mapping(new_reach_geometry), "properties": {}}

    return new_reach


def get_lines_list(line):
    """Returns a list containing shapely.geometry.LineString objects.

    Arguments
    ---------
        line : shapely.geometry.(Multi)LineString

    Returns
    -------
        result : list
    """

    if line.geom_type == "MultiLineString":
        result = list(line.geoms)
    elif line.geom_type == "LineString":
        result = [line]
    else:
        raise ValueError("Wrong type for 'line' argument.")

    return result


def adjust_reaches_with_confluence_using_mask(
    rep_masked_in, upstream_reach, downstream_reach, mask
):
    """Modifies argument geometries such that upstream and downstream reaches
    fit confluence and defluence points

    Arguments
    ---------
        rep_masked_in : fiona.Collection
            Replacement layer inside the 'mask'
        upstream_reach : shapely.geometry.LineString
            Upstream reach that fits source and replacement data at the edge of the 'mask'
        downstream_reach : shapely.geometry.LineString
            Downstream reach that fits source and replacement data at the edge of the 'mask'
        mask : shapely.geometry.Polygon

    Returns
    -------
        rectified_rep_features : list
            Modified replacement data reaches within the mask
        upstream_reach : shapely.geometry.LineString
            Modified upstream reach to fit defluence point
        downstream_reach : shapely.geometry.LineString
            Modified downstream reach to fit confluence point

    """

    features_list = [feature for feature in rep_masked_in]
    sub_list = features_list.copy()
    intersections = []

    # Looping on pairs of reaches,
    for feature in rep_masked_in:

        sub_list.remove(feature)
        geometry = shape(feature["geometry"])

        for element in sub_list:

            inter = geometry.intersection(shape(element["geometry"]))

            if inter.geom_type == "MultiPoint":
                intersections.append(inter)

    # Getting mergedd features for splitting
    confluence_points = unary_union(intersections)
    unified_rep = unary_union(
        [shape(feature["geometry"]) for feature in rep_masked_in]
    )

    rectified_rep = split(unified_rep, confluence_points)

    # Selecting little reaches that go from confluence/defluence points to mask boundary
    # Saving kept features from replacement data
    selected_geometries = []
    rectified_rep_features = []
    for geometry in list(rectified_rep.geoms):
        if geometry.intersects(mask.boundary):
            selected_geometries.append(geometry)
        else:
            feature = {"geometry": mapping(geometry), "properties": {}}
            rectified_rep_features.append(feature)
    # -----------------------------------------------------------------------
    # If no segment touches the mask boundary, we do not correct
    # the reaches and return the current state (avoids min(distances) on empty list)
    if not selected_geometries:
        return rectified_rep_features, upstream_reach, downstream_reach
    # -----------------------------------------------------------------------
    # Correcting upstream and downstream reaches - extension to confluence/defluence points
    upstream_reach_geometry = shape(upstream_reach["geometry"])
    downstream_reach_geometry = shape(downstream_reach["geometry"])

    for reach_geometry in [upstream_reach_geometry, downstream_reach_geometry]:
        distances = [f.distance(reach_geometry) for f in selected_geometries]
        selected_geometries_dict = dict(zip(distances, selected_geometries))

        if reach_geometry == upstream_reach_geometry:
            new_upstream_reach_geometry = reach_geometry.union(
                selected_geometries_dict[min(distances)]
            )
            new_upstream_reach_geometry = linemerge(new_upstream_reach_geometry)
            upstream_reach = {
                "geometry": mapping(new_upstream_reach_geometry),
                "properties": {},
            }
        else:
            new_downstream_reach_geometry = reach_geometry.union(
                selected_geometries_dict[min(distances)]
            )
            new_downstream_reach_geometry = linemerge(
                new_downstream_reach_geometry
            )
            downstream_reach = {
                "geometry": mapping(new_downstream_reach_geometry),
                "properties": {},
            }

    return rectified_rep_features, upstream_reach, downstream_reach


def compute_reach_length(reach):
    """Compute length of a reach

    Arguments
    ---------
        reaches : dict
            Reach dictionary (following the Python geo protocol, as in a fiona.Collection)

    """

    # Retrieve geometry of the feature
    geometry = shape(reach["geometry"])
    if geometry.geom_type != "LineString":
        raise RuntimeError(
            f"Cannot process geometry of type {geometry.geom_type}"
        )

    # Compute length (in meters) of the linestring using geopy.distance.distance
    coords = list((geometry.coords))
    lon1, lat1 = coords[0]
    length = 0.0
    for lon2, lat2 in coords[1:]:
        length += distance(lonlat(lon1, lat1), lonlat(lon2, lat2)).meters
        lon1, lat1 = lon2, lat2
    return length
    # reach["properties"]["reach_len"] = length


def add_two_reaches_connection(upstream_reach, downstream_reach):
    """Add a connection between to reaches
    replacement reaches

    Arguments
    ---------
        upstream_reach : dict
            Upstream reach dictionary
            (following the Python geo protocol, as in a fiona.Collection)
        downstream_reach : dict
            Downstream reach dictionary
            (following the Python geo protocol, as in a fiona.Collection)

    """

    # Update connectivity attributes for upstream reach
    if upstream_reach["properties"]["n_rch_dn"] <= 0:
        upstream_reach["properties"]["n_rch_dn"] = 1
        upstream_reach["properties"]["rch_id_dn"] = downstream_reach[
            "properties"
        ]["reach_id"]
    else:
        upstream_reach["properties"]["n_rch_dn"] += 1
        old_list = upstream_reach["properties"]["rch_id_dn"]
        upstream_reach["properties"][
            "rch_id_dn"
        ] = f"{old_list} {downstream_reach['properties']['reach_id']}"

    # Update connectivity attributes for downstream reach
    if downstream_reach["properties"]["n_rch_up"] <= 0:
        downstream_reach["properties"]["n_rch_up"] = 1
        downstream_reach["properties"]["rch_id_up"] = upstream_reach[
            "properties"
        ]["reach_id"]
    else:
        downstream_reach["properties"]["n_rch_up"] += 1
        old_list = downstream_reach["properties"]["rch_id_up"]
        downstream_reach["properties"][
            "rch_id_up"
        ] = f"{old_list} {upstream_reach['properties']['reach_id']}"


def compute_connectivity(upstream_reach, downstream_reach, rep_reaches):
    """Compute connectivity between edge and replacement reaches, as well as connectivity between
    replacement reaches

    Arguments
    ---------
        edge_reaches : list
            List of edge reaches
        rep_reaches : fiona.Collection
            Replacement layer inside the mask

    """

    # Find reaches connected to upstream reach
    geometry = shape(upstream_reach["geometry"])
    upstream_endpoint1 = geometry.coords[0]
    upstream_endpoint2 = geometry.coords[-1]
    for feature in rep_reaches:

        # Retrieve feature endpoints
        geometry = shape(feature["geometry"])
        if geometry.geom_type != "LineString":
            raise RuntimeError(
                f"Cannot process geometry of type {geometry.geom_type}"
            )
        endpoint1 = geometry.coords[0]
        endpoint2 = geometry.coords[-1]

        # Compute every possible distance between endpoints
        dist11 = distance(
            lonlat(*endpoint1), lonlat(*upstream_endpoint1)
        ).meters
        dist12 = distance(
            lonlat(*endpoint1), lonlat(*upstream_endpoint2)
        ).meters
        dist21 = distance(
            lonlat(*endpoint2), lonlat(*upstream_endpoint1)
        ).meters
        dist22 = distance(
            lonlat(*endpoint2), lonlat(*upstream_endpoint2)
        ).meters

        # Add connection if the minimum of every possible distance is less than 30m
        if np.min([dist11, dist12, dist21, dist22]) <= 30.0:
            add_two_reaches_connection(upstream_reach, feature)

    # Find reaches connected to downstream reaches
    geometry = shape(downstream_reach["geometry"])
    downstream_endpoint1 = geometry.coords[0]
    downstream_endpoint2 = geometry.coords[-1]
    for feature in rep_reaches:

        # Retrieve feature endpoints
        geometry = shape(feature["geometry"])
        if geometry.geom_type != "LineString":
            raise RuntimeError(
                f"Cannot process geometry of type {geometry.geom_type}"
            )
        endpoint1 = geometry.coords[0]
        endpoint2 = geometry.coords[-1]

        # Compute every possible distance between endpoints
        dist11 = distance(
            lonlat(*endpoint1), lonlat(*downstream_endpoint1)
        ).meters
        dist12 = distance(
            lonlat(*endpoint1), lonlat(*downstream_endpoint2)
        ).meters
        dist21 = distance(
            lonlat(*endpoint2), lonlat(*downstream_endpoint1)
        ).meters
        dist22 = distance(
            lonlat(*endpoint2), lonlat(*downstream_endpoint2)
        ).meters

        # Add connection if the minimum of every possible distance is less than 30m
        if np.min([dist11, dist12, dist21, dist22]) <= 30.0:
            add_two_reaches_connection(feature, downstream_reach)

    # Find connections between reaches in rep_reaches
    for from_index, from_feature in enumerate(rep_reaches[:-1]):

        # Retrieve "from" feature endpoints
        from_geometry = shape(from_feature["geometry"])
        from_endpoint1 = from_geometry.coords[0]
        from_endpoint2 = from_geometry.coords[-1]

        for to_feature in rep_reaches[from_index + 1 :]:

            # Retrieve "to" feature endpoints
            to_geometry = shape(to_feature["geometry"])
            to_endpoint1 = to_geometry.coords[0]
            to_endpoint2 = to_geometry.coords[-1]

            # Compute every possible distance between endpoints
            dist12 = distance(
                lonlat(*from_endpoint1), lonlat(*to_endpoint2)
            ).meters
            dist21 = distance(
                lonlat(*from_endpoint2), lonlat(*to_endpoint1)
            ).meters
            dist11 = distance(
                lonlat(*from_endpoint1), lonlat(*to_endpoint1)
            ).meters
            dist22 = distance(
                lonlat(*from_endpoint2), lonlat(*to_endpoint2)
            ).meters

            # Check for wrong ordered geometries or add connectivity if distance is less than 50m
            if dist12 < 50.0 and dist21 < 50.0:
                logger.info(from_geometry)
                logger.info(to_geometry)
                plt.plot(
                    [point[0] for point in from_geometry.coords],
                    [point[1] for point in from_geometry.coords],
                )
                plt.plot(
                    [point[0] for point in to_geometry.coords],
                    [point[1] for point in to_geometry.coords],
                )
                plt.show()
                raise RuntimeError(
                    "Both endpoint 1<->2 distances are less than 50.0"
                )
            elif dist12 < 50.0:
                add_two_reaches_connection(to_feature, from_feature)
            elif dist21 < 50.0:
                add_two_reaches_connection(from_feature, to_feature)


def apply_default_attributes(src, default_attributes):
    """Apply default attributes to all features of the source

    Arguments
    ---------
        src : fiona.Collection
            Source layer
        default attributes : dict
            Attributes and their default values

    Returns
    -------
        src : fiona.Collection
            Source layer with modified attributes

    """

    # Loop on features in source
    for feature in src:

        # Apply default attributes
        feature["properties"] = default_attributes.copy()

    return src


def compute_reaches_distances(downstream_reach, reaches_id_table):
    """Compute outlet distances starting from a downstream reach

    Arguments
    ---------
        downstream_reach : dict
            Downstream reach dictionary
            (following the Python geo protocol, as in a fiona.Collection)
        reaches_id_table : dict
            Reach ID lookup table (key=reach_id, value=feature)

    """

    ds_dist_out = (
        downstream_reach["properties"]["dist_out"]
        - downstream_reach["properties"]["reach_len"]
    )
    stack = [(downstream_reach["properties"]["reach_id"], ds_dist_out)]
    while len(stack) > 0:

        reach_id, ds_dist_out = stack.pop(0)
        reach = reaches_id_table[reach_id]
        reach_length = reach["properties"]["reach_len"]
        us_dist_out = ds_dist_out + reach_length
        reach["properties"]["dist_out"] = us_dist_out

        # Add upstream reaches to the stack
        if reach["properties"]["n_rch_up"] > 0:
            up_rch_id_list = reach["properties"]["rch_id_up"].split()
            for up_rch_id in up_rch_id_list:
                stack.append((up_rch_id, us_dist_out))


def replace_node_on_reach(node, reach):
    """Replace a node on a reach

    Arguments
    ---------
        node : dict
            Node dictionary (following the Python geo protocol, as in a fiona.Collection)
        reach : dict
            Reach dictionary (following the Python geo protocol, as in a fiona.Collection)

    Returns
    -------
        rep_node : dict
            Replaced node dictionary (following the Python geo protocol, as in a fiona.Collection)

    """

    # Retrieve geometries of the reach and the node
    reach_geometry = shape(reach["geometry"])
    if reach_geometry.geom_type != "LineString":
        raise RuntimeError(
            f"Cannot process reach geometry of type {reach_geometry.geom_type}"
        )
    node_geometry = shape(node["geometry"])
    if node_geometry.geom_type != "Point":
        raise RuntimeError(
            f"Cannot process node geometry of type {node_geometry.geom_type}"
        )

    # Compute the nearest point on the reach line
    # dist = reach_geometry.project(
    #    node_geometry
    # )
    point_on_reach = reach_geometry.interpolate(
        reach_geometry.project(node_geometry)
    )

    # Test if node is close to the end points
    endpoint1 = reach_geometry.interpolate(0.0)
    endpoint2 = reach_geometry.interpolate(reach_geometry.length)
    distance1 = distance(
        lonlat(endpoint1.x, endpoint1.y),
        lonlat(point_on_reach.x, point_on_reach.y),
    ).meters
    distance2 = distance(
        lonlat(endpoint2.x, endpoint2.y),
        lonlat(point_on_reach.x, point_on_reach.y),
    ).meters
    if distance1 < 50.0 or distance2 < 50.0:

        # Set new node to None for node close to one of the endpoints
        new_node = None

    else:

        # Create new node
        new_node = {
            "geometry": mapping(point_on_reach),
            "properties": node["properties"].copy(),
        }

        disp = distance(
            lonlat(point_on_reach.x, point_on_reach.y),
            lonlat(node_geometry.x, node_geometry.y),
        ).meters
        if disp > 10.0:

            # Update outlet distance
            alpha = distance1 / reach_geometry.length
            dn_dist_out = reach["properties"]["dist_out"]
            up_dist_out = dn_dist_out - reach["properties"]["reach_len"]
            dist_out = dn_dist_out + alpha * (up_dist_out - dn_dist_out)
            new_node["properties"]["dist_out"] = dist_out

    return new_node


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
            raise RuntimeError(
                f"Cannot process geometry of type {geometry.geom_type}"
            )

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
                new_node["properties"][
                    "node_id"
                ] = f"{reach_id[:-1]}{node_index:04d}{reach_type}"
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
