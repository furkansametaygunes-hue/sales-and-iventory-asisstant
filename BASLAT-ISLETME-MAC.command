#!/bin/bash
cd "$(dirname "$0")" || exit 1

echo "============================================"
echo "  URUN TREND ANALIZI (Isletme surumu)"
echo "============================================"
echo

# ---- 1. Python var mi? ----
if command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    echo "[HATA] Python bulunamadi."
    echo
    echo "Yapman gereken:"
    echo "  1. python.org/downloads adresine git"
    echo "  2. macOS surumunu indir ve kur"
    echo "  3. Bu dosyayi tekrar cift tikla"
    echo
    read -r -p "Kapatmak icin Enter'a bas..."
    exit 1
fi

echo "Python bulundu: $($PY --version 2>&1)"
echo

# ---- 2. Sanal ortam ----
if [ ! -x ".venv/bin/python" ]; then
    echo "Ilk kurulum yapiliyor, 1-2 dakika surebilir..."
    echo
    $PY -m venv .venv || { echo "[HATA] Sanal ortam olusturulamadi."; read -r; exit 1; }
fi

VPY=".venv/bin/python"

# ---- 3. Paketler ----
if ! $VPY -c "import streamlit, plotly, pandas, pyarrow" >/dev/null 2>&1; then
    echo "Paketler kuruluyor, lutfen bekle..."
    echo
    $VPY -m pip install --upgrade pip --quiet
    $VPY -m pip install -r requirements.txt || {
        echo; echo "[HATA] Paketler kurulamadi. Internet baglantini kontrol et."
        read -r; exit 1; }
    echo; echo "Paketler kuruldu."; echo
fi

# ---- 5. Calistir ----
echo "============================================"
echo "  Dashboard aciliyor..."
echo "  Tarayici kendiliginden acilacak."
echo "  Kapatmak icin bu pencerede Ctrl+C"
echo "============================================"
echo

$VPY -m streamlit run app_business.py
