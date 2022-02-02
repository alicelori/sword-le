import fiona
from fiona.crs import from_epsg
from geopy.distance import distance, lonlat
import json
import math
import numpy as np
import pyproj
from shapely.geometry import Point, LineString, MultiLineString, mapping, shape
from shapely.ops import transform, split, snap, unary_union
import tqdm


def select_reaches_using_mask(src, mask, where='in', crs=None, verbose=True):
    """ Remove or keep reaches and reaches portions that are in the mask
    
        Arguments
        ---------
            src : fiona.Collection
                Source layer
            mask : shapely.geometry.Polygon
                Polygon of the selection area
            inside : str
                'in' to keep reaches and portions inside, 'out' to keep reaches and portions outside
            verbose : bool
                True for verbose mode
    
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
        
        if crs != from_epsg(4326):
            
            reproject = pyproj.Transformer.from_crs(crs, pyproj.CRS('EPSG:4326'), always_xy=True).transform
    
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
                if geometry.intersection(mask) is not None:
                    
                    kept_portion = {"geometry" : mapping(geometry.intersection(mask)),
                                    "properties" : feature["properties"]}
                    kept_portion["properties"]["cut"] = True
                    selected_features.append(kept_portion)
                    nfeaturescut += 1
                    
            else:
                
                # Cut the geometry to keep outside portion (using difference method of Shapely)
                if geometry.difference(mask) is not None:

                    mask_boundary_intersection = geometry.intersection(mask.boundary)
                    
                    # Reach is on the mask but not crossing it entirely
                    if mask_boundary_intersection.geom_type == "Point":
                        
                        kept_portion = {"geometry" : mapping(geometry.difference(mask)),
                                        "properties" : feature["properties"]}
                        selected_features.append(kept_portion)
                        nfeaturescut += 1

                    # Reach crosses the mask entirely
                    elif mask_boundary_intersection.geom_type == "MultiPoint":
                        
                        # 2 Points
                        if len(list(mask_boundary_intersection.geoms)) == 2:
                            
                            geometry = snap(geometry, mask_boundary_intersection, tolerance = 1e-5)
                            splitted_geometries = split(geometry, mask_boundary_intersection)
                            # print("> Crossing reach - len splitted geometries", len(list(splitted_geometries.geoms)))
                            for sp_geometry in list(splitted_geometries.geoms):

                                if sp_geometry.intersects(mask.interiors) == False:
                                    # print("geometry selected")
                                    kept_portion = {"geometry" : mapping(sp_geometry),
                                                    "properties" : feature["properties"]}
                                    selected_features.append(kept_portion)
                                    nfeaturescut += 1

                        # More than 2 Points 
                        else: 
                            raise ValueError("More than 2 intersection points between 'mask' boundary and 'src'")
                    
        elif mask.covers(geometry):
            
            # Geometry lies entirely inside the mask
            if where == "in":
            
                # Keep source geometry
                selected_features.append(feature)
            
        else:
            
            # Geometry lies entirely outside the mask
            if where == "out":
            
                selected_features.append(feature)
                
    if verbose:
        print("Selected %i portions (%i cut)" % (len(selected_features), nfeaturescut))
                
    return selected_features
    

# def find_upstream_downstream_reaches_using_mask(src_outmasked, mask, verbose=True):

#     #TODO : 
#     # - Selection du reach amont et aval avec 'reach id' et pas avec 'dist_out'
#     # - Rajouter la modification du paramètre discriminant pour déterminer quel reach est en amont ou aval (2eme partie de la fonction) 

#     """ Determines the two reaches of the source upstream and dowtream 
#         of the mask 

#         Arguments
#         ---------
#             src_outmasked : fiona.Collection
#                 Reaches located outside of 'mask'
#             mask : shapely.geometry.Polygon
#                 Polygon of the selection area

#         Returns
#         -------
#             src_upstream_reach : shapely.geometry.linestring.LineString
#                 First upstream src_upstream_reach next to the 'mask'
#             downstream_reach : shapely.geometry.linestring.LineString
#                 First downstream src_upstream_reach next to the 'mask'
    
#     """ 

#     # Selecting reachs touching the mask : upstream and downstream reaches 
#     src_selected_reaches = []
#     for feature in src_outmasked:
        
#         # Retrieve feature geometry 
#         geometry = shape(feature["geometry"])
        
#         # Catching the two src reaches touching the mask
#         if geometry.intersects(mask.exterior.buffer(0.001)):
#             src_selected_reaches.append(feature)

#     if verbose:
#         print("Upstream and downstream reaches : %i reaches selected" % len(src_selected_reaches))

#     # Check that there is only 2 reaches : downstream and upstream
#     if len(src_selected_reaches) == 2:
        
#         src_upstream_reach, downstream_reach = None, None

#         # Assigning 'downstream' or 'upstream' name to reaches according to 'dist_out' parameter
#         if src_selected_reaches[0]['properties']['dist_out'] > src_selected_reaches[1]['properties']['dist_out']:
#             src_upstream_reach = src_selected_reaches[0]
#             src_downstream_reach = src_selected_reaches[1]
        
#         elif src_selected_reaches[0]['properties']['dist_out'] < src_selected_reaches[1]['properties']['dist_out']:
#             src_upstream_reach = src_selected_reaches[1]
#             src_downstream_reach = src_selected_reaches[0]
        
#         else:
#             raise ValueError("'dist_out' parameter is the same for the two selected reaches.")

#     else:
#         raise ValueError("Incorrect buffer value : algorithm must select 2 reaches.")

#     return src_upstream_reach, src_downstream_reach

def find_upstream_downstream_reaches_using_mask(src_masked_out, mask, verbose=True):
    """ Determines the two reaches of the source upstream and dowtream 
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


    distances = [mask.distance(shape(feature["geometry"])) for feature in src_masked_out]
    reaches_dist_to_mask = dict(zip(distances, src_masked_out))

    sorted_distances = sorted(reaches_dist_to_mask.keys())

    # Getting the four reaches closest to the mask, for the nearest to the most far
    reach_1 = reaches_dist_to_mask[sorted_distances[0]]
    reach_2 = reaches_dist_to_mask[sorted_distances[1]]
    reach_3 = reaches_dist_to_mask[sorted_distances[2]]
    reach_4 = reaches_dist_to_mask[sorted_distances[3]]

    # Finding which reach is upstream or downstream between reach_3 and reach_4 (Checking 'reach_id' parameter)
    if reach_3["properties"]["reach_id"] < reach_4["properties"]["reach_id"]:
        far_upstream_reach = reach_4
        far_downstream_reach = reach_3

    elif reach_3["properties"]["reach_id"] > reach_4["properties"]["reach_id"]:
        far_upstream_reach = reach_3
        far_downstream_reach = reach_4
    
    else:
        raise ValueError("'reach_id' parameter is the same for 'reach_3' and 'reach_4' features")

    # Finding which reach is upstream or downstream between reach_1 and reach_2
    if shape(reach_1["geometry"]).distance(shape(far_upstream_reach["geometry"])) < shape(reach_2["geometry"]).distance(shape(far_upstream_reach["geometry"])):
        upstream_reach = reach_1
        downstream_reach = reach_2
    
    elif shape(reach_1["geometry"]).distance(shape(far_upstream_reach["geometry"])) > shape(reach_2["geometry"]).distance(shape(far_upstream_reach["geometry"])):
        upstream_reach = reach_2
        downstream_reach = reach_1
    
    else:
        raise ValueError("'reach_1' and 'reach_2' are at the same distance from 'far_upstream_reach'")

    return upstream_reach, downstream_reach


def get_number_of_reaches_connected_to_mask(src, mask):
    """ Returns the number of src reaches connected to the mask

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
        intersection = geometry.intersection(mask.boundary)
        # print("> mask boundary is ", mask.boundary.geom_type)
        if intersection.geom_type == "Point":
            # print("Point")
            n_src_reaches += 1
        elif intersection.geom_type == "MultiPoint":
            # print("MultiPoint")
            n_src_reaches += len(intersection.geoms)
        else:
            raise ValueError(f"{intersection.geom_type} is not supported")

    return n_src_reaches


def get_matching_src_rep_reaches_using_mask(src, rep, mask, n_src_reaches):
    """ Returns pairs of reaches (1 replacement reach associated with 1 source reach)

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

        rep_distances = [shape(rep_feature["geometry"]).distance(shape(src_feature["geometry"])) for rep_feature in rep]
        src_rep_distances_dict = dict(zip(rep_distances, rep))

        rep_feature = src_rep_distances_dict[min(rep_distances)]

        pairs.append([src_feature, rep_feature])

    return pairs 


def find_closest_intersection_point_to_the_mask(rep_masked_out, src_reach, mask):
    """ Gives the closest intersection point to the mask between 'src_reach' and 'rep_masked_out'

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
            intersection = shape(src_reach["geometry"]).intersection(shape(feature["geometry"]))
    
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


def correct_reach_using_intersection_point(rep, src_reach, intersection_point, mask):
    """ Corrects 'src_reach' to fit 'rep' data at the edge of the mask
    
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

    rep_reach = None

    # Retrieving 'src_reach' geometry
    src_reach_geometry = shape(src_reach["geometry"])

    # Selecting rep reach geometry that intersects 'src_reach'
    for feature in rep:
        if src_reach_geometry.intersects(shape(feature["geometry"])):
            rep_reach_geometry = shape(feature["geometry"])

    # Splitting 'src_reach' and selected rep reach with 'intersection_point'
    # A too large tolerance value interrupts code when intersection point is near the end of the line. 
    # (tol=0.1 fails for the roi "ile de la cité")
    rep_reach_geometry = snap(rep_reach_geometry, intersection_point, tolerance = 1e-5)
    src_reach_geometry = snap(src_reach_geometry, intersection_point, tolerance = 1e-5) 

    rep_reach_1, rep_reach_2 = split(rep_reach_geometry, intersection_point).geoms
    src_reach_1, src_reach_2 = split(src_reach_geometry, intersection_point).geoms

    # Computing the new reach geometry as sum of :
    # - rep reach part that is close to the mask 
    # - src reach part that is far from the mask
    rep_distances = [r.centroid.distance(mask.centroid) for r in [rep_reach_1, rep_reach_2]]
    rep_dict = dict(zip(rep_distances, [rep_reach_1, rep_reach_2]))

    src_distances = [s.centroid.distance(mask.centroid) for s in [src_reach_1, src_reach_2]]
    src_dict = dict(zip(src_distances, [src_reach_1, src_reach_2]))

    new_reach_geometry = MultiLineString(get_lines_list(src_dict[max(src_distances)]) + get_lines_list(rep_dict[min(rep_distances)]))

    # Final corrected reach 
    new_reach =  {'geometry': mapping(new_reach_geometry),
                  'properties': {}}

    return new_reach

def get_lines_list(line):
    """ Returns a list containing shapely.geometry.LineString objects.

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


def adjust_reaches_with_confluence_using_mask(rep_masked_in, upstream_reach, downstream_reach, mask):
    """ Modifies argument geometries such that upstream and downstream reaches 
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
    unified_rep = unary_union([shape(feature["geometry"]) for feature in rep_masked_in])

    # Splitting
    rectified_rep = snap(unified_rep, confluence_points, tolerance = 0.1)
    rectified_rep = split(unified_rep, confluence_points)

    # Selecting little reaches that go from confluence/defluence points to mask boundary  
    # Saving kept features from replacement data
    selected_geometries = []
    rectified_rep_features = []
    for geometry in list(rectified_rep.geoms):
        if geometry.intersects(mask.boundary):
            selected_geometries.append(geometry)
        else:
            feature = {'geometry' : mapping(geometry), 
                       'properties' : {}}
            rectified_rep_features.append(feature)

    # Correcting upstream and downstream reaches - extension to confluence/defluence points
    upstream_reach_geometry = shape(upstream_reach["geometry"])
    downstream_reach_geometry = shape(downstream_reach["geometry"])

    for reach_geometry in [upstream_reach_geometry, downstream_reach_geometry]:
        distances = [f.distance(reach_geometry) for f in selected_geometries]
        selected_geometries_dict = dict(zip(distances, selected_geometries))

        if reach_geometry == upstream_reach_geometry:
            new_upstream_reach_geometry = reach_geometry.union(selected_geometries_dict[min(distances)])
            upstream_reach = {'geometry' : mapping(new_upstream_reach_geometry), 
                              'properties' : {}}
        else:
            new_downstream_reach_geometry = reach_geometry.union(selected_geometries_dict[min(distances)])
            downstream_reach = {'geometry' : mapping(new_downstream_reach_geometry), 
                                'properties' : {}}
    
    return rectified_rep_features, upstream_reach, downstream_reach


def apply_default_attributes(src, default_attributes, verbose=True):
    """ Apply default attributes to all features of the source
    
        Arguments
        ---------
            src : fiona.Collection
                Source layer
            default attributes : dict
                Attributes and their default values
            verbose : bool
                True for verbose mode
    
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


def create_nodes(reaches, spacing=200.0, verbose=True):
    """ Create nodes on every reaches in a list
    
        Arguments
        ---------
            reaches : list
                List of reaches (dictionnaries following the Python geo protocol, as in a fiona.Collection)
            spacing : float
                Prescribed spacing between nodes (the actual spacing will differ to ensure equal spacing between nodes)
            verbose : bool
                True for verbose mode
    
        Returns
        -------
            nodes : list
                List of nodes (dictionnaries following the Python geo protocol, as in a fiona.Collection)

    """
    
    # Loop on features in reaches to extract segments
    # Segments are tuples (LineString, feature index in the source, index of the LineString in the source geometry)
    segments = []
    for feature_index, feature in enumerate(reaches):
        
        # Retrieve geometry of the feature
        geometry = shape(feature["geometry"])

        if geometry.type == "MultiLineString":
            
            # Extract LineStrings of a MultiLineString object
            for index, geom in enumerate(geometry.geoms):
                segments.append((geom, feature_index, index))
            
        elif geometry.type == "LineString":

            # Store LineString
            segments.append((geometry, feature_index, 0))
            
        else:
            raise RuntimeError("Cannot process geometry of type %s" % geometry.type)
            
    # Loop on segments to create nodes
    nodes = []
    for segment in segments:
        
        # Retrieve objects from the tuple
        geometry, feature_index, subindex = segment
        
        # Compute length (in meters) of the linestring using geopy.distance.distance
        coords = list((geometry.coords))
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

        # Initialise current distance to zero
        dist = 0.0
        
        # Retrieve coordinates of the first node in the geometry
        lon1, lat1 = coords[0]
        
        # Loop on remaining points in the geometry
        for lon2, lat2 in coords[1:]:
            
            # Compute distance increment between current Point2 and Point1
            ddist = distance(lonlat(lon1, lat1), lonlat(lon2, lat2)).meters
            
            if dist + ddist >= next_node_dist:
                
                #Create a new node as dist + ddist >= next_node_dist
                alpha = (next_node_dist - dist) / ddist
                lon = lon1 + alpha * (lon2 - lon1)
                lat = lat1 + alpha * (lat2 - lat1)
                nodes.append((Point((lon, lat)), feature_index, subindex, len(nodes)+1))
                
                # Increments next_node_dist
                next_node_dist += actual_spacing
                
            # Increment current distance
            dist += ddist

            # Pass Point2 coordinates to Point 1 for the next loop iteration
            lon1, lat1 = lon2, lat2
            
        if verbose:
            print("Created %i nodes on segment %i" % (nnodes, feature_index))

      
    return nodes