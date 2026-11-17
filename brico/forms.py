from .config import Config
from .validators import (
    validate_branch_code,
    validate_branch_name,
    validate_choice,
    validate_email,
    validate_int,
    validate_person_name,
    validate_phone,
    validate_price,
    validate_product_name,
    validate_sku,
    validate_text,
)


def parse_lines(form):
    ids = form.getlist("product_id")
    qtys = form.getlist("quantity")
    if len(ids) != len(qtys):
        return [], [], ["The product lines could not be read. Try again."]
    lines = []
    selected = []
    errors = []
    for index, (product_id, quantity) in enumerate(zip(ids, qtys), start=1):
        if not str(product_id).strip() and not str(quantity).strip():
            continue
        selected.append({"product_id": product_id, "quantity": quantity or "1"})
        parsed_id, id_error = validate_int(product_id, "Product", minimum=1, maximum=10**9)
        parsed_qty, qty_error = validate_int(quantity, "Quantity", minimum=1, maximum=10000)
        if id_error or qty_error:
            errors.append(f"Line {index}: {id_error or qty_error}")
        else:
            lines.append({"product_id": parsed_id, "quantity": parsed_qty})
    if not errors and not lines:
        errors.append("Add at least one product.")
    return lines, selected, errors


def product_form(form, branches):
    errors = {}
    sku, sku_error = validate_sku(form.get("sku", ""))
    name, name_error = validate_product_name(form.get("name", ""))
    category, category_error = validate_choice(form.get("category", ""), set(Config.CATEGORIES), "category")
    description, description_error = validate_text(form.get("description", ""), "Description", maximum=500)
    price, price_error = validate_price(form.get("unit_price", ""))
    reorder, reorder_error = validate_int(form.get("reorder_level", ""), "Reorder level", minimum=0, maximum=100000)
    for key, message in {
        "sku": sku_error,
        "name": name_error,
        "category": category_error,
        "description": description_error,
        "unit_price": price_error,
        "reorder_level": reorder_error,
    }.items():
        if message:
            errors[key] = message
    opening = []
    for branch in branches:
        raw = form.get(f"stock_{branch['id']}", "0")
        qty, qty_error = validate_int(raw, f"Stock at {branch['name']}", minimum=0, maximum=100000)
        if qty_error:
            errors[f"stock_{branch['id']}"] = qty_error
        elif not errors:
            opening.append((branch["id"], qty))
    data = {
        "sku": sku or form.get("sku", ""),
        "name": name or form.get("name", ""),
        "category": category or form.get("category", ""),
        "description": description if description is not None else form.get("description", ""),
        "unit_price": price if price is not None else form.get("unit_price", ""),
        "reorder_level": reorder if reorder is not None else form.get("reorder_level", ""),
    }
    return data, opening, errors


def branch_form(form):
    errors = {}
    code, code_error = validate_branch_code(form.get("code", ""))
    name, name_error = validate_branch_name(form.get("name", ""))
    address, address_error = validate_text(form.get("address", ""), "Address", minimum=4, maximum=160, required=True)
    phone, phone_error = validate_phone(form.get("phone", ""))
    for key, message in {
        "code": code_error,
        "name": name_error,
        "address": address_error,
        "phone": phone_error,
    }.items():
        if message:
            errors[key] = message
    data = {
        "code": code or form.get("code", ""),
        "name": name or form.get("name", ""),
        "address": address if address is not None else form.get("address", ""),
        "phone": phone or form.get("phone", ""),
    }
    return data, errors


def customer_form(form):
    errors = {}
    name, name_error = validate_person_name(form.get("full_name", ""), "Name")
    email, email_error = validate_email(form.get("email", ""))
    phone, phone_error = validate_phone(form.get("phone", ""))
    address, address_error = validate_text(form.get("address", ""), "Address", maximum=160)
    for key, message in {
        "full_name": name_error,
        "email": email_error,
        "phone": phone_error,
        "address": address_error,
    }.items():
        if message:
            errors[key] = message
    data = {
        "full_name": name or form.get("full_name", ""),
        "email": email or form.get("email", ""),
        "phone": phone or form.get("phone", ""),
        "address": address if address is not None else form.get("address", ""),
    }
    return data, errors
