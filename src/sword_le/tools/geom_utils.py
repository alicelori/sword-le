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
