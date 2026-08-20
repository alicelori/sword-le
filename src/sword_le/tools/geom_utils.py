import numpy as np
from shapely import line_interpolate_point
from shapely.geometry import LineString


def resample_line(line, step):
    distances = np.arange(0, line.length, step)
    distances = np.append(distances, line.length)

    return LineString([line_interpolate_point(line, d).coords[0] for d in distances])
