import requests
import pandas as pd
import os
import matplotlib

matplotlib.use("Agg")  # Use non-GUI backend for matplotlib
import matplotlib.pyplot as plt
import plotly.express as px
from src.config import ACCOUNT_IDS, NOTION_API_KEY, DATABASE_ID
import requests
from datetime import datetime


ACCESS_TOKEN = os.getenv("UP_API_TOKEN")


def check_up_token():
    if not os.getenv("UP_API_TOKEN"):
        raise ValueError(
            "Please set the UP_API_TOKEN environment variable in your .env file."
        )


def check_notion_token():
    if not os.getenv("NOTION_API_KEY"):
        raise ValueError(
            "Please set the NOTION_API_KEY environment variable in your .env file."
        )


def is_category_match(category_info, parent_category_info, parent_category):
    if not parent_category:
        return False
    return any(
        (parent_category_info and parent_category_info["id"] == cat)
        or (category_info and category_info["id"] == cat)
        for cat in parent_category
    )


def is_description_match(transaction_description, description):
    return (
        description.replace(" ", "").strip().lower()
        in transaction_description.replace(" ", "").strip()
    )


def is_food_match(
    transaction_description,
    category_info,
    parent_category_info,
    food_keywords,
    food_child_categories,
    food_parent_category,
):
    return any(keyword in transaction_description for keyword in food_keywords) or (
        category_info
        and (
            category_info["id"] in food_child_categories
            and (
                parent_category_info
                and parent_category_info["id"] == food_parent_category
            )
        )
    )


def is_amount_match(transaction, min_amount, max_amount):
    amount = transaction.get("attributes", {}).get("amount", {}).get("value", None)
    if amount is None:
        return True

    amount = float(amount)
    return not (
        (min_amount is not None and amount < min_amount)
        or (max_amount is not None and amount > max_amount)
    )


def fetch_transactions(
    account_id=None,
    since=None,
    until=None,
    parent_category=None,
    description=None,
    all_accounts=False,
    min_amount=None,
    max_amount=None,
    food_related=False,
):
    accounts_to_fetch = (
        account_id if account_id else ACCOUNT_IDS.values() if all_accounts else []
    )
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    food_keywords = ["coles", "woolworths"]
    food_child_categories = {"restaurants-and-cafes", "takeaway"}
    food_parent_category = "good-life"
    all_transactions = []

    for account in accounts_to_fetch:
        url = f"https://api.up.com.au/api/v1/accounts/{account}/transactions"
        params = {
            "filter[since]": since if since else None,
            "filter[until]": until if until else None,
            "page[size]": 100,
        }
        while url:
            response = requests.get(url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                transactions = data["data"]

                for transaction in transactions:
                    transaction_description = (
                        transaction.get("attributes", {}).get("description", "").lower()
                    )
                    category_info = (
                        transaction.get("relationships", {})
                        .get("category", {})
                        .get("data")
                    )
                    parent_category_info = (
                        transaction.get("relationships", {})
                        .get("parentCategory", {})
                        .get("data")
                    )

                    # Evaluate conditions only when relevant
                    if parent_category:
                        if not is_category_match(
                            category_info, parent_category_info, parent_category
                        ):
                            continue

                    if description:
                        if not is_description_match(
                            transaction_description, description
                        ):
                            continue

                    if min_amount is not None or max_amount is not None:
                        if not is_amount_match(transaction, min_amount, max_amount):
                            continue

                    if food_related:
                        if not is_food_match(
                            transaction_description,
                            category_info,
                            parent_category_info,
                            food_keywords,
                            food_child_categories,
                            food_parent_category,
                        ):
                            continue

                    # Add the transaction if it passes all checks
                    all_transactions.append(transaction)

                url = data["links"].get("next", None)
                params = {}  # Reset params for the next page
            else:
                print("Error:", response.json())
                return {"error": "Failed to retrieve data"}

    return {"transactions": all_transactions}


def push_to_notion(transaction_data):
    url = "https://api.notion.com/v1/pages"

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    amount = transaction_data.get("amount")
    if isinstance(amount, str):
        try:
            amount = float(amount)
        except ValueError:
            amount = None

    created_at = transaction_data.get("createdAt")
    if created_at is None:
        print("Invalid 'createdAt' format:", transaction_data.get("createdAt"))
        return

    if isinstance(created_at, str):
        try:
            created_at = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            created_at = None

    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Name": {"title": [{"text": {"content": transaction_data["description"]}}]},
            "Amount": {"number": amount},
            "createdAt": {
                "date": {"start": (created_at.isoformat() if created_at else None)}
            },
        },
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        print("Successfully pushed data to Notion")
    else:
        print("Failed to push data:", response.json())


def plot_dashboard_bar(accounts_data, account_name):
    transactions = accounts_data["transactions"]

    # Store withdrawals as negative values
    withdrawals = [
        float(txn["attributes"]["amount"]["value"])
        for txn in transactions
        if float(txn["attributes"]["amount"]["value"]) < 0
    ]
    deposits = [
        float(txn["attributes"]["amount"]["value"])
        for txn in transactions
        if float(txn["attributes"]["amount"]["value"]) > 0
    ]

    # Dynamically set the title with the selected account name
    fig = px.bar(
        x=["Withdrawals", "Deposits"],
        y=[sum(withdrawals), sum(deposits)],
        labels={"x": "Transaction Type", "y": "Amount (AUD)"},
        title=f"Total Withdrawals and Deposits for '{account_name}' Account",
    )

    # Update colors for each bar
    fig.update_traces(marker_color=["red", "green"])

    # Return the HTML div of the bar chart
    bar_chart_html = fig.to_html(full_html=False)
    return bar_chart_html
