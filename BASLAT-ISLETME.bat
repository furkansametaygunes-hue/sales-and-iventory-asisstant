@echo off
title Urun Trend Analizi - Isletme Surumu
cd /d "%~dp0"

echo ============================================
echo   URUN TREND ANALIZI (Isletme surumu)
echo ============================================
echo.

REM ---------- 1. Python var mi? ----------
set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto FOUND

py --version >nul 2>&1
if not errorlevel 1 set "PY=py"
if defined PY goto FOUND

echo [HATA] Python bulunamadi.
echo.
echo Yapman gereken:
echo    1. python.org/downloads adresine git
echo    2. Indir ve kur
echo    3. Kurulumda "Add Python to PATH" kutusunu ISARETLE
echo    4. Bilgisayari yeniden baslat
echo    5. Bu dosyayi tekrar cift tikla
echo.
pause
exit /b 1

:FOUND
%PY% --version
echo.

REM ---------- 2. Sanal ortam ----------
if exist ".venv\Scripts\python.exe" goto HASVENV
echo Ilk kurulum yapiliyor, 1-2 dakika surebilir...
echo.
%PY% -m venv .venv
if errorlevel 1 goto VENVFAIL
goto HASVENV

:VENVFAIL
echo.
echo [HATA] Sanal ortam olusturulamadi.
pause
exit /b 1

:HASVENV
set "VPY=.venv\Scripts\python.exe"

REM ---------- 3. Paketler ----------
"%VPY%" -c "import streamlit, plotly, pandas, pyarrow" >nul 2>&1
if not errorlevel 1 goto HASPKGS

echo Paketler kuruluyor, lutfen bekle...
echo.
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto PKGFAIL
echo.
echo Paketler kuruldu.
echo.
goto HASPKGS

:PKGFAIL
echo.
echo [HATA] Paketler kurulamadi. Internet baglantini kontrol et.
pause
exit /b 1

:HASPKGS


REM ---------- 5. Calistir ----------
echo ============================================
echo   Aciliyor... Sol taraftan Excel dosyasini yukle.
echo   Tarayici kendiliginden acilacak.
echo   Kapatmak icin bu pencerede Ctrl+C
echo ============================================
echo.

"%VPY%" -m streamlit run app_business.py

echo.
pause
