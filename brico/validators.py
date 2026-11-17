import re
from decimal import Decimal, InvalidOperation

from .config import Config

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,29}$")
PERSON_NAME_RE = re.compile(r"^[^\W\d_]+(?: [^\W\d_]+)*$", re.UNICODE)
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,29}$")
BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '&-]{1,79}$")
BRANCH_CODE_RE = re.compile(r"^[A-Z]{2,10}$")


def clean(value):
    return "" if value is None else str(value).strip()


def collapse(value):
    return re.sub(r"\s+", " ", clean(value))


def validate_email(value):
    value = clean(value).lower()
    if not value:
        return None, "Email is required."
    if any(ch.isspace() for ch in value):
        return None, "Email cannot contain spaces."
    if len(value) > 120 or not EMAIL_RE.fullmatch(value):
        return None, "Enter a valid email address, such as name@company.com."
    return value, None


def validate_phone(value):
    raw = clean(value)
    if not raw:
        return None, "Phone number is required."
    if re.search(r"[A-Za-z]", raw):
        return None, "Phone number cannot contain letters."
    compact = re.sub(r"[\s\-().]", "", raw)
    if not re.fullmatch(r"\+?[0-9]{10,15}", compact):
        return None, "Phone number must contain 10 to 15 digits. A leading + is allowed."
    return compact, None


def validate_username(value):
    value = clean(value)
    if not value:
        return None, "Username is required."
    if any(ch.isspace() for ch in value):
        return None, "Username cannot contain spaces."
    if value[0].isdigit():
        return None, "Username cannot start with a number."
    if not value[0].isalpha():
        return None, "Username cannot start with a special character."
    if not USERNAME_RE.fullmatch(value):
        return None, "Username can contain only letters, numbers, and underscores."
    return value, None


def validate_person_name(value, label="Name"):
    value = collapse(value)
    if not value:
        return None, f"{label} is required."
    if len(value) < 2:
        return None, f"{label} must be at least 2 characters."
    if len(value) > 80:
        return None, f"{label} must be 80 characters or fewer."
    if re.search(r"\d", value):
        return None, f"{label} cannot contain numbers."
    if not PERSON_NAME_RE.fullmatch(value):
        return None, f"{label} cannot contain special characters."
    return value, None


def validate_password(value):
    if value is None or value == "":
        return "Password is required."
    if len(value) < Config.MIN_PASSWORD:
        return f"Password must not be less than {Config.MIN_PASSWORD} characters."
    if len(value) > 128:
        return "Password must be 128 characters or fewer."
    return None


def validate_sku(value):
    value = clean(value).upper()
    if not value:
        return None, "SKU is required."
    if any(ch.isspace() for ch in value):
        return None, "SKU cannot contain spaces."
    if not value[0].isalnum():
        return None, "SKU cannot start with a special character."
    if not SKU_RE.fullmatch(value):
        return None, "SKU can contain only letters, numbers, and hyphens."
    return value, None


def validate_product_name(value):
    value = collapse(value)
    if len(value) < 2:
        return None, "Enter the product name."
    if len(value) > 120:
        return None, "Product name must be 120 characters or fewer."
    if re.search(r"[\x00-\x1f]", value):
        return None, "Product name contains an invalid character."
    return value, None


def validate_price(value):
    raw = clean(value)
    if not raw:
        return None, "Price is required."
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None, "Enter a valid price."
    if amount.as_tuple().exponent < -2:
        return None, "Price can have at most two decimal places."
    if amount <= 0 or amount >= Decimal("1000000"):
        return None, "Price must be greater than 0 and less than 1,000,000."
    return amount.quantize(Decimal("0.01")), None


def validate_int(value, label, minimum=0, maximum=100000):
    raw = clean(value)
    if raw == "":
        return None, f"{label} is required."
    if not re.fullmatch(r"-?\d+", raw):
        return None, f"{label} must be a whole number."
    number = int(raw)
    if number < minimum or number > maximum:
        return None, f"{label} must be between {minimum} and {maximum}."
    return number, None


def validate_choice(value, allowed, label):
    if value not in allowed:
        return None, f"Choose a valid {label}."
    return value, None


def validate_text(value, label, minimum=0, maximum=255, required=False):
    value = collapse(value)
    if not value and required:
        return None, f"{label} is required."
    if not value:
        return "", None
    if len(value) < minimum:
        return None, f"{label} must be at least {minimum} characters."
    if len(value) > maximum:
        return None, f"{label} must be {maximum} characters or fewer."
    return value, None


def validate_branch_name(value):
    value = collapse(value)
    if not BRANCH_NAME_RE.fullmatch(value or ""):
        return None, "Branch name must be 2 to 80 characters and can use letters, numbers, spaces, apostrophes, and hyphens."
    return value, None


def validate_branch_code(value):
    value = clean(value).upper()
    if not BRANCH_CODE_RE.fullmatch(value or ""):
        return None, "Branch code must be 2 to 10 letters."
    return value, None
