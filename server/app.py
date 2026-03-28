from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

from .environment import SQLAgentEnvironment
from .tasks import TASKS

app = FastAPI(
    title="SQL Agent Environment",
    version="1.0.0",
    description="OpenEnv-compatible SQL query generation environment for AI agent training.",
)

# One shared environment instance per process.
# For multi-session support, extend with session IDs or per-request instances.
_env = SQLAgentEnvironment()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class StepRequest(BaseModel):
    sql_query: str


class ResetRequest(BaseModel):
    seed: Optional[int] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "environment": "sql-agent-env", "version": "1.0.0"}


@app.post("/reset")
def reset(req: ResetRequest = None):
    obs = _env.reset()
    return JSONResponse(content=obs)


@app.post("/step")
def step(req: StepRequest):
    obs = _env.step(req.sql_query)
    return JSONResponse(content=obs)


@app.get("/state")
def state():
    return JSONResponse(content=_env.state)


@app.get("/tasks")
def list_tasks():
    return JSONResponse(content={"tasks": TASKS})


@app.get("/")
def root():
    return {
        "message": (
            "SQL Agent Environment v1.0.0. "
            "POST /reset to start an episode, "
            "POST /step with {\"sql_query\": \"...\"} to interact."
        )
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
