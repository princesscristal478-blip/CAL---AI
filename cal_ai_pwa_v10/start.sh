#!/bin/bash
# Cal AI — Local Start Script
# Para sa Mac at Linux (walang ngrok)

set -e

echo ""
echo " ╔══════════════════════════════════════════╗"
echo " ║            Cal AI — Local Start          ║"
echo " ║     Push notifications: localhost only   ║"
echo " ╚══════════════════════════════════════════╝"
echo ""

# ── Install dependencies ──────────────────────────────────────────────────────
echo " [1/2] Sinisigurado ang Python dependencies..."
pip install -r requirements.txt -q --disable-pip-version-check
echo " [OK] Dependencies ready."
echo ""

# ── Push notification reminder ────────────────────────────────────────────────
echo " ℹ️  PUSH NOTIFICATIONS:"
echo "    Gamitin ang  http://localhost:5000  sa Chrome o Edge."
echo "    (Gumagana ang push notifications sa localhost nang walang HTTPS.)"
echo "    Para sa ibang devices sa network, kailangan mong mag-setup ng HTTPS"
echo "    gamit ang self-signed cert o local tunnel tulad ng Cloudflare Tunnel."
echo ""

# ── Start Flask ───────────────────────────────────────────────────────────────
echo " [2/2] Sinisimulan ang Flask sa http://localhost:5000 ..."
echo ""
echo " ════════════════════════════════════════════"
echo "  Buksan ang:  http://localhost:5000"
echo "  Pindutin Ctrl+C para itigil."
echo " ════════════════════════════════════════════"
echo ""

python app.py
