from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from ..config import Config
from ..forms import customer_form, parse_lines
from ..queries import branches, catalog, customer, customers, quotation, quotations, sale, sales
from ..security import login_required
from ..services import AppError, convert_quotation, create_quotation, create_sale, save_customer, set_quote_status
from ..validators import validate_choice, validate_int, validate_text

bp = Blueprint("commerce", __name__)


def _branch_for_sale():
    user = session["user"]
    if user["role"] == "admin":
        return None
    return user["branch_id"]


def _selected(form):
    ids = form.getlist("product_id")
    qtys = form.getlist("quantity")
    if not ids:
        return [{"product_id": "", "quantity": "1"}]
    return [
        {"product_id": product_id, "quantity": quantity or "1"}
        for product_id, quantity in zip(ids, qtys)
        if str(product_id).strip() or str(quantity).strip()
    ] or [{"product_id": "", "quantity": "1"}]


@bp.get("/customers")
@login_required
def customer_list():
    search = request.args.get("q", "").strip()
    return render_template("customers/list.html", rows=customers(search), search=search)


@bp.route("/customers/new", methods=["GET", "POST"])
@login_required
def customer_new():
    return _customer_editor()


@bp.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def customer_edit(customer_id):
    row = customer(customer_id)
    if not row:
        abort(404)
    return _customer_editor(row)


def _customer_editor(row=None):
    errors = {}
    data = {
        "full_name": row["full_name"] if row else "",
        "email": row["email"] if row else "",
        "phone": row["phone"] if row else "",
        "address": row["address"] if row else "",
    }
    if request.method == "POST":
        data, errors = customer_form(request.form)
        if not errors:
            try:
                save_customer(data, row["id"] if row else None)
            except AppError as exc:
                errors["email"] = str(exc)
            else:
                flash("Customer saved.", "success")
                return redirect(url_for("commerce.customer_list"))
    return render_template("customers/form.html", data=data, errors=errors, editing=row is not None)


@bp.get("/quotations")
@login_required
def quotation_list():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    if status not in dict(Config.QUOTE_STATUSES):
        status = ""
    rows = quotations(search, status)
    return render_template(
        "quotes/list.html",
        rows=rows,
        search=search,
        status=status,
        statuses=Config.QUOTE_STATUSES,
    )


@bp.route("/quotations/new", methods=["GET", "POST"])
@login_required
def quotation_new():
    return _document("quote")


@bp.get("/quotations/<int:quote_id>")
@login_required
def quotation_detail(quote_id):
    header, items = quotation(quote_id)
    if not header:
        abort(404)
    return render_template(
        "quotes/detail.html",
        quote=header,
        items=items,
        payment_methods=Config.PAYMENT_METHODS,
    )


@bp.post("/quotations/<int:quote_id>/status")
@login_required
def quotation_status(quote_id):
    status, error = validate_choice(request.form.get("status", ""), {"sent", "accepted", "rejected"}, "status")
    if error:
        flash(error, "error")
    else:
        try:
            set_quote_status(quote_id, status)
        except AppError as exc:
            flash(str(exc), "error")
        else:
            flash("Quotation updated.", "success")
    return redirect(url_for("commerce.quotation_detail", quote_id=quote_id))


@bp.post("/quotations/<int:quote_id>/convert")
@login_required
def quotation_convert(quote_id):
    method, error = validate_choice(
        request.form.get("payment_method", ""),
        {key for key, _label in Config.PAYMENT_METHODS},
        "payment method",
    )
    if error:
        flash(error, "error")
        return redirect(url_for("commerce.quotation_detail", quote_id=quote_id))
    try:
        sale_id = convert_quotation(session["user"]["id"], quote_id, method)
    except AppError as exc:
        flash(str(exc), "error")
        return redirect(url_for("commerce.quotation_detail", quote_id=quote_id))
    flash("Quotation sold and stock updated.", "success")
    return redirect(url_for("commerce.sale_detail", sale_id=sale_id))


@bp.get("/sales")
@login_required
def sale_list():
    search = request.args.get("q", "").strip()
    branch_id = request.args.get("branch_id", "")
    branch_filter = int(branch_id) if branch_id.isdigit() else None
    rows = sales(search, branch_filter)
    return render_template(
        "sales/list.html",
        rows=rows,
        search=search,
        branch_id=branch_filter,
        branches=branches(),
        payment_labels=dict(Config.PAYMENT_METHODS),
    )


@bp.route("/sales/new", methods=["GET", "POST"])
@login_required
def sale_new():
    return _document("sale")


@bp.get("/sales/<int:sale_id>")
@login_required
def sale_detail(sale_id):
    header, items = sale(sale_id)
    if not header:
        abort(404)
    return render_template("sales/detail.html", sale=header, items=items)


def _document(mode):
    user = session["user"]
    branch_rows = branches()
    customer_rows = customers()
    items = catalog()
    errors = []
    selected = [{"product_id": "", "quantity": "1"}]
    form = {
        "customer_id": request.form.get("customer_id", ""),
        "branch_id": request.form.get("branch_id", ""),
        "notes": request.form.get("notes", ""),
        "payment_method": request.form.get("payment_method", "cash"),
    }
    if user["role"] != "admin":
        form["branch_id"] = str(user["branch_id"] or "")
    elif request.method == "GET" and not form["branch_id"] and branch_rows:
        form["branch_id"] = str(branch_rows[0]["id"])

    if request.method == "POST":
        selected = _selected(request.form)
        lines, _posted, line_errors = parse_lines(request.form)
        errors.extend(line_errors)
        customer_id, customer_error = validate_int(form["customer_id"], "Customer", minimum=1, maximum=10**9)
        if customer_error:
            errors.append(customer_error)
        if user["role"] == "admin":
            branch_id, branch_error = validate_int(form["branch_id"], "Branch", minimum=1, maximum=10**9)
            if branch_error:
                errors.append(branch_error)
        else:
            branch_id = user["branch_id"]
            if not branch_id:
                errors.append("Your account is not assigned to a branch.")
        notes, note_error = validate_text(form["notes"], "Notes", maximum=255)
        if note_error:
            errors.append(note_error)
        method = form["payment_method"]
        if mode == "sale":
            method, method_error = validate_choice(
                method, {key for key, _label in Config.PAYMENT_METHODS}, "payment method"
            )
            if method_error:
                errors.append(method_error)
        if not errors:
            try:
                if mode == "quote":
                    record_id = create_quotation(user["id"], customer_id, branch_id, notes, lines)
                else:
                    record_id = create_sale(user["id"], customer_id, branch_id, method, lines)
            except AppError as exc:
                errors.append(str(exc))
            else:
                if mode == "quote":
                    flash("Quotation saved.", "success")
                    return redirect(url_for("commerce.quotation_detail", quote_id=record_id))
                flash("Sale recorded and stock updated.", "success")
                return redirect(url_for("commerce.sale_detail", sale_id=record_id))
    return render_template(
        "commerce/document_form.html",
        mode=mode,
        form=form,
        errors=errors,
        selected=selected,
        customers=customer_rows,
        branches=branch_rows,
        catalog=items,
        locked_branch=user["role"] != "admin",
        payment_methods=Config.PAYMENT_METHODS,
    )
