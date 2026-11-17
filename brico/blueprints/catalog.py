from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from ..config import Config
from ..forms import product_form
from ..queries import active_products, branches, inventory, movements, product, products
from ..security import admin_required, login_required
from ..services import AppError, receive_or_adjust, set_product_active, transfer_stock, update_product, create_product
from ..validators import validate_choice, validate_int, validate_text

bp = Blueprint("catalog", __name__)


def _optional_int(value):
    return int(value) if value and str(value).isdigit() else None


@bp.get("/products")
@login_required
def product_list():
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    if category and category not in Config.CATEGORIES:
        category = ""
    show_archived = session["user"]["role"] == "admin" and request.args.get("archived") == "1"
    rows = products(search, category, include_inactive=show_archived)
    return render_template(
        "products/list.html",
        rows=rows,
        search=search,
        category=category,
        show_archived=show_archived,
        categories=Config.CATEGORIES,
    )


@bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def product_new():
    branch_rows = branches()
    errors = {}
    data = {
        "sku": "",
        "name": "",
        "category": Config.CATEGORIES[0],
        "description": "",
        "unit_price": "",
        "reorder_level": "5",
    }
    if request.method == "POST":
        data, opening, errors = product_form(request.form, branch_rows)
        if not errors:
            try:
                create_product(data, opening, session["user"]["id"])
            except AppError as exc:
                errors["form"] = str(exc)
            else:
                flash(f"{data['name']} is now on the catalogue.", "success")
                return redirect(url_for("catalog.product_list"))
    return render_template(
        "products/form.html",
        data=data,
        errors=errors,
        branches=branch_rows,
        categories=Config.CATEGORIES,
        editing=False,
    )


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_edit(product_id):
    row = product(product_id)
    if not row:
        abort(404)
    errors = {}
    data = {
        "sku": row["sku"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "unit_price": f"{row['unit_price']:.2f}",
        "reorder_level": row["reorder_level"],
    }
    if request.method == "POST":
        data, _opening, errors = product_form(request.form, [])
        if not errors:
            try:
                update_product(
                    product_id,
                    {
                        "sku": data["sku"],
                        "name": data["name"],
                        "category": data["category"],
                        "description": data["description"],
                        "unit_price": data["unit_price"],
                        "reorder_level": data["reorder_level"],
                    },
                )
            except AppError as exc:
                errors["form"] = str(exc)
            else:
                flash("Product updated.", "success")
                return redirect(url_for("catalog.product_list"))
    return render_template(
        "products/form.html",
        data=data,
        errors=errors,
        branches=[],
        categories=Config.CATEGORIES,
        editing=True,
        product_id=product_id,
        is_active=row["is_active"],
    )


@bp.post("/products/<int:product_id>/archive")
@admin_required
def product_toggle(product_id):
    row = product(product_id)
    if not row:
        abort(404)
    set_product_active(product_id, not row["is_active"])
    flash("Product restored to the catalogue." if not row["is_active"] else "Product archived.", "success")
    return redirect(url_for("catalog.product_list"))


@bp.get("/inventory")
@login_required
def inventory_list():
    search = request.args.get("q", "").strip()
    branch_id = _optional_int(request.args.get("branch_id"))
    low_only = request.args.get("low") == "1"
    rows = inventory(search, branch_id, low_only)
    return render_template(
        "inventory/list.html",
        rows=rows,
        branches=branches(),
        search=search,
        branch_id=branch_id,
        low_only=low_only,
    )


@bp.route("/inventory/receive", methods=["GET", "POST"])
@admin_required
def receive():
    errors = {}
    form = {
        "product_id": request.form.get("product_id", ""),
        "branch_id": request.form.get("branch_id", ""),
        "quantity": request.form.get("quantity", ""),
        "mode": request.form.get("mode", "receive"),
        "note": request.form.get("note", ""),
    }
    if request.method == "POST":
        mode, mode_error = validate_choice(form["mode"], {"receive", "adjustment"}, "stock action")
        product_id, product_error = validate_int(form["product_id"], "Product", minimum=1, maximum=10**9)
        branch_id, branch_error = validate_int(form["branch_id"], "Branch", minimum=1, maximum=10**9)
        note, note_error = validate_text(form["note"], "Note", maximum=255, required=mode == "adjustment")
        if mode == "adjustment":
            quantity, qty_error = validate_int(form["quantity"], "Quantity", minimum=-100000, maximum=100000)
            if quantity == 0:
                qty_error = "An adjustment cannot be zero."
        else:
            quantity, qty_error = validate_int(form["quantity"], "Quantity", minimum=1, maximum=100000)
        for key, message in {
            "mode": mode_error,
            "product_id": product_error,
            "branch_id": branch_error,
            "quantity": qty_error,
            "note": note_error,
        }.items():
            if message:
                errors[key] = message
        if not errors:
            try:
                receive_or_adjust(
                    product_id,
                    branch_id,
                    quantity,
                    "receive" if mode == "receive" else "adjustment",
                    note,
                    session["user"]["id"],
                )
            except AppError as exc:
                errors["form"] = str(exc)
            else:
                flash("Stock updated.", "success")
                return redirect(url_for("catalog.inventory_list"))
    return render_template(
        "inventory/receive.html",
        form=form,
        errors=errors,
        products=active_products(),
        branches=branches(),
    )


@bp.route("/inventory/transfer", methods=["GET", "POST"])
@admin_required
def transfer():
    errors = {}
    form = {
        "product_id": request.form.get("product_id", ""),
        "source_id": request.form.get("source_id", ""),
        "dest_id": request.form.get("dest_id", ""),
        "quantity": request.form.get("quantity", ""),
        "note": request.form.get("note", ""),
    }
    if request.method == "POST":
        product_id, product_error = validate_int(form["product_id"], "Product", minimum=1, maximum=10**9)
        source_id, source_error = validate_int(form["source_id"], "Source branch", minimum=1, maximum=10**9)
        dest_id, dest_error = validate_int(form["dest_id"], "Destination branch", minimum=1, maximum=10**9)
        quantity, qty_error = validate_int(form["quantity"], "Quantity", minimum=1, maximum=100000)
        note, note_error = validate_text(form["note"], "Note", maximum=255)
        for key, message in {
            "product_id": product_error,
            "source_id": source_error,
            "dest_id": dest_error,
            "quantity": qty_error,
            "note": note_error,
        }.items():
            if message:
                errors[key] = message
        if not errors:
            try:
                transfer_stock(product_id, source_id, dest_id, quantity, note, session["user"]["id"])
            except AppError as exc:
                errors["form"] = str(exc)
            else:
                flash("Stock transferred.", "success")
                return redirect(url_for("catalog.inventory_list"))
    return render_template(
        "inventory/transfer.html",
        form=form,
        errors=errors,
        products=active_products(),
        branches=branches(),
    )


@bp.get("/movements")
@login_required
def movement_list():
    search = request.args.get("q", "").strip()
    branch_id = _optional_int(request.args.get("branch_id"))
    movement_type = request.args.get("type", "")
    if movement_type not in Config.MOVEMENT_LABELS:
        movement_type = ""
    rows = movements(search, branch_id, movement_type)
    return render_template(
        "movements/list.html",
        rows=rows,
        branches=branches(),
        search=search,
        branch_id=branch_id,
        movement_type=movement_type,
        movement_types=Config.MOVEMENT_LABELS,
    )
