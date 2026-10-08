# Schemas

Four JSON shapes shared by backend and frontend. Pydantic models in `backend/schemas/` must match this file.

## 1. Dispute input

Based on `data/DISP-002.json`. Top-level keys:

- `dispute_ticket`: `dispute_id`, `trip_id`, `filed_by` (`rider` | `driver`), `dispute_type` (`no_show_charge` | `route_deviation`), `description`, `filed_at`, `status`
- `rider_profile`, `driver_profile`: ids, `account_age_days`, `total_trips`, `avg_rating`, `dispute_history`, `fraud_flags`
- `trip_data`: pickup/dropoff, times, fees
- `gps_telemetry`: list of `{timestamp, lat, lng, speed_kmh, status}`
- `chat_logs`: list of `{timestamp, sender, type, content}`
- `app_events`: list of `{timestamp, event_type, details}`
- `cancellation_policy` (no-show cases)

Route deviation cases will also need planned route + fare breakdown (TBD with Person C).

**Never pass the dataset's "expected ruling" or evidence summary to the agents.**

## 2. Evidence output

```json
{
  "dispute_id": "DISP-002",
  "tool": "no_show_check",
  "facts": {
    "driver_distance_from_pickup_m": 0,
    "arrived_minutes_vs_scheduled": -2,
    "total_wait_min": 8,
    "contact_attempts": 5,
    "rider_replies": 0
  },
  "flags": []
}
```

## 3. Advocate brief

```json
{
  "dispute_id": "DISP-002",
  "side": "rider | driver",
  "position": "one-sentence ask",
  "arguments": [
    { "point": "...", "evidence_refs": ["no_show_check.total_wait_min"], "clauses": ["NS-2.1"] }
  ],
  "weaknesses_acknowledged": ["..."]
}
```

Same schema and length cap for both sides.

## 4. Ruling

```json
{
  "dispute_id": "DISP-002",
  "outcome": "refund | compensation | no_action | charge_upheld | charge_reversed | escalate",
  "amount_sgd": 0.0,
  "confidence": 0.92,
  "clauses_cited": ["NS-2.1"],
  "explanation_rider": "plain language",
  "explanation_driver": "plain language",
  "escalated": false,
  "escalation_reason": null
}
```

`amount_sgd` is computed in code from the policy formula, never by the Judge.

## Agent log message (UI stream)

```json
{ "seq": 1, "agent": "rider_advocate | driver_advocate | judge | system", "type": "evidence | argument | rebuttal | ruling", "content": "...", "timestamp": "..." }
```
