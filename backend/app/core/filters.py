"""
Reusable geo-filter helpers for raw-SQL query builders.

Every service that constructs WHERE clauses for region / market / area
should call ``apply_geo_filters`` instead of hand-coding the logic.
This keeps the single-value → multi-value migration in one place.
"""


def apply_geo_filters(
    clauses: list[str],
    params: dict,
    *,
    region: list[str] | None = None,
    market: list[str] | None = None,
    area: list[str] | None = None,
    site_id: str | None = None,
    vendor: str | None = None,
    prefix: str = "",
    region_col: str = "region",
    market_col: str = "m_market",
    area_col: str = "m_area",
    site_id_col: str = "s_site_id",
    vendor_col: str = "construction_gc",
) -> None:
    """Mutate *clauses* and *params* in-place, adding IN / = filters.

    Parameters
    ----------
    prefix : str
        Optional prefix for bind-parameter names to avoid collisions
        (e.g. ``"f_"`` for sla_history).
    """
    if region:
        placeholders = ", ".join(f":{prefix}region_{i}" for i in range(len(region)))
        clauses.append(f"{region_col} IN ({placeholders})")
        for i, val in enumerate(region):
            params[f"{prefix}region_{i}"] = val

    if market:
        placeholders = ", ".join(f":{prefix}market_{i}" for i in range(len(market)))
        clauses.append(f"{market_col} IN ({placeholders})")
        for i, val in enumerate(market):
            params[f"{prefix}market_{i}"] = val

    if area:
        placeholders = ", ".join(f":{prefix}area_{i}" for i in range(len(area)))
        clauses.append(f"{area_col} IN ({placeholders})")
        for i, val in enumerate(area):
            params[f"{prefix}area_{i}"] = val

    if site_id:
        clauses.append(f"{site_id_col} = :{prefix}site_id")
        params[f"{prefix}site_id"] = site_id

    if vendor:
        clauses.append(f"{vendor_col} = :{prefix}vendor")
        params[f"{prefix}vendor"] = vendor
