"""Vendor comparison. Pure functions over plain dicts so the logic is testable and reusable."""
from __future__ import annotations

from typing import Any

DEFAULT_WEIGHTS = {
    "price": 0.25,
    "delivery": 0.20,
    "rating": 0.20,
    "warranty": 0.10,
    "reliability": 0.20,
    "compliance": 0.05,
}


def price_delta_pct(unit_price: float, historical_avg: float | None) -> float | None:
    if not historical_avg:
        return None
    return round((unit_price - historical_avg) / historical_avg * 100, 1)


def evaluate_vendors(
    vendors: list[dict[str, Any]],
    *,
    category: str,
    quantity: int,
    budget: int | None,
    days_until_required: int | None,
    weights: dict[str, float] | None = None,
    excluded_ids: set[int] | None = None,
    relax: bool = False,
) -> list[dict[str, Any]]:
    """Return every vendor as an offer dict with eligibility, reasons, score and rank."""
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    excluded_ids = excluded_ids or set()
    offers: list[dict[str, Any]] = []
    for v in vendors:
        unit = v["catalog"].get(category)
        offer = {
            "vendor_id": v["id"],
            "name": v["name"],
            "approved": v["approved"],
            "unit_price": unit,
            "total": unit * quantity if unit else None,
            "delivery_days": v["delivery_days"],
            "rating": v["rating"],
            "warranty_years": v["warranty_years"],
            "reliability": v["reliability_score"],
            "compliance": v["compliance_score"],
            "historical_avg": v["historical_avg"].get(category),
            "price_delta_pct": price_delta_pct(unit, v["historical_avg"].get(category)) if unit else None,
            "eligible": True,
            "reasons": [],
            "warnings": [],
            "score": 0.0,
            "rank": None,
        }
        hard: list[str] = []
        soft: list[str] = []
        if unit is None:
            hard.append(f"Does not supply '{category}'")
        if not v["approved"]:
            hard.append("Not an approved vendor")
        if not v["available"] or v["id"] in excluded_ids:
            hard.append("Currently unavailable")
        if unit is not None:
            if days_until_required is not None and v["delivery_days"] > days_until_required:
                (soft if relax else hard).append(
                    f"Delivery in {v['delivery_days']}d misses the {days_until_required}d requirement"
                )
            if budget is not None and unit * quantity > budget:
                (soft if relax else hard).append("Quote exceeds the requested budget")
        offer["reasons"] = hard
        offer["warnings"] = soft
        offer["eligible"] = not hard
        offers.append(offer)

    priced = [o for o in offers if o["eligible"]]
    if priced:
        min_price = min(o["unit_price"] for o in priced)
        min_delivery = min(o["delivery_days"] for o in priced)
        for o in priced:
            o["score"] = round(
                weights["price"] * (min_price / o["unit_price"])
                + weights["delivery"] * (min_delivery / o["delivery_days"])
                + weights["rating"] * (o["rating"] / 5)
                + weights["warranty"] * min(o["warranty_years"] / 3, 1)
                + weights["reliability"] * (o["reliability"] / 100)
                + weights["compliance"] * (o["compliance"] / 100),
                4,
            )
    offers.sort(key=lambda o: (not o["eligible"], -o["score"], o["unit_price"] or 10**12))
    rank = 1
    for o in offers:
        if o["eligible"]:
            o["rank"] = rank
            rank += 1
    return offers
