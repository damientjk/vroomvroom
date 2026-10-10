"""Fare validation evidence tool.

Surfaces the fare facts for a dispute (handoff §4 ``fare_validate()``):
the fare type, what the rider was charged, the per-km rate and surge, plus
a check that the fare breakdown's components add up to the charged fare.
For no-show disputes there is no fare breakdown, so the charged amount is
the cancellation fee.  Facts only: refunds come from the outcome formulas.
"""

from __future__ import annotations

from schemas import DisputeCase, EvidenceOutput

# Breakdown keys that are not components of the charged fare.
_NON_COMPONENT_KEYS = {"actual_fare_sgd", "per_km_rate_sgd"}
_ROUNDING_TOLERANCE_SGD = 0.01


def fare_validate(case: DisputeCase) -> EvidenceOutput:
    """Return fare facts for *case*.

    Computes:
      - fare_type, per_km_rate_sgd, surge_applied (from fare_breakdown)
      - actual_fare_sgd and fare_source ("fare_breakdown" or
        "cancellation_fee")
      - components_sum_sgd: sum of the breakdown's other *_sgd amounts
      - breakdown_consistent: components add up to the charged fare
    """
    trip = case.trip_data
    breakdown = trip.fare_breakdown

    if breakdown is not None:
        fare_type = breakdown.get("fare_type")
        actual_fare_sgd = breakdown.get("actual_fare_sgd")
        fare_source = "fare_breakdown" if actual_fare_sgd is not None else None
        per_km_rate_sgd = breakdown.get("per_km_rate_sgd")
        surge_applied = breakdown.get("surge_applied")
        components = [
            value
            for key, value in breakdown.items()
            if key.endswith("_sgd")
            and key not in _NON_COMPONENT_KEYS
            and isinstance(value, (int, float))
        ]
    else:
        fare_type = None
        actual_fare_sgd = None
        fare_source = None
        per_km_rate_sgd = None
        surge_applied = None
        components = []

    if actual_fare_sgd is None and trip.cancellation_fee is not None:
        actual_fare_sgd = trip.cancellation_fee
        fare_source = "cancellation_fee"

    # Fixed fares (and no-show fees) have no itemised components to check.
    if components and actual_fare_sgd is not None:
        components_sum_sgd = round(sum(components), 2)
        breakdown_consistent = (
            abs(components_sum_sgd - actual_fare_sgd) <= _ROUNDING_TOLERANCE_SGD
        )
    else:
        components_sum_sgd = None
        breakdown_consistent = None

    facts: dict[str, object] = {
        "fare_type": fare_type,
        "actual_fare_sgd": actual_fare_sgd,
        "fare_source": fare_source,
        "per_km_rate_sgd": per_km_rate_sgd,
        "surge_applied": surge_applied,
        "components_sum_sgd": components_sum_sgd,
        "breakdown_consistent": breakdown_consistent,
    }

    flags: list[str] = []
    if actual_fare_sgd is None:
        flags.append("FARE_DATA_MISSING")
    if breakdown_consistent is False:
        flags.append("FARE_BREAKDOWN_MISMATCH")

    return EvidenceOutput(
        dispute_id=case.dispute_ticket.dispute_id,
        tool="fare_validate",
        facts=facts,
        flags=flags,
    )
