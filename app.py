"""
app.py  —  Step 4. The dashboard people actually look at.

Run locally:  streamlit run app.py
Deploy free:  push to GitHub -> share.streamlit.io -> pick the repo -> Deploy
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Product Trend Dashboard", layout="wide")

# Validated categorical palette (colourblind-checked, fixed order — never cycled)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, MUTED, GRID = "#0b0b0b", "#898781", "#e1e0d9"
GOOD, BAD = "#0ca30c", "#d03b3b"


@st.cache_data
def load():
    monthly = pd.read_parquet("data/monthly.parquet")
    summary = pd.read_csv("data/product_summary.csv")
    return monthly, summary


monthly, summary = load()

st.title("Most-Used Products — Trend Analysis")
st.caption(
    f"{summary.shape[0]} products · "
    f"{monthly['month'].min():%b %Y} – {monthly['month'].max():%b %Y} · "
    "quantity = units sold"
)

# ---------- controls (one row, above the charts) ----------
c1, c2, c3 = st.columns([2, 1, 1])
with c1:
    default = summary.head(5)["description"].tolist()
    picked = st.multiselect("Products", summary["description"].tolist(),
                            default=default, max_selections=5)
with c2:
    metric = st.selectbox("Metric", ["quantity", "revenue", "orders"])
with c3:
    smooth = st.toggle("3-month moving average", value=True)

if not picked:
    st.info("Pick at least one product.")
    st.stop()

# colour follows the entity, not its rank — so filtering doesn't repaint
colour_key = {d: SERIES[i % len(SERIES)]
              for i, d in enumerate(summary["description"].tolist())}

view = monthly[monthly["description"].isin(picked)].copy()

# ---------- KPI tiles ----------
sel = summary[summary["description"].isin(picked)]
k = st.columns(4)
k[0].metric("Units sold (selected)", f"{int(sel['total_quantity'].sum()):,}")
k[1].metric("Revenue (selected)", f"£{sel['total_revenue'].sum():,.0f}")
rising = int((sel["status"] == "Rising").sum())
k[2].metric("Rising", f"{rising} of {len(sel)}")
best = sel.loc[sel["slope_pct_per_month"].idxmax()]
k[3].metric("Fastest growing", best["description"][:22].title(),
            f"{best['slope_pct_per_month']:+.1f}%/mo")

# ---------- the trendline chart ----------
fig = go.Figure()
ycol = f"{metric}_ma" if smooth else metric
end_labels = []

for desc in picked:
    g = view[view["description"] == desc].sort_values("month")
    colour = colour_key[desc]

    fig.add_trace(go.Scatter(
        x=g["month"], y=g[ycol], name=desc.title(), mode="lines",
        line=dict(color=colour, width=2),
        hovertemplate="%{x|%b %Y}<br>%{y:,.0f}<extra>" + desc.title() + "</extra>",
    ))

    # dotted least-squares trendline — the direction, stripped of noise
    y = g[metric].to_numpy(float)
    x = np.arange(len(y), dtype=float)
    if len(y) > 1:
        slope, intercept = np.polyfit(x, y, 1)
        fig.add_trace(go.Scatter(
            x=g["month"], y=slope * x + intercept, mode="lines",
            line=dict(color=colour, width=1, dash="dot"),
            showlegend=False, hoverinfo="skip", opacity=0.55,
        ))

    end_labels.append((desc, g["month"].iloc[-1], float(g[ycol].iloc[-1]), colour))

# direct end labels — required relief, since some hues sit under 3:1.
# Nudge them apart so they never overlap: sort high to low, then push each
# one down until it clears the previous by a minimum gap.
if end_labels:
    span = view[ycol].max() - view[ycol].min() or 1
    gap = span * 0.055
    end_labels.sort(key=lambda t: t[2], reverse=True)
    placed = []
    for desc, x_end, y_end, colour in end_labels:
        y_lab = y_end if not placed else min(y_end, placed[-1] - gap)
        placed.append(y_lab)
        fig.add_annotation(x=x_end, y=y_lab, text=f" {desc.title()[:24]}",
                           showarrow=False, xanchor="left",
                           font=dict(size=11, color=INK))

fig.update_layout(
    height=460, plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
    margin=dict(l=10, r=190, t=30, b=10), hovermode="x unified",
    legend=dict(orientation="h", y=-0.16, font=dict(size=11, color=INK)),
    font=dict(family="system-ui, -apple-system, sans-serif"),
)
fig.update_xaxes(showgrid=False, linecolor="#c3c2b7", tickfont=dict(color=MUTED))
fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED),
                 title=dict(text=metric.title(), font=dict(color=MUTED)))

st.plotly_chart(fig, width="stretch")
st.caption("Solid = actual (smoothed if toggled). Dotted = least-squares trendline.")

# ---------- ranking + table view (accessibility fallback) ----------
left, right = st.columns([1, 1])

with left:
    st.subheader("Ranking by units used")
    rank = summary.head(10).sort_values("total_quantity")
    bar = go.Figure(go.Bar(
        x=rank["total_quantity"], y=rank["description"].str.title(),
        orientation="h",
        marker=dict(color=[colour_key.get(d, "#c3c2b7") for d in rank["description"]],
                    line=dict(color="#fcfcfb", width=2)),
        hovertemplate="%{y}<br>%{x:,} units<extra></extra>",
    ))
    bar.update_layout(height=420, plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb",
                      margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    bar.update_xaxes(gridcolor=GRID, tickfont=dict(color=MUTED))
    bar.update_yaxes(tickfont=dict(color=INK, size=11))
    st.plotly_chart(bar, width="stretch")

with right:
    st.subheader("The numbers")
    show = summary[["rank", "description", "total_quantity",
                    "slope_pct_per_month", "momentum_pct", "status"]].copy()
    show.columns = ["#", "Product", "Units", "Trend %/mo", "Momentum %", "Status"]
    st.dataframe(
        show.style.map(
            lambda v: f"color: {GOOD}" if v == "Rising"
            else (f"color: {BAD}" if v == "Declining" else f"color: {MUTED}"),
            subset=["Status"],
        ),
        hide_index=True, height=420, width="stretch",
    )

with st.expander("How to read this"):
    st.markdown(
        "**Trend %/mo** is the least-squares slope divided by the product's own "
        "average, so a big product and a small one can be compared directly. "
        "**Momentum %** compares the last 3 months against the 3 before them — "
        "it reacts faster than the slope, so when momentum and trend disagree, "
        "something just changed. Rising/Declining is set at ±2%/month."
    )
