#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Integration tests."""
import json
import os

import fiona
import pytest
from shapely.geometry import shape

from sword_le import swordle

SWORD_DIR = "./data/SWORD_v17b_shp"
MASK_PATH_RAMIER = "./data/masque_ramier/masque_ramier_polygone.shp"
TOPAGE_EXTRACTION_PATH_RAMIER = (
    "./data/topage_extraction_ramier/topage_extraction_ramier_4326.shp"
)


# pylint: disable=redefined-outer-name
# Input
@pytest.fixture
def src():
    """Return sword v17b path."""
    with fiona.Collection(
        os.path.join(SWORD_DIR, "shp/EU/eu_sword_reaches_hb23_v17b.shp"), "r"
    ) as collection:
        yield collection


@pytest.fixture
def rep():
    """Return topage path"""
    with fiona.Collection(TOPAGE_EXTRACTION_PATH_RAMIER, "r") as collection:
        yield collection


@pytest.fixture
def mask():
    """Return mask path"""
    return shape(fiona.Collection(MASK_PATH_RAMIER, "r")[0]["geometry"])


# Output
@pytest.fixture
def default_attributes():
    """Return attribute path"""
    with open(
        "./data/default_attributes_v17b.json", "r", encoding="utf-8"
    ) as fin:
        default_attributes = json.load(fin)
    return default_attributes


@pytest.fixture
def src_masked_out():
    """Return sword reaches outside using mask"""
    with fiona.Collection(
        "./data/out_logic1/test_src_masked_out.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def rep_masked_out():
    """Return topage reaches outside using mask"""
    with fiona.Collection(
        "./data/out_logic1/test_rep_masked_out.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def rep_masked_in():
    """Return topage reaches inside using mask"""
    with fiona.Collection(
        "./data/out_logic1/test_rep_masked_in.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def src_upstream_reach1():
    """Return sword reach upstream with logic1"""
    with fiona.Collection(
        "./data/out_logic1/test_src_up_reach.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def src_downstream_reach1():
    """Return sword downstream reach with logic1"""
    with fiona.Collection(
        "./data/out_logic1/test_src_dw_reach.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def src_upstream_reach2():
    """Return sword upstream reach with logic2"""
    with fiona.Collection(
        "./data/out_logic2/test_src_up_reach.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def src_downstream_reach2():
    """Return sword downstream reach with logic1"""
    with fiona.Collection(
        "./data/out_logic2/test_src_dw_reach.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def intersection_points():
    """Return intersection point with the mask"""
    with fiona.Collection(
        "./data/out_logic1/test_points.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def new_upstream_reach():
    """Return new upstream reach"""
    with fiona.Collection(
        "./data/out_logic1/test_new_up_reach.shp", "r"
    ) as collection:
        yield collection


@pytest.fixture
def new_downstream_reach():
    """Return new downstream reach"""
    with fiona.Collection(
        "./data/out_logic1/test_new_dw_reach.shp", "r"
    ) as collection:
        yield collection


# Unit test
@pytest.mark.external
def test_integration_select_reaches_using_mask(src, mask, src_masked_out):
    """Test integration topage reaches outside using mask"""
    result = swordle.select_reaches_using_mask(src, mask, where="out")
    geoms_result = [shape(f["geometry"]) for f in result]
    geoms = [shape(f["geometry"]) for f in src_masked_out]
    assert len(geoms_result) == len(geoms)
    for g1, g2 in zip(geoms_result, geoms):
        assert g1.equals_exact(g2, tolerance=1e-6)


@pytest.mark.external
def test_integration_find_upstream_downstream_reaches_using_mask_logic1(
    src, mask, src_upstream_reach1, src_downstream_reach1
):
    """Test integration find upstream and downstream reaches using mask with logic1"""
    src_masked_out = swordle.select_reaches_using_mask(src, mask, where="out")
    src_upstream_reach_result_logic1, src_downstream_reach_result_logic1 = (
        swordle.find_upstream_downstream_reaches_using_mask_logic1(
            src_masked_out, mask
        )
    )
    src_upstream_reach_feature_logic1 = next(iter(src_upstream_reach1))
    src_downstream_reach_feature_logic1 = next(iter(src_downstream_reach1))
    assert (
        src_downstream_reach_feature_logic1.properties
        == src_downstream_reach_result_logic1["properties"]
    )
    assert (
        src_upstream_reach_feature_logic1.properties
        == src_upstream_reach_result_logic1["properties"]
    )


@pytest.mark.external
def test_integration_find_upstream_downstream_reaches_using_mask_logic2(
    src, mask, src_upstream_reach2, src_downstream_reach2
):
    """Test integration find upstream and downstream reaches using mask with logic2"""
    src_masked_out = swordle.select_reaches_using_mask(src, mask, where="out")
    src_upstream_reach_result_logic2, src_downstream_reach_result_logic2 = (
        swordle.find_upstream_downstream_reaches_using_mask_logic2(
            src_masked_out, mask
        )
    )
    src_upstream_reach_feature_logic2 = next(iter(src_upstream_reach2))
    src_downstream_reach_feature_logic2 = next(iter(src_downstream_reach2))
    assert (
        src_downstream_reach_feature_logic2.properties
        == src_downstream_reach_result_logic2["properties"]
    )
    assert (
        src_upstream_reach_feature_logic2.properties
        == src_upstream_reach_result_logic2["properties"]
    )


@pytest.mark.external
def test_integration_find_closest_intersection_point_to_the_mask(
    src, mask, rep_masked_out, intersection_points
):
    """Test integration find closest intersection point to the mask"""
    src_upstream_reach_result, src_downstream_reach_result = (
        swordle.find_upstream_downstream_reaches_using_mask_logic1(src, mask)
    )
    upstream_intersection_point_result = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_upstream_reach_result, mask
        )
    )
    downstream_intersection_point_result = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_downstream_reach_result, mask
        )
    )
    intersection_points = [
        shape(feature["geometry"]) for feature in intersection_points
    ]
    assert len(intersection_points) == 2
    for r in [
        shape(upstream_intersection_point_result),
        shape(downstream_intersection_point_result),
    ]:
        assert any(
            r.equals_exact(p, tolerance=1e-4) for p in intersection_points
        )


@pytest.mark.external
def test_integration_correct_reach_using_intersection_point(
    src,
    rep_masked_out,
    mask,
    new_upstream_reach,
    new_downstream_reach,
    rep_masked_in,
):
    """Test integration correct reach using intersection point"""
    src_upstream_reach_result, src_downstream_reach_result = (
        swordle.find_upstream_downstream_reaches_using_mask_logic1(src, mask)
    )
    upstream_intersection_point_result = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_upstream_reach_result, mask
        )
    )
    downstream_intersection_point_result = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_downstream_reach_result, mask
        )
    )

    upstream_reach_result = swordle.correct_reach_using_intersection_point(
        rep_masked_out,
        src_upstream_reach_result,
        upstream_intersection_point_result,
        mask,
    )
    downstream_reach_result = swordle.correct_reach_using_intersection_point(
        rep_masked_out,
        src_downstream_reach_result,
        downstream_intersection_point_result,
        mask,
    )
    _, upstream_reach_result, downstream_reach_result = (
        swordle.adjust_reaches_with_confluence_using_mask(
            rep_masked_in, upstream_reach_result, downstream_reach_result, mask
        )
    )

    new_upstream_reach_feature = next(iter(new_upstream_reach))
    new_downstream_reach_feature = next(iter(new_downstream_reach))

    geom_upstream_reach_result = shape(upstream_reach_result["geometry"])
    coords1_upstream_reach_result = list(geom_upstream_reach_result.coords)
    coords2_new_upstream_reach_feature = shape(
        new_upstream_reach_feature.geometry
    ).coords

    geom_downstream_reach_result = shape(downstream_reach_result["geometry"])
    coords1_downstream_reach_result = list(geom_downstream_reach_result.coords)
    coords2_new_downstream_reach_feature = shape(
        new_downstream_reach_feature.geometry
    ).coords

    assert list(coords1_upstream_reach_result) == list(
        coords2_new_upstream_reach_feature
    )
    assert list(coords1_downstream_reach_result) == list(
        coords2_new_downstream_reach_feature
    )
