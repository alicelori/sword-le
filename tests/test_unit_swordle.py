#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unit tests for utility functions."""
import json
import os

import fiona
import pytest
from shapely.geometry import Point, shape

from sword_le import swordle

SWORD_DIR = "./tests/data/sword-le-test-data/SWORD_v17b_shp"
MASK_PATH_RAMIER = "./tests/data/sword-le-test-data/masque_ramier/masque_ramier_polygone.shp"
TOPAGE_EXTRACTION_PATH_RAMIER = (
    "./tests/data/sword-le-test-data/topage_extraction_ramier/topage_extraction_ramier_4326.shp"
)


# pylint: disable=redefined-outer-name
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


@pytest.fixture
def default_attributes():
    """Return attribute path"""
    with open(
        "./tests/data/sword-le-test-data/default_attributes_v17b.json", "r", encoding="utf-8"
    ) as fin:
        default_attributes_json = json.load(fin)
    return default_attributes_json


@pytest.fixture
def src_masked_out(src, mask):
    """Return sword reaches outside using mask"""
    return swordle.select_reaches_using_mask(src, mask, where="out")


@pytest.fixture
def rep_masked_out(rep, mask):
    """Return topage reaches outside using mask"""
    return swordle.select_reaches_using_mask(
        rep, mask, where="out", crs=rep.crs
    )


@pytest.fixture
def rep_masked_in(rep, mask):
    """Return topage reaches inside using mask"""
    return swordle.select_reaches_using_mask(rep, mask, where="in", crs=rep.crs)


@pytest.mark.external
def test_select_reaches_using_mask(src, mask):
    """Test topage reaches outside using mask"""
    result = swordle.select_reaches_using_mask(src, mask, where="out")
    assert isinstance(result, list)
    assert len(result) > 0


@pytest.mark.external
def test_get_number_of_reaches_connected_to_mask(src, mask):
    """Test the number of reaches connected to mask"""
    nb_reach = swordle.get_number_of_reaches_connected_to_mask(src, mask)
    assert isinstance(nb_reach, int)


@pytest.mark.external
def test_get_matching_src_rep_reaches_using_mask(src, rep, mask):
    """Test the number of reaches connected to mask"""
    nb_reach = swordle.get_number_of_reaches_connected_to_mask(src, mask)
    result = swordle.get_matching_src_rep_reaches_using_mask(
        src, rep, mask, nb_reach
    )
    assert isinstance(result, list)


@pytest.mark.external
def test_get_lines_list(src):
    """Test get lines list in sword"""
    for feature in src:
        geom = shape(feature["geometry"])
        result = swordle.get_lines_list(geom)
    assert isinstance(result, list)


@pytest.mark.external
def test_apply_default_attributes(rep, default_attributes):
    """Test apply sword attributes to topage"""
    result = swordle.apply_default_attributes(rep, default_attributes)
    assert isinstance(result, fiona.Collection)


@pytest.mark.external
def test_find_upstream_downstream_reaches_using_mask_logic1(
    src_masked_out, mask
):
    """Test find upstream/downstream reaches using mask (logic1)"""
    src_up, src_down = (
        swordle.find_upstream_downstream_reaches_using_mask_logic1(
            src_masked_out, mask
        )
    )
    assert isinstance(src_up, dict)
    assert isinstance(src_down, dict)


@pytest.mark.external
def test_find_upstream_downstream_reaches_using_mask_logic2(
    src_masked_out, mask
):
    """Test find upstream/downstream reaches using mask (logic2)"""
    src_up2, src_down2 = (
        swordle.find_upstream_downstream_reaches_using_mask_logic2(
            src_masked_out, mask
        )
    )
    assert isinstance(src_up2, dict)
    assert isinstance(src_down2, dict)


@pytest.mark.external
def test_find_closest_intersection_point_to_the_mask(
    rep_masked_out, src_masked_out, mask
):
    """Test find closest intersection point to the mask"""
    src_up, _ = swordle.find_upstream_downstream_reaches_using_mask_logic1(
        src_masked_out, mask
    )
    up_intersection_point = swordle.find_closest_intersection_point_to_the_mask(
        rep_masked_out, src_up, mask
    )
    assert isinstance(up_intersection_point, Point)


@pytest.mark.external
def test_correct_reach_using_intersection_point(
    rep_masked_out, src_masked_out, mask
):
    """Test correct reach using intersectino point"""
    src_up, _ = swordle.find_upstream_downstream_reaches_using_mask_logic1(
        src_masked_out, mask
    )
    up_intersection_point = swordle.find_closest_intersection_point_to_the_mask(
        rep_masked_out, src_up, mask
    )
    up = swordle.correct_reach_using_intersection_point(
        rep_masked_out, src_up, up_intersection_point, mask
    )
    assert isinstance(up, dict)


@pytest.mark.external
def test_adjust_reaches_with_confluence_using_mask(
    rep_masked_in, rep_masked_out, src_masked_out, mask
):
    """Test adjsut reach with confluence using mask"""
    src_upstream_reach, src_downstream_reach = (
        swordle.find_upstream_downstream_reaches_using_mask_logic1(
            src_masked_out, mask
        )
    )
    upstream_intersection_point = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_upstream_reach, mask
        )
    )
    downstream_intersection_point = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_downstream_reach, mask
        )
    )
    upstream_reach = swordle.correct_reach_using_intersection_point(
        rep_masked_out, src_upstream_reach, upstream_intersection_point, mask
    )
    downstream_reach = swordle.correct_reach_using_intersection_point(
        rep_masked_out,
        src_downstream_reach,
        downstream_intersection_point,
        mask,
    )
    rectified_rep_features, upstream_reach, downstream_reach = (
        swordle.adjust_reaches_with_confluence_using_mask(
            rep_masked_in, upstream_reach, downstream_reach, mask
        )
    )
    assert isinstance(rectified_rep_features, list)
    assert isinstance(upstream_reach, dict)
    assert isinstance(downstream_reach, dict)


@pytest.mark.external
def test_compute_reach_length(rep_masked_out, src_masked_out, mask):
    """Test compute reach length"""
    src_upstream_reach, _ = (
        swordle.find_upstream_downstream_reaches_using_mask_logic1(
            src_masked_out, mask
        )
    )
    upstream_intersection_point = (
        swordle.find_closest_intersection_point_to_the_mask(
            rep_masked_out, src_upstream_reach, mask
        )
    )
    upstream_reach = swordle.correct_reach_using_intersection_point(
        rep_masked_out, src_upstream_reach, upstream_intersection_point, mask
    )
    reach_length = swordle.compute_reach_length(upstream_reach)
    assert isinstance(reach_length, float)
