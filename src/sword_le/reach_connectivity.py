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


def compute_reach_connectivity(orientation):
    """
    Build upstream/downstream reach connectivity.

    Returns
    -------
    dict
        {
            reach_id: {
                "rch_id_up": [...],
                "rch_id_dn": [...]
            }
        }
    """

    connectivity = {}

    for rid, ori_set in orientation.items():
        dn_junction, up_junction = next(iter(ori_set))

        connectivity[rid] = {
            "rch_id_up": [],
            "rch_id_dn": [],
        }

        for other_rid, other_ori_set in orientation.items():
            if other_rid == rid:
                continue

            other_dn, other_up = next(iter(other_ori_set))

            # reaches connected upstream
            if other_dn == up_junction:
                connectivity[rid]["rch_id_up"].append(other_rid)

            # reaches connected downstream
            if other_up == dn_junction:
                connectivity[rid]["rch_id_dn"].append(other_rid)

    return connectivity


def add_reach_connectivity(
    gdf_reaches,
    orientation,
):
    connectivity = compute_reach_connectivity(orientation)

    gdf_reaches["rch_id_up"] = gdf_reaches.index.astype(str).map(
        lambda rid: connectivity.get(rid, {}).get("rch_id_up", [])
    )

    gdf_reaches["rch_id_dn"] = gdf_reaches.index.astype(str).map(
        lambda rid: connectivity.get(rid, {}).get("rch_id_dn", [])
    )

    return gdf_reaches


def parse_rch_ids(value):

    if value is None:
        return []

    if isinstance(value, list):
        return [str(v) for v in value]

    value = str(value).strip()

    if value in ("", "0", "None", "nan", "NaN"):
        return []

    return value.split()


def reconnect_connectivity(
    connectivity,
    old_upstream_reach,
    old_downstream_reach,
    new_upstream_reach_id,
    new_downstream_reach_id,
):
    old_up_ids = parse_rch_ids(old_upstream_reach["properties"]["rch_id_up"])

    old_dn_ids = parse_rch_ids(old_downstream_reach["properties"]["rch_id_dn"])

    connectivity.setdefault(str(new_upstream_reach_id), {})

    connectivity[str(new_upstream_reach_id)]["rch_id_up"] = old_up_ids

    connectivity.setdefault(str(new_downstream_reach_id), {})

    connectivity[str(new_downstream_reach_id)]["rch_id_dn"] = old_dn_ids

    old_upstream_id = str(old_upstream_reach["properties"]["reach_id"])

    for rid in old_up_ids:
        rid = str(rid)

        connectivity.setdefault(rid, {})

        dn = connectivity[rid].get("rch_id_dn", [])

        if old_upstream_id in dn:
            dn = [str(new_upstream_reach_id) if x == old_upstream_id else x for x in dn]
        else:
            dn.append(str(new_upstream_reach_id))

        connectivity[rid]["rch_id_dn"] = dn

    old_downstream_id = str(old_downstream_reach["properties"]["reach_id"])

    for rid in old_dn_ids:
        rid = str(rid)

        connectivity.setdefault(rid, {})

        up = connectivity[rid].get("rch_id_up", [])

        if old_downstream_id in up:
            up = [
                str(new_downstream_reach_id) if x == old_downstream_id else x
                for x in up
            ]
        else:
            up.append(str(new_downstream_reach_id))

        connectivity[rid]["rch_id_up"] = up

    return connectivity
