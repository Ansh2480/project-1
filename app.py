from datetime import date

import streamlit as st

from database.db import (
    add_customer,
    add_expense,
    add_order,
    add_product,
    add_visit,
    authenticate,
    change_stock,
    clear_sample_data,
    complete_follow_up,
    create_user,
    ensure_samples_seeded,
    get_customers,
    get_expenses,
    get_best_sellers,
    get_monthly_sales,
    get_orders,
    get_payment_history,
    get_products,
    get_summary,
    get_visits,
    init_db,
    record_payment,
    update_order_status,
    update_customer,
    update_product,
)


st.set_page_config(
    page_title="Udyogini | Your business companion",
    page_icon=":material/local_florist:",
    layout="wide",
    initial_sidebar_state="expanded",
)
init_db()


def money(amount: float) -> str:
    return f"₹{amount:,.2f}"


def show_auth() -> None:
    st.space("large")
    left, center, right = st.columns([1, 1.15, 1])
    with center:
        st.title("Udyogini", text_alignment="center")
        st.caption("Your home business, beautifully organised", text_alignment="center")
        mode = st.segmented_control(
            "Choose an account action",
            ["Sign in", "Create account"],
            default="Sign in",
            label_visibility="collapsed",
            width="stretch",
            key="auth_mode",
        )
        if mode == "Create account":
            with st.form("signup_form"):
                username = st.text_input("Username", max_chars=32)
                password = st.text_input("Passphrase · 12 characters or more", type="password", max_chars=128)
                confirm = st.text_input("Confirm passphrase", type="password", max_chars=128)
                submitted = st.form_submit_button("Create my account", width="stretch")
            if submitted:
                if password != confirm:
                    st.error("Those passphrases do not match.")
                else:
                    ok, message = create_user(username, password)
                    if ok:
                        st.success(message)
                        st.caption("Eight fictional customers and sample business records are ready to explore.")
                    else:
                        st.error(message)
        else:
            with st.form("login_form"):
                username = st.text_input("Username", max_chars=32)
                password = st.text_input("Passphrase", type="password", max_chars=128)
                submitted = st.form_submit_button("Sign in", width="stretch")
            if submitted:
                user, message = authenticate(username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                st.error(message)
        st.caption("A private notebook for customers, orders, follow-ups and earnings.", text_alignment="center")


def show_overview(user_id: int) -> None:
    summary = get_summary(user_id)
    orders = get_orders(user_id)
    visits = get_visits(user_id)
    st.title("Namaste! Here’s your business at a glance", icon=":material/waving_hand:")
    st.caption("A clear view of today’s work, payments and people to visit.")
    top = st.container(border=True)
    with top:
        a, b, c, d = st.columns(4)
        a.metric("Sales on the books", money(summary["sales"]))
        b.metric("Payments received", money(summary["paid"]))
        c.metric("Still to collect", money(summary["due"]))
        d.metric("Follow-ups due", summary["follow_ups_due"])

    sample_count = sum(1 for item in get_customers(user_id) if item["is_sample"])
    if sample_count:
        st.info("You’re viewing fictional sample records. Add your own customers and products alongside them.", icon=":material/lightbulb:")

    left, right = st.columns([1.3, 1], gap="large")
    with left:
        st.subheader("Orders to keep moving", icon=":material/receipt_long:")
        active = [o for o in orders if o["status"] != "Delivered"][:6]
        if active:
            st.dataframe(
                [{"Customer": o["customer"], "Area": o["area"], "Order": o["item"],
                  "Balance": money(max(0, o["balance"])), "Status": o["status"]} for o in active],
                hide_index=True, alt="Recent active customer orders",
            )
        else:
            st.success("No open orders. You’re all caught up!")
    with right:
        st.subheader("Next visits", icon=":material/directions_walk:")
        upcoming = sorted(
            [v for v in visits if v["follow_up_date"] and not v["follow_up_done"]],
            key=lambda v: v["follow_up_date"],
        )[:5]
        if upcoming:
            for visit in upcoming:
                st.markdown(f"**{visit['customer']}** · {visit['area']}  \nFollow up: {visit['follow_up_date']} · {visit['outcome']}")
        else:
            st.caption("Your planned follow-ups will appear here.")

    st.subheader("At a glance", icon=":material/auto_graph:")
    x, y, z = st.columns(3)
    x.metric("Customers", len(get_customers(user_id)))
    y.metric("Products in your list", len(get_products(user_id)))
    z.metric("Estimated net profit", money(summary["net_profit"]))

    monthly = get_monthly_sales(user_id)
    best_sellers = get_best_sellers(user_id)
    chart_left, chart_right = st.columns(2, gap="large")
    with chart_left:
        st.subheader("Sales by month", icon=":material/bar_chart:")
        if monthly:
            st.bar_chart(
                {"Month": [row["month"] for row in monthly],
                 "Sales (₹)": [row["sales"] for row in monthly]},
                x="Month", y="Sales (₹)", alt="Order value by month",
            )
        else:
            st.caption("Your sales chart will grow as you add orders.")
    with chart_right:
        st.subheader("Popular products", icon=":material/trending_up:")
        if best_sellers:
            st.bar_chart(
                {"Product": [row["item"] for row in best_sellers],
                 "Quantity sold": [row["quantity"] for row in best_sellers]},
                x="Product", y="Quantity sold", horizontal=True,
                alt="Most ordered products by quantity",
            )
        else:
            st.caption("Your best sellers will appear as you record orders.")


def show_customers(user_id: int) -> None:
    st.title("Your customer book", icon=":material/groups:")
    st.caption("Keep names, areas and useful notes together, then plan a round by locality.")
    customers = get_customers(user_id)
    with st.expander("Add a customer", icon=":material/person_add:", expanded=not customers):
        with st.form("customer_form", clear_on_submit=True):
            name = st.text_input("Customer name *", max_chars=80)
            phone = st.text_input("Phone number (optional)", max_chars=20)
            area = st.text_input("Locality / area *", max_chars=80)
            address = st.text_input("House or address (optional)", max_chars=160)
            notes = st.text_area("Helpful notes (optional)", max_chars=500, height=90)
            submitted = st.form_submit_button("Save customer", width="stretch")
        if submitted:
            if not name.strip() or not area.strip():
                st.error("Add a name and locality to save this customer.")
            else:
                try:
                    add_customer(user_id, name, phone, area, address, notes)
                    st.success("Customer saved.")
                    st.rerun()
                except Exception:
                    st.error("Could not save the customer. Try a different name or phone number.")

    customers = get_customers(user_id)
    if not customers:
        st.info("Your customer book is empty. Add your first customer above.")
        return
    area_list = sorted({c["area"] for c in customers})
    selected_area = st.selectbox("Show customers in", ["All localities"] + area_list)
    visible = customers if selected_area == "All localities" else [c for c in customers if c["area"] == selected_area]
    st.markdown(f"**{len(visible)} neighbours** · {selected_area}")
    st.dataframe(
        [{"Name": c["name"] + (" · sample" if c["is_sample"] else ""), "Phone": c["phone"],
          "Locality": c["area"], "Address": c["address"], "Notes": c["notes"]} for c in visible],
        hide_index=True, alt="Customer contact book grouped by locality",
    )
    with st.expander("Edit a customer", icon=":material/edit:"):
        edit_options = {f"{c['name']} · {c['area']}": c for c in customers}
        edit_label = st.selectbox("Choose a customer to edit", list(edit_options), key="edit_customer_choice")
        chosen = edit_options[edit_label]
        with st.form(f"edit_customer_form_{chosen['id']}"):
            edited_name = st.text_input("Name", value=chosen["name"], key=f"edit_name_{chosen['id']}")
            edited_phone = st.text_input("Phone", value=chosen["phone"], key=f"edit_phone_{chosen['id']}")
            edited_area = st.text_input("Locality", value=chosen["area"], key=f"edit_area_{chosen['id']}")
            edited_address = st.text_input("Address", value=chosen["address"], key=f"edit_address_{chosen['id']}")
            edited_notes = st.text_area("Notes", value=chosen["notes"], key=f"edit_notes_{chosen['id']}")
            saved = st.form_submit_button("Save customer changes")
        if saved:
            try:
                update_customer(user_id, chosen["id"], edited_name, edited_phone,
                                edited_area, edited_address, edited_notes)
                st.success("Customer updated.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    if any(c["is_sample"] for c in customers):
        with st.expander("Remove fictional example records", icon=":material/delete_outline:"):
            st.caption("This removes only the starter customers, products, orders, visits and expenses marked as samples.")
            confirmed = st.checkbox("I want to remove the sample records", key="confirm_sample_removal")
            if st.button("Remove sample records", disabled=not confirmed, type="secondary"):
                clear_sample_data(user_id)
                st.success("Sample records removed. Your own records were kept.")
                st.rerun()


def show_products(user_id: int) -> None:
    st.title("Your product shelf", icon=":material/inventory_2:")
    st.caption("Set prices and costs, keep an eye on stock, and use the catalogue when taking orders.")
    products = get_products(user_id)
    with st.expander("Add a product", icon=":material/add_box:", expanded=not products):
        with st.form("product_form", clear_on_submit=True):
            name = st.text_input("Product name *", max_chars=100)
            category = st.text_input("Category", placeholder="Snacks, pickles, crafts…", max_chars=60)
            c1, c2, c3 = st.columns(3)
            price = c1.number_input("Selling price (₹)", min_value=0.0, step=10.0)
            cost = c2.number_input("Your cost (₹)", min_value=0.0, step=10.0)
            stock = c3.number_input("Current stock", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Save product", width="stretch")
        if submitted:
            try:
                add_product(user_id, name, category, price, cost, stock)
                st.success("Product added.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    products = get_products(user_id)
    if not products:
        st.info("Add your first product to build a catalogue and take orders.")
        return
    low_stock = [p for p in products if p["stock"] <= 3]
    if low_stock:
        st.warning("Low stock: " + ", ".join(f"{p['name']} ({p['stock']})" for p in low_stock),
                   icon=":material/inventory:")
    st.dataframe(
        [{"Product": p["name"] + (" · sample" if p["is_sample"] else ""), "Category": p["category"],
          "Price": money(p["price"]), "Cost": money(p["cost"]), "Stock": p["stock"],
          "Margin / item": money(p["price"] - p["cost"])} for p in products],
        hide_index=True, alt="Product catalogue with price, cost, stock and margin",
    )
    st.markdown("### Adjust stock")
    options = {f"{p['name']} · {p['stock']} in stock": p for p in products}
    label = st.selectbox("Choose product", list(options), key="stock_product")
    product = options[label]
    with st.form("stock_form"):
        amount = st.number_input("Add or remove units", value=0.0, step=1.0, help="Use a negative number to record stock used or damaged.")
        submitted = st.form_submit_button("Update stock")
    if submitted:
        try:
            change_stock(user_id, product["id"], amount)
            st.success("Stock updated.")
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    with st.expander("Edit product details", icon=":material/edit:"):
        edit_options = {f"{p['name']} · {p['category']}": p for p in products}
        edit_label = st.selectbox("Choose a product to edit", list(edit_options), key="edit_product_choice")
        chosen = edit_options[edit_label]
        with st.form(f"edit_product_form_{chosen['id']}"):
            name = st.text_input("Product name", value=chosen["name"], key=f"edit_product_name_{chosen['id']}")
            category = st.text_input("Category", value=chosen["category"], key=f"edit_product_category_{chosen['id']}")
            col1, col2 = st.columns(2)
            price = col1.number_input("Selling price (₹)", min_value=0.0, value=float(chosen["price"]), key=f"edit_product_price_{chosen['id']}")
            cost = col2.number_input("Unit cost (₹)", min_value=0.0, value=float(chosen["cost"]), key=f"edit_product_cost_{chosen['id']}")
            saved = st.form_submit_button("Save product changes")
        if saved:
            try:
                update_product(user_id, chosen["id"], name, category, price, cost)
                st.success("Product updated.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))


def show_orders(user_id: int) -> None:
    st.title("Orders & payments", icon=":material/receipt_long:")
    st.caption("Record what was ordered, what has been paid, and what still needs to be delivered.")
    customers = get_customers(user_id)
    products = get_products(user_id)
    if not customers:
        st.info("Add a customer before recording an order.")
        return
    if not products:
        st.info("Add a product before recording an order.")
        return
    with st.expander("Record an order", icon=":material/add_shopping_cart:", expanded=False):
        with st.form("order_form", clear_on_submit=True):
            customer_options = {f"{c['name']} · {c['area']}": c for c in customers}
            customer_label = st.selectbox("Customer", list(customer_options))
            customer = customer_options[customer_label]
            product_options = {f"{p['name']} · {money(p['price'])} · stock {p['stock']}": p for p in products}
            product_label = st.selectbox("Product", list(product_options))
            product = product_options[product_label]
            c1, c2 = st.columns(2)
            quantity = c1.number_input("Quantity", min_value=0.1, value=1.0, step=1.0)
            paid = c2.number_input("Paid now (₹)", min_value=0.0, value=0.0, step=10.0)
            delivery = st.date_input("Promised delivery date", value=date.today())
            method = st.selectbox("Payment method", ["Cash", "UPI", "Bank transfer", "Other"])
            submitted = st.form_submit_button("Save order", width="stretch")
        if submitted:
            try:
                add_order(user_id, customer["id"], product["name"], quantity,
                          product["price"], paid, delivery.isoformat(), product["id"],
                          product["cost"], method)
                st.success("Order saved and stock reserved.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    orders = get_orders(user_id)
    if not orders:
        st.info("Your orders will appear here.")
        return
    st.dataframe(
        [{"#": o["id"], "Customer": o["customer"] + (" · sample" if o["is_sample"] else ""),
          "Area": o["area"], "Product": o["item"], "Qty": o["quantity"],
          "Total": money(o["total"]), "Paid": money(o["amount_paid"]),
          "Balance": money(max(0, o["balance"])), "Status": o["status"],
          "Delivery": o["due_date"]} for o in orders],
        hide_index=True, alt="Order list with customer, delivery status and amount due",
    )
    choices = {f"#{o['id']} · {o['customer']} · {o['item']} · balance {money(max(0, o['balance']))}": o for o in orders}
    st.markdown("### Update order or record a payment")
    selected = choices[st.selectbox("Choose an order", list(choices))]
    col1, col2 = st.columns(2)
    if selected["balance"] > 0:
        with col1:
            with st.form("payment_form"):
                payment = st.number_input("Payment received (₹)", min_value=0.0,
                                          max_value=float(selected["balance"]), step=10.0)
                method = st.selectbox("Received by", ["Cash", "UPI", "Bank transfer", "Other"])
                saved = st.form_submit_button("Save payment", width="stretch")
            if saved:
                if payment <= 0:
                    st.error("Enter an amount greater than zero.")
                else:
                    record_payment(user_id, selected["id"], payment, method)
                    st.success("Payment recorded.")
                    st.rerun()
    with col2:
        with st.form("status_form"):
            statuses = ["Pending", "Preparing", "Ready", "Delivered"]
            status = st.selectbox("Order status", statuses, index=statuses.index(selected["status"]))
            updated = st.form_submit_button("Save status", width="stretch")
        if updated:
            update_order_status(user_id, selected["id"], status)
            st.success("Order status updated.")
            st.rerun()
    history = get_payment_history(user_id)
    st.subheader("Payment history", icon=":material/payments:")
    if history:
        st.dataframe(
            [{"Date": p["paid_at"], "Customer": p["customer"], "Product": p["item"],
              "Amount": money(p["amount"]), "Method": p["method"]} for p in history],
            hide_index=True, alt="History of customer payments received",
        )
    else:
        st.caption("Payments will appear here when you record them.")


def show_visits(user_id: int) -> None:
    st.title("Door-to-door visits", icon=":material/directions_walk:")
    st.caption("Remember who you spoke to and when to stop by again.")
    customers = get_customers(user_id)
    if not customers:
        st.info("Add customers before planning visits.")
        return
    with st.expander("Log a visit or follow-up", icon=":material/event:", expanded=False):
        with st.form("visit_form", clear_on_submit=True):
            customer_options = {f"{c['name']} · {c['area']}": c for c in customers}
            customer_label = st.selectbox("Customer", list(customer_options))
            customer = customer_options[customer_label]
            visit_date = st.date_input("Visit date", value=date.today())
            outcome = st.selectbox("What happened?", ["Interested", "Order placed", "Not home", "Not interested", "Follow up"])
            follow_up = st.date_input("Next visit (optional)", value=None)
            notes = st.text_input("Note (optional)", max_chars=250)
            submitted = st.form_submit_button("Save visit", width="stretch")
        if submitted:
            add_visit(user_id, customer["id"], visit_date.isoformat(), outcome,
                      follow_up.isoformat() if follow_up else "", notes)
            st.success("Visit saved.")
            st.rerun()
    visits = get_visits(user_id)
    if visits:
        due = [v for v in visits if not v["follow_up_done"] and v["follow_up_date"]
               and v["follow_up_date"] <= date.today().isoformat()]
        if due:
            st.warning(f"{len(due)} follow-up(s) are due. Check the list below.", icon=":material/notifications_active:")
            for visit in due:
                c1, c2 = st.columns([3, 1], vertical_alignment="center")
                c1.markdown(f"**{visit['customer']}** · {visit['area']} · due {visit['follow_up_date']}")
                if c2.button("Done", key=f"followup_done_{visit['id']}", icon=":material/check:"):
                    complete_follow_up(user_id, visit["id"])
                    st.rerun()
        st.dataframe(
            [{"Customer": v["customer"] + (" · sample" if v["is_sample"] else ""),
              "Area": v["area"], "Visited": v["visit_date"], "Outcome": v["outcome"],
              "Follow up": (v["follow_up_date"] + (" · done" if v["follow_up_done"] else "")) or "—",
              "Note": v["notes"]} for v in visits],
            hide_index=True, alt="Door-to-door visit history and follow-up dates",
        )
    else:
        st.caption("Your visit history will appear here.")


def show_finances(user_id: int) -> None:
    st.title("Income & expenses", icon=":material/account_balance_wallet:")
    st.caption("See money collected, ingredient costs and what remains after expenses.")
    summary = get_summary(user_id)
    a, b, c = st.columns(3)
    a.metric("Sales value", money(summary["sales"]))
    b.metric("Business expenses", money(summary["expenses"]))
    c.metric("Estimated net profit", money(summary["net_profit"]))
    st.caption("Estimated profit = order value − product costs − recorded expenses. Add accurate costs for a useful estimate.")
    with st.expander("Add a business expense", icon=":material/add_card:", expanded=False):
        with st.form("expense_form", clear_on_submit=True):
            label = st.text_input("What was it for?", max_chars=100)
            col1, col2 = st.columns(2)
            category = col1.selectbox("Category", ["Ingredients", "Packaging", "Travel", "Equipment", "Other"])
            amount = col2.number_input("Amount (₹)", min_value=0.0, step=10.0)
            expense_date = st.date_input("Date", value=date.today())
            submitted = st.form_submit_button("Save expense", width="stretch")
        if submitted:
            try:
                add_expense(user_id, label, category, amount, expense_date.isoformat())
                st.success("Expense saved.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    expenses = get_expenses(user_id)
    if expenses:
        st.subheader("Expense book", icon=":material/receipt:")
        st.dataframe(
            [{"Date": e["expense_date"], "Description": e["label"] + (" · sample" if e["is_sample"] else ""),
              "Category": e["category"], "Amount": money(e["amount"])} for e in expenses],
            hide_index=True, alt="Business expenses by date and category",
        )


def show_reports(user_id: int) -> None:
    st.title("Reports & catalogue", icon=":material/description:")
    st.caption("Download a simple order report or a product list to share with customers.")
    orders = get_orders(user_id)
    products = get_products(user_id)
    report_tab, catalogue_tab = st.tabs(["Order report", "Product catalogue"])
    with report_tab:
        if orders:
            rows = ["Order,Customer,Area,Product,Quantity,Total,Paid,Balance,Status,Delivery date"]
            for o in orders:
                fields = [str(o["id"]), o["customer"], o["area"], o["item"], str(o["quantity"]),
                          f"{o['total']:.2f}", f"{o['amount_paid']:.2f}", f"{max(0, o['balance']):.2f}",
                          o["status"], o["due_date"]]
                rows.append(",".join('"' + value.replace('"', '""') + '"' for value in fields))
            st.download_button("Download order report (CSV)", "\n".join(rows),
                               file_name="udyogini_orders.csv", mime="text/csv",
                               icon=":material/download:", width="stretch")
            st.caption(f"{len(orders)} orders · {money(sum(max(0, o['balance']) for o in orders))} still due")
        else:
            st.info("Record an order before downloading a report.")
    with catalogue_tab:
        if products:
            st.dataframe(
                [{"Product": p["name"], "Category": p["category"], "Price": money(p["price"]),
                  "Available": p["stock"]} for p in products],
                hide_index=True, alt="Customer-facing product catalogue",
            )
            rows = ["Product,Category,Price,Available"]
            for p in products:
                fields = [p["name"], p["category"], f"{p['price']:.2f}", str(p["stock"])]
                rows.append(",".join('"' + value.replace('"', '""') + '"' for value in fields))
            st.download_button("Download product catalogue (CSV)", "\n".join(rows),
                               file_name="udyogini_catalogue.csv", mime="text/csv",
                               icon=":material/download:", width="stretch")
        else:
            st.info("Add products to create your catalogue.")


if "user" not in st.session_state:
    show_auth()
else:
    user = st.session_state.user
    ensure_samples_seeded(user["id"])
    with st.sidebar:
        st.title("Udyogini", anchor=False)
        st.caption("A companion for your home business")
        page = st.radio(
            "Go to",
            ["Overview", "Customers", "Products", "Orders & payments", "Visits & follow-ups", "Income & expenses", "Reports & catalogue"],
            format_func=lambda label: {
                "Overview": ":material/dashboard: Overview",
                "Customers": ":material/groups: Customers",
                "Products": ":material/inventory_2: Products",
                "Orders & payments": ":material/receipt_long: Orders & payments",
                "Visits & follow-ups": ":material/directions_walk: Visits & follow-ups",
                "Income & expenses": ":material/account_balance_wallet: Income & expenses",
                "Reports & catalogue": ":material/description: Reports & catalogue",
            }[label],
        )
        st.caption(f"Signed in as **{user['username']}**")
        if st.button("Sign out", icon=":material/logout:", width="stretch"):
            st.session_state.pop("user", None)
            st.rerun()

    pages = {
        "Overview": lambda: show_overview(user["id"]),
        "Customers": lambda: show_customers(user["id"]),
        "Products": lambda: show_products(user["id"]),
        "Orders & payments": lambda: show_orders(user["id"]),
        "Visits & follow-ups": lambda: show_visits(user["id"]),
        "Income & expenses": lambda: show_finances(user["id"]),
        "Reports & catalogue": lambda: show_reports(user["id"]),
    }
    pages[page]()
