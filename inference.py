"""
inference.py — SQL Agent Environment
=====================================
Required env vars:
  API_BASE_URL   — OpenAI-compatible base URL  (default: HuggingFace router)
  MODEL_NAME     — Model identifier            (default: Qwen/Qwen2.5-Coder-7B-Instruct)
  HF_TOKEN       — HuggingFace API token
Optional:
  ENV_URL        — URL of the running environment server (default: http://localhost:7860)
  API_KEY        — Alternative to HF_TOKEN
"""

import json
import os
import re
import textwrap
from typing import List

from openai import OpenAI

from client import SQLAgentEnv, SQLAction

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY      = os.getenv("HF_TOKEN") or os.getenv("API_KEY", "hf-xxx")
MODEL_NAME   = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-Coder-7B-Instruct")
ENV_URL      = os.getenv("ENV_URL", "http://localhost:7860")

MAX_STEPS    = 20       # safety cap for the whole episode
TEMPERATURE  = 0.1
MAX_TOKENS   = 400
FALLBACK_SQL = "SELECT 1;"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert SQL query writer.

    IMPORTANT — DATABASE ENGINE: SQLite (not PostgreSQL, not MySQL).
    Write only SQLite-compatible SQL.

    SQLite notes:
    - String literals use single quotes: WHERE country = 'United States'
    - RANK() OVER (...) window functions are supported in SQLite 3.25+
      (Python 3.10+ ships with SQLite 3.39+, so RANK() works here).
    - If RANK() is unavailable or fails, use a correlated subquery instead:
        SELECT
            c.name,
            MAX(o.order_date) AS most_recent_order,
            (SELECT COUNT(*) + 1
             FROM (SELECT customer_id, SUM(total_amount) AS tot
                   FROM orders GROUP BY customer_id) x2
             WHERE x2.tot > x1.tot) AS rank
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN (SELECT customer_id, SUM(total_amount) AS tot
              FROM orders GROUP BY customer_id) x1
          ON c.customer_id = x1.customer_id
        ORDER BY rank;
    - DATE functions: use strftime() — e.g. strftime('%Y', order_date)
    - No ILIKE; use LOWER(col) LIKE LOWER(pattern) for case-insensitive matching.

    Rules:
    - Respond with EXACTLY one valid SQL SELECT query — no explanation, no markdown,
      no backticks, no comments.
    - Never write DROP, DELETE, INSERT, UPDATE, CREATE, ALTER, or TRUNCATE.
    - If unsure, write your best guess as a SELECT query.
""").strip()


def build_user_prompt(observation, history: List[str]) -> str:
    hint_line = f"\nHint: {observation.hint}" if getattr(observation, "hint", "") else ""
    prev_queries = "\n".join(history[-3:]) if history else "None yet."
    return textwrap.dedent(f"""
        Schema:
        {observation.schema}

        Question: {observation.question}
        {hint_line}

        Task: {observation.task_id} ({observation.task_difficulty})
        Attempt: {observation.attempt}/{observation.max_attempts}

        Previous queries and outcomes:
        {prev_queries}

        Write a single SQLite SELECT query that answers the question above.
    """).strip()


def extract_sql(text: str) -> str:
    """Strip markdown fences and extract the first SQL statement."""
    if not text:
        return FALLBACK_SQL
    # Remove ```sql ... ``` or ``` ... ```
    text = re.sub(r"```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```", "", text)
    text = text.strip()

    # If it starts with SELECT or WITH, use as-is
    if re.match(r"^\s*(SELECT|WITH)\b", text, re.IGNORECASE):
        return text

    # Find the first SELECT/WITH anywhere in the text
    match = re.search(r"((?:WITH|SELECT)\b.*)", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()

    return FALLBACK_SQL


def ask_llm(client: OpenAI, observation, history: List[str]) -> str:
    prompt = build_user_prompt(observation, history)
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        raw = completion.choices[0].message.content or ""
        return extract_sql(raw)
    except Exception as exc:
        print(f"  [LLM error] {exc}. Using fallback SQL.")
        return FALLBACK_SQL


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    env = SQLAgentEnv(base_url=ENV_URL)

    history: List[str] = []
    episode_results = []

    try:
        result = env.reset()
        observation = result.observation

        print("=" * 60)
        print("EPISODE STARTED")
        print(f"  Model  : {MODEL_NAME}")
        print(f"  Env URL: {ENV_URL}")
        print("=" * 60)
        print(f"First task : {observation.task_id} ({observation.task_difficulty})")
        print(f"Question   : {observation.question}\n")

        for step_num in range(1, MAX_STEPS + 1):
            if result.done:
                print("Environment signalled done before step.")
                break

            sql = ask_llm(llm, observation, history)

            print(
                f"Step {step_num:2d} | {observation.task_id:20s} | "
                f"attempt {observation.attempt}/{observation.max_attempts}"
            )
            print(f"  SQL     : {sql[:120]}{'...' if len(sql) > 120 else ''}")

            result = env.step(SQLAction(sql_query=sql))
            observation = result.observation

            print(f"  Reward  : {result.reward:.2f} | Done: {result.done}")
            print(f"  Feedback: {observation.feedback[:120]}")
            print()

            history.append(f"Step {step_num}: {sql[:80]} → reward {result.reward:.2f}")
            episode_results.append({
                "step":     step_num,
                "task_id":  observation.task_id,
                "reward":   result.reward,
                "sql":      sql,
                "feedback": observation.feedback,
            })

            if result.done:
                print("All tasks complete!")
                break
        else:
            print(f"Reached max steps ({MAX_STEPS}).")

    finally:
        env.close()

    # Summary
    print("\n" + "=" * 60)
    print("EPISODE SUMMARY")
    print("=" * 60)
    for r in episode_results:
        print(f"  Step {r['step']:2d} | {r['task_id']:20s} | reward: {r['reward']:.2f}")
    total = sum(r["reward"] for r in episode_results)
    max_possible = 3.0  # one perfect score per task
    print(f"\n  Total cumulative reward : {total:.2f} / {max_possible:.1f}")
    print(f"  Steps used              : {len(episode_results)}")
    print()
    print(json.dumps(episode_results, indent=2))


if __name__ == "__main__":
    main()
