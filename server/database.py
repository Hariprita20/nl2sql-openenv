import sqlite3
from typing import Tuple, List, Optional

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
_DB_SCHEMA = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT,
    city        TEXT,
    country     TEXT,
    signup_date TEXT,
    tier        TEXT CHECK(tier IN ('bronze','silver','gold','platinum'))
);

CREATE TABLE products (
    product_id     INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,
    price          REAL NOT NULL,
    stock_quantity INTEGER DEFAULT 0
);

CREATE TABLE orders (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER REFERENCES customers(customer_id),
    order_date   TEXT NOT NULL,
    status       TEXT CHECK(status IN ('pending','shipped','delivered','cancelled')),
    total_amount REAL NOT NULL
);

CREATE TABLE order_items (
    item_id    INTEGER PRIMARY KEY,
    order_id   INTEGER REFERENCES orders(order_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity   INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Seed data — customers
# ---------------------------------------------------------------------------
_CUSTOMERS = [
    (1,  'Alice Johnson',   'alice@example.com',  'New York',       'United States', '2022-01-15', 'gold'),
    (2,  'Bob Smith',       'bob@example.com',    'Los Angeles',    'United States', '2022-03-22', 'silver'),
    (3,  'Carol White',     'carol@example.com',  'Chicago',        'United States', '2021-11-05', 'platinum'),
    (4,  'David Brown',     'david@example.com',  'London',         'United Kingdom','2023-02-10', 'bronze'),
    (5,  'Emma Davis',      'emma@example.com',   'Toronto',        'Canada',        '2022-07-18', 'silver'),
    (6,  'Frank Wilson',    'frank@example.com',  'Sydney',         'Australia',     '2023-01-30', 'bronze'),
    (7,  'Grace Lee',       'grace@example.com',  'Houston',        'United States', '2021-08-12', 'gold'),
    (8,  'Henry Martinez',  'henry@example.com',  'Berlin',         'Germany',       '2022-09-25', 'silver'),
    (9,  'Ivy Chen',        'ivy@example.com',    'San Francisco',  'United States', '2023-04-05', 'platinum'),
    (10, 'Jack Taylor',     'jack@example.com',   'Miami',          'United States', '2021-06-20', 'gold'),
]

# ---------------------------------------------------------------------------
# Seed data — products
# Electronics: 1-5, 14  |  Clothing: 6-9, 15  |  Books: 10-13
# ---------------------------------------------------------------------------
_PRODUCTS = [
    (1,  'Laptop Pro 15',              'Electronics', 1299.99,  45),
    (2,  'Wireless Mouse',             'Electronics',   29.99, 200),
    (3,  'USB-C Hub',                  'Electronics',   49.99, 150),
    (4,  '4K Monitor',                 'Electronics',  549.99,  30),
    (5,  'Mechanical Keyboard',        'Electronics',  149.99,  75),
    (6,  'Running Shoes',              'Clothing',      89.99, 120),
    (7,  'Winter Jacket',              'Clothing',     179.99,  60),
    (8,  'Cotton T-Shirt',             'Clothing',      24.99, 300),
    (9,  'Yoga Pants',                 'Clothing',      59.99,  90),
    (10, 'Python Cookbook',            'Books',         49.99,  80),
    (11, 'Data Science Handbook',      'Books',         59.99,  65),
    (12, 'Clean Code',                 'Books',         39.99,  95),
    (13, 'Design Patterns',            'Books',         44.99,  70),
    (14, 'Noise-Cancelling Headphones','Electronics',  299.99,  55),
    (15, 'Casual Sneakers',            'Clothing',      74.99, 110),
]

# ---------------------------------------------------------------------------
# Seed data — 30 orders
# Totals derived from order_items below so joins give consistent results.
# ---------------------------------------------------------------------------
_ORDERS = [
    # order_id, customer_id, order_date,   status,       total_amount
    (1,  1, '2023-01-15', 'delivered',  1329.98),
    (2,  2, '2023-02-20', 'delivered',   269.98),
    (3,  3, '2023-03-10', 'delivered',   849.98),
    (4,  4, '2023-04-05', 'shipped',     134.98),
    (5,  5, '2023-05-12', 'delivered',   249.97),
    (6,  1, '2023-06-18', 'delivered',   599.98),
    (7,  6, '2023-07-22', 'pending',     149.98),
    (8,  7, '2023-08-30', 'delivered',   449.98),
    (9,  8, '2023-09-15', 'delivered',   139.97),
    (10, 9, '2023-10-05', 'delivered',  1329.98),
    (11,10, '2023-11-20', 'shipped',     699.98),
    (12, 2, '2023-12-01', 'delivered',   179.98),
    (13, 3, '2024-01-10', 'delivered',   104.98),
    (14, 5, '2024-02-14', 'delivered',   109.97),
    (15, 7, '2024-03-20', 'cancelled',    84.98),
    (16, 1, '2024-04-05', 'delivered',   399.97),
    (17, 4, '2024-05-15', 'delivered',    84.98),
    (18, 9, '2024-06-20', 'delivered',  1399.97),
    (19,10, '2024-07-04', 'shipped',     204.98),
    (20, 3, '2024-08-15', 'delivered',    89.98),
    (21, 6, '2024-09-01', 'delivered',   124.97),
    (22, 8, '2024-10-10', 'delivered',    79.98),
    (23, 2, '2024-11-05', 'delivered',   849.98),
    (24, 7, '2024-12-01', 'delivered',   269.98),
    (25, 5, '2025-01-10', 'delivered',  1399.97),
    (26, 1, '2025-02-14', 'delivered',   449.98),
    (27, 9, '2025-03-01', 'delivered',   134.98),
    (28,10, '2025-04-20', 'shipped',     329.98),
    (29, 4, '2025-05-15', 'delivered',    94.98),
    (30, 3, '2025-06-10', 'delivered',  1479.98),
]

# ---------------------------------------------------------------------------
# Seed data — 60 order_items (2 per order)
#
# Revenue by category (quantity * unit_price):
#   Electronics  ≈ $11,900   (highest)
#   Clothing     ≈ $1,665    (middle)
#   Books        ≈  $515     (lowest)
# ---------------------------------------------------------------------------
_ORDER_ITEMS = [
    # item_id, order_id, product_id, quantity, unit_price

    # Order 1 — Alice: Laptop + Wireless Mouse  (Electronics)
    (1,  1,  1, 1, 1299.99),
    (2,  1,  2, 1,   29.99),

    # Order 2 — Bob: Winter Jacket + Running Shoes  (Clothing)
    (3,  2,  7, 1,  179.99),
    (4,  2,  6, 1,   89.99),

    # Order 3 — Carol: 4K Monitor + Noise-Cancelling Headphones  (Electronics)
    (5,  3,  4, 1,  549.99),
    (6,  3, 14, 1,  299.99),

    # Order 4 — David: Casual Sneakers + Yoga Pants  (Clothing)
    (7,  4, 15, 1,   74.99),
    (8,  4,  9, 1,   59.99),

    # Order 5 — Emma: Mechanical Keyboard + USB-C Hub ×2  (Electronics)
    (9,  5,  5, 1,  149.99),
    (10, 5,  3, 2,   49.99),

    # Order 6 — Alice: 4K Monitor + USB-C Hub  (Electronics)
    (11, 6,  4, 1,  549.99),
    (12, 6,  3, 1,   49.99),

    # Order 7 — Frank: Running Shoes + Yoga Pants  (Clothing)
    (13, 7,  6, 1,   89.99),
    (14, 7,  9, 1,   59.99),

    # Order 8 — Grace: Mechanical Keyboard + Noise-Cancelling Headphones  (Electronics)
    (15, 8,  5, 1,  149.99),
    (16, 8, 14, 1,  299.99),

    # Order 9 — Henry: Python Cookbook ×2 + Clean Code  (Books)
    (17, 9, 10, 2,   49.99),
    (18, 9, 12, 1,   39.99),

    # Order 10 — Ivy: Laptop + Wireless Mouse  (Electronics)
    (19,10,  1, 1, 1299.99),
    (20,10,  2, 1,   29.99),

    # Order 11 — Jack: 4K Monitor + Mechanical Keyboard  (Electronics)
    (21,11,  4, 1,  549.99),
    (22,11,  5, 1,  149.99),

    # Order 12 — Bob: Mechanical Keyboard + Wireless Mouse  (Electronics)
    (23,12,  5, 1,  149.99),
    (24,12,  2, 1,   29.99),

    # Order 13 — Carol: Data Science Handbook + Design Patterns  (Books)
    (25,13, 11, 1,   59.99),
    (26,13, 13, 1,   44.99),

    # Order 14 — Emma: Cotton T-Shirt ×2 + Yoga Pants  (Clothing)
    (27,14,  8, 2,   24.99),
    (28,14,  9, 1,   59.99),

    # Order 15 — Grace: Yoga Pants + Cotton T-Shirt  (Clothing, cancelled)
    (29,15,  9, 1,   59.99),
    (30,15,  8, 1,   24.99),

    # Order 16 — Alice: Noise-Cancelling Headphones + USB-C Hub ×2  (Electronics)
    (31,16, 14, 1,  299.99),
    (32,16,  3, 2,   49.99),

    # Order 17 — David: Design Patterns + Clean Code  (Books)
    (33,17, 13, 1,   44.99),
    (34,17, 12, 1,   39.99),

    # Order 18 — Ivy: Laptop + USB-C Hub ×2  (Electronics)
    (35,18,  1, 1, 1299.99),
    (36,18,  3, 2,   49.99),

    # Order 19 — Jack: Winter Jacket + Cotton T-Shirt  (Clothing)
    (37,19,  7, 1,  179.99),
    (38,19,  8, 1,   24.99),

    # Order 20 — Carol: Clean Code + Python Cookbook  (Books)
    (39,20, 12, 1,   39.99),
    (40,20, 10, 1,   49.99),

    # Order 21 — Frank: Casual Sneakers + Cotton T-Shirt ×2  (Clothing)
    (41,21, 15, 1,   74.99),
    (42,21,  8, 2,   24.99),

    # Order 22 — Henry: USB-C Hub + Wireless Mouse  (Electronics)
    (43,22,  3, 1,   49.99),
    (44,22,  2, 1,   29.99),

    # Order 23 — Bob: 4K Monitor + Noise-Cancelling Headphones  (Electronics)
    (45,23,  4, 1,  549.99),
    (46,23, 14, 1,  299.99),

    # Order 24 — Grace: Running Shoes + Winter Jacket  (Clothing)
    (47,24,  6, 1,   89.99),
    (48,24,  7, 1,  179.99),

    # Order 25 — Emma: Laptop + USB-C Hub ×2  (Electronics)
    (49,25,  1, 1, 1299.99),
    (50,25,  3, 2,   49.99),

    # Order 26 — Alice: Noise-Cancelling Headphones + Mechanical Keyboard  (Electronics)
    (51,26, 14, 1,  299.99),
    (52,26,  5, 1,  149.99),

    # Order 27 — Ivy: Casual Sneakers + Yoga Pants  (Clothing)
    (53,27, 15, 1,   74.99),
    (54,27,  9, 1,   59.99),

    # Order 28 — Jack: Noise-Cancelling Headphones + Wireless Mouse  (Electronics)
    (55,28, 14, 1,  299.99),
    (56,28,  2, 1,   29.99),

    # Order 29 — David: Python Cookbook + Design Patterns  (Books)
    (57,29, 10, 1,   49.99),
    (58,29, 13, 1,   44.99),

    # Order 30 — Carol: Laptop + Winter Jacket  (Electronics + Clothing)
    (59,30,  1, 1, 1299.99),
    (60,30,  7, 1,  179.99),
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_connection() -> sqlite3.Connection:
    """Creates a fresh in-memory SQLite database pre-loaded with all data."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Create schema
    cur.executescript(_DB_SCHEMA)

    # Insert customers
    cur.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?)", _CUSTOMERS
    )
    # Insert products
    cur.executemany(
        "INSERT INTO products VALUES (?,?,?,?,?)", _PRODUCTS
    )
    # Insert orders
    cur.executemany(
        "INSERT INTO orders VALUES (?,?,?,?,?)", _ORDERS
    )
    # Insert order_items
    cur.executemany(
        "INSERT INTO order_items VALUES (?,?,?,?,?)", _ORDER_ITEMS
    )
    conn.commit()
    return conn


def get_schema_ddl() -> str:
    """Returns the CREATE TABLE statements as a clean string for agents."""
    return _DB_SCHEMA.strip()


# DML keywords the agent must NOT use
_FORBIDDEN = {"DROP", "DELETE", "INSERT", "UPDATE", "CREATE", "ALTER", "TRUNCATE"}


def execute_query(
    conn: sqlite3.Connection,
    sql: str,
) -> Tuple[List[dict], List[str], Optional[str]]:
    """
    Safely execute a SQL SELECT query.

    Returns:
        (rows_as_dicts, column_names, error_message_or_None)

    Rules:
    - Rejects any statement containing forbidden DML/DDL keywords.
    - Catches ALL exceptions and returns the error string.
    - Limits output to 50 rows.
    - Never raises.
    """
    if not sql or not sql.strip():
        return [], [], "Empty query."

    sql_upper = sql.upper()
    for keyword in _FORBIDDEN:
        # Match keyword as a whole word to avoid false positives like 'CREATED'
        import re
        if re.search(rf"\b{keyword}\b", sql_upper):
            return [], [], f"Forbidden keyword '{keyword}' detected. Only SELECT queries are allowed."

    try:
        cur = conn.cursor()
        cur.execute(sql)
        columns: List[str] = [desc[0] for desc in (cur.description or [])]
        raw_rows = cur.fetchmany(50)
        rows: List[dict] = [dict(zip(columns, row)) for row in raw_rows]
        return rows, columns, None
    except Exception as exc:
        return [], [], str(exc)
