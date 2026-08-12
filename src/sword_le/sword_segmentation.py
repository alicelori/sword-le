from shapely.geometry import Point
from shapely.ops import substring
import pandas as pd
from shapely.ops import linemerge


def load_obstructions(csv_path):

    df = pd.read_csv(csv_path)

    return [
        Point(x, y)
        for x, y in zip(
            df["Longitude"],
            df["Latitude"],
        )
    ]


def cut_at_obstructions(
    segments,
    obstruction_points,
    buffer_deg=0.00009,  # ~10 m
    cut_deg=0.0018,  # ~200 m
):
    """
    Split segments around obstruction points.

    Parameters
    ----------
    segments : list[LineString]

    obstruction_points : list[Point]

    buffer_deg : float
        Approximate 10 m buffer in degrees.

    cut_deg : float
        Approximate 200 m cut distance in degrees.

    Returns
    -------
    list[dict]

    Example
    -------
    {
        "geometry": LineString,
        "has_obstruction": True,
    }
    """

    output_segments = []

    for line in segments:
        current_segments = [
            {
                "geometry": line,
                "has_obstruction": False,
            }
        ]

        for obstruction in obstruction_points:
            obstruction_buffer = obstruction.buffer(buffer_deg)

            next_segments = []

            for seg_data in current_segments:
                seg = seg_data["geometry"]

                if not seg.intersects(obstruction_buffer):
                    next_segments.append(seg_data)
                    continue

                distance_along = seg.project(obstruction)

                start_cut = max(
                    0.0,
                    distance_along - cut_deg,
                )

                end_cut = min(
                    seg.length,
                    distance_along + cut_deg,
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

                if before.length > 0:
                    next_segments.append(
                        {
                            "geometry": before,
                            "has_obstruction": False,
                        }
                    )

                if middle.length > 0:
                    next_segments.append(
                        {
                            "geometry": middle,
                            "has_obstruction": True,
                        }
                    )

                if after.length > 0:
                    next_segments.append(
                        {
                            "geometry": after,
                            "has_obstruction": False,
                        }
                    )

            current_segments = next_segments

        output_segments.extend(current_segments)

    return output_segments


def split_long_lines(
    segments,
    max_length_deg=0.27,
):
    """
    Split long segments while preserving
    obstruction metadata.
    """

    output_segments = []

    for seg_data in segments:
        if isinstance(seg_data, dict):
            line = seg_data["geometry"]

            has_obstruction = seg_data.get(
                "has_obstruction",
                False,
            )

        else:
            line = seg_data

            has_obstruction = False

        if line.length <= max_length_deg:
            output_segments.append(
                {
                    "geometry": line,
                    "has_obstruction": has_obstruction,
                }
            )

            continue

        start = 0.0

        while start < line.length:
            end = min(
                start + max_length_deg,
                line.length,
            )

            output_segments.append(
                {
                    "geometry": substring(
                        line,
                        start,
                        end,
                    ),
                    "has_obstruction": has_obstruction,
                }
            )

            start = end

    return output_segments


def merge_short_reaches(
    segments,
    pivot_nodes,
    min_length_deg=0.00135,  # ~150 m
    tolerance=1e-6,
):
    """
    Merge reaches shorter than approximately 150 m,
    except when they are connected through a pivot node
    or contain an obstruction.

    Parameters
    ----------
    segments : list[dict]
        List of segments.

    pivot_nodes : list[tuple]
        Pivot node coordinates.

    min_length_deg : float
        Approximate minimum reach length in degrees.
        150 m ≈ 0.00135°.

    tolerance : float
        Distance tolerance used to identify pivot nodes.

    Returns
    -------
    list[dict]
        Updated segments.
    """

    if len(segments) <= 1:
        return segments

    pivot_points = [Point(pivot) for pivot in pivot_nodes]

    merged_segments = [segments[0]]

    for segment in segments[1:]:
        geom = segment["geometry"]

        if geom.length >= min_length_deg or segment["has_obstruction"]:
            merged_segments.append(segment)

            continue

        previous = merged_segments[-1]

        shared_point = Point(previous["geometry"].coords[-1])

        is_pivot = any(
            shared_point.distance(pivot) < tolerance for pivot in pivot_points
        )

        if is_pivot:
            merged_segments.append(segment)

            continue

        merged_geom = linemerge(
            [
                previous["geometry"],
                geom,
            ]
        )

        previous["geometry"] = merged_geom

        previous["has_obstruction"] = (
            previous["has_obstruction"] or segment["has_obstruction"]
        )

    return merged_segments
