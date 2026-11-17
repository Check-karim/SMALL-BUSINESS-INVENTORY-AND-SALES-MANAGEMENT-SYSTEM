from flask import Blueprint, render_template

from ..db import init_db
from ..queries import branches, public_stats

bp = Blueprint("public", __name__)


@bp.get("/")
def home():
    stats = None
    branch_rows = []
    try:
        init_db()
        stats = public_stats()
        branch_rows = branches()
    except Exception:
        stats = None
    return render_template("home.html", stats=stats, branches=branch_rows)


@bp.get("/about")
def about():
    branch_rows = []
    try:
        init_db()
        branch_rows = branches()
    except Exception:
        branch_rows = []
    return render_template("about.html", branches=branch_rows)
