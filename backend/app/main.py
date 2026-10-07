from fastapi import FastAPI

app = FastAPI(title="Ryde Dispute Resolution")


@app.get("/health")
def health():
    return {"status": "ok"}
