"""
test_local.py — Integration tests for the SQL Agent Environment.

Starts the FastAPI server as a subprocess, exercises every endpoint,
validates rewards, and prints ALL TESTS PASSED on success.
"""

import json
import subprocess
import sys
import time
import os

# Force UTF-8 output on Windows so Unicode characters in feedback don't crash prints
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests

BASE_URL = "http://localhost:7860"
SERVER_PROC = None


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def start_server():
    global SERVER_PROC
    env = os.environ.copy()
    SERVER_PROC = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.app:app",
         "--host", "0.0.0.0", "--port", "7860"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    # Wait up to 30 s for the server to be ready
    for _ in range(30):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                print(f"[OK] Server ready (pid={SERVER_PROC.pid})")
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    stop_server()
    raise RuntimeError("Server did not start within 30 s.")


def stop_server():
    if SERVER_PROC is not None:
        SERVER_PROC.terminate()
        try:
            SERVER_PROC.wait(timeout=5)
        except subprocess.TimeoutExpired:
            SERVER_PROC.kill()
        print("[OK] Server stopped.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check(condition: bool, label: str):
    if condition:
        print(f"  [PASS] {label}")
    else:
        print(f"  [FAIL] {label}")
        stop_server()
        sys.exit(1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health():
    print("\n--- /health ---")
    r = requests.get(f"{BASE_URL}/health", timeout=5)
    check(r.status_code == 200, "HTTP 200")
    data = r.json()
    check(data.get("status") == "ok", f"status==ok  (got {data})")


def test_tasks():
    print("\n--- GET /tasks ---")
    r = requests.get(f"{BASE_URL}/tasks", timeout=5)
    check(r.status_code == 200, "HTTP 200")
    data = r.json()
    tasks = data.get("tasks", [])
    check(len(tasks) == 3, f"3 tasks defined (got {len(tasks)})")
    ids = [t["id"] for t in tasks]
    check("simple_select" in ids, "simple_select task present")
    check("join_aggregation" in ids, "join_aggregation task present")
    check("window_ranking" in ids, "window_ranking task present")


def test_reset():
    print("\n--- POST /reset ---")
    r = requests.post(f"{BASE_URL}/reset", json={}, timeout=5)
    check(r.status_code == 200, "HTTP 200")
    data = r.json()
    print(f"  question  : {data.get('question','')[:80]}")
    check("schema" in data,    "response has 'schema'")
    check("question" in data,  "response has 'question'")
    check("task_id" in data,   "response has 'task_id'")
    check(data.get("done") is False, "done==False on reset")
    check(data.get("reward") == 0.0, "reward==0.0 on reset")
    return data


def test_step_correct(obs_data: dict):
    print("\n--- POST /step  (correct query — task 1) ---")
    sql = (
        "SELECT name, city FROM customers "
        "WHERE country = 'United States' "
        "ORDER BY name"
    )
    r = requests.post(f"{BASE_URL}/step", json={"sql_query": sql}, timeout=5)
    check(r.status_code == 200, "HTTP 200")
    data = r.json()
    reward = data.get("reward", -1)
    print(f"  reward    : {reward}")
    print(f"  feedback  : {data.get('feedback','')[:100]}")
    print(f"  result    : {str(data.get('result',''))[:120]}")
    check(reward >= 0.7, f"reward >= 0.7 for correct US customers query (got {reward})")
    return data


def test_step_bad_query():
    print("\n--- POST /step  (non-existent table — should give 0.0) ---")
    # Reset first so we are on task 1
    requests.post(f"{BASE_URL}/reset", json={}, timeout=5)
    r = requests.post(
        f"{BASE_URL}/step",
        json={"sql_query": "SELECT * FROM nonexistent_table"},
        timeout=5,
    )
    check(r.status_code == 200, "HTTP 200")
    data = r.json()
    reward = data.get("reward", -1)
    print(f"  reward    : {reward}")
    print(f"  feedback  : {data.get('feedback','')[:100]}")
    check(reward == 0.0, f"reward==0.0 for bad table name (got {reward})")


def test_step_forbidden():
    print("\n--- POST /step  (DROP TABLE — should give 0.0) ---")
    requests.post(f"{BASE_URL}/reset", json={}, timeout=5)
    r = requests.post(
        f"{BASE_URL}/step",
        json={"sql_query": "DROP TABLE customers"},
        timeout=5,
    )
    check(r.status_code == 200, "HTTP 200")
    data = r.json()
    reward = data.get("reward", -1)
    print(f"  reward    : {reward}")
    check(reward == 0.0, f"reward==0.0 for DROP statement (got {reward})")


def test_state():
    print("\n--- GET /state ---")
    r = requests.get(f"{BASE_URL}/state", timeout=5)
    check(r.status_code == 200, "HTTP 200")
    data = r.json()
    print(f"  state     : {json.dumps(data)}")
    check("episode_id" in data,        "state has episode_id")
    check("step_count" in data,        "state has step_count")
    check("cumulative_reward" in data, "state has cumulative_reward")
    check("done" in data,              "state has done")


def test_full_episode():
    print("\n--- Full episode walkthrough (3 tasks) ---")
    requests.post(f"{BASE_URL}/reset", json={}, timeout=5)

    queries = [
        # Task 1 — easy
        "SELECT name, city FROM customers WHERE country = 'United States' ORDER BY name",
        # Task 2 — medium
        (
            "SELECT p.category, SUM(oi.quantity * oi.unit_price) AS total_revenue "
            "FROM order_items oi "
            "JOIN products p ON oi.product_id = p.product_id "
            "GROUP BY p.category "
            "ORDER BY total_revenue DESC"
        ),
        # Task 3 — hard (window function with SQLite RANK())
        (
            "SELECT c.name, MAX(o.order_date) AS most_recent_order, "
            "RANK() OVER (ORDER BY SUM(o.total_amount) DESC) AS rank "
            "FROM customers c "
            "JOIN orders o ON c.customer_id = o.customer_id "
            "GROUP BY c.customer_id, c.name "
            "ORDER BY rank"
        ),
    ]

    total_reward = 0.0
    for i, sql in enumerate(queries, 1):
        r = requests.post(f"{BASE_URL}/step", json={"sql_query": sql}, timeout=5)
        check(r.status_code == 200, f"task {i}: HTTP 200")
        data = r.json()
        reward = data.get("reward", 0.0)
        total_reward += reward
        print(f"  Task {i} reward: {reward:.2f} | feedback: {data.get('feedback','')[:80]}")

    check(total_reward > 0, f"episode produced non-zero reward (got {total_reward:.2f})")
    print(f"  Total episode reward: {total_reward:.2f}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Starting SQL Agent Environment tests...")
    start_server()
    try:
        test_health()
        test_tasks()
        obs = test_reset()
        test_step_correct(obs)
        test_step_bad_query()
        test_step_forbidden()
        test_state()
        test_full_episode()
    finally:
        stop_server()

    print("\n" + "=" * 40)
    print("ALL TESTS PASSED")
    print("=" * 40)
