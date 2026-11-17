from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import pymysql

from .db import execute, transaction


class AppError(Exception):
    """A business rule the person using the system can act on."""


def money(price, qty):
    return (Decimal(price) * Decimal(qty)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def next_number(cur, kind):
    year = date.today().year
    stem = f"SL-{year}" if kind == "sale" else f"QT-{year}"
    key = f"{kind}-{year}"
    cur.execute(
        """
        INSERT INTO counters (name, next_value)
        VALUES (%s, LAST_INSERT_ID(1))
        ON DUPLICATE KEY UPDATE next_value = LAST_INSERT_ID(next_value + 1)
        """,
        (key,),
    )
    cur.execute("SELECT LAST_INSERT_ID() AS n")
    return f"{stem}-{int(cur.fetchone()['n']):04d}"


def change_stock(cur, product_id, branch_id, delta, movement_type, reference_no, note, user_id, product_name, branch_name):
    delta = int(delta)
    if delta == 0:
        return None
    cur.execute(
        """
        INSERT INTO stock (product_id, branch_id, quantity)
        VALUES (%s, %s, 0)
        ON DUPLICATE KEY UPDATE quantity = quantity
        """,
        (product_id, branch_id),
    )
    cur.execute(
        "SELECT quantity FROM stock WHERE product_id=%s AND branch_id=%s FOR UPDATE",
        (product_id, branch_id),
    )
    current = int(cur.fetchone()["quantity"])
    updated = current + delta
    if updated < 0:
        raise AppError(
            f"Only {current} units of {product_name} are available at {branch_name}."
        )
    cur.execute(
        "UPDATE stock SET quantity=%s WHERE product_id=%s AND branch_id=%s",
        (updated, product_id, branch_id),
    )
    cur.execute(
        """
        INSERT INTO stock_movements
        (product_id, branch_id, movement_type, quantity, balance_after, reference_no, note, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (product_id, branch_id, movement_type, delta, updated, reference_no, note, user_id),
    )
    return updated


def _branch_name(cur, branch_id):
    cur.execute("SELECT id, name FROM branches WHERE id=%s", (branch_id,))
    row = cur.fetchone()
    if not row:
        raise AppError("Choose a valid branch.")
    return row["name"]


def _require_customer(cur, customer_id):
    cur.execute("SELECT id FROM customers WHERE id=%s", (customer_id,))
    if not cur.fetchone():
        raise AppError("Choose a customer.")


def _resolve_lines(cur, raw_lines):
    merged = {}
    order = []
    for line in raw_lines:
        product_id = int(line["product_id"])
        if product_id not in merged:
            order.append(product_id)
            merged[product_id] = 0
        merged[product_id] += int(line["quantity"])
    resolved = []
    for product_id in order:
        cur.execute(
            "SELECT id, name, unit_price, is_active FROM products WHERE id=%s FOR UPDATE",
            (product_id,),
        )
        product = cur.fetchone()
        if not product or not product["is_active"]:
            raise AppError("One of the selected products is no longer available.")
        qty = merged[product_id]
        price = product["unit_price"]
        resolved.append(
            {
                "product_id": product["id"],
                "name": product["name"],
                "quantity": qty,
                "unit_price": price,
                "line_total": money(price, qty),
            }
        )
    if not resolved:
        raise AppError("Add at least one product.")
    return resolved


def _stock_check(cur, lines, branch_id, branch_name):
    for line in lines:
        cur.execute(
            "SELECT quantity FROM stock WHERE product_id=%s AND branch_id=%s FOR UPDATE",
            (line["product_id"], branch_id),
        )
        row = cur.fetchone()
        available = int(row["quantity"]) if row else 0
        if line["quantity"] > available:
            raise AppError(
                f"Only {available} units of {line['name']} are available at {branch_name}."
            )


def create_product(data, opening, user_id):
    try:
        with transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO products (sku, name, category, description, unit_price, reorder_level)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    data["sku"],
                    data["name"],
                    data["category"],
                    data["description"],
                    data["unit_price"],
                    data["reorder_level"],
                ),
            )
            product_id = cur.lastrowid
            for branch_id, qty in opening:
                cur.execute("SELECT name FROM branches WHERE id=%s", (branch_id,))
                branch = cur.fetchone()
                if not branch:
                    raise AppError("A branch in the opening stock could not be found.")
                if qty:
                    change_stock(
                        cur,
                        product_id,
                        branch_id,
                        qty,
                        "receive",
                        data["sku"],
                        "Opening stock",
                        user_id,
                        data["name"],
                        branch["name"],
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO stock (product_id, branch_id, quantity)
                        VALUES (%s, %s, 0)
                        ON DUPLICATE KEY UPDATE quantity = quantity
                        """,
                        (product_id, branch_id),
                    )
            return product_id
    except pymysql.err.IntegrityError as exc:
        raise AppError("That SKU is already in use.") from exc


def update_product(product_id, data):
    try:
        with transaction() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM products WHERE id=%s FOR UPDATE", (product_id,))
            if not cur.fetchone():
                raise AppError("That product could not be found.")
            cur.execute(
                """
                UPDATE products
                SET sku=%s, name=%s, category=%s, description=%s, unit_price=%s, reorder_level=%s
                WHERE id=%s
                """,
                (
                    data["sku"],
                    data["name"],
                    data["category"],
                    data["description"],
                    data["unit_price"],
                    data["reorder_level"],
                    product_id,
                ),
            )
    except pymysql.err.IntegrityError as exc:
        raise AppError("That SKU is already in use.") from exc


def set_product_active(product_id, active):
    execute("UPDATE products SET is_active=%s WHERE id=%s", (1 if active else 0, product_id))


def receive_or_adjust(product_id, branch_id, delta, movement_type, note, user_id):
    with transaction() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name, is_active FROM products WHERE id=%s", (product_id,))
        product = cur.fetchone()
        if not product or not product["is_active"]:
            raise AppError("Choose an active product.")
        branch_name = _branch_name(cur, branch_id)
        change_stock(
            cur,
            product_id,
            branch_id,
            delta,
            movement_type,
            None,
            note,
            user_id,
            product["name"],
            branch_name,
        )


def transfer_stock(product_id, source_id, dest_id, qty, note, user_id):
    if source_id == dest_id:
        raise AppError("Choose two different branches.")
    with transaction() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name, is_active FROM products WHERE id=%s", (product_id,))
        product = cur.fetchone()
        if not product or not product["is_active"]:
            raise AppError("Choose an active product.")
        source = _branch_name(cur, source_id)
        dest = _branch_name(cur, dest_id)
        detail = note or f"Transfer from {source} to {dest}"
        change_stock(
            cur, product_id, source_id, -qty, "transfer_out", None, detail, user_id, product["name"], source
        )
        change_stock(
            cur, product_id, dest_id, qty, "transfer_in", None, detail, user_id, product["name"], dest
        )


def create_branch(data):
    try:
        with transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO branches (code, name, address, phone) VALUES (%s, %s, %s, %s)",
                (data["code"], data["name"], data["address"], data["phone"]),
            )
            branch_id = cur.lastrowid
            cur.execute("SELECT id FROM products")
            for product in cur.fetchall():
                cur.execute(
                    """
                    INSERT INTO stock (product_id, branch_id, quantity)
                    VALUES (%s, %s, 0)
                    ON DUPLICATE KEY UPDATE quantity = quantity
                    """,
                    (product["id"], branch_id),
                )
            return branch_id
    except pymysql.err.IntegrityError as exc:
        raise AppError("That branch code is already in use.") from exc


def update_branch(branch_id, data):
    try:
        with transaction() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM branches WHERE id=%s FOR UPDATE", (branch_id,))
            if not cur.fetchone():
                raise AppError("That branch could not be found.")
            cur.execute(
                "UPDATE branches SET code=%s, name=%s, address=%s, phone=%s WHERE id=%s",
                (data["code"], data["name"], data["address"], data["phone"], branch_id),
            )
    except pymysql.err.IntegrityError as exc:
        raise AppError("That branch code is already in use.") from exc


def save_customer(data, customer_id=None):
    try:
        if customer_id:
            execute(
                "UPDATE customers SET full_name=%s, email=%s, phone=%s, address=%s WHERE id=%s",
                (data["full_name"], data["email"], data["phone"], data["address"], customer_id),
            )
            return customer_id
        return execute(
            "INSERT INTO customers (full_name, email, phone, address) VALUES (%s, %s, %s, %s)",
            (data["full_name"], data["email"], data["phone"], data["address"]),
        )
    except pymysql.err.IntegrityError as exc:
        raise AppError("A customer with this email is already on file.") from exc


def create_quotation(user_id, customer_id, branch_id, notes, raw_lines):
    with transaction() as conn:
        cur = conn.cursor()
        _require_customer(cur, customer_id)
        branch_name = _branch_name(cur, branch_id)
        lines = _resolve_lines(cur, raw_lines)
        _stock_check(cur, lines, branch_id, branch_name)
        quote_no = next_number(cur, "quote")
        total = sum((line["line_total"] for line in lines), Decimal("0.00"))
        cur.execute(
            """
            INSERT INTO quotations (quote_no, customer_id, branch_id, user_id, status, notes, total)
            VALUES (%s, %s, %s, %s, 'draft', %s, %s)
            """,
            (quote_no, customer_id, branch_id, user_id, notes, total),
        )
        quote_id = cur.lastrowid
        for line in lines:
            cur.execute(
                """
                INSERT INTO quotation_items (quotation_id, product_id, quantity, unit_price, line_total)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (quote_id, line["product_id"], line["quantity"], line["unit_price"], line["line_total"]),
            )
        return quote_id


def set_quote_status(quote_id, status):
    allowed = {
        "draft": {"sent", "accepted", "rejected"},
        "sent": {"accepted", "rejected"},
        "accepted": {"rejected"},
        "rejected": set(),
        "converted": set(),
    }
    with transaction() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM quotations WHERE id=%s FOR UPDATE", (quote_id,))
        row = cur.fetchone()
        if not row:
            raise AppError("That quotation could not be found.")
        if status not in allowed[row["status"]]:
            raise AppError("That status change is no longer available.")
        cur.execute("UPDATE quotations SET status=%s WHERE id=%s", (status, quote_id))


def create_sale(user_id, customer_id, branch_id, payment_method, raw_lines):
    with transaction() as conn:
        cur = conn.cursor()
        _require_customer(cur, customer_id)
        branch_name = _branch_name(cur, branch_id)
        lines = _resolve_lines(cur, raw_lines)
        _stock_check(cur, lines, branch_id, branch_name)
        return _write_sale(cur, user_id, customer_id, branch_id, branch_name, payment_method, lines, None)


def convert_quotation(user_id, quote_id, payment_method):
    with transaction() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM quotations WHERE id=%s FOR UPDATE", (quote_id,))
        quote = cur.fetchone()
        if not quote:
            raise AppError("That quotation could not be found.")
        if quote["status"] == "converted":
            raise AppError("This quotation has already been turned into a sale.")
        if quote["status"] == "rejected":
            raise AppError("A rejected quotation cannot be sold.")
        cur.execute(
            """
            SELECT qi.product_id, qi.quantity, qi.unit_price, qi.line_total, p.name, p.is_active
            FROM quotation_items qi
            JOIN products p ON p.id = qi.product_id
            WHERE qi.quotation_id = %s
            ORDER BY qi.id
            """,
            (quote_id,),
        )
        lines = list(cur.fetchall())
        if not lines:
            raise AppError("This quotation has no products.")
        branch_name = _branch_name(cur, quote["branch_id"])
        _stock_check(cur, lines, quote["branch_id"], branch_name)
        sale_id = _write_sale(
            cur,
            user_id,
            quote["customer_id"],
            quote["branch_id"],
            branch_name,
            payment_method,
            lines,
            quote_id,
        )
        cur.execute("UPDATE quotations SET status='converted' WHERE id=%s", (quote_id,))
        return sale_id


def _write_sale(cur, user_id, customer_id, branch_id, branch_name, payment_method, lines, quotation_id):
    sale_no = next_number(cur, "sale")
    total = sum((Decimal(line["line_total"]) for line in lines), Decimal("0.00"))
    for line in lines:
        change_stock(
            cur,
            line["product_id"],
            branch_id,
            -int(line["quantity"]),
            "sale",
            sale_no,
            "Customer purchase",
            user_id,
            line["name"],
            branch_name,
        )
    cur.execute(
        """
        INSERT INTO sales (sale_no, customer_id, branch_id, user_id, quotation_id, payment_method, total)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (sale_no, customer_id, branch_id, user_id, quotation_id, payment_method, total),
    )
    sale_id = cur.lastrowid
    for line in lines:
        cur.execute(
            """
            INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, line_total)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (sale_id, line["product_id"], line["quantity"], line["unit_price"], line["line_total"]),
        )
    return sale_id
