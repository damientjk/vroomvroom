"""History lookup evidence tool.

Summarises both the rider's and driver's account history so the Judge can
contextualise a dispute. Per policy doc §7.2 the output shape is::

    {
      "rider":   { avg_rating, total_trips, account_age_days,
                    dispute_history: {...}, fraud_flags },
      "driver":  { avg_rating, total_trips, account_age_days,
                    dispute_history: {...}, fraud_flags }
    }

The Judge prompt explicitly forbids ratings/history from overriding trip
evidence in the outcome decision — these are context only.
"""

from __future__ import annotations

from schemas import DisputeCase, EvidenceOutput


def history_lookup(case: DisputeCase) -> EvidenceOutput:
    """Return a summary of both parties' account history."""
    rider = case.rider_profile
    driver = case.driver_profile

    facts = {
        "rider": {
            "avg_rating": rider.avg_rating,
            "total_trips": rider.total_trips,
            "account_age_days": rider.account_age_days,
            "dispute_history": rider.dispute_history.model_dump(),
            "fraud_flags": rider.fraud_flags,
            "fraud_flag_details": rider.fraud_flag_details,
        },
        "driver": {
            "avg_rating": driver.avg_rating,
            "total_trips": driver.total_trips,
            "account_age_days": driver.account_age_days,
            "dispute_history": driver.dispute_history.model_dump(),
            "fraud_flags": driver.fraud_flags,
            "fraud_flag_details": driver.fraud_flag_details,
        },
    }

    flags: list[str] = []
    if rider.fraud_flags:
        flags.append("RIDER_FRAUD_FLAG")
    if driver.fraud_flags:
        flags.append("DRIVER_FRAUD_FLAG")

    return EvidenceOutput(
        dispute_id=case.dispute_ticket.dispute_id,
        tool="history_lookup",
        facts=facts,
        flags=flags,
    )
