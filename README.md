# Brico NB Ltd — inventory and sales

Python and MySQL web app for products, branch stock, quotations, sales, and reports.

## Run

1. Start MySQL. With XAMPP, start the MySQL module. The default account is `root` with an empty password.
2. From this folder:

```
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

3. Open http://127.0.0.1:5000

The first launch creates the `brico_nb` database, the tables, three branches, a starter catalogue, and the administrator.

If MySQL uses a different user or password, change `brico/config.py`.

## Sign in

Administrator, preloaded:

- username: `admin`
- password: `admin`

Sales staff use Register. A new password must not be less than 6 characters. The preloaded administrator password is the issued exception.

## Record rules

- Email must be a valid address.
- Phone numbers must contain 10 to 15 digits. A leading `+` is allowed.
- A username cannot contain spaces and cannot start with a number or a special character.
- A person’s name can contain only letters and spaces.
