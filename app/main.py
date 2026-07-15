from fastapi import FastAPI

app = FastAPI(
    title="Enterprise Agentic Research Platform",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return the current health status of the API service."""
    return {"status": "healthy"}