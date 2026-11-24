"""Generate 7-day per-SKU demand forecasts from sample historical sales data."""
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LinearRegression


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "historical_sales.csv"


def build_sample_history():
    skus = ["MLK-001", "BRD-001", "EGG-012", "APL-001", "RCE-500", "COK-330"]
    baseline = [8, 6, 4, 7, 3, 12]
    rows = []
    for sku_index, sku in enumerate(skus):
        for day in range(90):
            quantity = max(
                0,
                round(
                    baseline[sku_index]
                    + (sku_index % 3) * 0.15 * day
                    + 2 * ((day % 7) in (4, 5, 6))
                    + ((day * (sku_index + 3)) % 5) * 0.35
                ),
            )
            rows.append(
                {
                    "date": pd.Timestamp("2026-08-31") + pd.Timedelta(days=day),
                    "sku": sku,
                    "quantity": quantity,
                }
            )
    pd.DataFrame(rows).to_csv(DATA_FILE, index=False)


def predict_next_7_days():
    if not DATA_FILE.exists():
        build_sample_history()
    sales = pd.read_csv(DATA_FILE, parse_dates=["date"])
    sales["day_index"] = (sales["date"] - sales["date"].min()).dt.days
    forecasts = {}

    for sku, sku_sales in sales.groupby("sku"):
        sku_sales = sku_sales.sort_values("date")
        model = LinearRegression()
        model.fit(sku_sales[["day_index"]], sku_sales["quantity"])
        start = sales["day_index"].max() + 1
        future_days = pd.DataFrame({"day_index": range(start, start + 7)})
        predicted = model.predict(future_days).clip(min=0).round().astype(int)
        forecasts[sku] = [int(value) for value in predicted]
    return forecasts


if __name__ == "__main__":
    print("7-day demand forecast")
    for sku, demand in predict_next_7_days().items():
        print(f"{sku}: {demand}")
