# vroomvroom

Multi-agent autonomous dispute resolution for Ryde (Tencent Cloud AI CAN DO IT Hackathon Singapore 2026, Digital Native Track).

A dispute is filed, a Rider Advocate and a Driver Advocate gather evidence and argue each side, and a Judge issues a ruling with a confidence score and plain-language explanation. Low-confidence or safety cases go to a human reviewer.

Dispute types: **No-Show Charge**, **Route Deviation**.

## Layout

```
backend/
  app/       FastAPI app
  tools/     evidence tools (plain code: route_deviation, no_show_check, ...)
  agents/    advocate + judge prompts and orchestration
  schemas/   Pydantic models (see schemas.md)
  tests/
frontend/    UI (Streamlit or React, TBD)
data/        sample disputes (DISP-002, ...)
docs/        team brief, sample dataset, policy doc
schemas.md   agreed JSON shapes
```

## Run the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in keys, never commit .env
uvicorn app.main:app --reload
pytest
```

See [docs/team-brief.md](docs/team-brief.md) for the plan and roles.
