# Policy Implementation Handoff — for Damien

**Project:** RydeResolve — Multi-Agent Autonomous Dispute Resolution System
**From:** Marcus (Product, Data & Pitch)
**To:** Damien (Backend & Agents)
**Date:** 2026-10-09
**Active profile:** `HACKATHON_2026`
**Companion docs:** `docs/ryde_dispute_policy.md` (full clause text), `docs/policy_sources.md` (source verification), `schemas.md` (JSON shapes)

> This document is the implementation-spec distillation of the policy doc.
> Every rule below is traceable to a clause ID and classification there.
> `OFFICIAL` = verified Ryde source. `DATASET` = from DISP-002. `PROPOSED` = our design assumption, not from any verified source. Do not invent official rules.

---

## 1. Constants Module

Implement as `backend/app/policy_constants.py`. Profile switching = one-line change.

### HACKATHON_2026 (active)

| Constant | Value | Clause | Classification |
|---|---|---|---|
| `ARRIVAL_RADIUS_M` | `10` | NS-1.1 | DATASET (app event details: "within 10m") |
| `FREE_WAIT_TIME_MIN` | `5` | NS-1.3 | DATASET (`cancellation_policy.free_wait_time_min`) |
| `NO_SHOW_THRESHOLD_MIN` | `8` | NS-1.4 | DATASET (`cancellation_policy.no_show_threshold_min`) |
| `MINIMUM_CONTACT_ATTEMPTS` | `2` | NS-1.5 | PROPOSED |
| `CANCELLATION_FEE_SGD` | `5.00` | NS-1.6 | DATASET (`cancellation_policy.cancellation_fee_after_wait`) |
| `ROAD_NETWORK_FACTOR` | `1.3` | RD-2.1 | PROPOSED |
| `DEVIATION_REVIEW_THRESHOLD_PCT` | `20.0` | RD-2.2 | PROPOSED |
| `SPEEDING_THRESHOLD_KMH` | `90` | S-1.1 | PROPOSED |
| `AUTO_RULING_THRESHOLD` | `0.85` | E-1.6 | PROPOSED |
| `SPOT_CHECK_THRESHOLD` | `0.70` | E-1.6 | PROPOSED |

```python
SAFETY_KEYWORDS = [
    "threat", "threaten", "assault", "hit", "attack", "harass",
    "abuse", "racist", "race", "discriminat", "dangerous",
    "reckless", "scared", "afraid", "unsafe", "weapon",
]
```

### RYDE_PUBLIC_REFERENCE (reference only — do NOT use in prototype)

| Constant | Value | Source |
|---|---|---|
| `FREE_WAIT_TIME_MIN` | `3` | SRC-02, SRC-03 |
| `NO_SHOW_THRESHOLD_MIN` | `3` | SRC-02, SRC-03 (same 3-min period, no separate threshold) |
| `CANCELLATION_FEE_RIDER_FACING` | `6.61` | SRC-02, SRC-05 |
| `CANCELLATION_FEE_DRIVER_RECEIVING` | `4.50` | SRC-03 |

---

## 2. `no_show_check()` — Evidence Tool Spec

**Dispute type:** `no_show_charge`
**Input:** `DisputeCase` (full JSON from `data/DISP-002.json`)

### Required input JSON fields

| Field path | Used by | Purpose |
|---|---|---|
| `trip_data.pickup_location.{lat,lng}` | NS-1.1 | Haversine to driver GPS |
| `gps_telemetry[].{lat,lng,speed_kmh,status,timestamp}` | NS-1.1 | Find arrived GPS point, compute distance |
| `app_events[].event_type == "driver_arrived"` | NS-1.1 | Cross-verify arrival |
| `trip_data.scheduled_time` | NS-1.2 | Compare to arrival |
| `trip_data.driver_arrival_time` | NS-1.2 | Arrival time |
| `trip_data.driver_wait_start` | NS-1.3 | Wait start |
| `trip_data.cancellation_time` | NS-1.3, NS-1.4 | Wait end |
| `cancellation_policy.free_wait_time_min` | NS-1.3 | Free wait threshold |
| `cancellation_policy.no_show_threshold_min` | NS-1.4 | No-show threshold |
| `chat_logs[].{sender,type,content,timestamp}` | NS-1.5 | Count driver contact attempts |
| `app_events[].event_type == "driver_called_rider"` | NS-1.5 | Count call attempts |
| `chat_logs[].sender == "rider"` | NS-1.5 | Count rider replies |
| `cancellation_policy.cancellation_fee_after_wait` | NS-1.6 | Fee amount |

### Clause-by-clause specification

#### NS-1.1 — Driver GPS Arrival Verification

| | |
|---|---|
| **Classification** | DATASET (10m from app event details) |
| **Input fields** | `gps_telemetry`, `trip_data.pickup_location`, `app_events[driver_arrived]` |
| **Condition** | Find first GPS point with `status == "arrived"`. Compute `haversine(pickup, arrived_gps)`. |
| **Formula** | `driver_distance_from_pickup_m = haversine(pickup.lat, pickup.lng, arrived_gps.lat, arrived_gps.lng)` |
| **Gate** | `arrived = driver_distance_from_pickup_m <= ARRIVAL_RADIUS_M` (`<= 10`) |
| **Output fields** | `driver_distance_from_pickup_m: float`, `arrived: bool` |
| **Pass →** | Proceed to NS-1.2 |
| **Fail →** | `("charge_reversed", 5.00, ["NS-1.1", "NS-1.7"])` |
| **Missing evidence** | No GPS point with `status == "arrived"` → `arrived = False`, add `"gps_arrived_point"` to `missing_evidence` |
| **Conflicting evidence** | GPS shows arrived but `app_events` has no `driver_arrived` event → add `"app_event_driver_arrived"` to `missing_evidence`, `arrived` stays `True` (GPS is tier 2, app_events tier 1 — flag but don't override) |
| **Boundary tests** | Distance exactly 10m → pass. Distance 10.01m → fail. Distance 0m → pass. No `arrived` status in GPS → missing evidence. |

#### NS-1.2 — Scheduled Pickup Time Verification

| | |
|---|---|
| **Classification** | PROPOSED |
| **Input fields** | `trip_data.driver_arrival_time`, `trip_data.scheduled_time` |
| **Condition** | Informational — does not gate the chain. Computes signed minutes. |
| **Formula** | `arrived_minutes_vs_scheduled = (driver_arrival_time - scheduled_time).total_seconds() / 60.0` |
| **Gate** | None (informational). If `arrived_minutes_vs_scheduled > 0`, flag late arrival. If `> NO_SHOW_THRESHOLD_MIN`, charge cannot stand (rider wasn't a no-show for pre-arrival period). |
| **Output fields** | `arrived_minutes_vs_scheduled: float` |
| **Missing evidence** | `driver_arrival_time` absent → derive from first `arrived` GPS timestamp. If neither exists → add `"driver_arrival_time"` to `missing_evidence`. |
| **Boundary tests** | Arrival exactly at scheduled time → `0.0` (on time). Arrival 1 second before → `-0.017` (early). Arrival 1 second after → `0.017` (late, flag). |

#### NS-1.3 — Free Waiting Period

| | |
|---|---|
| **Classification** | DATASET (`free_wait_time_min = 5`) |
| **Input fields** | `trip_data.driver_wait_start`, `trip_data.cancellation_time`, `cancellation_policy.free_wait_time_min` |
| **Condition** | Total wait must be >= free wait period. |
| **Formula** | `total_wait_min = (cancellation_time - driver_wait_start).total_seconds() / 60.0` |
| **Gate** | `free_wait_expired = total_wait_min >= FREE_WAIT_TIME_MIN` (`>= 5`) |
| **Output fields** | `total_wait_min: float`, `free_wait_expired: bool` |
| **Pass →** | Proceed to NS-1.4 |
| **Fail →** | `("charge_reversed", 5.00, ["NS-1.3", "NS-1.7"])` |
| **Missing evidence** | `driver_wait_start` absent → derive from first `waiting` GPS timestamp. `cancellation_time` absent → add `"cancellation_time"` to `missing_evidence`. |
| **Conflicting evidence** | `wait_timer_expired` app event timestamp differs from computed expiry by > 1 min → add `"wait_timer_mismatch"` to `missing_evidence` |
| **Boundary tests** | Wait exactly 5.0 min → pass. Wait 4.99 min → fail. Wait 8.0 min → pass. Wait 0 min → fail. |

#### NS-1.4 — No-Show Threshold

| | |
|---|---|
| **Classification** | DATASET (`no_show_threshold_min = 8`) |
| **Input fields** | `total_wait_min` (from NS-1.3), `cancellation_policy.no_show_threshold_min` |
| **Condition** | Total wait must be >= no-show threshold. |
| **Formula** | `no_show_threshold_reached = total_wait_min >= NO_SHOW_THRESHOLD_MIN` (`>= 8`) |
| **Gate** | `no_show_threshold_reached` |
| **Output fields** | `no_show_threshold_reached: bool` |
| **Pass →** | Proceed to NS-1.5 |
| **Fail →** | `("charge_reversed", 5.00, ["NS-1.4", "NS-1.7"])` |
| **Boundary tests** | Wait exactly 8.0 min → pass. Wait 7.99 min → fail. Wait 8.01 min → pass. |

#### NS-1.5 — Contact Attempts

| | |
|---|---|
| **Classification** | PROPOSED (threshold = 2; dataset shows 5 but states no minimum) |
| **Input fields** | `chat_logs` (driver messages + calls), `app_events` (`driver_called_rider`) |
| **Condition** | Driver contact attempts must be >= minimum. |
| **Formula** | `contact_attempts = count(chat_logs where sender=="driver" and type in ("message","call")) + count(app_events where event_type=="driver_called_rider")` |
| **Gate** | `contact_made = contact_attempts >= MINIMUM_CONTACT_ATTEMPTS` (`>= 2`) |
| **Additional output** | `rider_replies = count(chat_logs where sender=="rider")` |
| **Output fields** | `contact_attempts: int`, `rider_replies: int` |
| **Pass →** | Proceed to NS-1.6 |
| **Fail →** | `("charge_reversed", 5.00, ["NS-1.5", "NS-1.7"])` |
| **Missing evidence** | `chat_logs` key absent → add `"chat_logs"` to `missing_evidence`. Empty list is OK (not missing). |
| **Boundary tests** | 0 attempts → fail. 1 attempt → fail. 2 attempts → pass. 5 attempts → pass. |

#### NS-1.6 — Cancellation Fee Eligibility (Charge Upheld)

| | |
|---|---|
| **Classification** | DATASET (`cancellation_fee = 5.00`) |
| **Input fields** | All gates from NS-1.1–NS-1.5, `cancellation_policy.cancellation_fee_after_wait` |
| **Condition** | All gates pass: `arrived and free_wait_expired and no_show_threshold_reached and contact_made` |
| **Formula** | `amount_sgd = CANCELLATION_FEE_SGD` |
| **Output** | `("charge_upheld", 5.00, ["NS-1.6"])` |

#### NS-1.7 — Charge Reversed (Refund Conditions)

| | |
|---|---|
| **Classification** | PROPOSED (full-refund policy; official sources don't describe partial refunds) |
| **Condition** | Any of NS-1.1, NS-1.3, NS-1.4, NS-1.5 fails. |
| **Formula** | `amount_sgd = CANCELLATION_FEE_SGD` (refunded, always full fee) |
| **Output** | `("charge_reversed", 5.00, [<failed_clause_id>, "NS-1.7"])` |

#### NS-1.8 — Missing Evidence Handling

| | |
|---|---|
| **Classification** | PROPOSED |
| **Critical fields** | `["gps_telemetry", "driver_arrival_time", "cancellation_time", "chat_logs"]` |
| **Condition** | Any critical field absent or empty where it must exist. |
| **Output** | `("escalate", 0.00, ["NS-1.8", "E-1.5"])` with `escalated=True`, `escalation_reason="missing evidence: [...]"` |
| **Output field** | `missing_evidence: list[str]` — list of missing field names |

### `no_show_check()` output (full)

```json
{
  "dispute_id": "DISP-002",
  "tool": "no_show_check",
  "facts": {
    "driver_distance_from_pickup_m": 0.0,
    "arrived": true,
    "arrived_minutes_vs_scheduled": -2.0,
    "total_wait_min": 8.0,
    "free_wait_expired": true,
    "no_show_threshold_reached": true,
    "contact_attempts": 5,
    "rider_replies": 0,
    "missing_evidence": []
  },
  "flags": []
}
```

---

## 3. `route_deviation()` — Evidence Tool Spec

**Dispute type:** `route_deviation`
**Input:** `DisputeCase` with `gps_telemetry` (in-trip points), `trip_data.pickup_location`, `trip_data.dropoff_location`, `trip_data.fare_breakdown`

> **Critical:** Ryde uses fixed fares (SRC-04, OFFICIAL). A route deviation does NOT automatically create a monetary refund. Refunds only for metered/distance fares.

### Required input JSON fields

| Field path | Used by | Purpose |
|---|---|---|
| `trip_data.pickup_location.{lat,lng}` | RD-2.1 | Baseline start |
| `trip_data.dropoff_location.{lat,lng}` | RD-2.1 | Baseline end |
| `gps_telemetry[]` (en-route + in-trip) | RD-2.1 | Actual distance |
| `chat_logs[]` (rider messages) | RD-2.3 | Detour request detection |
| `gps_telemetry[].speed_kmh` | RD-2.4 | Traffic inference |
| `trip_data.fare_breakdown` | RD-2.5 | Fare type, per-km rate |

### Clause-by-clause specification

#### RD-2.1 — Actual vs. Reasonable Baseline Route

| | |
|---|---|
| **Classification** | PROPOSED |
| **Input fields** | `trip_data.pickup_location`, `trip_data.dropoff_location`, `gps_telemetry` |
| **Formula** | `straight_line_km = haversine_km(pickup, dropoff)` |
| | `baseline_distance_km = straight_line_km * ROAD_NETWORK_FACTOR` (`* 1.3`) |
| | `actual_distance_km = sum(haversine_km(gps[i], gps[i+1]) for consecutive in-trip points)` |
| | `deviation_pct = ((actual_distance_km - baseline_distance_km) / baseline_distance_km) * 100` |
| **Output fields** | `baseline_distance_km: float`, `actual_distance_km: float`, `deviation_pct: float` |
| **Missing evidence** | `gps_telemetry` absent or fewer than 2 in-trip points → add `"gps_telemetry"` to missing evidence, cannot compute. |

#### RD-2.2 — Deviation Review Threshold (20%)

| | |
|---|---|
| **Classification** | PROPOSED |
| **Condition** | `review_triggered = deviation_pct >= DEVIATION_REVIEW_THRESHOLD_PCT` (`>= 20.0`) |
| **Output fields** | `review_triggered: bool` |
| **Not triggered →** | `("no_action", 0.00, ["RD-2.2"], False)` |
| **Triggered →** | Proceed to RD-2.3 |
| **Boundary tests** | Deviation exactly 20.0% → triggered. 19.99% → not triggered. 20.01% → triggered. 0% → not triggered. |

#### RD-2.3 — Rider-Requested Detours

| | |
|---|---|
| **Classification** | PROPOSED |
| **Input fields** | `chat_logs` (rider messages) |
| **Condition** | Code surfaces rider messages containing route content. LLM determines intent. |
| **Formula** | `rider_route_messages = [c for c in chat_logs if c.sender == "rider" and contains_route_content(c.content)]` |
| | `rider_requested_detour = len(rider_route_messages) > 0` |
| **Output fields** | `rider_route_messages: list`, `rider_requested_detour: bool` |
| **Detour found →** | `("no_action", 0.00, ["RD-2.3"], False)` |
| **No detour →** | Proceed to RD-2.4 |
| **Note** | `contains_route_content()` is a keyword filter (e.g. "route", "detour", "go via", "take", "highway"). It surfaces **candidate** messages only — it does NOT determine intent. The LLM makes the final intent determination. The keyword filter cannot distinguish a request from a complaint: "please take the expressway" (request → `rider_requested_detour=true`) and "why are you taking this route??" (complaint → `rider_requested_detour=false`) both match the filter. TC-05 tests this: rider says "Are we going the right way?" — keyword match fires, but Judge must rule `rider_requested_detour=false` (question, not a request). |

#### RD-2.4 — Traffic and Road Conditions

| | |
|---|---|
| **Classification** | PROPOSED |
| **Input fields** | `gps_telemetry[].speed_kmh`, `gps_telemetry[].timestamp`, driver chat messages |
| **Condition** | Code computes duration + avg speed. LLM judges whether slow segments + driver messages indicate traffic. |
| **Formula** | `trip_duration_min = (last_gps.timestamp - first_gps.timestamp).total_seconds() / 60.0` |
| | `avg_speed_kmh = actual_distance_km / (trip_duration_min / 60.0)` |
| **Output fields** | `trip_duration_min: float`, `avg_speed_kmh: float`, `traffic_justified: bool` |
| **Note** | `traffic_justified` is set by the LLM, not by code. Code surfaces the candidates (slow segments, driver messages about traffic). The Judge LLM determines whether the pattern indicates traffic. The boolean is then used by `compute_route_deviation_outcome()`. |

#### RD-2.5 — Fare Validation

| | |
|---|---|
| **Classification** | OFFICIAL (fixed fare per SRC-04) + PROPOSED (refund logic) |
| **Input fields** | `trip_data.fare_breakdown` (TBD schema) |
| **Condition** | Determine fare type: `"fixed"`, `"metered"`, or `"distance_time"` |
| **Output fields** | `fare_type: str`, `per_km_rate_sgd: float\|null` |
| **Fixed fare + unjustified deviation ≥20%** | `("no_action", 0.00, ["RD-2.5"], True)` — conduct flag |
| **Metered/distance + unjustified deviation ≥20%** | Proceed to RD-2.6 |
| **Missing fare data** | Add `"fare_breakdown"` to missing evidence → escalate |

#### RD-2.6 — Refund Calculation (Metered/Distance Fares Only)

| | |
|---|---|
| **Classification** | PROPOSED |
| **Condition** | `fare_type in ("metered", "distance_time") and deviation_pct >= 20 and not rider_requested_detour and not traffic_justified` |
| **Formula** | `excess_distance_km = actual_distance_km - baseline_distance_km` |
| | `excess_fare_sgd = excess_distance_km * per_km_rate_sgd` |
| | `refund_sgd = min(excess_fare_sgd, actual_fare_sgd)` |
| **Output** | `("refund", refund_sgd, ["RD-2.6"], False)` |
| **Missing `per_km_rate_sgd`** | Escalate (missing evidence) |

#### RD-2.7 — Missing Evidence Handling

| | |
|---|---|
| **Classification** | PROPOSED (mirrors NS-1.8) |
| **Critical fields** | `["gps_telemetry", "fare_breakdown", "per_km_rate_sgd"]` (conditional) |
| **Condition** | `gps_telemetry` absent or fewer than 2 in-trip points (cannot compute actual distance); OR `fare_breakdown` absent (cannot determine fare type); OR `per_km_rate_sgd` absent when fare type is metered/distance_time and RD-2.6 would fire (deviation ≥ 20%, no rider request, no traffic justification) |
| **Output** | `("escalate", 0.00, ["RD-2.7", "E-1.5"], False)` with `escalated=True`, `escalation_reason="missing evidence for route deviation: [...]"` |
| **Output field** | `missing_evidence: list[str]` — list of missing field names |
| **Gate position** | Gate 0 — checked before RD-2.2 (deviation threshold). Same pattern as NS-1.8 in no-show chain. |

### `route_deviation()` output (full)

```json
{
  "dispute_id": "...",
  "tool": "route_deviation",
  "facts": {
    "baseline_distance_km": 5.2,
    "actual_distance_km": 7.8,
    "deviation_pct": 50.0,
    "review_triggered": true,
    "rider_route_messages": [],
    "rider_requested_detour": false,
    "trip_duration_min": 18.5,
    "avg_speed_kmh": 25.3,
    "traffic_justified": false,
    "fare_type": "fixed",
    "per_km_rate_sgd": null,
    "missing_evidence": []
  },
  "flags": []
}
```

---

## 4. `fare_validate()` — Evidence Tool Spec

This tool may be called separately or its output merged with `route_deviation()`.

### Output fields

| Field | Type | Source |
|---|---|---|
| `fare_type` | `"fixed"` \| `"metered"` \| `"distance_time"` | `trip_data.fare_breakdown` |
| `actual_fare_sgd` | `float` | `trip_data.fare_breakdown` or `trip_data.cancellation_fee` |
| `per_km_rate_sgd` | `float \| null` | `trip_data.fare_breakdown` (null for fixed fares) |
| `surge_applied` | `bool` | `trip_data.fare_breakdown` |

### Output JSON

```json
{
  "fare_type": "fixed",
  "actual_fare_sgd": 12.50,
  "per_km_rate_sgd": null,
  "surge_applied": false
}
```

---

## 5. `history_lookup()` — Evidence Tool Spec

Surfaces rider and driver profiles for the Judge's context. Per E-1.4, profiles **never override** trip evidence in the outcome.

### Output fields

```json
{
  "rider": {
    "avg_rating": 3.9,
    "total_trips": 34,
    "dispute_history": { "total_disputes": 4, "upheld": 1, "rejected": 3 },
    "fraud_flags": 1
  },
  "driver": {
    "avg_rating": 4.9,
    "total_trips": 3201,
    "dispute_history": { "total_disputes": 1, "upheld_against": 0, "rejected": 1 },
    "fraud_flags": 0
  }
}
```

---

## 6. `check_safety()` — Safety Escalation Spec

### S-1.1 — Safety Incident Categories

| | |
|---|---|
| **Classification** | OFFICIAL (SRC-06 zero-tolerance) + PROPOSED (detection triggers) |
| **Input fields** | `chat_logs[].content`, `dispute_ticket.description`, `gps_telemetry[].speed_kmh` |
| **Keyword check** | `keyword_hits = [kw for kw in SAFETY_KEYWORDS if kw in text.lower()]` where `text` = all chat content + dispute description |
| **Speeding check** | `speeding = any(p.speed_kmh > SPEEDING_THRESHOLD_KMH for p in gps_telemetry)` (`> 90`) |
| **Incident detected** | `keyword_hits or speeding` |
| **Output** | `(True, category_string)` or `(False, None)` |

**Safety categories (SRC-06 OFFICIAL):**
1. Threats — explicit or implied violence in chat
2. Harassment — sexual, racial, verbal
3. Assault — physical
4. Dangerous driving — GPS speeding, erratic movement
5. Discrimination — race, ethnicity, national origin, disability

### S-1.2 — Mandatory Human Review

| | |
|---|---|
| **Classification** | OFFICIAL (SRC-06) + PROPOSED (routing) |
| **Trigger** | Safety incident (S-1.1) OR confidence < 0.70 (E-1.6) |
| **Output** | `outcome = "escalate"`, `amount_sgd = 0.00`, `escalated = True`, `escalation_reason = "safety incident: <category>"` or `"low confidence"` |
| **Rule** | Safety incidents are **never** auto-resolved. Always escalate. |

---

## 7. Refund Formula Functions

These are deterministic Python functions. The Judge LLM never computes amounts.

### `compute_no_show_outcome(facts, constants)`

**Returns:** `(outcome: str, amount_sgd: float, clauses_cited: list[str])`

```python
def compute_no_show_outcome(facts, constants):
    # Gate 0: Missing evidence → escalate
    if facts["missing_evidence"]:
        return ("escalate", 0.00, ["NS-1.8", "E-1.5"])

    # Gate 1: Driver arrived?
    if not facts["arrived"]:
        return ("charge_reversed", constants.CANCELLATION_FEE_SGD, ["NS-1.1", "NS-1.7"])

    # Gate 2: Free wait expired?
    if not facts["free_wait_expired"]:
        return ("charge_reversed", constants.CANCELLATION_FEE_SGD, ["NS-1.3", "NS-1.7"])

    # Gate 3: No-show threshold reached?
    if not facts["no_show_threshold_reached"]:
        return ("charge_reversed", constants.CANCELLATION_FEE_SGD, ["NS-1.4", "NS-1.7"])

    # Gate 4: Contact attempts?
    if facts["contact_attempts"] < constants.MINIMUM_CONTACT_ATTEMPTS:
        return ("charge_reversed", constants.CANCELLATION_FEE_SGD, ["NS-1.5", "NS-1.7"])

    # All gates passed
    return ("charge_upheld", constants.CANCELLATION_FEE_SGD, ["NS-1.6"])
```

### `compute_route_deviation_outcome(facts, constants)`

**Returns:** `(outcome: str, amount_sgd: float, clauses_cited: list[str], conduct_flag: bool)`

```python
def compute_route_deviation_outcome(facts, constants):
    # Gate 0: Missing evidence → escalate
    if facts["missing_evidence"]:
        return ("escalate", 0.00, ["RD-2.7", "E-1.5"], False)

    # Gate 1: Deviation below review threshold?
    if not facts["review_triggered"]:
        return ("no_action", 0.00, ["RD-2.2"], False)

    # Gate 2: Rider requested detour?
    if facts["rider_requested_detour"]:
        return ("no_action", 0.00, ["RD-2.3"], False)

    # Gate 3: Fare type determines path
    if facts["fare_type"] == "fixed":
        if not facts["traffic_justified"]:
            # Unjustified deviation on fixed fare → no refund, conduct flag
            return ("no_action", 0.00, ["RD-2.5"], True)
        # Traffic-excused deviation on fixed fare
        return ("no_action", 0.00, ["RD-2.4", "RD-2.5"], False)

    # Gate 4: Metered/distance fare with unjustified deviation
    if not facts["traffic_justified"]:
        excess_km = facts["actual_distance_km"] - facts["baseline_distance_km"]
        excess_fare = excess_km * facts["per_km_rate_sgd"]
        refund = min(excess_fare, facts["actual_fare_sgd"])
        return ("refund", refund, ["RD-2.6"], False)

    # Traffic-excused deviation on metered fare
    return ("no_action", 0.00, ["RD-2.4"], False)
```

### `check_safety(chat_logs, gps_telemetry, description, constants)`

**Returns:** `(is_safety_incident: bool, category: str|None)`

```python
def check_safety(chat_logs, gps_telemetry, description, constants):
    text = " ".join([c["content"] for c in chat_logs]) + " " + description
    keyword_hits = [kw for kw in constants.SAFETY_KEYWORDS if kw in text.lower()]
    speeding = any(p["speed_kmh"] > constants.SPEEDING_THRESHOLD_KMH for p in gps_telemetry)

    if keyword_hits or speeding:
        categories = []
        if keyword_hits:
            categories.append("keyword: " + ", ".join(keyword_hits))
        if speeding:
            categories.append("speeding")
        return (True, "; ".join(categories))
    return (False, None)
```

---

## 8. DISP-002 Expected Computed Facts

Running DISP-002 through `no_show_check()` and `compute_no_show_outcome()`:

### Input values (from `data/DISP-002.json`)

| Input | Value |
|---|---|
| Pickup coordinates | lat 1.2847, lng 103.8382 |
| First `arrived` GPS | 08:43:00, lat 1.2847, lng 103.8382, speed 0 |
| Scheduled time | 08:45:00 |
| Driver arrival time | 08:43:00 |
| Driver wait start | 08:43:00 |
| Cancellation time | 08:51:00 |
| `free_wait_time_min` | 5 |
| `no_show_threshold_min` | 8 |
| `cancellation_fee_after_wait` | 5.00 |
| Driver chat messages | 4 |
| Driver calls (app events) | 1 |
| Rider chat messages | 0 |

### Computed facts

| Fact | Computation | Value |
|---|---|---|
| `driver_distance_from_pickup_m` | haversine(1.2847, 103.8382, 1.2847, 103.8382) | **0.0** |
| `arrived` | 0.0 <= 10 | **true** |
| `arrived_minutes_vs_scheduled` | (08:43 - 08:45) / 60 = -120s / 60 | **-2.0** |
| `total_wait_min` | (08:51 - 08:43) / 60 = 480s / 60 | **8.0** |
| `free_wait_expired` | 8.0 >= 5 | **true** |
| `no_show_threshold_reached` | 8.0 >= 8 | **true** |
| `contact_attempts` | 4 messages + 1 call | **5** |
| `rider_replies` | 0 rider messages | **0** |
| `missing_evidence` | all critical fields present | **[]** |

### Gate-by-gate trace through `compute_no_show_outcome()`

| Step | Code path | Facts | Result |
|---|---|---|---|
| 1 | `if facts["missing_evidence"]:` | `[]` (empty) | Not triggered |
| 2 | `if not facts["arrived"]:` | `arrived = True` | Not triggered |
| 3 | `if not facts["free_wait_expired"]:` | `free_wait_expired = True` | Not triggered |
| 4 | `if not facts["no_show_threshold_reached"]:` | `no_show_threshold_reached = True` | Not triggered |
| 5 | `if facts["contact_attempts"] < 2:` | `5 < 2` = `False` | Not triggered |
| 6 | `return ("charge_upheld", 5.00, ["NS-1.6"])` | All gates passed | **Result** |

### Expected ruling

```
outcome:          "charge_upheld"
amount_sgd:       5.00
clauses_cited:    ["NS-1.6"]
confidence:       ~0.90+  (all evidence present, consistent)
escalated:        false
conduct_flag:     false
```

> The verdict is derived entirely from evidence-derived facts. The dataset's
> "Expected ruling" field is never read by the code. The "Evidence Summary" in
> `docs/sample-dataset-DISP-002.md` is never passed to the agents.

---

## 9. Boundary Test Cases

One per clause edge, designed to catch off-by-one and threshold errors:

| # | Clause | Scenario | Input | Expected |
|---|---|---|---|---|
| B1 | NS-1.1 | GPS exactly at 10m radius | `driver_distance_from_pickup_m = 10.0` | `arrived = True` (pass) |
| B2 | NS-1.1 | GPS just outside radius | `driver_distance_from_pickup_m = 10.01` | `arrived = False` (fail → reversed) |
| B3 | NS-1.3 | Wait exactly 5.0 min | `total_wait_min = 5.0` | `free_wait_expired = True` (pass) |
| B4 | NS-1.3 | Wait just under threshold | `total_wait_min = 4.99` | `free_wait_expired = False` (fail → reversed) |
| B5 | NS-1.4 | Wait exactly 8.0 min | `total_wait_min = 8.0` | `no_show_threshold_reached = True` (pass) |
| B6 | NS-1.4 | Wait just under threshold | `total_wait_min = 7.99` | `no_show_threshold_reached = False` (fail → reversed) |
| B7 | NS-1.5 | Exactly 2 contact attempts | `contact_attempts = 2` | Pass (`2 >= 2`) |
| B8 | NS-1.5 | Only 1 contact attempt | `contact_attempts = 1` | Fail → reversed (`1 < 2`) |
| B9 | NS-1.8 | GPS telemetry absent | `gps_telemetry` key missing | `missing_evidence = ["gps_telemetry"]` → escalate |
| B10 | NS-1.8 | Chat logs absent | `chat_logs` key missing | `missing_evidence = ["chat_logs"]` → escalate |
| B11 | RD-2.2 | Deviation exactly 20.0% | `deviation_pct = 20.0` | `review_triggered = True` |
| B12 | RD-2.2 | Deviation just under | `deviation_pct = 19.99` | `review_triggered = False` → no_action |
| B13 | RD-2.5 | Fixed fare, unjustified deviation | `fare_type = "fixed"`, `traffic_justified = False` | `no_action`, `conduct_flag = True` |
| B14 | RD-2.6 | Metered fare, unjustified, refund capped | `excess_fare = 15.0`, `actual_fare = 10.0` | `refund = 10.0` (capped) |
| B15 | S-1.1 | Speeding exactly at threshold | `speed_kmh = 90` | Not triggered (`> 90`, not `>= 90`) |
| B16 | S-1.1 | Speeding just over threshold | `speed_kmh = 91` | Safety incident → escalate |
| B17 | RD-2.7 | GPS telemetry has only 1 in-trip point | `len(in_trip_points) = 1` | `missing_evidence = ["gps_telemetry"]` → escalate |
| B18 | RD-2.7 | Fare breakdown absent for route_deviation | `fare_breakdown` key absent | `missing_evidence = ["fare_breakdown"]` → escalate |
| B19 | RD-2.7 | Per-km rate absent when RD-2.6 would fire | `per_km_rate_sgd = None`, metered fare, deviation ≥ 20% | `missing_evidence = ["per_km_rate_sgd"]` → escalate |

---

## 10. Missing/Conflicting Evidence Matrix

What happens when each input field is absent or contradictory:

| Missing field | Clause affected | Behavior | Outcome |
|---|---|---|---|
| `gps_telemetry` (entire key absent) | NS-1.1, RD-2.1, RD-2.7, S-1.1 | Cannot verify arrival, compute route, or check speeding | Add to `missing_evidence` → escalate (NS-1.8 for no-show, RD-2.7 for route deviation) |
| `gps_telemetry` has no `arrived` status point | NS-1.1 | Cannot find driver arrival GPS | `arrived = False`, add `"gps_arrived_point"` to `missing_evidence` |
| `gps_telemetry` has fewer than 2 in-trip points | RD-2.1, RD-2.7 | Cannot compute actual distance for route deviation | Add `"gps_telemetry"` to `missing_evidence` → escalate (RD-2.7) |
| `driver_arrival_time` absent | NS-1.2 | Derive from first `arrived` GPS timestamp | If GPS also absent → add to `missing_evidence` → escalate |
| `cancellation_time` absent | NS-1.3, NS-1.4 | Cannot compute wait duration | Add to `missing_evidence` → escalate |
| `chat_logs` (entire key absent) | NS-1.5, RD-2.3, S-1.1 | Cannot count contact, detect detour, scan for safety keywords | Add to `missing_evidence` → escalate |
| `chat_logs` is empty list `[]` | NS-1.5 | `contact_attempts = 0`, `rider_replies = 0` | `0 < 2` → charge_reversed (NOT missing evidence — empty is valid) |
| `cancellation_policy` block absent | NS-1.3, NS-1.4, NS-1.6 | Fall back to constants module defaults | OK — constants module has HACKATHON_2026 values |
| `app_events` absent | NS-1.1, NS-1.5 | Cross-verification unavailable | GPS + chat_logs are primary; app_events absence is a flag, not escalation |
| `trip_data.fare_breakdown` absent | RD-2.5, RD-2.6, RD-2.7 | Cannot determine fare type | For route_deviation disputes: add `"fare_breakdown"` to `missing_evidence` → escalate (RD-2.7) |
| GPS and app_events contradict on arrival | NS-1.1 | GPS says 0m, app_events has no `driver_arrived` | `arrived = True` (GPS is sufficient), add `"app_event_driver_arrived"` to `missing_evidence` as flag |
| `wait_timer_expired` app event time ≠ computed expiry | NS-1.3 | Timestamps differ by > 1 min | Add `"wait_timer_mismatch"` to `missing_evidence` as flag |

### Evidence reliability tiers (E-1.1, PROPOSED)

When evidence conflicts, higher tier takes precedence:

| Tier | Source | Reliability |
|---|---|---|
| 1 | `app_events` (system-generated) | Highest |
| 2 | `gps_telemetry` (device-generated) | High |
| 3 | `chat_logs` (user-generated) | Medium |
| 4 | `dispute_ticket.description` (party's account) | Low |
| 5 | `rider_profile` / `driver_profile` | Contextual only (E-1.4: never overrides trip evidence) |

---

## 11. Evidence/Fairness Clauses (E-1.x) — Implementation Notes

These are not tools but constraints on the Judge prompt and system design:

| Clause | Constraint | Implementation |
|---|---|---|
| E-1.1 | Higher-tier evidence overrides lower-tier when conflicting | Judge prompt instruction + evidence tier labels in tool output |
| E-1.2 | Both advocates get same tools, schema, length cap | `MAX_ARGUMENTS = 5`, `MAX_POINT_CHARS = 400` in `models.py` |
| E-1.3 | Every argument cites evidence_ref + clause ID; ruling cites clauses | Pydantic `min_length=1` on `Argument.evidence_refs` and `Argument.clauses` |
| E-1.4 | Profiles never override trip evidence in outcome | Outcome computed by code, not LLM. Judge prompt: "Do not let ratings/history override trip evidence." |
| E-1.5 | No adverse inference from missing data | Missing evidence → escalate, never auto-rule against the party |
| E-1.6 | Confidence thresholds: ≥0.85 auto, 0.70–0.84 spot-check, <0.70 escalate | Judge LLM sets confidence; code checks threshold and routes |

---

*End of handoff. All rules traceable to `docs/ryde_dispute_policy.md`. All sources traceable to `docs/policy_sources.md`. No official Ryde policy invented — `PROPOSED` rules are design assumptions for the hackathon.*
