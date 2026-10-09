import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"

# WARNING: Only load dispute data from data/*.json (clean JSON).
# docs/sample-dataset-DISP-002.md contains an "Evidence Summary" and
# "Expected ruling" section that must NEVER be passed to the AI agents
# (per schemas.md: "Never pass the dataset's 'expected ruling' or
# evidence summary to the agents").


def test_disp_002_loads():
    case = json.loads((DATA / "DISP-002.json").read_text())
    assert case["dispute_ticket"]["dispute_id"] == "DISP-002"
    assert case["dispute_ticket"]["dispute_type"] == "no_show_charge"
