"""
Configuration — edit this before running the bot.
"""

# ── Alpaca API Keys ────────────────────────────────────────────────────────────
# Get from: alpaca.markets -> Login -> API Keys
API_KEY    = "YOUR_ALPACA_API_KEY"
API_SECRET = "YOUR_ALPACA_SECRET_KEY"

# ── Mode ───────────────────────────────────────────────────────────────────────
PAPER   = True   # True = paper trading (fake money) | False = real money
DRY_RUN = True   # True = no orders placed at all, just log

# ── Trading ────────────────────────────────────────────────────────────────────
TRADE_AMOUNT  = 1000   # USD per triangle cycle
FEE_RATE      = 0.0    # Alpaca forex = commission free
MIN_PROFIT_PC = 0.05   # Minimum profit % to trigger a trade

# ── Scanner ────────────────────────────────────────────────────────────────────
SCAN_INTERVAL = 2      # Seconds between scans

# ── Triangles ─────────────────────────────────────────────────────────────────
# Format: (currency_A, currency_B, base_currency)
TRIANGLES = [
    ("EUR", "GBP", "USD"),
    ("EUR", "JPY", "USD"),
    ("GBP", "JPY", "USD"),
    ("EUR", "CHF", "USD"),
    ("GBP", "CHF", "USD"),
    ("AUD", "JPY", "USD"),
    ("EUR", "AUD", "USD"),
]
