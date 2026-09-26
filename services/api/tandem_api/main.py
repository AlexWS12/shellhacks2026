from fastapi import FastAPI

app = FastAPI(title="Tandem API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
