# Udyogini

Udyogini is a mobile-friendly business companion for homemakers who sell homemade products door-to-door. It helps keep customer details by locality, plan visits, manage products and stock, track orders and partial payments, and understand business income and expenses.

## Run on Windows

Open PowerShell in the `F:\Udyogini` folder and run:

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run app.py
```

Open the local address Streamlit prints, usually `http://localhost:8501`. Create a username and a passphrase of at least 12 characters. The app creates a local SQLite database automatically.

## Run in Replit

1. Create a Python Replit project and add the files and folders from this project.
2. Replit installs the package from `requirements.txt`. If it does not, run `pip install -r requirements.txt` in the Shell.
3. Set the run command to `streamlit run app.py --server.address 0.0.0.0 --server.port 3000`.
4. Press Run and open the web preview.

## Modules

- **Overview:** sales, collections, outstanding balances, follow-ups, recent orders, monthly sales and best sellers.
- **Customers:** customer book, locality filtering, visit notes and editing.
- **Products:** product catalogue, costs, prices, stock adjustments, low-stock prompts and product editing.
- **Orders & payments:** orders against available stock, delivery status, partial payments and payment history.
- **Visits & follow-ups:** visit outcomes, planned return dates and a button to mark follow-ups done.
- **Income & expenses:** expense log and an estimated profit summary.
- **Reports & catalogue:** downloadable CSV files for orders and products.

Accounts without starter records receive eight clearly labelled fictional customers plus sample products, orders, visits and expenses at sign-in. The sample rows are marked in the interface. From the customer page, you can remove the sample set; that action leaves your own records in place.

## Data and security

- Business data lives locally in `database/udyogini.db` and is excluded from Git.
- Passwords are saved as salted PBKDF2-HMAC-SHA256 hashes. Repeated failed sign-ins trigger a temporary lockout.
- SQL queries use parameters, and business record queries include the signed-in account ID.
- This is a local learning project with a custom password sign-in flow. Do not expose it to the public internet with real customer or financial data. A public release needs managed OIDC sign-in, HTTPS, protected database backups, and deployment security controls.
