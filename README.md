# SQL Agent Environment

> A production-quality OpenEnv environment where an AI agent writes SQL queries to answer natural language questions against a realistic business database — with partial-credit scoring and multi-attempt episodes.

---

## Why Real-World?

SQL is the universal language of business data. Every company — from startups to Fortune 500 enterprises — stores critical data in relational databases and needs analysts or automated agents to query it. This environment simulates exactly that workflow:

1. The agent receives a natural language question and the full database schema.
2. It writes a SQL SELECT query.
3. The environment executes the query against a live SQLite database and grades the result.
4. The agent may retry up to 3 times per task, learning from execution errors and partial feedback.

Unlike toy environments (grid worlds, games), SQL query generation is:
- **Universally applicable** — every data-driven company faces this daily.
- **Verifiable** — query results are deterministic; scoring is objective.
- **Compositional** — tasks range from simple filters to window functions.
- **Efficient** — runs entirely in-process with SQLite; no external services needed.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Container                     │
│                                                          │
│  ┌──────────────┐    ┌─────────────────────────────┐    │
│  │  FastAPI     │    │  SQLAgentEnvironment         │    │
│  │  server/     │◄──►│  (environment.py)            │    │
│  │  app.py      │    │                              │    │
│  │              │    │  ┌──────────┐  ┌──────────┐  │    │
│  │  POST /reset │    │  │ tasks.py │  │database  │  │    │
│  │  POST /step  │    │  │ graders  │  │.py       │  │    │
│  │  GET  /state │    │  └──────────┘  │ SQLite   │  │    │
│  └──────────────┘    │                │ :memory: │  │    │
│         ▲            │                └──────────┘  │    │
│         │            └─────────────────────────────┘    │
│    port 7860                                             │
└─────────────────────────────────────────────────────────┘
         ▲
         │  HTTP  (requests)
         │
┌─────────────────────────────────────────────────────────┐
│                    client.py                             │
│  SQLAgentEnv                                             │
│    .from_docker_image(image, port, env_vars)             │
│    .reset()  → StepResult                               │
│    .step(SQLAction)  → StepResult                       │
│    .state()  → dict                                     │
└─────────────────────────────────────────────────────────┘
         ▲
         │
┌─────────────────────────────────────────────────────────┐
│                   inference.py                           │
│  OpenAI-compatible LLM call → SQL extraction → step()   │
└─────────────────────────────────────────────────────────┘
```

---

## Database Schema

Four tables loaded with realistic seed data at startup (SQLite in-memory):

| Table         | Rows | Key Columns                                           |
|---------------|------|-------------------------------------------------------|
| `customers`   | 10   | customer_id, name, city, country, tier                |
| `products`    | 15   | product_id, name, category, price, stock_quantity     |
| `orders`      | 30   | order_id, customer_id, order_date, status, total_amount |
| `order_items` | 60   | item_id, order_id, product_id, quantity, unit_price   |

---

## Action Space

| Field       | Type   | Description                        |
|-------------|--------|------------------------------------|
| `sql_query` | string | A SQLite-compatible SELECT query   |

Only SELECT queries are accepted. DROP, DELETE, INSERT, UPDATE, CREATE, ALTER, and TRUNCATE are rejected with an error message and 0.0 reward.

---

## Observation Space

| Field             | Type    | Description                                  |
|-------------------|---------|----------------------------------------------|
| `schema`          | string  | Full database DDL (CREATE TABLE statements)  |
| `question`        | string  | Natural language question to answer          |
| `result`          | string  | Query result (first 5 rows) or error message |
| `reward`          | float   | Score for the last action (0.0 – 1.0)        |
| `done`            | bool    | True when all 3 tasks are complete           |
| `feedback`        | string  | Human-readable explanation of the reward     |
| `task_id`         | string  | Identifier of the current task               |
| `task_difficulty` | string  | `easy` / `medium` / `hard`                   |
| `attempt`         | int     | Current attempt number (1 – 3)               |
| `max_attempts`    | int     | Maximum attempts per task (always 3)         |
| `hint`            | string  | Optional hint for the current task           |

---

## Tasks

### Task 1 — `simple_select` (Easy)

> "List the full name and city of every customer from the United States. Order the results alphabetically by name."

**Expected result:** 6 rows (Alice Johnson, Bob Smith, Carol White, Grace Lee, Ivy Chen, Jack Taylor)
**Grading:** Name coverage × 0.5 + city coverage × 0.4 + ordering bonus × 0.1

### Task 2 — `join_aggregation` (Medium)

> "What is the total revenue generated by each product category? Show the category name and total revenue, ordered from highest to lowest revenue."

**Expected result:** 3 rows — Electronics (highest), Clothing, Books (lowest)
**Grading:** Full credit for all 3 categories correctly ordered; partial credit for partial results

### Task 3 — `window_ranking` (Hard)

> "For each customer who has placed at least one order, show their name, their most recent order date, and their rank by total spending (rank 1 = highest total spending). Order by rank."

**Expected result:** 10 rows with name, most recent order date, and rank
**Grading:** Partial credit for each correct column (name, rank, date) + bonus for correct ordering

---

## Reward Function

Rewards are deterministic and partially-credited:

| Score Range | Meaning                                              |
|-------------|------------------------------------------------------|
| 1.00        | Perfect answer — all expected rows and columns       |
| 0.70–0.99   | Mostly correct — minor issues (ordering, extra cols) |
| 0.30–0.69   | Partial — correct approach but incomplete result     |
| 0.10–0.29   | Minimal — something is present but largely wrong     |
| 0.00        | No rows, query error, or completely wrong            |

**Advancement rule:** The agent advances to the next task if `reward >= 0.7` OR if it has used all 3 attempts. This encourages quality over brute-force retrying.

**Maximum cumulative reward:** 3.0 (1.0 per task × 3 tasks)

---

## Quick Start (Local)

```bash
# 1. Install dependencies
cd sql_agent_env
pip install -r server/requirements.txt

# 2. Start the server
uvicorn server.app:app --host 0.0.0.0 --port 7860

# 3. Test it
curl http://localhost:7860/health
# {"status":"ok","environment":"sql-agent-env","version":"1.0.0"}

curl -s -X POST http://localhost:7860/reset | python -m json.tool

curl -s -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{"sql_query": "SELECT name, city FROM customers WHERE country = '\''United States'\'' ORDER BY name"}' \
  | python -m json.tool
```

---

## Docker

```bash
# Build the image
docker build -t sql-agent-env:latest .

# Run the container
docker run -p 7860:7860 sql-agent-env:latest

# Or with env vars
docker run -p 7860:7860 \
  -e HF_TOKEN=your_token \
  sql-agent-env:latest
```

---

## Run inference.py

```bash
# Required environment variables
export API_BASE_URL=https://router.huggingface.co/v1
export MODEL_NAME=Qwen/Qwen2.5-Coder-7B-Instruct
export HF_TOKEN=your_hf_token
export ENV_URL=http://localhost:7860

# Run the agent
python inference.py
```

The script will:
1. Connect to the running environment server at `ENV_URL`
2. Call `reset()` to start an episode
3. For each step, call the LLM API to generate a SQL query
4. Call `step(SQLAction(sql_query=...))` and print the reward + feedback
5. Print a full episode summary with cumulative reward

---

## Run Tests

```bash
python test_local.py
```

This script starts the server, exercises all endpoints, validates rewards, and prints `ALL TESTS PASSED` if everything works.

---

## Pre-Submission Checklist

- [x] `inference.py` at project root (exact name, not `run.py` or similar)
- [x] `openenv.yaml` at project root with all required fields
- [x] `Dockerfile` with `EXPOSE 7860` and `HEALTHCHECK`
- [x] Server starts on port `7860`
- [x] `GET /health` returns `{"status": "ok"}`
- [x] `POST /reset` returns full observation dict
- [x] `POST /step` with `{"sql_query": "..."}` returns observation with `reward` and `done`
- [x] `client.py` with `SQLAgentEnv.from_docker_image()` classmethod
- [x] Typed observation dataclass with `.goal` alias property
- [x] Partial-credit reward function (not binary)
- [x] 3 tasks of increasing difficulty
- [x] Multi-step episodes (up to 3 attempts per task)
- [x] `<100 MB RAM` (SQLite in-memory, no external databases)
- [x] Deterministic graders (same query always gets same score)
