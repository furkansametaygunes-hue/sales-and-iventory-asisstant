# Product Trend Analysis

Which products drive the volume, and which ones are quietly dying?

A retailer carrying thousands of product lines cannot watch them all by hand. This
project takes raw transaction data, finds the most-used products, fits a trendline
to each one, and flags the ones whose direction has turned — usually two quarters
before it shows up in the revenue total.

**Live dashboard:** _(paste your Streamlit URL here after Step 6)_

---

## The pipeline

```
raw transactions
   └─ clean.py      remove cancellations, junk codes, outliers  →  clean.parquet
       └─ analyze.py   monthly grid + trendline + momentum      →  monthly.parquet
           └─ app.py     interactive dashboard                  →  public URL
```

## Run it

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python src/make_sample_data.py     # or drop the real dataset into data/
python src/clean.py
python src/analyze.py
python src/load_db.py              # optional — builds the SQLite database
streamlit run app.py
```

To use the real data instead of the sample, download **Online Retail II** from the
UCI Machine Learning Repository into `data/online_retail_II.xlsx` and run:

```bash
python src/clean.py data/online_retail_II.xlsx
```

## Method notes

**Zero-filled months.** A product that sold nothing in August must appear as a zero,
not be missing. If the month is simply absent, the trendline skips it and the
product looks healthier than it is. This is the most common error in this kind of
analysis.

**Normalised slope.** The raw least-squares slope is in units per month, so +30 is
enormous for a product averaging 100/month and trivial for one averaging 3,000.
Dividing each slope by that product's own mean turns it into % change per month,
which is comparable across products of any size.

**Slope plus momentum.** The slope covers the whole period — stable, but slow to
react. Momentum compares the last 3 months against the 3 before. When the two
disagree, something recently changed, and that is usually the most interesting
thing on the dashboard.

## What I found

_(Fill this in from your own run — this is the section that matters most.)_

- The top 5 products account for **X%** of all units sold
- **N** of the top 20 are declining faster than 5% per month
- _Product_ fell 44% in the last quarter while its two-year trend was still
  positive — a turn an annual report would miss entirely

## What a business would do with this

Cut reorder volume on the declining lines and reallocate the shelf space to the
rising ones. The trendline surfaces the decision earlier than the revenue total
does.

## Tech

Python · pandas · NumPy · SQLite · Plotly · Streamlit
