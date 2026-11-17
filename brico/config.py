import os


class Config:
    """Local settings for the Brico NB inventory system.

    The default MySQL account matches a standard XAMPP install:
    user "root" with an empty password on port 3306.
    """

    SECRET_KEY = os.environ.get("SECRET_KEY", "brico-nb-local-dev-key")
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
    MYSQL_USER = os.environ.get("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DB = os.environ.get("MYSQL_DB", "brico_nb")

    # Issued with the system. Registration and password changes use a longer password.
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin"
    MIN_PASSWORD = 6

    CATEGORIES = (
        "Hand Tools",
        "Power Tools",
        "Plumbing",
        "Electrical",
        "Paint",
        "Fasteners",
        "Building Materials",
        "Safety",
    )

    PAYMENT_METHODS = (
        ("cash", "Cash"),
        ("card", "Card"),
        ("transfer", "Bank transfer"),
    )

    QUOTE_STATUSES = (
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("converted", "Converted"),
    )

    MOVEMENT_LABELS = {
        "receive": "Goods received",
        "sale": "Sale",
        "adjustment": "Adjustment",
        "transfer_in": "Transfer in",
        "transfer_out": "Transfer out",
    }
