from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..forms import branch_form
from ..queries import branch, branches, dashboard, report, team
from ..security import admin_required, login_required
from ..services import AppError, create_branch, update_branch

bp = Blueprint("manage", __name__)


@bp.get("/dashboard")
@login_required
def dashboard_page():
    return render_template("dashboard.html", snap=dashboard())


@bp.get("/reports")
@admin_required
def reports():
    today = date.today()
    default_start = today.replace(day=1)
    start = _parse_date(request.args.get("start"), default_start)
    end = _parse_date(request.args.get("end"), today)
    error = None
    if start > end:
        error = "The start date must be on or before the end date."
        start, end = default_start, today
    data = report(start, end)
    count = int(data["summary"]["sales_count"] or 0)
    revenue = data["summary"]["revenue"] or 0
    average = (revenue / count) if count else 0
    return render_template(
        "reports.html",
        data=data,
        start=start.isoformat(),
        end=end.isoformat(),
        average=average,
        error=error,
    )


@bp.get("/branches")
@admin_required
def branch_list():
    return render_template("branches/list.html", rows=branches())


@bp.route("/branches/new", methods=["GET", "POST"])
@admin_required
def branch_new():
    return _branch_editor()


@bp.route("/branches/<int:branch_id>/edit", methods=["GET", "POST"])
@admin_required
def branch_edit(branch_id):
    row = branch(branch_id)
    if not row:
        abort(404)
    return _branch_editor(row)


def _branch_editor(row=None):
    errors = {}
    data = {
        "code": row["code"] if row else "",
        "name": row["name"] if row else "",
        "address": row["address"] if row else "",
        "phone": row["phone"] if row else "",
    }
    if request.method == "POST":
        data, errors = branch_form(request.form)
        if not errors:
            try:
                if row:
                    update_branch(row["id"], data)
                else:
                    create_branch(data)
            except AppError as exc:
                errors["form"] = str(exc)
            else:
                flash("Branch saved.", "success")
                return redirect(url_for("manage.branch_list"))
    return render_template("branches/form.html", data=data, errors=errors, editing=row is not None)


@bp.get("/team")
@admin_required
def team_page():
    return render_template("team.html", rows=team())


def _parse_date(value, fallback):
    try:
        return datetime.strptime(value or "", "%Y-%m-%d").date()
    except ValueError:
        return fallback
