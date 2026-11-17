from .db import query_all, query_one


def like_param(term):
    cleaned = term.replace("\\", "").replace("%", "").replace("_", "")
    return f"%{cleaned}%"


def branches():
    return query_all("SELECT * FROM branches ORDER BY name")


def branch(branch_id):
    return query_one("SELECT * FROM branches WHERE id=%s", (branch_id,))


def products(search="", category="", include_inactive=False):
    sql = """
        SELECT p.id, p.sku, p.name, p.category, p.unit_price, p.reorder_level, p.is_active,
               COALESCE(SUM(s.quantity), 0) AS on_hand,
               COALESCE(SUM(s.quantity <= p.reorder_level), 0) AS low_branches
        FROM products p
        LEFT JOIN stock s ON s.product_id = p.id
        WHERE 1=1
    """
    params = []
    if not include_inactive:
        sql += " AND p.is_active = 1"
    if category:
        sql += " AND p.category = %s"
        params.append(category)
    if search:
        sql += " AND (p.name LIKE %s OR p.sku LIKE %s)"
        like = like_param(search)
        params.extend([like, like])
    sql += """
        GROUP BY p.id, p.sku, p.name, p.category, p.unit_price, p.reorder_level, p.is_active
        ORDER BY p.name
        LIMIT 300
    """
    return query_all(sql, params)


def product(product_id):
    return query_one("SELECT * FROM products WHERE id=%s", (product_id,))


def inventory(search="", branch_id=None, low_only=False):
    sql = """
        SELECT p.id AS product_id, p.sku, p.name, p.category, p.reorder_level,
               b.id AS branch_id, b.name AS branch_name,
               COALESCE(s.quantity, 0) AS quantity
        FROM products p
        CROSS JOIN branches b
        LEFT JOIN stock s ON s.product_id = p.id AND s.branch_id = b.id
        WHERE p.is_active = 1
    """
    params = []
    if branch_id:
        sql += " AND b.id = %s"
        params.append(branch_id)
    if search:
        sql += " AND (p.name LIKE %s OR p.sku LIKE %s)"
        like = like_param(search)
        params.extend([like, like])
    if low_only:
        sql += " AND COALESCE(s.quantity, 0) <= p.reorder_level"
    sql += " ORDER BY p.name, b.name LIMIT 400"
    return query_all(sql, params)


def movements(search="", branch_id=None, movement_type=""):
    sql = """
        SELECT m.*, p.sku, p.name AS product_name, b.name AS branch_name, u.full_name AS staff_name
        FROM stock_movements m
        JOIN products p ON p.id = m.product_id
        JOIN branches b ON b.id = m.branch_id
        JOIN users u ON u.id = m.user_id
        WHERE 1=1
    """
    params = []
    if branch_id:
        sql += " AND m.branch_id = %s"
        params.append(branch_id)
    if movement_type:
        sql += " AND m.movement_type = %s"
        params.append(movement_type)
    if search:
        sql += " AND (p.name LIKE %s OR p.sku LIKE %s OR m.reference_no LIKE %s)"
        like = like_param(search)
        params.extend([like, like, like])
    sql += " ORDER BY m.id DESC LIMIT 200"
    return query_all(sql, params)


def customers(search=""):
    sql = "SELECT * FROM customers"
    params = []
    if search:
        sql += " WHERE full_name LIKE %s OR email LIKE %s OR phone LIKE %s"
        like = like_param(search)
        params.extend([like, like, like])
    sql += " ORDER BY full_name LIMIT 200"
    return query_all(sql, params)


def customer(customer_id):
    return query_one("SELECT * FROM customers WHERE id=%s", (customer_id,))


def quotations(search="", status=""):
    sql = """
        SELECT q.*, c.full_name AS customer_name, b.name AS branch_name, u.full_name AS staff_name
        FROM quotations q
        JOIN customers c ON c.id = q.customer_id
        JOIN branches b ON b.id = q.branch_id
        JOIN users u ON u.id = q.user_id
        WHERE 1=1
    """
    params = []
    if status:
        sql += " AND q.status = %s"
        params.append(status)
    if search:
        sql += " AND (q.quote_no LIKE %s OR c.full_name LIKE %s)"
        like = like_param(search)
        params.extend([like, like])
    sql += " ORDER BY q.id DESC LIMIT 200"
    return query_all(sql, params)


def quotation(quote_id):
    header = query_one(
        """
        SELECT q.*, c.full_name AS customer_name, c.email AS customer_email, c.phone AS customer_phone,
               c.address AS customer_address, b.name AS branch_name, b.phone AS branch_phone,
               u.full_name AS staff_name
        FROM quotations q
        JOIN customers c ON c.id = q.customer_id
        JOIN branches b ON b.id = q.branch_id
        JOIN users u ON u.id = q.user_id
        WHERE q.id = %s
        """,
        (quote_id,),
    )
    if not header:
        return None, []
    items = query_all(
        """
        SELECT qi.*, p.name, p.sku
        FROM quotation_items qi
        JOIN products p ON p.id = qi.product_id
        WHERE qi.quotation_id = %s
        ORDER BY qi.id
        """,
        (quote_id,),
    )
    return header, items


def sales(search="", branch_id=None):
    sql = """
        SELECT s.*, c.full_name AS customer_name, b.name AS branch_name, u.full_name AS staff_name
        FROM sales s
        JOIN customers c ON c.id = s.customer_id
        JOIN branches b ON b.id = s.branch_id
        JOIN users u ON u.id = s.user_id
        WHERE 1=1
    """
    params = []
    if branch_id:
        sql += " AND s.branch_id = %s"
        params.append(branch_id)
    if search:
        sql += " AND (s.sale_no LIKE %s OR c.full_name LIKE %s)"
        like = like_param(search)
        params.extend([like, like])
    sql += " ORDER BY s.id DESC LIMIT 200"
    return query_all(sql, params)


def sale(sale_id):
    header = query_one(
        """
        SELECT s.*, c.full_name AS customer_name, c.email AS customer_email, c.phone AS customer_phone,
               c.address AS customer_address, b.name AS branch_name, b.address AS branch_address,
               b.phone AS branch_phone, u.full_name AS staff_name, q.quote_no
        FROM sales s
        JOIN customers c ON c.id = s.customer_id
        JOIN branches b ON b.id = s.branch_id
        JOIN users u ON u.id = s.user_id
        LEFT JOIN quotations q ON q.id = s.quotation_id
        WHERE s.id = %s
        """,
        (sale_id,),
    )
    if not header:
        return None, []
    items = query_all(
        """
        SELECT si.*, p.name, p.sku
        FROM sale_items si
        JOIN products p ON p.id = si.product_id
        WHERE si.sale_id = %s
        ORDER BY si.id
        """,
        (sale_id,),
    )
    return header, items


def catalog():
    rows = query_all(
        """
        SELECT id, sku, name, unit_price
        FROM products
        WHERE is_active = 1
        ORDER BY name
        """
    )
    stock_rows = query_all("SELECT product_id, branch_id, quantity FROM stock")
    stock = {}
    for row in stock_rows:
        stock.setdefault(row["product_id"], {})[str(row["branch_id"])] = int(row["quantity"])
    items = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "sku": row["sku"],
                "name": row["name"],
                "price": f"{row['unit_price']:.2f}",
                "stock": stock.get(row["id"], {}),
            }
        )
    return items


def active_products():
    return query_all(
        "SELECT id, sku, name FROM products WHERE is_active = 1 ORDER BY name"
    )


def team():
    return query_all(
        """
        SELECT u.id, u.username, u.full_name, u.email, u.phone, u.role, u.created_at,
               b.name AS branch_name
        FROM users u
        LEFT JOIN branches b ON b.id = u.branch_id
        ORDER BY u.role, u.full_name
        """
    )


def dashboard():
    product_count = query_one("SELECT COUNT(*) AS c FROM products WHERE is_active = 1")["c"]
    branch_count = query_one("SELECT COUNT(*) AS c FROM branches")["c"]
    low_count = query_one(
        """
        SELECT COUNT(*) AS c
        FROM products p
        CROSS JOIN branches b
        LEFT JOIN stock s ON s.product_id = p.id AND s.branch_id = b.id
        WHERE p.is_active = 1 AND COALESCE(s.quantity, 0) <= p.reorder_level
        """
    )["c"]
    today = query_one(
        """
        SELECT COUNT(*) AS c, COALESCE(SUM(total), 0) AS revenue
        FROM sales
        WHERE DATE(created_at) = CURDATE()
        """
    )
    open_quotes = query_one(
        """
        SELECT COUNT(*) AS c FROM quotations
        WHERE status IN ('draft', 'sent', 'accepted')
        """
    )["c"]
    recent_sales = query_all(
        """
        SELECT s.id, s.sale_no, s.total, s.created_at, c.full_name AS customer_name, b.name AS branch_name
        FROM sales s
        JOIN customers c ON c.id = s.customer_id
        JOIN branches b ON b.id = s.branch_id
        ORDER BY s.id DESC
        LIMIT 6
        """
    )
    low_rows = query_all(
        """
        SELECT p.sku, p.name, b.name AS branch_name, COALESCE(s.quantity, 0) AS quantity, p.reorder_level
        FROM products p
        CROSS JOIN branches b
        LEFT JOIN stock s ON s.product_id = p.id AND s.branch_id = b.id
        WHERE p.is_active = 1 AND COALESCE(s.quantity, 0) <= p.reorder_level
        ORDER BY quantity, p.name
        LIMIT 6
        """
    )
    return {
        "product_count": product_count,
        "branch_count": branch_count,
        "low_count": low_count,
        "today_count": today["c"],
        "today_revenue": today["revenue"],
        "open_quotes": open_quotes,
        "recent_sales": recent_sales,
        "low_rows": low_rows,
    }


def public_stats():
    return {
        "branches": query_one("SELECT COUNT(*) AS c FROM branches")["c"],
        "products": query_one("SELECT COUNT(*) AS c FROM products WHERE is_active = 1")["c"],
        "low": query_one(
            """
            SELECT COUNT(*) AS c
            FROM products p
            CROSS JOIN branches b
            LEFT JOIN stock s ON s.product_id = p.id AND s.branch_id = b.id
            WHERE p.is_active = 1 AND COALESCE(s.quantity, 0) <= p.reorder_level
            """
        )["c"],
    }


def report(start, end):
    summary = query_one(
        """
        SELECT COUNT(*) AS sales_count,
               COALESCE(SUM(total), 0) AS revenue,
               COALESCE(SUM((SELECT SUM(quantity) FROM sale_items si WHERE si.sale_id = s.id)), 0) AS units
        FROM sales s
        WHERE DATE(s.created_at) BETWEEN %s AND %s
        """,
        (start, end),
    )
    by_branch = query_all(
        """
        SELECT b.name, COUNT(s.id) AS sales_count, COALESCE(SUM(s.total), 0) AS revenue
        FROM branches b
        LEFT JOIN sales s ON s.branch_id = b.id AND DATE(s.created_at) BETWEEN %s AND %s
        GROUP BY b.id, b.name
        ORDER BY revenue DESC, b.name
        """,
        (start, end),
    )
    top_products = query_all(
        """
        SELECT p.name, p.sku, SUM(si.quantity) AS quantity, SUM(si.line_total) AS revenue
        FROM sale_items si
        JOIN sales s ON s.id = si.sale_id
        JOIN products p ON p.id = si.product_id
        WHERE DATE(s.created_at) BETWEEN %s AND %s
        GROUP BY p.id, p.name, p.sku
        ORDER BY revenue DESC
        LIMIT 8
        """,
        (start, end),
    )
    by_day = query_all(
        """
        SELECT DATE(created_at) AS day, COUNT(*) AS sales_count, SUM(total) AS revenue
        FROM sales
        WHERE DATE(created_at) BETWEEN %s AND %s
        GROUP BY DATE(created_at)
        ORDER BY day
        """,
        (start, end),
    )
    payments = query_all(
        """
        SELECT payment_method, COUNT(*) AS sales_count, SUM(total) AS revenue
        FROM sales
        WHERE DATE(created_at) BETWEEN %s AND %s
        GROUP BY payment_method
        ORDER BY revenue DESC
        """,
        (start, end),
    )
    low_rows = query_all(
        """
        SELECT p.sku, p.name, b.name AS branch_name, COALESCE(s.quantity, 0) AS quantity, p.reorder_level
        FROM products p
        CROSS JOIN branches b
        LEFT JOIN stock s ON s.product_id = p.id AND s.branch_id = b.id
        WHERE p.is_active = 1 AND COALESCE(s.quantity, 0) <= p.reorder_level
        ORDER BY quantity, p.name, b.name
        """
    )
    peak = max((row["revenue"] for row in by_branch), default=0)
    return {
        "summary": summary,
        "by_branch": by_branch,
        "top_products": top_products,
        "by_day": by_day,
        "payments": payments,
        "low_rows": low_rows,
        "peak": peak,
    }
