#!/usr/bin/env python3
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

def generate_reaches_id(
    upstream_reach_id,
    segments,
    existing_reach_ids,
    start_counter=9000,
):
    """
    Generate unique reach IDs.

    Parameters
    ----------
    upstream_reach_id : str | int
        Reach used as reference for the ID prefix.

    segments : list[dict]
        Segment dictionaries containing:
        - geometry
        - has_obstruction

    existing_reach_ids : set[str]
        Existing reach IDs.

    start_counter : int, optional
        Initial counter value.

    Returns
    -------
    tuple
        (
            updated_segments,
            new_reaches,
        )
    """

    upstream_reach_id = str(upstream_reach_id)

    prefix = upstream_reach_id[:-5]

    counter = start_counter

    new_reaches = []

    for segment in segments:

        suffix = (
            4
            if segment.get(
                "has_obstruction",
                False,
            )
            else 1
        )

        while True:

            reach_id = (
                f"{prefix}{counter}{suffix}"
            )

            if reach_id not in existing_reach_ids:
                break

            counter += 1

        segment["reach_id"] = reach_id

        existing_reach_ids.add(
            reach_id
        )

        new_reaches.append(
            {
                "reach_id": reach_id,
                "has_obstruction": segment.get(
                    "has_obstruction",
                    False,
                ),
            }
        )

        counter += 1

    return (
        segments,
        new_reaches,
    )