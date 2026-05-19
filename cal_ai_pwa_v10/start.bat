@echo off
title Cal AI — Local Start

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║            Cal AI — Local Start          ║
echo  ║     Push notifications: localhost only   ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── Install dependencies ─────────────────────────────────────────────────────
echo  [1/2] Sinisigurado ang Python dependencies...
pip install -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    echo  [!] pip install failed. Siguraduhing naka-install ang Python at pip.
    pause
    exit /b 1
)
echo  [OK] Dependencies ready.
echo.

REM ── Push notification reminder ────────────────────────────────────────────────
echo  i  PUSH NOTIFICATIONS:
echo     Gamitin ang  http://localhost:5000  sa Chrome o Edge.
echo     (Gumagana ang push notifications sa localhost nang walang HTTPS.)
echo     Para sa ibang devices sa network, kailangan ng HTTPS
echo     (self-signed cert o Cloudflare Tunnel).
echo.

REM ── Start Flask ───────────────────────────────────────────────────────────────
echo  [2/2] Sinisimulan ang Flask sa http://localhost:5000 ...
echo.
echo  ════════════════════════════════════════════
echo   Buksan ang:  http://localhost:5000
echo   Pindutin Ctrl+C para itigil.
echo  ════════════════════════════════════════════
echo.

python app.py

REM Keep window open on error
if errorlevel 1 (
    echo.
    echo  [!] Nag-error ang Flask. Tingnan ang output sa itaas.
    pause
)
