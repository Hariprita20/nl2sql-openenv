from dataclasses import dataclass, field
from typing import Optional
import uuid

try:
    from openenv.core.env_server.interfaces import Environment as BaseEnvironment
    from openenv.core.env_server.types import State as BaseState
    HAS_OPENENV = True
except ImportError:
    HAS_OPENENV = False

    class BaseEnvironment:
        pass

    @dataclass
    class BaseState:
        episode_id: str = ""
        step_count: int = 0


@dataclass
class SQLAction:
    sql_query: str

    def to_dict(self):
        return {"sql_query": self.sql_query}


@dataclass
class SQLObservation:
    schema: str               # Database DDL shown to the agent
    question: str             # Natural language question
    result: str               # Query execution result or error message
    reward: float             # 0.0 to 1.0
    done: bool
    feedback: str             # Human-readable explanation of reward
    task_id: str              # Which task is active
    task_difficulty: str      # easy / medium / hard
    attempt: int              # Which attempt (1, 2, or 3)
    max_attempts: int         # Always 3
    hint: str = ""

    @property
    def goal(self):
        """Alias so inference scripts can use observation.goal"""
        return self.question

    @property
    def last_action_error(self):
        return self.result.startswith("ERROR:") if self.result else False

    @property
    def url(self):
        """Stub for compatibility with generic inference scripts"""
        return f"task://{self.task_id}/attempt/{self.attempt}"


@dataclass
class SQLState:
    episode_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_count: int = 0
    current_task_id: str = ""
    current_task_idx: int = 0
    total_tasks: int = 3
    cumulative_reward: float = 0.0
