"""
Configuration — edit this before running the bot.
"""

# ── Alpaca API Keys ────────────────────────────────────────────────────────────
API_KEY    = "YOUR_ALPACA_API_KEY"
API_SECRET = "YOUR_ALPACA_SECRET_KEY"

# ── Mode ───────────────────────────────────────────────────────────────────────
PAPER   = True   # True = paper trading (fake money) | False = real money
DRY_RUN = True   # True = no orders placed at all, just log

# ── Trading ────────────────────────────────────────────────────────────────────
TRADE_AMOUNT  = 1000   # USD per triangle cycle
FEE_RATE      = 0.0015 # Alpaca crypto fee = 0.15% per trade
MIN_PROFIT_PC = 0.5    # Minimum profit % after fees to trigger a trade

# ── Scanner ────────────────────────────────────────────────────────────────────
SCAN_INTERVAL = 2      # Seconds between scans

# ── Crypto Triangles ──────────────────────────────────────────────────────────
# Format: (asset_A, asset_B, quote_currency)
# Loop:   QUOTE -> A -> B -> QUOTE  (and reverse)
# All pairs must be available on Alpaca crypto
TRIANGLES = [
    ("BTC", "ETH",  "USD"),
    ("BTC", "SOL",  "USD"),
    ("ETH", "SOL",  "USD"),
    ("BTC", "AVAX", "USD"),
    ("ETH", "AVAX", "USD"),
    ("BTC", "LINK", "USD"),
    ("ETH", "LINK", "USD"),
]
