"""SQLite storage and authentication helpers for Udyogini.

Every business record is scoped to its owner. Values are passed through SQL
parameters, and passwords are stored as salted PBKDF2 hashes.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("UDYOGINI_DB_PATH", BASE_DIR / "udyogini.db"))
PBKDF2_ITERATIONS = 600_000
LOCKOUT_SECONDS = 300
MAX_LOGIN_ATTEMPTS = 5


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until REAL NOT NULL DEFAULT 0,
                samples_seeded INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                phone TEXT NOT NULL DEFAULT '',
                area TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                is_sample INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, phone, name)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                item TEXT NOT NULL,
                quantity REAL NOT NULL CHECK(quantity > 0),
                unit_price REAL NOT NULL CHECK(unit_price >= 0),
                amount_paid REAL NOT NULL DEFAULT 0 CHECK(amount_paid >= 0),
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK(status IN ('Pending', 'Preparing', 'Ready', 'Delivered')),
                due_date TEXT NOT NULL DEFAULT '',
                product_id INTEGER,
                unit_cost REAL NOT NULL DEFAULT 0,
                is_sample INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                price REAL NOT NULL CHECK(price >= 0),
                cost REAL NOT NULL DEFAULT 0 CHECK(cost >= 0),
                stock REAL NOT NULL DEFAULT 0 CHECK(stock >= 0),
                is_sample INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                visit_date TEXT NOT NULL,
                outcome TEXT NOT NULL,
                follow_up_date TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                is_sample INTEGER NOT NULL DEFAULT 0,
                follow_up_done INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Other',
                amount REAL NOT NULL CHECK(amount > 0),
                expense_date TEXT NOT NULL,
                is_sample INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                amount REAL NOT NULL CHECK(amount > 0),
                method TEXT NOT NULL DEFAULT 'Cash',
                paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_customers_owner ON customers(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_owner ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
            CREATE INDEX IF NOT EXISTS idx_visits_owner_date ON visits(user_id, visit_date);
            CREATE INDEX IF NOT EXISTS idx_expenses_owner_date ON expenses(user_id, expense_date);
            """
        )
        # Keep existing local databases usable as the project grows.
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "samples_seeded" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN samples_seeded INTEGER NOT NULL DEFAULT 0")
        order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
        for column, definition in {
            "product_id": "INTEGER",
            "unit_cost": "REAL NOT NULL DEFAULT 0",
            "is_sample": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if column not in order_columns:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {column} {definition}")
        customer_columns = {row["name"] for row in conn.execute("PRAGMA table_info(customers)")}
        if "is_sample" not in customer_columns:
            conn.execute("ALTER TABLE customers ADD COLUMN is_sample INTEGER NOT NULL DEFAULT 0")
        visit_columns = {row["name"] for row in conn.execute("PRAGMA table_info(visits)")}
        if "follow_up_done" not in visit_columns:
            conn.execute("ALTER TABLE visits ADD COLUMN follow_up_done INTEGER NOT NULL DEFAULT 0")
        payment_columns = {row["name"] for row in conn.execute("PRAGMA table_info(payments)")}
        if "method" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN method TEXT NOT NULL DEFAULT 'Cash'")


def _password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )


def create_user(username: str, password: str) -> tuple[bool, str]:
    username = username.strip()
    if not 3 <= len(username) <= 32 or not username.replace("_", "").isalnum():
        return False, "Choose a username of 3–32 letters, numbers, or underscores."
    if len(password) < 12:
        return False, "Use a password with at least 12 characters."
    salt = secrets.token_bytes(16)
    digest = _password_digest(password, salt)
    try:
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, password_salt) VALUES (?, ?, ?)",
                (username, digest.hex(), salt.hex()),
            )
            _seed_samples(conn, cursor.lastrowid)
            conn.execute("UPDATE users SET samples_seeded = 1 WHERE id = ?", (cursor.lastrowid,))
        return True, "Account created. You can sign in now."
    except sqlite3.IntegrityError:
        return False, "That username is already in use."


def _seed_samples(conn: sqlite3.Connection, user_id: int) -> None:
    """Add clearly marked fictional starter records to a newly created account."""
    customers = [
        ("Anita Kulkarni", "", "Shukrawar Peth", "House 12", "Sample customer"),
        ("Meena Joshi", "", "Shukrawar Peth", "Near the temple", "Likes less spicy pickle"),
        ("Farida Shaikh", "", "Raviwar Peth", "Lane 3", "Sample customer"),
        ("Sunita Patil", "", "Raviwar Peth", "House 8", "Usually visits on Fridays"),
        ("Kavita Deshmukh", "", "Sadashiv Peth", "Near the market", "Sample customer"),
        ("Lata More", "", "Sadashiv Peth", "Building B", "Prefers small packs"),
        ("Pooja Jadhav", "", "Narayan Peth", "House 21", "Sample customer"),
        ("Rekha Pawar", "", "Narayan Peth", "Corner house", "Ask about papad next visit"),
    ]
    ids = []
    for name, phone, area, address, notes in customers:
        cur = conn.execute(
            "INSERT INTO customers (user_id, name, phone, area, address, notes, is_sample) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, name, phone, area, address, notes),
        )
        ids.append(cur.lastrowid)
    products = [
        ("Besan laddoo", "Sweets", 240, 145, 12),
        ("Mango pickle", "Pickles", 180, 105, 10),
        ("Roasted papad", "Snacks", 120, 68, 16),
        ("Coconut chutney", "Chutneys", 90, 48, 8),
    ]
    product_ids = []
    for name, category, price, cost, stock in products:
        cur = conn.execute(
            "INSERT INTO products (user_id, name, category, price, cost, stock, is_sample) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, name, category, price, cost, stock),
        )
        product_ids.append(cur.lastrowid)
    today = time.strftime("%Y-%m-%d")
    order_samples = [
        (ids[0], product_ids[0], "Besan laddoo", 2, 240, 480, 200),
        (ids[1], product_ids[1], "Mango pickle", 1, 180, 105, 0),
        (ids[3], product_ids[2], "Roasted papad", 3, 120, 204, 150),
        (ids[6], product_ids[3], "Coconut chutney", 2, 90, 48, 180),
    ]
    for customer_id, product_id, item, quantity, price, cost, paid in order_samples:
        cur = conn.execute(
            "INSERT INTO orders (user_id, customer_id, item, quantity, unit_price, amount_paid, status, due_date, product_id, unit_cost, is_sample) VALUES (?, ?, ?, ?, ?, ?, 'Preparing', ?, ?, ?, 1)",
            (user_id, customer_id, item, quantity, price, paid, today, product_id, cost),
        )
        if paid:
            conn.execute(
                "INSERT INTO payments (user_id, order_id, amount) VALUES (?, ?, ?)",
                (user_id, cur.lastrowid, paid),
            )
        conn.execute(
            "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ? AND user_id = ?",
            (quantity, product_id, user_id),
        )
    visits = [
        (ids[0], "Interested", today, "Asked about next week's sweets"),
        (ids[2], "Follow up", today, "Try again in the afternoon"),
        (ids[4], "Order placed", today, "Sample visit record"),
        (ids[7], "Not home", today, "Sample visit record"),
    ]
    for customer_id, outcome, follow_up, notes in visits:
        conn.execute(
            "INSERT INTO visits (user_id, customer_id, visit_date, outcome, follow_up_date, notes, is_sample) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, customer_id, today, outcome, follow_up, notes),
        )
    for label, category, amount in [
        ("Ingredients", "Materials", 620),
        ("Paper pouches", "Packaging", 180),
        ("Local travel", "Travel", 90),
    ]:
        conn.execute(
            "INSERT INTO expenses (user_id, label, category, amount, expense_date, is_sample) VALUES (?, ?, ?, ?, ?, 1)",
            (user_id, label, category, amount, today),
        )


def ensure_samples_seeded(user_id: int) -> None:
    with connect() as conn:
        row = conn.execute("SELECT samples_seeded FROM users WHERE id = ?", (user_id,)).fetchone()
        if row and not row["samples_seeded"]:
            _seed_samples(conn, user_id)
            conn.execute("UPDATE users SET samples_seeded = 1 WHERE id = ?", (user_id,))


def authenticate(username: str, password: str) -> tuple[dict[str, Any] | None, str]:
    now = time.time()
    with connect() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        if user is None:
            # Keep the unknown-user path computationally similar to a failed login.
            _password_digest(password, b"udyogini-fixed-salt")
            return None, "Username or password is incorrect."
        if user["locked_until"] > now:
            return None, "Too many attempts. Please wait a few minutes and try again."
        salt = bytes.fromhex(user["password_salt"])
        expected = bytes.fromhex(user["password_hash"])
        actual = _password_digest(password, salt)
        if not hmac.compare_digest(actual, expected):
            failed = user["failed_attempts"] + 1
            locked_until = now + LOCKOUT_SECONDS if failed >= MAX_LOGIN_ATTEMPTS else 0
            conn.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                (0 if locked_until else failed, locked_until, user["id"]),
            )
            return None, "Username or password is incorrect."
        conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = 0 WHERE id = ?",
            (user["id"],),
        )
        if not user["samples_seeded"]:
            _seed_samples(conn, user["id"])
            conn.execute("UPDATE users SET samples_seeded = 1 WHERE id = ?", (user["id"],))
        return {"id": user["id"], "username": user["username"]}, "Signed in."


def add_customer(user_id: int, name: str, phone: str, area: str, address: str, notes: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO customers (user_id, name, phone, area, address, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name.strip(), phone.strip(), area.strip(), address.strip(), notes.strip()),
        )


def get_customers(user_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, name, phone, area, address, notes, is_sample FROM customers WHERE user_id = ? ORDER BY name COLLATE NOCASE",
            (user_id,),
        ).fetchall()


def update_customer(user_id: int, customer_id: int, name: str, phone: str,
                    area: str, address: str, notes: str) -> None:
    if not name.strip() or not area.strip():
        raise ValueError("Name and locality are required.")
    with connect() as conn:
        conn.execute(
            "UPDATE customers SET name = ?, phone = ?, area = ?, address = ?, notes = ? WHERE id = ? AND user_id = ?",
            (name.strip(), phone.strip(), area.strip(), address.strip(), notes.strip(), customer_id, user_id),
        )


def add_order(user_id: int, customer_id: int, item: str, quantity: float,
              unit_price: float, amount_paid: float, due_date: str,
              product_id: int | None = None, unit_cost: float = 0,
              payment_method: str = "Cash") -> None:
    with connect() as conn:
        owner = conn.execute(
            "SELECT id FROM customers WHERE id = ? AND user_id = ?", (customer_id, user_id)
        ).fetchone()
        if owner is None:
            raise ValueError("Customer not found.")
        if quantity <= 0 or unit_price < 0 or amount_paid < 0 or amount_paid > quantity * unit_price:
            raise ValueError("Check the quantity, price, and payment amount.")
        if product_id is not None:
            product = conn.execute(
                "SELECT stock FROM products WHERE id = ? AND user_id = ?", (product_id, user_id)
            ).fetchone()
            if product is None or product["stock"] < quantity:
                raise ValueError("Product not found or there is not enough stock.")
            conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ? AND user_id = ?",
                (quantity, product_id, user_id),
            )
        cur = conn.execute(
            "INSERT INTO orders (user_id, customer_id, item, quantity, unit_price, amount_paid, due_date, product_id, unit_cost) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, customer_id, item.strip(), quantity, unit_price, amount_paid,
             due_date, product_id, unit_cost),
        )
        if amount_paid > 0:
            conn.execute(
                "INSERT INTO payments (user_id, order_id, amount, method) VALUES (?, ?, ?, ?)",
                (user_id, cur.lastrowid, amount_paid, payment_method),
            )


def get_orders(user_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """SELECT o.id, c.name AS customer, c.area, o.item, o.quantity, o.is_sample,
                      o.unit_price, o.quantity * o.unit_price AS total,
                      o.amount_paid, o.quantity * o.unit_price - o.amount_paid AS balance,
                      o.status, o.due_date, o.created_at
               FROM orders o JOIN customers c ON c.id = o.customer_id
               WHERE o.user_id = ? AND c.user_id = ? ORDER BY o.id DESC""",
            (user_id, user_id),
        ).fetchall()


def record_payment(user_id: int, order_id: int, amount: float, method: str = "Cash") -> None:
    with connect() as conn:
        row = conn.execute(
            "SELECT quantity * unit_price AS total, amount_paid FROM orders WHERE id = ? AND user_id = ?",
            (order_id, user_id),
        ).fetchone()
        if row is None:
            raise ValueError("Order not found.")
        if amount <= 0 or row["amount_paid"] + amount > row["total"]:
            raise ValueError("Payment must be positive and cannot exceed the balance due.")
        conn.execute(
            "UPDATE orders SET amount_paid = amount_paid + ? WHERE id = ? AND user_id = ?",
            (amount, order_id, user_id),
        )
        conn.execute(
            "INSERT INTO payments (user_id, order_id, amount, method) VALUES (?, ?, ?, ?)",
            (user_id, order_id, amount, method),
        )


def update_order_status(user_id: int, order_id: int, status: str) -> None:
    if status not in {"Pending", "Preparing", "Ready", "Delivered"}:
        raise ValueError("Invalid order status.")
    with connect() as conn:
        conn.execute(
            "UPDATE orders SET status = ? WHERE id = ? AND user_id = ?",
            (status, order_id, user_id),
        )


def get_products(user_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, name, category, price, cost, stock, is_sample FROM products WHERE user_id = ? ORDER BY name COLLATE NOCASE",
            (user_id,),
        ).fetchall()


def add_product(user_id: int, name: str, category: str, price: float, cost: float, stock: float) -> None:
    if not name.strip() or price < 0 or cost < 0 or stock < 0:
        raise ValueError("Enter a product name and valid non-negative amounts.")
    with connect() as conn:
        conn.execute(
            "INSERT INTO products (user_id, name, category, price, cost, stock) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name.strip(), category.strip(), price, cost, stock),
        )


def update_product(user_id: int, product_id: int, name: str, category: str,
                   price: float, cost: float) -> None:
    if not name.strip() or price < 0 or cost < 0:
        raise ValueError("Enter a product name and valid non-negative amounts.")
    with connect() as conn:
        conn.execute(
            "UPDATE products SET name = ?, category = ?, price = ?, cost = ? WHERE id = ? AND user_id = ?",
            (name.strip(), category.strip(), price, cost, product_id, user_id),
        )


def change_stock(user_id: int, product_id: int, adjustment: float) -> None:
    with connect() as conn:
        row = conn.execute(
            "SELECT stock FROM products WHERE id = ? AND user_id = ?", (product_id, user_id)
        ).fetchone()
        if row is None or row["stock"] + adjustment < 0:
            raise ValueError("Stock adjustment would make the stock negative.")
        conn.execute(
            "UPDATE products SET stock = stock + ? WHERE id = ? AND user_id = ?",
            (adjustment, product_id, user_id),
        )


def add_visit(user_id: int, customer_id: int, visit_date: str, outcome: str,
              follow_up_date: str, notes: str) -> None:
    with connect() as conn:
        owner = conn.execute(
            "SELECT id FROM customers WHERE id = ? AND user_id = ?", (customer_id, user_id)
        ).fetchone()
        if owner is None:
            raise ValueError("Customer not found.")
        conn.execute(
            "INSERT INTO visits (user_id, customer_id, visit_date, outcome, follow_up_date, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, customer_id, visit_date, outcome, follow_up_date, notes.strip()),
        )


def get_visits(user_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT v.id, c.name AS customer, c.area, v.visit_date, v.outcome, v.follow_up_date, v.notes, v.is_sample, v.follow_up_done FROM visits v JOIN customers c ON c.id = v.customer_id WHERE v.user_id = ? AND c.user_id = ? ORDER BY v.visit_date DESC, v.id DESC",
            (user_id, user_id),
        ).fetchall()


def add_expense(user_id: int, label: str, category: str, amount: float, expense_date: str) -> None:
    if not label.strip() or amount <= 0:
        raise ValueError("Add a description and an amount greater than zero.")
    with connect() as conn:
        conn.execute(
            "INSERT INTO expenses (user_id, label, category, amount, expense_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, label.strip(), category, amount, expense_date),
        )


def get_expenses(user_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT id, label, category, amount, expense_date, is_sample FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, id DESC",
            (user_id,),
        ).fetchall()


def get_summary(user_id: int) -> dict[str, Any]:
    with connect() as conn:
        totals = conn.execute(
            """SELECT COALESCE(SUM(o.quantity * o.unit_price), 0) AS sales,
                      COALESCE(SUM(o.quantity * o.unit_cost), 0) AS cost,
                      COALESCE(SUM(o.quantity * o.unit_price - o.amount_paid), 0) AS due,
                      COUNT(*) AS order_count
               FROM orders o WHERE o.user_id = ?""", (user_id,)
        ).fetchone()
        paid = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE user_id = ?", (user_id,)
        ).fetchone()["total"]
        expenses = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()["total"]
        due_today = conn.execute(
            "SELECT COUNT(*) AS total FROM visits WHERE user_id = ? AND follow_up_done = 0 AND follow_up_date <> '' AND follow_up_date <= date('now','localtime')",
            (user_id,),
        ).fetchone()["total"]
        return {**dict(totals), "paid": paid, "expenses": expenses,
                "net_profit": totals["sales"] - totals["cost"] - expenses,
                "follow_ups_due": due_today}


def get_monthly_sales(user_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT strftime('%Y-%m', created_at) AS month, SUM(quantity * unit_price) AS sales FROM orders WHERE user_id = ? GROUP BY strftime('%Y-%m', created_at) ORDER BY month DESC LIMIT 6",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def get_best_sellers(user_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT item, SUM(quantity) AS quantity, SUM(quantity * unit_price) AS sales FROM orders WHERE user_id = ? GROUP BY item ORDER BY quantity DESC LIMIT 5",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_payment_history(user_id: int) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT p.id, c.name AS customer, o.item, p.amount, p.method, p.paid_at FROM payments p JOIN orders o ON o.id = p.order_id JOIN customers c ON c.id = o.customer_id WHERE p.user_id = ? AND o.user_id = ? AND c.user_id = ? ORDER BY p.paid_at DESC, p.id DESC",
            (user_id, user_id, user_id),
        ).fetchall()


def complete_follow_up(user_id: int, visit_id: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE visits SET follow_up_done = 1 WHERE id = ? AND user_id = ?",
            (visit_id, user_id),
        )


def clear_sample_data(user_id: int) -> None:
    """Remove only fictional demo rows for the signed-in account."""
    with connect() as conn:
        conn.execute(
            "DELETE FROM payments WHERE user_id = ? AND order_id IN (SELECT id FROM orders WHERE user_id = ? AND is_sample = 1)",
            (user_id, user_id),
        )
        conn.execute("DELETE FROM visits WHERE user_id = ? AND is_sample = 1", (user_id,))
        conn.execute("DELETE FROM expenses WHERE user_id = ? AND is_sample = 1", (user_id,))
        conn.execute("DELETE FROM orders WHERE user_id = ? AND is_sample = 1", (user_id,))
        conn.execute(
            "UPDATE products SET is_sample = 0 WHERE user_id = ? AND is_sample = 1 AND EXISTS (SELECT 1 FROM orders WHERE orders.product_id = products.id AND orders.user_id = ?)",
            (user_id, user_id),
        )
        conn.execute(
            "DELETE FROM products WHERE user_id = ? AND is_sample = 1", (user_id,)
        )
        conn.execute(
            "UPDATE customers SET is_sample = 0 WHERE user_id = ? AND is_sample = 1 AND (EXISTS (SELECT 1 FROM orders WHERE orders.customer_id = customers.id AND orders.user_id = ?) OR EXISTS (SELECT 1 FROM visits WHERE visits.customer_id = customers.id AND visits.user_id = ?))",
            (user_id, user_id, user_id),
        )
        conn.execute(
            "DELETE FROM customers WHERE user_id = ? AND is_sample = 1", (user_id,)
        )
