from functools import wraps

from flask import redirect, render_template, request, session, url_for


def safe_next(target):
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    return target


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login", next=request.path))
        if session["user"].get("role") != "admin":
            return (
                render_template(
                    "error.html",
                    code=403,
                    title="Administrators only",
                    message="This part of the system is reserved for the administrator.",
                ),
                403,
            )
        return view(*args, **kwargs)

    return wrapped


def session_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
        "branch_id": row["branch_id"],
        "branch_name": row.get("branch_name") or "All branches",
    }
