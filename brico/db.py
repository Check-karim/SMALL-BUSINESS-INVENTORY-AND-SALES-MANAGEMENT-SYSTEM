import re
import threading
from contextlib import contextmanager
from decimal import Decimal

import pymysql
from flask import current_app, g, has_app_context
from pymysql.cursors import DictCursor
from werkzeug.security import generate_password_hash

from .config import Config

_ready = False
_lock = threading.Lock()

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS branches (
        id INT AUTO_INCREMENT PRIMARY KEY,
        code VARCHAR(10) NOT NULL UNIQUE,
        name VARCHAR(80) NOT NULL,
        address VARCHAR(160) NOT NULL,
        phone VARCHAR(20) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(30) NOT NULL UNIQUE,
        password_hash VARCHAR(512) NOT NULL,
        full_name VARCHAR(80) NOT NULL,
        email VARCHAR(120) NOT NULL UNIQUE,
        phone VARCHAR(20) NOT NULL,
        role ENUM('admin', 'staff') NOT NULL DEFAULT 'staff',
        branch_id INT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_users_branch FOREIGN KEY (branch_id) REFERENCES branches (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        sku VARCHAR(30) NOT NULL UNIQUE,
        name VARCHAR(120) NOT NULL,
        category VARCHAR(60) NOT NULL,
        description VARCHAR(500) NOT NULL DEFAULT '',
        unit_price DECIMAL(12,2) NOT NULL,
        reorder_level INT NOT NULL DEFAULT 5,
        is_active TINYINT(1) NOT NULL DEFAULT 1,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS stock (
        product_id INT NOT NULL,
        branch_id INT NOT NULL,
        quantity INT NOT NULL DEFAULT 0,
        PRIMARY KEY (product_id, branch_id),
        CONSTRAINT fk_stock_product FOREIGN KEY (product_id) REFERENCES products (id),
        CONSTRAINT fk_stock_branch FOREIGN KEY (branch_id) REFERENCES branches (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_movements (
        id INT AUTO_INCREMENT PRIMARY KEY,
        product_id INT NOT NULL,
        branch_id INT NOT NULL,
        movement_type ENUM('receive','sale','adjustment','transfer_in','transfer_out') NOT NULL,
        quantity INT NOT NULL,
        balance_after INT NOT NULL,
        reference_no VARCHAR(40) NULL,
        note VARCHAR(255) NOT NULL DEFAULT '',
        user_id INT NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_movements_created (created_at),
        CONSTRAINT fk_mov_product FOREIGN KEY (product_id) REFERENCES products (id),
        CONSTRAINT fk_mov_branch FOREIGN KEY (branch_id) REFERENCES branches (id),
        CONSTRAINT fk_mov_user FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS customers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        full_name VARCHAR(80) NOT NULL,
        email VARCHAR(120) NOT NULL UNIQUE,
        phone VARCHAR(20) NOT NULL,
        address VARCHAR(160) NOT NULL DEFAULT '',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS quotations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        quote_no VARCHAR(20) NOT NULL UNIQUE,
        customer_id INT NOT NULL,
        branch_id INT NOT NULL,
        user_id INT NOT NULL,
        status ENUM('draft','sent','accepted','rejected','converted') NOT NULL DEFAULT 'draft',
        notes VARCHAR(255) NOT NULL DEFAULT '',
        total DECIMAL(12,2) NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_quotes_created (created_at),
        CONSTRAINT fk_quote_customer FOREIGN KEY (customer_id) REFERENCES customers (id),
        CONSTRAINT fk_quote_branch FOREIGN KEY (branch_id) REFERENCES branches (id),
        CONSTRAINT fk_quote_user FOREIGN KEY (user_id) REFERENCES users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS quotation_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        quotation_id INT NOT NULL,
        product_id INT NOT NULL,
        quantity INT NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL,
        line_total DECIMAL(12,2) NOT NULL,
        CONSTRAINT fk_qi_quote FOREIGN KEY (quotation_id) REFERENCES quotations (id) ON DELETE CASCADE,
        CONSTRAINT fk_qi_product FOREIGN KEY (product_id) REFERENCES products (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS sales (
        id INT AUTO_INCREMENT PRIMARY KEY,
        sale_no VARCHAR(20) NOT NULL UNIQUE,
        customer_id INT NOT NULL,
        branch_id INT NOT NULL,
        user_id INT NOT NULL,
        quotation_id INT NULL,
        payment_method ENUM('cash','card','transfer') NOT NULL DEFAULT 'cash',
        total DECIMAL(12,2) NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_sales_created (created_at),
        CONSTRAINT fk_sale_customer FOREIGN KEY (customer_id) REFERENCES customers (id),
        CONSTRAINT fk_sale_branch FOREIGN KEY (branch_id) REFERENCES branches (id),
        CONSTRAINT fk_sale_user FOREIGN KEY (user_id) REFERENCES users (id),
        CONSTRAINT fk_sale_quote FOREIGN KEY (quotation_id) REFERENCES quotations (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS sale_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        sale_id INT NOT NULL,
        product_id INT NOT NULL,
        quantity INT NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL,
        line_total DECIMAL(12,2) NOT NULL,
        CONSTRAINT fk_si_sale FOREIGN KEY (sale_id) REFERENCES sales (id) ON DELETE CASCADE,
        CONSTRAINT fk_si_product FOREIGN KEY (product_id) REFERENCES products (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS counters (
        name VARCHAR(40) PRIMARY KEY,
        next_value INT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

BRANCHES = [
    ("CTR", "Central Yard", "14 Harbour Road, Northbridge", "02079460021"),
    ("NTH", "North Depot", "88 Mill Lane, Northbridge", "02079460022"),
    ("WST", "West Counter", "3 Station Approach, Westford", "02079460023"),
]

# sku, name, category, description, price, reorder, (central, north, west)
PRODUCTS = [
    ("HAM-160", "Claw Hammer", "Hand Tools", "Forged steel claw hammer, 16 ounce.", "18.50", 8, (24, 10, 4)),
    ("TAP-8M", "Tape Measure", "Hand Tools", "Eight metre tape with a magnetic hook.", "9.75", 10, (40, 18, 6)),
    ("LVL-600", "Spirit Level", "Hand Tools", "600 millimetre box level with three vials.", "22.00", 6, (12, 7, 2)),
    ("DRL-18V", "Cordless Drill", "Power Tools", "18 volt drill driver with two batteries.", "129.00", 4, (8, 5, 1)),
    ("BIT-20", "Drill Bit Set", "Power Tools", "Twenty piece metal and wood bit set.", "16.40", 8, (20, 9, 3)),
    ("PIP-15", "Copper Pipe", "Plumbing", "15 millimetre copper pipe, 3 metre length.", "14.25", 12, (30, 16, 5)),
    ("TAP-MIX", "Basin Mixer Tap", "Plumbing", "Chrome mixer tap for a bathroom basin.", "46.00", 5, (10, 4, 0)),
    ("LED-6W", "LED Downlight", "Electrical", "Six watt fire-rated downlight, warm white.", "11.90", 15, (50, 22, 8)),
    ("CBL-25", "Cable Reel", "Electrical", "25 metre extension reel with a thermal cut-out.", "27.50", 6, (14, 6, 2)),
    ("PNT-10", "White Emulsion", "Paint", "10 litre trade white matt emulsion.", "32.00", 8, (18, 9, 1)),
    ("SCR-440", "Wood Screws", "Fasteners", "Box of 4 by 40 millimetre wood screws.", "6.80", 20, (60, 25, 7)),
    ("PLY-18", "Plywood Sheet", "Building Materials", "18 millimetre hardwood plywood sheet.", "38.50", 6, (15, 8, 2)),
    ("GLV-L", "Work Gloves", "Safety", "Large leather palm work gloves.", "8.20", 10, (22, 3, 11)),
]

CUSTOMERS = [
    ("Elena Marsh", "elena.marsh@example.com", "02079460111", "12 Orchard Close, Northbridge"),
    ("Jonah Pike", "jonah.pike@example.com", "02079460112", "4 Quay Street, Westford"),
]


def mysql_settings():
    if has_app_context():
        cfg = current_app.config
        return {
            "host": cfg["MYSQL_HOST"],
            "port": int(cfg["MYSQL_PORT"]),
            "user": cfg["MYSQL_USER"],
            "password": cfg["MYSQL_PASSWORD"],
            "database": cfg["MYSQL_DB"],
        }
    return {
        "host": Config.MYSQL_HOST,
        "port": Config.MYSQL_PORT,
        "user": Config.MYSQL_USER,
        "password": Config.MYSQL_PASSWORD,
        "database": Config.MYSQL_DB,
    }


def connect(database=None, autocommit=False):
    settings = mysql_settings()
    name = settings["database"] if database is None else database
    if name and not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError("Database name can contain only letters, numbers, and underscores.")
    kwargs = {
        "host": settings["host"],
        "port": settings["port"],
        "user": settings["user"],
        "password": settings["password"],
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": autocommit,
        "connect_timeout": 5,
    }
    if name:
        kwargs["database"] = name
    return pymysql.connect(**kwargs)


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_all(sql, params=()):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise


def query_one(sql, params=()):
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            last_id = cur.lastrowid
        conn.commit()
        return last_id
    except Exception:
        conn.rollback()
        raise


@contextmanager
def transaction():
    """Use the request connection for several statements. Do not call query_all inside it."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        settings = mysql_settings()
        name = settings["database"]
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise ValueError("Database name can contain only letters, numbers, and underscores.")
        bootstrap = connect(database="")
        try:
            with bootstrap.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            bootstrap.commit()
        finally:
            bootstrap.close()

        conn = connect()
        try:
            with conn.cursor() as cur:
                for statement in TABLES:
                    cur.execute(statement)
            conn.commit()
            _seed(conn)
        finally:
            conn.close()
        _ready = True


def _seed(conn):
    with conn.cursor() as cur:
        for code, name, address, phone in BRANCHES:
            cur.execute("SELECT id FROM branches WHERE code=%s", (code,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO branches (code, name, address, phone) VALUES (%s, %s, %s, %s)",
                    (code, name, address, phone),
                )

        cur.execute("SELECT id FROM users WHERE username=%s", (Config.ADMIN_USERNAME,))
        admin = cur.fetchone()
        if not admin:
            cur.execute(
                """
                INSERT INTO users (username, password_hash, full_name, email, phone, role, branch_id)
                VALUES (%s, %s, %s, %s, %s, 'admin', NULL)
                """,
                (
                    Config.ADMIN_USERNAME,
                    generate_password_hash(Config.ADMIN_PASSWORD, method="pbkdf2:sha256"),
                    "System Admin",
                    "admin@briconb.example",
                    "02079460010",
                ),
            )
            admin_id = cur.lastrowid
        else:
            admin_id = admin["id"]

        cur.execute("SELECT id, code FROM branches")
        branch_ids = {row["code"]: row["id"] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) AS c FROM products")
        if cur.fetchone()["c"] == 0:
            codes = [code for code, *_ in BRANCHES]
            for sku, name, category, description, price, reorder, quantities in PRODUCTS:
                cur.execute(
                    """
                    INSERT INTO products (sku, name, category, description, unit_price, reorder_level)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (sku, name, category, description, Decimal(price), reorder),
                )
                product_id = cur.lastrowid
                for code, qty in zip(codes, quantities):
                    branch_id = branch_ids[code]
                    cur.execute(
                        "INSERT INTO stock (product_id, branch_id, quantity) VALUES (%s, %s, %s)",
                        (product_id, branch_id, qty),
                    )
                    if qty:
                        cur.execute(
                            """
                            INSERT INTO stock_movements
                            (product_id, branch_id, movement_type, quantity, balance_after, reference_no, note, user_id)
                            VALUES (%s, %s, 'receive', %s, %s, 'OPENING', 'Opening stock', %s)
                            """,
                            (product_id, branch_id, qty, qty, admin_id),
                        )

        cur.execute("SELECT COUNT(*) AS c FROM customers")
        if cur.fetchone()["c"] == 0:
            for name, email, phone, address in CUSTOMERS:
                cur.execute(
                    "INSERT INTO customers (full_name, email, phone, address) VALUES (%s, %s, %s, %s)",
                    (name, email, phone, address),
                )
    conn.commit()
