"""
decide.py — Analizi KARARA cevirir.

Isletmeci trend grafigi istemiyor; "bu hafta ne kadar siparis vereyim",
"hangi urun para yiyor", "nereye bakmaliyim" sorularinin cevabini istiyor.
Bu dosya o cevaplari uretiyor.

Kullanilan formuller standart stok yonetimi formulleri:

  gunluk talep      mu  = son N gunun ortalama gunluk satisi
  talep sapmasi     sig = ayni pencerenin standart sapmasi
  koruma suresi     P   = tedarik suresi (L) + siparis araligi (R)
  emniyet stogu     SS  = z * sig * sqrt(P)
  hedef seviye      T   = mu * P + SS
  siparis onerisi   Q   = max(0, T - eldeki stok)
  yeniden siparis   ROP = mu * L + SS      (stok bunun altina duserse siparis ver)

z, istenen hizmet seviyesinden gelir: %90 -> 1.28, %95 -> 1.65, %99 -> 2.33
Yuksek hizmet seviyesi = daha az stoksuz kalma, ama daha fazla bagli para.
"""

import numpy as np
import pandas as pd

Z = {90: 1.28, 95: 1.65, 97: 1.88, 99: 2.33}


def daily_series(df, window_days=56):
    """Urun x gun tablosu. Satis olmayan gun SIFIR, eksik degil —
    aksi halde gunluk talep oldugundan yuksek cikar."""
    d = df.copy()
    d["day"] = pd.to_datetime(d["date"]).dt.normalize()
    g = d.groupby(["product", "day"], as_index=False)["quantity"].sum()

    last = g["day"].max()
    start = last - pd.Timedelta(days=window_days - 1)
    days = pd.date_range(start, last, freq="D")

    grid = (pd.DataFrame({"product": g["product"].unique()})
            .merge(pd.DataFrame({"day": days}), how="cross"))
    out = (grid.merge(g, on=["product", "day"], how="left")
              .fillna({"quantity": 0.0})
              .sort_values(["product", "day"]))
    return out, last


def reorder_table(df, stock=None, lead_time=7, review=7, service=95,
                  window_days=56, dead_days=60):
    """Her urun icin siparis karari uretir.

    df    : temizlenmis satirlar — date, product, quantity, revenue, (profit)
    stock : opsiyonel DataFrame — product, on_hand, (cost)
    """
    z = Z.get(service, 1.65)
    daily, last_day = daily_series(df, window_days)
    P = lead_time + review

    # her urunun en son satis tarihi — olu stok tespiti icin tum veriden
    last_sale = (df.assign(day=pd.to_datetime(df["date"]).dt.normalize())
                   .groupby("product")["day"].max())

    rows = []
    for prod, g in daily.groupby("product"):
        q = g["quantity"].to_numpy(float)
        mu = q.mean()                      # gunluk ortalama talep
        sig = q.std(ddof=1) if len(q) > 1 else 0.0

        ss = z * sig * np.sqrt(P)          # emniyet stogu
        target = mu * P + ss               # hedef seviye
        rop = mu * lead_time + ss          # yeniden siparis noktasi

        gun_gecti = (last_day - last_sale.get(prod, last_day)).days

        rows.append({
            "Ürün": prod,
            "Günlük talep": round(mu, 2),
            "Talep sapması": round(sig, 2),
            "Emniyet stoğu": int(np.ceil(ss)),
            "Sipariş noktası": int(np.ceil(rop)),
            "Hedef seviye": int(np.ceil(target)),
            "Son satıştan beri (gün)": int(gun_gecti),
        })

    out = pd.DataFrame(rows)

    # ---- eldeki stok varsa gercek siparis miktarini hesapla ----
    if stock is not None and len(stock):
        s = stock.rename(columns=str).copy()
        out = out.merge(s, on="Ürün", how="left")
        out["Eldeki stok"] = pd.to_numeric(out.get("on_hand"), errors="coerce")

        out["Sipariş öner"] = (out["Hedef seviye"] - out["Eldeki stok"]).clip(lower=0)
        out["Sipariş öner"] = np.ceil(out["Sipariş öner"].fillna(0)).astype(int)

        # kac gun yeter — stoksuz kalmaya ne kadar var
        out["Kaç gün yeter"] = np.where(
            out["Günlük talep"] > 0,
            (out["Eldeki stok"] / out["Günlük talep"]).round(0),
            np.nan)

        def durum(r):
            if pd.isna(r["Eldeki stok"]):
                return "Stok bilinmiyor"
            if r["Son satıştan beri (gün)"] >= dead_days:
                return "Ölü stok"
            if r["Eldeki stok"] <= 0:
                return "TÜKENDİ"
            if r["Eldeki stok"] <= r["Sipariş noktası"]:
                return "Sipariş ver"
            if r["Günlük talep"] > 0 and r["Eldeki stok"] > r["Hedef seviye"] * 2.5:
                return "Fazla stok"
            return "Yeterli"

        out["Durum"] = out.apply(durum, axis=1)
    else:
        # stok dosyasi yoksa: donem ihtiyacini soyle, karari isletmeciye birak
        out["Eldeki stok"] = np.nan
        out["Sipariş öner"] = out["Hedef seviye"]
        out["Kaç gün yeter"] = np.nan
        out["Durum"] = np.where(out["Son satıştan beri (gün)"] >= dead_days,
                                "Ölü stok", "Stok bilinmiyor")

    order = {"TÜKENDİ": 0, "Sipariş ver": 1, "Fazla stok": 2, "Ölü stok": 3,
             "Yeterli": 4, "Stok bilinmiyor": 5}
    out["_o"] = out["Durum"].map(order).fillna(9)
    out = out.sort_values(["_o", "Günlük talep"], ascending=[True, False])
    return out.drop(columns=["_o"]).reset_index(drop=True), last_day


def abc_table(df, cost_map=None):
    """ABC analizi: cironun (veya karin) %80'ini hangi urunler getiriyor.

    A = ilk %80  -> asil parayi bunlar getiriyor, gozunu bunlardan ayirma
    B = sonraki %15
    C = kalan %5 -> cok urun, az para. Cesitliligi burada kis.
    """
    g = df.groupby("product", as_index=False).agg(
        adet=("quantity", "sum"), ciro=("revenue", "sum"))

    if cost_map:
        g["maliyet"] = g["product"].map(cost_map)
        g["kar"] = g["ciro"] - g["maliyet"].fillna(0) * g["adet"]
        metric = "kar"
    else:
        metric = "ciro"

    g = g.sort_values(metric, ascending=False).reset_index(drop=True)
    total = g[metric].sum()
    g["pay %"] = (g[metric] / total * 100).round(1) if total else 0
    g["kümülatif %"] = g["pay %"].cumsum().round(1)

    # Sinif, urunden ONCEKI kumulatife gore verilir: esigi asan urun hala
    # o sinifa dahildir. Aksi halde cironun yarisini getiren bir urun
    # "C" damgasi yiyebiliyor.
    prev = g["kümülatif %"].shift(1).fillna(0)
    g["Sınıf"] = np.where(prev < 80, "A", np.where(prev < 95, "B", "C"))
    return g, metric


def dead_money(reorder, cost_map=None, dead_days=60):
    """Olu stokta ne kadar para bagli. Isletmecinin en cok tepki
    verdigi sayi genelde bu."""
    d = reorder[reorder["Durum"] == "Ölü stok"].copy()
    if not len(d) or "Eldeki stok" not in d:
        return d, 0.0
    if cost_map:
        d["Bağlı para"] = d["Eldeki stok"] * d["Ürün"].map(cost_map).fillna(0)
        return d, float(d["Bağlı para"].sum())
    return d, 0.0
