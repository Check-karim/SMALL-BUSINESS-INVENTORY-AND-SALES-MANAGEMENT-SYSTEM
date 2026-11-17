import secrets
from datetime import datetime, timedelta
from decimal import Decimal

import pymysql
from flask import Flask, abort, g, render_template, request, session

from .config import Config
from .db import close_db, init_db

NAV = [
    ("manage.dashboard_page", "Dashboard", {"manage.dashboard_page"}, "all"),
    ("catalog.product_list", "Products", {"catalog.product_list", "catalog.product_new", "catalog.product_edit"}, "all"),
    ("catalog.inventory_list", "Inventory", {"catalog.inventory_list", "catalog.receive", "catalog.transfer"}, "all"),
    ("catalog.movement_list", "Movements", {"catalog.movement_list"}, "admin"),
    ("commerce.quotation_list", "Quotations", {"commerce.quotation_list", "commerce.quotation_new", "commerce.quotation_detail"}, "all"),
    ("commerce.sale_list", "Sales", {"commerce.sale_list", "commerce.sale_new", "commerce.sale_detail"}, "all"),
    ("commerce.customer_list", "Customers", {"commerce.customer_list", "commerce.customer_new", "commerce.customer_edit"}, "all"),
    ("manage.reports", "Reports", {"manage.reports"}, "admin"),
    ("manage.branch_list", "Branches", {"manage.branch_list", "manage.branch_new", "manage.branch_edit"}, "admin"),
    ("manage.team_page", "Team", {"manage.team_page"}, "admin"),
]

PUBLIC_PAGES = {"public.home", "public.about", "static"}


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    app.teardown_appcontext(close_db)

    @app.before_request
    def prepare_request():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        if request.method == "POST":
            sent = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not sent or not expected or len(sent) != len(expected) or not secrets.compare_digest(sent, expected):
                abort(400)
        if request.endpoint in PUBLIC_PAGES:
            return None
        try:
            init_db()
            g.db_ready = True
        except Exception as exc:
            app.logger.exception("Database connection failed")
            g.db_ready = False
            return render_template("db_error.html", message=str(exc)), 503
        return None

    @app.context_processor
    def inject_globals():
        user = session.get("user")
        endpoint = request.endpoint or ""
        items = []
        if user:
            for endpoint_name, label, endpoints, who in NAV:
                if who == "admin" and user.get("role") != "admin":
                    continue
                items.append(
                    {
                        "endpoint": endpoint_name,
                        "label": label,
                        "active": endpoint in endpoints,
                    }
                )
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        return {
            "me": user,
            "nav_items": items,
            "csrf": session.get("csrf_token", ""),
            "greeting": greeting,
            "payment_labels": dict(Config.PAYMENT_METHODS),
            "status_labels": dict(Config.QUOTE_STATUSES),
            "movement_labels": Config.MOVEMENT_LABELS,
        }

    @app.template_filter("money")
    def money_filter(value):
        amount = Decimal("0.00") if value is None else Decimal(str(value))
        amount = amount.quantize(Decimal("0.01"))
        return f"${amount:,.2f}"

    @app.template_filter("when")
    def when_filter(value):
        if not value:
            return ""
        return value.strftime("%d %b %Y, %H:%M")

    @app.template_filter("day")
    def day_filter(value):
        if not value:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%d %b %Y")
        return str(value)

    @app.template_filter("signed")
    def signed_filter(value):
        number = int(value)
        return f"+{number}" if number > 0 else str(number)

    @app.errorhandler(404)
    def missing(_exc):
        return render_template("error.html", code=404, title="Page not found", message="That page is not part of the system."), 404

    @app.errorhandler(400)
    def bad_form(_exc):
        return render_template("error.html", code=400, title="Form expired", message="Go back, refresh the page, and submit the form again."), 400

    @app.errorhandler(pymysql.MySQLError)
    def database_error(exc):
        app.logger.exception("Database error")
        return render_template("db_error.html", message=str(exc)), 500

    from .blueprints.auth import bp as auth_bp
    from .blueprints.catalog import bp as catalog_bp
    from .blueprints.commerce import bp as commerce_bp
    from .blueprints.manage import bp as manage_bp
    from .blueprints.public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(commerce_bp)
    app.register_blueprint(manage_bp)

    with app.app_context():
        try:
            init_db()
        except Exception:
            app.logger.exception("MySQL is not ready. The homepage still opens, and data pages will retry.")

    return app
