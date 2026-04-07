import os
import re
import json
import textwrap
from typing import List, Optional

from openai import OpenAI
from client import SQLAgentEnv, SQLAction

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY", "hf-xxx")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-Coder-7B-Instruct")
ENV_URL = os.getenv("ENV_URL", "http://localhost:7860")
MAX_STEPS = 20
TEMPERATURE = 0.1
MAX_TOKENS = 300
FALLBACK_SQL = "SELECT 1;"

SYSTEM_PROMPT = """You are an expert SQL query writer for SQLite databases.
Respond with EXACTLY one valid SQL SELECT query.
No explanation, no markdown, no backticks.
Never write DROP, DELETE, INSERT, UPDATE, CREATE, ALTER, or TRUNCATE."""


def extract_sql(text):
    if not text:
        return FALLBACK_SQL
    text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    if re.match(r"^\s*(SELECT|WITH)\b", text, re.IGNORECASE):
        return text
    match = re.search(r"(SELECT|WITH)\b.*", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(0).strip()
    return FALLBACK_SQL


def build_prompt(observation, history):
    hint = getattr(observation, "hint", "")
    hint_line = f"Hint: {hint}" if hint else ""
    prev = "\n".join(history[-3:]) if history else "None"
    return f"""Schema:
{observation.schema}

Question: {observation.question}
{hint_line}
Task: {observation.task_id} ({observation.task_difficulty}) | Attempt {observation.attempt}/{observation.max_attempts}
Previous queries:
{prev}

Write a SQL SELECT query."""


def ask_llm(client, observation, history):
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(observation, history)},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        return extract_sql(completion.choices[0].message.content or "")
    except Exception as e:
        print(f"  [LLM error] {e}. Using fallback.", flush=True)
        return FALLBACK_SQL


def main():
    llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    env = SQLAgentEnv(base_url=ENV_URL)
    history = []
    episode_results = []

    try:
        result = env.reset()
        observation = result.observation
        print("=" * 60, flush=True)
        print("EPISODE STARTED", flush=True)
        print(f"  Model  : {MODEL_NAME}", flush=True)
        print(f"  Env URL: {ENV_URL}", flush=True)
        print("=" * 60, flush=True)
        print(f"First task : {observation.task_id} ({observation.task_difficulty})", flush=True)
        print(f"Question   : {observation.question}", flush=True)

        for step in range(1, MAX_STEPS + 1):
            if result.done:
                print("Environment complete.", flush=True)
                break

            sql = ask_llm(llm, observation, history)

            print(f"[START] task={observation.task_id}", flush=True)
            print(f"Step {step:2d} | {observation.task_id:20s} | attempt {observation.attempt}/{observation.max_attempts}", flush=True)
            print(f"  SQL: {sql[:120]}", flush=True)

            result = env.step(SQLAction(sql_query=sql))
            observation = result.observation

            print(f"[STEP] step={step} reward={result.reward}", flush=True)
            print(f"  Reward  : {result.reward:.2f} | Done: {result.done}", flush=True)
            print(f"  Feedback: {observation.feedback[:120]}", flush=True)

            history.append(f"Step {step}: {sql[:80]} reward={result.reward:.2f}")
            episode_results.append({
                "step": step,
                "task_id": observation.task_id,
                "reward": result.reward,
                "sql": sql,
                "feedback": observation.feedback,
            })

            if result.done:
                print("All tasks complete!", flush=True)
                break
        else:
            print(f"Reached max steps ({MAX_STEPS}).", flush=True)

    finally:
        env.close()

    print("\n" + "=" * 60, flush=True)
    print("EPISODE SUMMARY", flush=True)
    print("=" * 60, flush=True)
    for r in episode_results:
        print(f"  Step {r['step']:2d} | {r['task_id']:20s} | reward: {r['reward']:.2f}", flush=True)
    total = sum(r["reward"] for r in episode_results)
    print(f"  Total cumulative reward : {total:.2f} / 3.0", flush=True)

    for r in episode_results:
        print(f"[END] task={r['task_id']} score={r['reward']} steps=1", flush=True)

    print(json.dumps(episode_results, indent=2), flush=True)


if __name__ == "__main__":
    main()
