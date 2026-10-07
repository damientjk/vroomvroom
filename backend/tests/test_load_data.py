import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


def test_disp_002_loads():
    case = json.loads((DATA / "DISP-002.json").read_text())
    assert case["dispute_ticket"]["dispute_id"] == "DISP-002"
    assert case["dispute_ticket"]["dispute_type"] == "no_show_charge"
