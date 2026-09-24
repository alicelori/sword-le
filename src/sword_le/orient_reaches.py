import networkx as nx
from shapely import LineString


def get_reach_to_junctions(reaches):
    """
    Build a dictionary:

        reach_id -> (junction_1, junction_2)

    Here, junctions are simply represented by the
    first and last coordinates of each LineString.
    """

    reach_to_junctions = {}

    for reach in reaches:
        rid = reach["reach_id"]

        # First vertex of the geometry
        p0 = tuple(reach["geometry"].coords[0])

        # Last vertex of the geometry
        p1 = tuple(reach["geometry"].coords[-1])

        # Associate the reach with its two end junctions
        reach_to_junctions[rid] = (p0, p1)

    return reach_to_junctions


def create_graph(reach_to_junctions):
    """
    Create a bipartite graph:

        junction <-> reach <-> junction

    Reaches are represented as graph nodes,
    connected to the two junctions they touch.
    """

    G = nx.Graph()

    for rid, (p0, p1) in reach_to_junctions.items():
        # Connect reach to its first junction
        G.add_edge(rid, p0)

        # Connect reach to its second junction
        G.add_edge(rid, p1)

    return G


def get_all_paths(
    reaches,
    downstream_point,
    upstream_point,
):
    """
    Find all simple paths between:

        downstream_point -> upstream_point

    Each path alternates between:

        junction -> reach -> junction -> reach ...
    """

    reach_to_junctions = get_reach_to_junctions(reaches)

    G = create_graph(reach_to_junctions)

    paths = list(
        nx.all_simple_paths(
            G,
            source=downstream_point,
            target=upstream_point,
        )
    )

    return paths


def get_reach_orientation(paths):
    """
    Infer the orientation of each reach from
    the computed paths.

    For a path segment:

        J1 -> R1 -> J2

    we assume:

        downstream junction = J1
        upstream junction = J2

    and store:

        R1 -> (J1, J2)

    If a reach appears in multiple paths,
    all observed orientations are retained.
    """

    orientation = {}

    for path in paths:
        # Iterate through intermediate path elements
        for i in range(1, len(path) - 1):
            current = path[i]

            # Reach IDs are strings
            if not isinstance(current, str):
                continue

            # Previous node in the path
            downstream_junction = path[i - 1]

            # Next node in the path
            upstream_junction = path[i + 1]

            ori = (
                downstream_junction,
                upstream_junction,
            )

            # Store all observed orientations
            orientation.setdefault(
                current,
                set(),
            ).add(ori)

    return orientation


def reorient_reaches(reaches, orientation):
    """
    Reorient geometries so that every reach follows:

        downstream -> upstream

    Cases:
        - Geometry already correctly oriented:
          do nothing.

        - Geometry is reversed:
          reverse the coordinate sequence.

        - Geometry endpoints do not match the
          expected junctions:
          print a warning.
    """

    for reach in reaches:
        rid = reach["reach_id"]

        # Reach not covered by any computed path
        if rid not in orientation:
            print(f"{rid} not covered")
            continue

        # Normally a single orientation is expected
        downstream_junction, upstream_junction = next(iter(orientation[rid]))

        coords = list(reach["geometry"].coords)

        # Geometry start point
        geom_start = tuple(coords[0])

        # Geometry end point
        geom_end = tuple(coords[-1])

        # Case 1:
        # Already oriented downstream -> upstream
        if geom_start == downstream_junction and geom_end == upstream_junction:
            continue

        # Case 2:
        # Geometry is upstream -> downstream
        # Reverse vertex order
        elif geom_start == upstream_junction and geom_end == downstream_junction:
            reach["geometry"] = LineString(coords[::-1])

        # Case 3:
        # Geometry endpoints do not match
        # the expected junctions
        else:
            print(f"Unable to match reach {rid}")

    return reaches
