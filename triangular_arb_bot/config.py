"""
Configuration file — edit this before running the bot.
"""

# ── Exchange ───────────────────────────────────────────────────────────────────
EXCHANGE_ID = "binance"       # Options: binance, kraken, coinbasepro, kucoin
API_KEY     = "YOUR_API_KEY"
API_SECRET  = "YOUR_API_SECRET"

# ── Trading ────────────────────────────────────────────────────────────────────
TRADE_AMOUNT  = 100    # USDT per triangle cycle
FEE_RATE      = 0.001  # 0.1% = Binance spot default; 0.0% if you hold BNB discount
MIN_PROFIT_PC = 0.3    # Minimum profit % after fees to trigger a trade
DRY_RUN       = True   # ALWAYS test with True first!

# ── Scanner ────────────────────────────────────────────────────────────────────
SCAN_INTERVAL = 1      # Seconds between full scans

# ── Triangles to scan ─────────────────────────────────────────────────────────
# Format: (asset_A, asset_B, quote_currency)
# Loop:   QUOTE -> A -> B -> QUOTE  (and reverse)
TRIANGLES = [
    ("BTC", "ETH",  "USDT"),
    ("BTC", "BNB",  "USDT"),
    ("ETH", "BNB",  "USDT"),
    ("BTC", "SOL",  "USDT"),
    ("ETH", "SOL",  "USDT"),
    ("BTC", "XRP",  "USDT"),
    ("ETH", "XRP",  "USDT"),
    ("BTC", "ADA",  "USDT"),
    ("ETH", "ADA",  "USDT"),
    ("BTC", "DOGE", "USDT"),
]
