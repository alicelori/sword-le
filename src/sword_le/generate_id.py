def generate_reaches_id(
    upstream_reach_id,
    segments,
):
    """
    Generate replacement reach IDs and T values.

    Parameters
    ----------
    upstream_reach_id : str | int

    segments : list[dict]

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

    new_reaches = []

    for i, segment in enumerate(
        segments,
        start=9000,
    ):
        t_value = (
            4
            if segment.get(
                "has_obstruction",
                False,
            )
            else 1
        )

        reach_id = f"{prefix}{i}{t_value}"

        segment["reach_id"] = reach_id
        segment["T"] = t_value

        new_reaches.append(
            {
                "reach_id": reach_id,
                "T": t_value,
            }
        )
    return (
        segments,
        new_reaches,
    )
