"""
client.py — SQLAgentEnv client class.

Mirrors the BrowserGymEnv pattern from the official OpenEnv sample inference script:
  env = SQLAgentEnv.from_docker_image(image="sql-agent-env:latest", env_vars={...})
  result = env.reset()                        # StepResult
  result = env.step(SQLAction(sql_query=...)) # StepResult
  env.close()
"""

import subprocess
import time
from dataclasses import dataclass, fields
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SQLObservation:
    schema: str
    question: str
    result: str
    reward: float
    done: bool
    feedback: str
    task_id: str
    task_difficulty: str
    attempt: int
    max_attempts: int
    hint: str = ""

    @property
    def goal(self) -> str:
        """Alias so generic inference scripts can use observation.goal"""
        return self.question

    @property
    def last_action_error(self) -> bool:
        return bool(self.result and self.result.startswith("ERROR:"))

    @property
    def url(self) -> str:
        """Stub for compatibility with generic inference scripts"""
        return f"task://{self.task_id}/attempt/{self.attempt}"


@dataclass
class StepResult:
    observation: SQLObservation
    reward: float
    done: bool


@dataclass
class SQLAction:
    sql_query: str


# ---------------------------------------------------------------------------
# Environment client
# ---------------------------------------------------------------------------

class SQLAgentEnv:
    """
    Client for the SQL Agent Environment FastAPI server.

    Usage (local server already running):
        env = SQLAgentEnv(base_url="http://localhost:7860")

    Usage (spin up Docker image):
        env = SQLAgentEnv.from_docker_image("sql-agent-env:latest")

    Both return the same object; use reset() / step() / close() uniformly.
    """

    def __init__(self, base_url: str = "http://localhost:7860"):
        self.base_url = base_url.rstrip("/")
        self._container_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_docker_image(
        cls,
        image: str = "sql-agent-env:latest",
        port: int = 7860,
        env_vars: Optional[dict] = None,
    ) -> "SQLAgentEnv":
        """
        Launch the environment inside Docker, wait for it to be healthy,
        and return a connected client.
        """
        env_args: list = []
        for k, v in (env_vars or {}).items():
            env_args += ["-e", f"{k}={v}"]

        cmd = ["docker", "run", "-d", "--rm", "-p", f"{port}:{port}"] + env_args + [image]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        container_id = proc.stdout.strip()

        client = cls(base_url=f"http://localhost:{port}")
        client._container_id = container_id

        # Poll until /health returns 200 (up to 60 s)
        for _ in range(60):
            try:
                r = requests.get(f"{client.base_url}/health", timeout=2)
                if r.status_code == 200:
                    return client
            except requests.exceptions.ConnectionError:
                pass
            time.sleep(1)

        raise TimeoutError(
            f"Environment did not become healthy within 60 s (container: {container_id})"
        )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def reset(self) -> StepResult:
        r = requests.post(f"{self.base_url}/reset", json={}, timeout=10)
        r.raise_for_status()
        return self._parse_step_result(r.json())

    def step(self, action: SQLAction) -> StepResult:
        r = requests.post(
            f"{self.base_url}/step",
            json={"sql_query": action.sql_query},
            timeout=10,
        )
        r.raise_for_status()
        return self._parse_step_result(r.json())

    def state(self) -> dict:
        r = requests.get(f"{self.base_url}/state", timeout=10)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        if self._container_id:
            subprocess.run(
                ["docker", "stop", self._container_id],
                capture_output=True,
            )
            self._container_id = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_step_result(data: dict) -> StepResult:
        obs_field_names = {f.name for f in fields(SQLObservation)}
        obs = SQLObservation(**{k: data[k] for k in obs_field_names if k in data})
        return StepResult(
            observation=obs,
            reward=float(data.get("reward", 0.0)),
            done=bool(data.get("done", False)),
        )
