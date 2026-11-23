# Udyogini

*From your home to every doorstep.*

Udyogini is a mobile-friendly business companion for homemakers who sell homemade products door-to-door. It brings customer details, product stock, orders, payments, visits, and basic business summaries into one simple app.

## Project overview

Many small home businesses keep customer details and orders in memory or on paper. This can make it hard to remember who ordered, which neighbourhood to visit, what has been paid, and when to follow up.

Udyogini provides a lightweight digital notebook to help sellers keep those everyday details organised and make informed business decisions.

## Features

| Module | What it does |
| --- | --- |
| Overview | Shows delivered sales, payments received, balances due, follow-ups, recent orders, monthly sales, and popular products. |
| Customers | Stores customer contact details and notes, filters customers by locality, and lets sellers edit records. |
| Products | Tracks product prices, costs, stock, stock adjustments, and low-stock reminders. |
| Orders and payments | Records orders against available stock, tracks delivery status and partial payments, and keeps payment history. |
| Visits and follow-ups | Logs visit outcomes, schedules another visit, and lets sellers mark follow-ups complete. |
| Income and expenses | Records business expenses and estimates profit from delivered sales minus product costs and operating expenses. Ingredient costs are included in product costs to avoid counting them twice. |
| Reports and catalogue | Downloads order reports and a customer-facing product catalogue as CSV files. |

## Sample data

Accounts receive eight clearly marked fictional customers, sample products, orders, visits, and expenses. This gives a new user something to explore before entering their own information. Sample records can be removed from the Customers page; records already used in a real order or visit are kept.

## Technology

- Python
- Streamlit
- SQLite

## Project structure

```text
Udyogini/
├── app.py                    # Streamlit interface and application flow
├── requirements.txt          # Python dependencies
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml            # Warm, traditional-meets-modern theme
└── database/
    ├── __init__.py
    └── db.py                  # Database, authentication, and business logic
```

The SQLite database is created automatically at `database/udyogini.db` the first time the app runs. It is excluded from Git.

## Run locally on Windows

1. Install Python 3.10 or newer.
2. Open PowerShell in the project folder.
3. Install dependencies and start the app:

   ```powershell
   py -3 -m pip install -r requirements.txt
   py -3 -m streamlit run app.py
   ```

4. Open the local address printed by Streamlit, usually `http://localhost:8501`.
5. Select **Create account**. Choose a username and a password with at least 12 characters, then sign in.

## Publish a showcase app

The project can be deployed from GitHub using [Streamlit Community Cloud](https://share.streamlit.io/).

1. Push the project files to a GitHub repository. Do not upload `database/udyogini.db` or any secrets.
2. Sign in to Streamlit Community Cloud with the GitHub account that owns the repository.
3. Select **Create app**, then choose the repository, the `main` branch, and `app.py` as the app file.
4. Deploy the app and share its `*.streamlit.app` URL.

The app includes a custom local account system so a teacher can create an account and explore its sample records. Community Cloud does not guarantee persistence of files stored on the app's local filesystem, so treat this deployment as a showcase only.

## Security and privacy

- Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes; the app does not store readable passwords.
- Repeated unsuccessful sign-in attempts trigger a temporary lockout.
- Database queries use SQL parameters and scope business records to the signed-in account.
- The local SQLite file is excluded from Git to keep customer and business data out of the repository.
- This is a college project prototype, not a production service. Do not enter real customer or financial information in a public deployment. A real production release would need managed authentication, HTTPS, durable protected storage, backups, and additional security review.
