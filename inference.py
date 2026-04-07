import os
import re
import json
import textwrap
from typing import List, Optional
from openai import OpenAI
from client import SQLAgentEnv, SQLAction

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-Coder-7B-Instruct")
ENV_URL = os.getenv("ENV_URL", "http://localhost:7860")
BENCHMARK = "nl2sql"
MAX_STEPS = 20
TEMPERATURE = 0.1
MAX_TOKENS = 300
FALLBACK_SQL = "SELECT 1;"
SUCCESS_SCORE_THRESHOLD = 0.5

SYSTEM_PROMPT = """You are an expert SQL query writer for SQLite databases.
Respond with EXACTLY one valid SQL SELECT query.
No explanation, no markdown, no backticks.
Never write DROP, DELETE, INSERT, UPDATE, CREATE, ALTER, or TRUNCATE."""


def log_start(task, env, model):
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step, action, reward, done, error):
    error_val = error if error else "null"
    done_val = str(done).lower()
    action_clean = action.replace("\n", " ")[:80]
    print(f"[STEP] step={step} action={action_clean} reward={reward:.2f} done={done_val} error={error_val}", flush=True)


def log_end(success, steps, score, rewards):
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}", flush=True)


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
        print(f"[DEBUG] LLM error: {e}", flush=True)
        return FALLBACK_SQL


def main():
    llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    env = SQLAgentEnv(base_url=ENV_URL)
    history = []
    rewards = []
    steps_taken = 0
    score = 0.0
    success = False
    episode_results = []

    log_start(task="nl2sql-3task", env=BENCHMARK, model=MODEL_NAME)

    try:
        result = env.reset()
        observation = result.observation

        for step in range(1, MAX_STEPS + 1):
            if result.done:
                break

            sql = ask_llm(llm, observation, history)
            result = env.step(SQLAction(sql_query=sql))
            observation = result.observation

            reward = result.reward
            done = result.done
            error = observation.error_output if hasattr(observation, "error_output") and observation.error_output else None

            rewards.append(reward)
            steps_taken = step

            log_step(step=step, action=sql, reward=reward, done=done, error=error)

            history.append(f"Step {step}: reward={reward:.2f}")
            episode_results.append({
                "step": step,
                "task_id": observation.task_id,
                "reward": reward,
                "sql": sql,
            })

            if done:
                break

        score = sum(rewards) / 3.0 if rewards else 0.0
        score = min(max(score, 0.0), 1.0)
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as e:
        print(f"[DEBUG] Episode error: {e}", flush=True)
    finally:
        try:
            env.close()
        except Exception as e:
            print(f"[DEBUG] env.close() error: {e}", flush=True)
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    print(json.dumps(episode_results, indent=2), flush=True)


if __name__ == "__main__":
    main()
