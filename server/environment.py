import uuid
from typing import Optional

from .database import create_connection, get_schema_ddl, execute_query
from .tasks import TASKS, grade_simple_select, grade_join_aggregation, grade_window_ranking

GRADERS = {
    "simple_select":   grade_simple_select,
    "join_aggregation": grade_join_aggregation,
    "window_ranking":  grade_window_ranking,
}


class SQLAgentEnvironment:
    MAX_ATTEMPTS_PER_TASK = 3

    def __init__(self):
        self._conn = None
        self._schema_ddl = get_schema_ddl()
        self._task_idx = 0
        self._attempt = 1
        self._step_count = 0
        self._episode_id = str(uuid.uuid4())
        self._cumulative_reward = 0.0
        self._done = False

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def reset(self) -> dict:
        """Start a fresh episode. Returns the first observation dict."""
        self._conn = create_connection()
        self._task_idx = 0
        self._attempt = 1
        self._step_count = 0
        self._episode_id = str(uuid.uuid4())
        self._cumulative_reward = 0.0
        self._done = False

        task = TASKS[0]
        return {
            "schema":          self._schema_ddl,
            "question":        task["question"],
            "result":          "",
            "reward":          0.0,
            "done":            False,
            "feedback":        f"Task 1/3 ({task['difficulty']}): ready. Write your first SQL query.",
            "task_id":         task["id"],
            "task_difficulty": task["difficulty"],
            "attempt":         self._attempt,
            "max_attempts":    self.MAX_ATTEMPTS_PER_TASK,
            "hint":            task.get("hint", ""),
        }

    def step(self, sql_query: str) -> dict:
        """Execute sql_query, grade it, advance episode state, return observation."""
        if self._done:
            return self._make_terminal_obs(
                "Episode already complete. Call reset() to start a new episode."
            )

        task = TASKS[self._task_idx]
        rows, columns, error = execute_query(self._conn, sql_query)

        grader = GRADERS[task["id"]]
        reward, feedback = grader(rows, columns, error)

        self._step_count += 1
        self._cumulative_reward += reward

        # Advance to next task if score good enough OR attempts exhausted
        advance = (reward >= 0.7) or (self._attempt >= self.MAX_ATTEMPTS_PER_TASK)

        if advance:
            self._task_idx += 1
            self._attempt = 1
        else:
            self._attempt += 1

        done = self._task_idx >= len(TASKS)
        self._done = done

        # Format the execution result for display
        result_str = self._format_result(rows, columns, error)

        # Compose next-state fields
        if not done:
            next_task = TASKS[self._task_idx]
            feedback_full = (
                f"{feedback} -> Moving to task {self._task_idx + 1}/3 ({next_task['difficulty']})."
                if advance
                else f"{feedback} Attempt {self._attempt}/{self.MAX_ATTEMPTS_PER_TASK}."
            )
            return {
                "schema":          self._schema_ddl,
                "question":        next_task["question"],
                "result":          result_str,
                "reward":          reward,
                "done":            False,
                "feedback":        feedback_full,
                "task_id":         next_task["id"],
                "task_difficulty": next_task["difficulty"],
                "attempt":         self._attempt,
                "max_attempts":    self.MAX_ATTEMPTS_PER_TASK,
                "hint":            next_task.get("hint", ""),
            }
        else:
            feedback_full = (
                f"{feedback} All {len(TASKS)} tasks complete! "
                f"Cumulative reward: {self._cumulative_reward:.2f}"
            )
            return {
                "schema":          self._schema_ddl,
                "question":        task["question"],
                "result":          result_str,
                "reward":          reward,
                "done":            True,
                "feedback":        feedback_full,
                "task_id":         task["id"],
                "task_difficulty": task["difficulty"],
                "attempt":         self._attempt,
                "max_attempts":    self.MAX_ATTEMPTS_PER_TASK,
                "hint":            "",
            }

    @property
    def state(self) -> dict:
        safe_idx = min(self._task_idx, len(TASKS) - 1)
        return {
            "episode_id":       self._episode_id,
            "step_count":       self._step_count,
            "current_task_id":  TASKS[safe_idx]["id"],
            "current_task_idx": self._task_idx,
            "total_tasks":      len(TASKS),
            "cumulative_reward": self._cumulative_reward,
            "done":             self._done,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_result(rows, columns, error) -> str:
        if error:
            return f"ERROR: {error}"
        if not rows:
            return "(empty result set)"
        header = " | ".join(columns)
        separator = "-" * max(len(header), 10)
        rows_str = "\n".join(
            " | ".join(str(r.get(c, "")) for c in columns)
            for r in rows[:5]
        )
        suffix = f"\n... ({len(rows)} rows total)" if len(rows) > 5 else ""
        return f"{header}\n{separator}\n{rows_str}{suffix}"

    def _make_terminal_obs(self, message: str) -> dict:
        safe_idx = min(self._task_idx, len(TASKS) - 1)
        task = TASKS[safe_idx]
        return {
            "schema":          self._schema_ddl,
            "question":        task["question"],
            "result":          message,
            "reward":          0.0,
            "done":            True,
            "feedback":        message,
            "task_id":         task["id"],
            "task_difficulty": task["difficulty"],
            "attempt":         self._attempt,
            "max_attempts":    self.MAX_ATTEMPTS_PER_TASK,
            "hint":            "",
        }
