"""
app_business.py — Isletme surumu.

Isletmeci trend grafigi istemiyor. "Bu hafta ne kadar siparis vereyim",
"hangi urun para yiyor", "neye bakmaliyim" istiyor. Uygulama once
bunlari gosteriyor; grafik ikinci sirada.

Calistir:  python -m streamlit run app_business.py
"""

import io
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from decide import abc_table, dead_money, reorder_table   # noqa: E402

# ----------------------------------------------------------------------
# MUSTERIYE OZEL — degistirilecek tek yer
# ----------------------------------------------------------------------
BRAND = {
    "company": "Satış & Stok Asistanı",
    "subtitle": "Excel'ini yükle, ne sipariş edeceğini söylesin",
    "currency": "₺",
    "logo": None,
}

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
GOOD, WARN, BAD = "#0ca30c", "#fab219", "#d03b3b"

st.set_page_config(page_title=BRAND["company"], page_icon="📦", layout="wide")


# ----------------------------------------------------------------------
# Dosya okuma + kolon tanima
# ----------------------------------------------------------------------
def norm(s):
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.translate(str.maketrans("ıçğöşü", "icgosu")).replace(" ", "").replace("_", "").replace("-", "")


ALIASES = {
    "date": ["tarih", "islemtarihi", "satistarihi", "faturatarihi", "date",
             "invoicedate", "orderdate", "gun"],
    "product": ["urun", "urunadi", "urunismi", "stokadi", "stokkodu", "malzeme",
                "product", "productname", "description", "item", "stockcode", "ad"],
    "quantity": ["adet", "miktar", "satisadedi", "quantity", "qty", "amount", "sayi"],
    "price": ["fiyat", "birimfiyat", "satisfiyati", "price", "unitprice", "tutar"],
    "cost": ["maliyet", "alisfiyati", "birimmaliyet", "cost", "unitcost", "alis"],
    "onhand": ["stok", "eldekistok", "mevcutstok", "kalanstok", "onhand", "stock",
               "mevcut", "kalan", "stokmiktari"],
}


def guess(columns, kind):
    normed = {norm(c): c for c in columns}
    for a in ALIASES[kind]:
        if a in normed:
            return normed[a]
    for a in ALIASES[kind]:
        for n, orig in normed.items():
            if a in n:
                return orig
    return None


@st.cache_data(show_spinner=False)
def read_any(file_bytes, name):
    if name.lower().endswith((".xlsx", ".xls", ".xlsm")):
        sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
        return pd.concat(sheets.values(), ignore_index=True)
    for sep in [",", ";", "\t"]:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=sep)
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    return pd.read_csv(io.BytesIO(file_bytes))


def clean(df, c_date, c_prod, c_qty, c_price, c_cost):
    d = pd.DataFrame({
        "date": pd.to_datetime(df[c_date], errors="coerce", dayfirst=True),
        "product": df[c_prod].astype(str).str.strip(),
        "quantity": pd.to_numeric(df[c_qty], errors="coerce"),
    })
    d["price"] = (pd.to_numeric(df[c_price], errors="coerce")
                  if c_price and c_price != "(yok)" else 0.0)
    d["cost"] = (pd.to_numeric(df[c_cost], errors="coerce")
                 if c_cost and c_cost != "(yok)" else np.nan)

    start = len(d)
    d = d.dropna(subset=["date", "quantity"])
    d = d[d["quantity"] > 0]
    d = d[d["product"].notna() & (d["product"].str.lower() != "nan") & (d["product"] != "")]
    if len(d) > 20:
        d = d[d["quantity"] <= d["quantity"].quantile(0.999)]
    d["revenue"] = d["quantity"] * d["price"].fillna(0)
    d["month"] = d["date"].dt.to_period("M").dt.to_timestamp()
    return d.reset_index(drop=True), start


def monthly_table(d):
    m = (d.groupby(["product", "month"], as_index=False)
           .agg(quantity=("quantity", "sum"), revenue=("revenue", "sum")))
    months = pd.date_range(m["month"].min(), m["month"].max(), freq="MS")
    grid = (pd.DataFrame({"product": m["product"].unique()})
            .merge(pd.DataFrame({"month": months}), how="cross"))
    m = (grid.merge(m, on=["product", "month"], how="left")
             .fillna({"quantity": 0, "revenue": 0.0})
             .sort_values(["product", "month"]))
    m["qty_ma"] = (m.groupby("product")["quantity"]
                   .transform(lambda s: s.rolling(3, min_periods=1).mean()))
    return m


def trend_table(m):
    rows = []
    for prod, g in m.groupby("product"):
        q = g.sort_values("month")["quantity"]
        y = q.to_numpy(float)
        avg = y.mean()
        slope = np.polyfit(np.arange(len(y)), y, 1)[0] if len(y) > 1 and y.std() else 0.0
        pct = slope / avg * 100 if avg > 0 else 0.0
        prev3 = q.iloc[-6:-3].sum()
        mom = (q.iloc[-3:].sum() - prev3) / prev3 * 100 if prev3 > 0 else np.nan
        rows.append({"Ürün": prod, "Toplam adet": int(q.sum()),
                     "Ciro": round(g["revenue"].sum(), 2),
                     "Trend %/ay": round(pct, 2),
                     "Momentum %": round(mom, 1) if pd.notna(mom) else None,
                     "Durum": "Yükseliyor" if pct > 2 else ("Düşüyor" if pct < -2 else "Sabit")})
    t = pd.DataFrame(rows).sort_values("Toplam adet", ascending=False).reset_index(drop=True)
    t.insert(0, "#", range(1, len(t) + 1))
    return t


def build_excel(order, trend, abc, m):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        order.to_excel(w, sheet_name="Sipariş listesi", index=False)
        trend.to_excel(w, sheet_name="Trend", index=False)
        abc.to_excel(w, sheet_name="ABC", index=False)
        pv = m.pivot_table(index="month", columns="product", values="quantity",
                           aggfunc="sum").fillna(0)
        pv.index = pv.index.strftime("%Y-%m")
        pv.to_excel(w, sheet_name="Aylık adet")
        for ws in w.book.worksheets:
            for col in ws.columns:
                width = max(len(str(c.value or "")) for c in col) + 3
                ws.column_dimensions[col[0].column_letter].width = min(width, 40)
            ws.freeze_panes = "A2"
    return buf.getvalue()


# ----------------------------------------------------------------------
# ARAYUZ
# ----------------------------------------------------------------------
if BRAND["logo"]:
    st.image(BRAND["logo"], width=150)
st.title(BRAND["company"])
st.caption(BRAND["subtitle"])

with st.sidebar:
    st.header("1 · Satış dosyası")
    up = st.file_uploader("Excel veya CSV", type=["xlsx", "xls", "xlsm", "csv"])
    st.caption("Gerekli: **tarih**, **ürün**, **adet**. Fiyat ve maliyet varsa "
               "ciro ve kâr da çıkar.")

    st.header("2 · Stok dosyası")
    stock_up = st.file_uploader("Eldeki stok (opsiyonel)",
                                type=["xlsx", "xls", "xlsm", "csv"], key="stk")
    st.caption("Ürün ve mevcut stok adedi. **Bu dosya olmadan sipariş miktarı "
               "hesaplanamaz** — sadece dönem ihtiyacı gösterilir.")

if up is None:
    st.info("👈 Soldan satış dosyanı yükle.")
    st.markdown("""
### Bu uygulama ne yapıyor

Satış geçmişine bakıp üç soruyu cevaplıyor:

1. **Bu hafta ne kadar sipariş vermeliyim?** Her ürün için günlük talep,
   tedarik süresi ve dalgalanma hesaba katılarak bir adet öneriyor.
2. **Hangi ürün para yiyor?** Aylardır satmayan ama rafta duran stok,
   ve cironun %80'ini getiren ürünler.
3. **Hangi ürün ölüyor?** Trend düşüşü, ciroya yansımadan önce.

### Dosyada olması gerekenler

| Kolon | Örnek isimler | Zorunlu |
|---|---|---|
| Tarih | Tarih, İşlem Tarihi, Fatura Tarihi | ✅ |
| Ürün | Ürün Adı, Stok Adı, Malzeme | ✅ |
| Adet | Adet, Miktar, Satış Adedi | ✅ |
| Fiyat | Birim Fiyat, Satış Fiyatı | ➖ |
| Maliyet | Alış Fiyatı, Maliyet | ➖ |

Kolon isimleri birebir aynı olmak zorunda değil — program tahmin ediyor,
yanlış tahmin ederse soldan düzeltiyorsun.
""")
    st.stop()

try:
    raw = read_any(up.getvalue(), up.name)
except Exception as e:
    st.error(f"Dosya okunamadı: {e}")
    st.stop()

cols = list(raw.columns)


def sel(label, kind, optional=False, key=None):
    opts = (["(yok)"] + cols) if optional else cols
    g = guess(cols, kind)
    idx = opts.index(g) if g in opts else 0
    return st.selectbox(label, opts, index=idx, key=key)


with st.sidebar:
    st.header("3 · Kolonlar")
    st.caption(f"{len(raw):,} satır okundu")
    c_date = sel("Tarih", "date")
    c_prod = sel("Ürün", "product")
    c_qty = sel("Adet", "quantity")
    c_price = sel("Fiyat", "price", True)
    c_cost = sel("Maliyet", "cost", True)

    st.header("4 · Sipariş ayarları")
    lead = st.number_input("Tedarik süresi (gün)", 1, 90, 7,
                           help="Sipariş verdikten kaç gün sonra mal elinde oluyor?")
    review = st.number_input("Sipariş sıklığı (gün)", 1, 90, 7,
                             help="Kaç günde bir sipariş veriyorsun?")
    service = st.select_slider("Hizmet seviyesi", [90, 95, 97, 99], 95,
                               help="Yüksek = daha az stoksuz kalma, ama daha çok bağlı para")
    dead_days = st.number_input("Ölü stok eşiği (gün)", 14, 365, 60,
                                help="Bu kadar gündür satmayan ürün ölü sayılır")

try:
    d, n_raw = clean(raw, c_date, c_prod, c_qty, c_price, c_cost)
    if not len(d):
        raise ValueError("Temizlikten sonra hiç satır kalmadı")
    m = monthly_table(d)
    trend = trend_table(m)
except Exception as e:
    st.error(f"Analiz yapılamadı: {e}")
    st.info("Soldaki kolon eşleştirmesini kontrol et — genelde tarih veya "
            "adet kolonu yanlış seçilmiş oluyor.")
    st.stop()

# ---- stok dosyasi ----
stock_df = None
if stock_up is not None:
    try:
        sraw = read_any(stock_up.getvalue(), stock_up.name)
        scols = list(sraw.columns)
        with st.sidebar:
            st.caption("Stok dosyası kolonları")
            sp = st.selectbox("Ürün (stok)", scols,
                              index=scols.index(guess(scols, "product")) if guess(scols, "product") else 0)
            so = st.selectbox("Mevcut stok", scols,
                              index=scols.index(guess(scols, "onhand")) if guess(scols, "onhand") else 0)
        stock_df = pd.DataFrame({"Ürün": sraw[sp].astype(str).str.strip(),
                                 "on_hand": pd.to_numeric(sraw[so], errors="coerce")})
        stock_df = stock_df.dropna(subset=["Ürün"]).groupby("Ürün", as_index=False)["on_hand"].sum()
    except Exception as e:
        st.sidebar.error(f"Stok dosyası okunamadı: {e}")

cost_map = (d.dropna(subset=["cost"]).groupby("product")["cost"].median().to_dict()
            if d["cost"].notna().any() else None)

order, last_day = reorder_table(d, stock=stock_df, lead_time=lead, review=review,
                                service=service, dead_days=dead_days)
abc, metric = abc_table(d, cost_map)

months_span = m["month"].nunique()
if months_span < 6:
    st.warning(f"Sadece {months_span} ay veri var. Sipariş önerileri çalışır ama "
               "trend yorumu güvenilir değil — en az 12 ay gerekiyor.")

with st.sidebar:
    st.header("5 · Rapor")
    st.download_button("📥 Excel raporu indir", build_excel(order, trend, abc, m),
                       file_name="satis-stok-raporu.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")
    st.caption(f"Son veri: {last_day:%d.%m.%Y} · {len(d):,}/{n_raw:,} satır · "
               f"{d['product'].nunique()} ürün · {months_span} ay")

t1, t2, t3, t4 = st.tabs(["📦 Bu hafta ne yapmalı", "📈 Trend", "💰 Para nerede", "🪦 Ölü stok"])

# ======================================================================
with t1:
    has_stock = stock_df is not None and len(stock_df)

    if has_stock:
        tuk = order[order["Durum"] == "TÜKENDİ"]
        ver = order[order["Durum"] == "Sipariş ver"]
        faz = order[order["Durum"] == "Fazla stok"]
        k = st.columns(4)
        k[0].metric("Tükenmiş", len(tuk), help="Stok sıfır — satış kaybediyorsun")
        k[1].metric("Sipariş verilmeli", len(ver))
        k[2].metric("Fazla stoklu", len(faz), help="İhtiyacın çok üstünde — para bağlı")
        k[3].metric("Yeterli", int((order["Durum"] == "Yeterli").sum()))

        acil = order[order["Durum"].isin(["TÜKENDİ", "Sipariş ver"])]
        if len(acil):
            st.subheader("Sipariş listesi")
            st.caption(f"Tedarik {lead} gün · {review} günde bir sipariş · "
                       f"%{service} hizmet seviyesi. Bu ayarları soldan değiştirebilirsin.")
            st.dataframe(
                acil[["Ürün", "Eldeki stok", "Kaç gün yeter", "Günlük talep",
                      "Sipariş noktası", "Sipariş öner", "Durum"]],
                hide_index=True, width="stretch", height=min(420, 60 + 36 * len(acil)),
                column_config={
                    "Eldeki stok": st.column_config.NumberColumn(format="%d"),
                    "Kaç gün yeter": st.column_config.NumberColumn(format="%d gün"),
                    "Günlük talep": st.column_config.NumberColumn(format="%.1f"),
                    "Sipariş öner": st.column_config.NumberColumn("SİPARİŞ VER", format="%d"),
                })
            st.success(f"**{len(acil)} üründe sipariş gerekiyor.** "
                       f"Toplam {int(acil['Sipariş öner'].sum()):,} adet.".replace(",", "."))
        else:
            st.success("Şu an sipariş gerektiren ürün yok.")

        if len(faz):
            st.subheader("Fazla stok — burada para bağlı")
            st.dataframe(faz[["Ürün", "Eldeki stok", "Kaç gün yeter", "Hedef seviye"]],
                         hide_index=True, width="stretch",
                         column_config={"Kaç gün yeter": st.column_config.NumberColumn(format="%d gün")})
            st.caption("«Kaç gün yeter» 90 günün üstündeyse o ürüne fazla para bağlamışsın.")
    else:
        st.info("**Stok dosyası yüklenmedi.** Kesin sipariş miktarı için eldeki "
                "stok gerekiyor. Aşağıdaki tablo, her ürün için önümüzdeki "
                f"{lead + review} günde ihtiyacın olacak toplam adedi gösteriyor — "
                "kendi stoğunu bundan düşersen sipariş miktarını bulursun.")
        st.subheader(f"Önümüzdeki {lead + review} gün için ihtiyaç")
        st.dataframe(
            order[["Ürün", "Günlük talep", "Emniyet stoğu", "Hedef seviye",
                   "Son satıştan beri (gün)"]].head(30),
            hide_index=True, width="stretch", height=430,
            column_config={
                "Günlük talep": st.column_config.NumberColumn(format="%.1f"),
                "Hedef seviye": st.column_config.NumberColumn("İHTİYAÇ", format="%d"),
            })
        st.caption("**Emniyet stoğu**, talebin dalgalanmasına karşı tutulan tampon. "
                   "Talebi çok oynak ürünlerde daha yüksek çıkar.")

    with st.expander("Bu sayılar nasıl hesaplanıyor?"):
        st.markdown(f"""
- **Günlük talep** — son 56 günün ortalama günlük satışı. Satış olmayan günler
  sıfır olarak sayılıyor, yoksa talep olduğundan yüksek çıkardı.
- **Emniyet stoğu** = z × talep sapması × √({lead}+{review}) — talep dalgalanmasına
  karşı tampon. %{service} hizmet seviyesi için z = {{90: 1.28, 95: 1.65, 97: 1.88, 99: 2.33}}[{service}].
- **Sipariş noktası** = günlük talep × {lead} + emniyet stoğu. Stok bunun
  altına düşerse sipariş zamanı gelmiş demektir.
- **Hedef seviye** = günlük talep × ({lead}+{review}) + emniyet stoğu.
- **Sipariş öner** = hedef seviye − eldeki stok.

Bunlar standart stok yönetimi formülleri. Mevsimsellik hesaba katılmıyor;
bayram/sezon öncesi kendi bilginle artır.
""")

# ======================================================================
with t2:
    all_p = trend["Ürün"].tolist()
    picked = st.multiselect("Ürünler", all_p, default=all_p[:5], max_selections=5)
    if picked:
        colour = {p: SERIES[i % 5] for i, p in enumerate(all_p)}
        smooth = st.toggle("3 aylık hareketli ortalama", value=True)
        ycol = "qty_ma" if smooth else "quantity"
        view = m[m["product"].isin(picked)]

        fig = go.Figure()
        ends = []
        for p in picked:
            g = view[view["product"] == p].sort_values("month")
            c = colour[p]
            fig.add_trace(go.Scatter(x=g["month"], y=g[ycol], name=str(p)[:26], mode="lines",
                                     line=dict(color=c, width=2),
                                     hovertemplate="%{x|%b %Y}<br>%{y:,.0f} adet<extra>" + str(p)[:22] + "</extra>"))
            y = g["quantity"].to_numpy(float)
            if len(y) > 1:
                x = np.arange(len(y), dtype=float)
                a, b = np.polyfit(x, y, 1)
                fig.add_trace(go.Scatter(x=g["month"], y=a * x + b, mode="lines",
                                         line=dict(color=c, width=1, dash="dot"),
                                         showlegend=False, hoverinfo="skip", opacity=.5))
            ends.append((str(p)[:22], g["month"].iloc[-1], float(g[ycol].iloc[-1])))

        span = (view[ycol].max() - view[ycol].min()) or 1
        ends.sort(key=lambda t: t[2], reverse=True)
        placed = []
        for nm, xe, ye in ends:
            yl = ye if not placed else min(ye, placed[-1] - span * .055)
            placed.append(yl)
            fig.add_annotation(x=xe, y=yl, text=f" {nm}", showarrow=False,
                               xanchor="left", font=dict(size=11, color=INK))

        fig.update_layout(height=430, plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
                          margin=dict(l=10, r=175, t=20, b=10), hovermode="x unified",
                          legend=dict(orientation="h", y=-.17, font=dict(size=11)),
                          font=dict(family="system-ui, -apple-system, sans-serif"))
        fig.update_xaxes(showgrid=False, linecolor="#c3c2b7", tickfont=dict(color=MUTED))
        fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED),
                         title=dict(text="Adet", font=dict(color=MUTED)))
        st.plotly_chart(fig, width="stretch")
        st.caption("Kalın çizgi = gerçek satış. Noktalı çizgi = trendline.")

    st.dataframe(
        trend.style.map(lambda v: f"color:{GOOD};font-weight:700" if v == "Yükseliyor"
                        else (f"color:{BAD};font-weight:700" if v == "Düşüyor"
                              else f"color:{MUTED}"), subset=["Durum"]),
        hide_index=True, width="stretch", height=380,
        column_config={
            "Toplam adet": st.column_config.NumberColumn(format="%d"),
            "Ciro": st.column_config.NumberColumn(format=BRAND["currency"] + "%.0f"),
            "Trend %/ay": st.column_config.NumberColumn(format="%+.2f"),
            "Momentum %": st.column_config.NumberColumn(format="%+.1f"),
        })

    dus = trend[trend["Durum"] == "Düşüyor"].head(3)
    if len(dus):
        st.warning("**Düşüşte:** " + ", ".join(
            f"{r['Ürün']} (ayda %{r['Trend %/ay']:.1f})" for _, r in dus.iterrows()) +
            " — sipariş miktarını gözden geçir.")

# ======================================================================
with t3:
    label = "kâr" if metric == "kar" else "ciro"
    a_cnt = int((abc["Sınıf"] == "A").sum())
    a_share = float(abc[abc["Sınıf"] == "A"]["pay %"].sum())
    c_cnt = int((abc["Sınıf"] == "C").sum())

    k = st.columns(3)
    k[0].metric(f"A sınıfı ürün", f"{a_cnt} / {len(abc)}")
    k[1].metric(f"Bunların {label} payı", f"%{a_share:.0f}")
    k[2].metric("C sınıfı (az getiren)", c_cnt)

    st.markdown(f"**{a_cnt} ürün, toplam {label}in %{a_share:.0f}'ini getiriyor.** "
                f"Gözünü bunlardan ayırma: stoğu bunlarda tükenmesin, rafta "
                f"bunlar önde olsun. C sınıfındaki {c_cnt} ürün ise çok çeşit, "
                f"az para — çeşitliliği burada kısabilirsin.")

    if metric == "ciro":
        st.info("Maliyet kolonu yok, o yüzden sıralama ciroya göre. **Maliyeti de "
                "yüklersen kâra göre sıralanır** — çok satan bir ürünün aslında "
                "para kazandırmadığı genelde orada ortaya çıkıyor.")

    show = abc.rename(columns={"product": "Ürün", "adet": "Adet", "ciro": "Ciro"})
    cfg = {"Adet": st.column_config.NumberColumn(format="%d"),
           "Ciro": st.column_config.NumberColumn(format=BRAND["currency"] + "%.0f"),
           "pay %": st.column_config.NumberColumn("Pay %", format="%.1f"),
           "kümülatif %": st.column_config.NumberColumn("Kümülatif %", format="%.1f")}
    if "kar" in show:
        cfg["kar"] = st.column_config.NumberColumn("Kâr", format=BRAND["currency"] + "%.0f")
    st.dataframe(show, hide_index=True, width="stretch", height=430, column_config=cfg)

# ======================================================================
with t4:
    dead, tied = dead_money(order, cost_map, dead_days)
    if not len(dead):
        st.success(f"{dead_days} gündür satmayan ürün yok.")
    else:
        k = st.columns(2)
        k[0].metric("Ölü ürün", len(dead))
        if tied:
            k[1].metric("Bağlı para", f"{BRAND['currency']}{tied:,.0f}".replace(",", "."))
        st.dataframe(
            dead[["Ürün", "Eldeki stok", "Son satıştan beri (gün)"]],
            hide_index=True, width="stretch", height=min(430, 60 + 36 * len(dead)),
            column_config={"Eldeki stok": st.column_config.NumberColumn(format="%d")})
        st.markdown(f"""
Bu ürünler **{dead_days} gündür hiç satmadı.** Seçeneklerin:

- İndirimle elden çıkar — bağlı parayı çöz, rafı boşalt
- Tedarikçiye iade koşulunu sor
- Çok satanla birlikte kampanya yap
- Bir daha sipariş etme

Rafta duran mal para kazandırmıyor, sadece yer ve nakit tutuyor.
""")
