import secrets

import pymysql
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..config import Config
from ..db import execute, query_one
from ..queries import branches
from ..security import login_required, safe_next, session_user
from ..validators import validate_email, validate_password, validate_person_name, validate_phone, validate_username

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("manage.dashboard_page"))
    errors = {}
    form = {"username": request.form.get("username", "")}
    if request.method == "POST":
        username = form["username"].strip()
        password = request.form.get("password", "")
        if not username or not password:
            errors["form"] = "Enter your username and password."
        else:
            row = query_one(
                """
                SELECT u.*, b.name AS branch_name
                FROM users u
                LEFT JOIN branches b ON b.id = u.branch_id
                WHERE u.username = %s
                """,
                (username,),
            )
            if not row or not check_password_hash(row["password_hash"], password):
                errors["form"] = "Those credentials do not match."
            else:
                session.clear()
                session["user"] = session_user(row)
                session["csrf_token"] = secrets.token_hex(32)
                session.permanent = True
                nxt = safe_next(request.args.get("next"))
                return redirect(nxt or url_for("manage.dashboard_page"))
    return render_template("login.html", form=form, errors=errors)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user"):
        return redirect(url_for("manage.dashboard_page"))
    branch_rows = branches()
    errors = {}
    form = {
        "full_name": request.form.get("full_name", ""),
        "username": request.form.get("username", ""),
        "email": request.form.get("email", ""),
        "phone": request.form.get("phone", ""),
        "branch_id": request.form.get("branch_id", ""),
    }
    if request.method == "POST":
        full_name, name_error = validate_person_name(form["full_name"], "Name")
        username, user_error = validate_username(form["username"])
        email, email_error = validate_email(form["email"])
        phone, phone_error = validate_phone(form["phone"])
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        password_error = validate_password(password)
        if password_error is None and password != confirm:
            password_error = "Password and confirmation do not match."
        branch_id = None
        branch_error = None
        if not form["branch_id"].isdigit() or not any(str(row["id"]) == form["branch_id"] for row in branch_rows):
            branch_error = "Choose the branch you sell from."
        else:
            branch_id = int(form["branch_id"])
        if username and username.lower() == Config.ADMIN_USERNAME:
            user_error = "This username is reserved for the administrator."
        errors = {
            key: value
            for key, value in {
                "full_name": name_error,
                "username": user_error,
                "email": email_error,
                "phone": phone_error,
                "password": password_error,
                "branch_id": branch_error,
            }.items()
            if value
        }
        if not errors:
            try:
                execute(
                    """
                    INSERT INTO users (username, password_hash, full_name, email, phone, role, branch_id)
                    VALUES (%s, %s, %s, %s, %s, 'staff', %s)
                    """,
                    (
                        username,
                        generate_password_hash(password, method="pbkdf2:sha256"),
                        full_name,
                        email,
                        phone,
                        branch_id,
                    ),
                )
            except pymysql.err.IntegrityError as exc:
                message = str(exc).lower()
                if "username" in message:
                    errors["username"] = "That username is already taken."
                elif "email" in message:
                    errors["email"] = "That email is already registered."
                else:
                    errors["form"] = "The account could not be created."
            else:
                flash("Account created. You can sign in.", "success")
                return redirect(url_for("auth.login"))
        form["full_name"] = full_name or form["full_name"]
        form["username"] = username or form["username"]
        form["email"] = email or form["email"]
        form["phone"] = phone or form["phone"]
    return render_template("register.html", form=form, errors=errors, branches=branch_rows)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have signed out.", "info")
    return redirect(url_for("public.home"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    errors = {}
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm", "")
        row = query_one("SELECT password_hash FROM users WHERE id=%s", (session["user"]["id"],))
        if not row or not check_password_hash(row["password_hash"], current):
            errors["current_password"] = "The current password does not match."
        password_error = validate_password(new_password)
        if password_error:
            errors["new_password"] = password_error
        elif new_password != confirm:
            errors["confirm"] = "Password and confirmation do not match."
        if not errors:
            execute(
                "UPDATE users SET password_hash=%s WHERE id=%s",
                (
                    generate_password_hash(new_password, method="pbkdf2:sha256"),
                    session["user"]["id"],
                ),
            )
            flash("Password updated.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("profile.html", errors=errors)
