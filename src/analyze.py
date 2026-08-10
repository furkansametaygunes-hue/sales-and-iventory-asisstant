"""
analyze.py  —  Step 3. This is the actual "most used products trendline".

Three questions, three answers:
  1. WHICH products are used most?          -> ranking by total quantity
  2. HOW does each one move over time?      -> monthly series + 3-month moving average
  3. WHERE is each one heading?             -> trendline slope + momentum -> Rising/Stable/Declining

Run:  python src/analyze.py
In:   data/clean.parquet
Out:  data/monthly.parquet, data/product_summary.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

TOP_N = 5          # how many products to put on the chart
MA_WINDOW = 3      # moving-average window, in months


def monthly_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """One row per product per month. Missing months filled with 0 —
    a month with no sales is real information, not absent data."""
    g = (
        df.groupby(["stock_code", "description", "month"], as_index=False)
        .agg(quantity=("quantity", "sum"),
             revenue=("revenue", "sum"),
             orders=("invoice", "nunique"))
    )

    all_months = pd.date_range(g["month"].min(), g["month"].max(), freq="MS")
    products = g[["stock_code", "description"]].drop_duplicates()

    grid = products.merge(pd.DataFrame({"month": all_months}), how="cross")
    g = grid.merge(g, on=["stock_code", "description", "month"], how="left").fillna(
        {"quantity": 0, "revenue": 0.0, "orders": 0}
    )

    g = g.sort_values(["stock_code", "month"])

    # a smoothed column per metric, named "<metric>_ma" so the dashboard
    # can switch metric and smoothing independently
    for metric in ("quantity", "revenue", "orders"):
        g[f"{metric}_ma"] = (
            g.groupby("stock_code")[metric]
            .transform(lambda s: s.rolling(MA_WINDOW, min_periods=1).mean())
        )
    return g.reset_index(drop=True)


def trend_slope(series: pd.Series) -> float:
    """Least-squares slope: average change in units per month.
    This is the literal trendline — y = slope*x + intercept."""
    y = series.to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)
    if len(y) < 2 or np.all(y == y[0]):
        return 0.0
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def summarise(monthly: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for code, grp in monthly.groupby("stock_code"):
        grp = grp.sort_values("month")
        qty = grp["quantity"]
        total = qty.sum()
        slope = trend_slope(qty)
        avg = qty.mean()

        # momentum: last 3 months vs the 3 before them
        last3 = qty.iloc[-3:].sum()
        prev3 = qty.iloc[-6:-3].sum()
        momentum = (last3 - prev3) / prev3 * 100 if prev3 > 0 else np.nan

        # slope as % of the product's own average -> comparable across
        # products of very different size. This is the key trick:
        # +30 units/month means nothing until you know the baseline.
        slope_pct = slope / avg * 100 if avg > 0 else 0.0

        if slope_pct > 2:
            status = "Rising"
        elif slope_pct < -2:
            status = "Declining"
        else:
            status = "Stable"

        rows.append(
            {
                "stock_code": code,
                "description": grp["description"].iloc[0],
                "total_quantity": int(total),
                "total_revenue": round(grp["revenue"].sum(), 2),
                "avg_monthly_qty": round(avg, 1),
                "peak_month": grp.loc[qty.idxmax(), "month"].strftime("%Y-%m"),
                "slope_units_per_month": round(slope, 2),
                "slope_pct_per_month": round(slope_pct, 2),
                "momentum_pct": round(momentum, 1) if pd.notna(momentum) else None,
                "status": status,
            }
        )

    out = pd.DataFrame(rows).sort_values("total_quantity", ascending=False)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out.reset_index(drop=True)


if __name__ == "__main__":
    df = pd.read_parquet("data/clean.parquet")
    monthly = monthly_matrix(df)
    summary = summarise(monthly)

    Path("data").mkdir(exist_ok=True)
    monthly.to_parquet("data/monthly.parquet", index=False)
    summary.to_csv("data/product_summary.csv", index=False)

    pd.set_option("display.width", 200)
    print(f"\nTOP {TOP_N} MOST-USED PRODUCTS\n" + "=" * 96)
    cols = ["rank", "description", "total_quantity", "avg_monthly_qty",
            "slope_pct_per_month", "momentum_pct", "status"]
    print(summary.head(TOP_N)[cols].to_string(index=False))

    print("\nBIGGEST MOVERS (by trendline slope)\n" + "=" * 96)
    movers = summary.reindex(summary["slope_pct_per_month"].abs()
                             .sort_values(ascending=False).index)
    print(movers.head(5)[["description", "slope_pct_per_month",
                          "momentum_pct", "status"]].to_string(index=False))

    print(f"\nWrote data/monthly.parquet and data/product_summary.csv")
