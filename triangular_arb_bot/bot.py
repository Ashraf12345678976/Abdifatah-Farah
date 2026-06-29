"""
Triangular Arbitrage Bot
Scans 3 trading pairs on Binance for profitable loops.

Flow: USDT -> BTC -> ETH -> USDT (or any combo)
"""

import ccxt
import time
import logging
from itertools import permutations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

EXCHANGE_ID   = "binance"          # any ccxt-supported exchange
API_KEY       = "YOUR_API_KEY"     # set your key
API_SECRET    = "YOUR_API_SECRET"  # set your secret
TRADE_AMOUNT  = 100                # USDT to trade per cycle
FEE_RATE      = 0.001              # 0.1% per trade (Binance default)
MIN_PROFIT_PC = 0.3                # only trade if profit > 0.3%
DRY_RUN       = True               # True = simulate only, no real orders
SCAN_INTERVAL = 1                  # seconds between scans

# Triangles to scan: (base, mid, quote) — all priced in USDT
TRIANGLES = [
    ("BTC", "ETH",  "USDT"),
    ("BTC", "BNB",  "USDT"),
    ("ETH", "BNB",  "USDT"),
    ("BTC", "SOL",  "USDT"),
    ("ETH", "SOL",  "USDT"),
    ("BTC", "XRP",  "USDT"),
    ("ETH", "XRP",  "USDT"),
]


# ── Exchange Setup ─────────────────────────────────────────────────────────────

def connect() -> ccxt.Exchange:
    exchange = getattr(ccxt, EXCHANGE_ID)({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    exchange.load_markets()
    log.info(f"Connected to {EXCHANGE_ID} — {len(exchange.markets)} markets loaded")
    return exchange


# ── Price Fetcher ──────────────────────────────────────────────────────────────

def get_prices(exchange: ccxt.Exchange, triangle: tuple) -> dict | None:
    """Fetch bid/ask for the 3 pairs in a triangle."""
    a, b, quote = triangle
    pairs = {
        f"{a}/{quote}": None,
        f"{b}/{quote}": None,
        f"{a}/{b}":     None,
    }

    tickers = {}
    for symbol in pairs:
        if symbol not in exchange.markets:
            return None
        try:
            ticker = exchange.fetch_ticker(symbol)
            tickers[symbol] = {
                "bid": ticker["bid"],
                "ask": ticker["ask"],
            }
        except Exception as e:
            log.warning(f"Failed to fetch {symbol}: {e}")
            return None

    return tickers


# ── Arbitrage Calculator ───────────────────────────────────────────────────────

def calculate_profit(tickers: dict, triangle: tuple, amount_usdt: float) -> dict:
    """
    Two directions per triangle:
      Forward:  USDT -> A -> B -> USDT
      Reverse:  USDT -> B -> A -> USDT
    Returns the best opportunity found.
    """
    a, b, quote = triangle
    pair_a_q = f"{a}/{quote}"   # e.g. BTC/USDT
    pair_b_q = f"{b}/{quote}"   # e.g. ETH/USDT
    pair_a_b = f"{a}/{b}"       # e.g. BTC/ETH

    fee = 1 - FEE_RATE
    results = []

    # ── Direction 1: USDT -> A -> B -> USDT ──────────────────────────────────
    # Step 1: Buy A with USDT          (pay ask)
    qty_a = (amount_usdt / tickers[pair_a_q]["ask"]) * fee
    # Step 2: Sell A, get B            (sell at bid of A/B)
    qty_b = (qty_a * tickers[pair_a_b]["bid"]) * fee
    # Step 3: Sell B for USDT          (sell at bid of B/USDT)
    final_usdt = (qty_b * tickers[pair_b_q]["bid"]) * fee

    profit_pc = ((final_usdt - amount_usdt) / amount_usdt) * 100
    results.append({
        "direction": f"USDT->{a}->{b}->USDT",
        "start":     amount_usdt,
        "end":       round(final_usdt, 4),
        "profit":    round(final_usdt - amount_usdt, 4),
        "profit_pc": round(profit_pc, 4),
        "steps": [
            f"Buy  {a} at {tickers[pair_a_q]['ask']} → {round(qty_a, 6)} {a}",
            f"Sell {a} for {b} at {tickers[pair_a_b]['bid']} → {round(qty_b, 6)} {b}",
            f"Sell {b} for USDT at {tickers[pair_b_q]['bid']} → {round(final_usdt, 4)} USDT",
        ]
    })

    # ── Direction 2: USDT -> B -> A -> USDT ──────────────────────────────────
    # Step 1: Buy B with USDT          (pay ask)
    qty_b2 = (amount_usdt / tickers[pair_b_q]["ask"]) * fee
    # Step 2: Buy A with B             (pay ask of A/B)
    qty_a2 = (qty_b2 / tickers[pair_a_b]["ask"]) * fee
    # Step 3: Sell A for USDT          (sell at bid of A/USDT)
    final_usdt2 = (qty_a2 * tickers[pair_a_q]["bid"]) * fee

    profit_pc2 = ((final_usdt2 - amount_usdt) / amount_usdt) * 100
    results.append({
        "direction": f"USDT->{b}->{a}->USDT",
        "start":     amount_usdt,
        "end":       round(final_usdt2, 4),
        "profit":    round(final_usdt2 - amount_usdt, 4),
        "profit_pc": round(profit_pc2, 4),
        "steps": [
            f"Buy  {b} at {tickers[pair_b_q]['ask']} → {round(qty_b2, 6)} {b}",
            f"Buy  {a} with {b} at {tickers[pair_a_b]['ask']} → {round(qty_a2, 6)} {a}",
            f"Sell {a} for USDT at {tickers[pair_a_q]['bid']} → {round(final_usdt2, 4)} USDT",
        ]
    })

    # Return best direction
    return max(results, key=lambda x: x["profit_pc"])


# ── Order Executor ─────────────────────────────────────────────────────────────

def execute_triangle(exchange: ccxt.Exchange, opportunity: dict, triangle: tuple):
    """Execute or simulate the 3-leg trade."""
    a, b, quote = triangle

    if DRY_RUN:
        log.info("--- DRY RUN (no real orders) ---")
        for step in opportunity["steps"]:
            log.info(f"  SIMULATE: {step}")
        log.info(
            f"  NET: {opportunity['start']} USDT → {opportunity['end']} USDT "
            f"| Profit: {opportunity['profit']} USDT ({opportunity['profit_pc']}%)"
        )
        return

    # Real execution — market orders for speed
    try:
        pair_a_q = f"{a}/{quote}"
        pair_b_q = f"{b}/{quote}"
        pair_a_b = f"{a}/{b}"

        log.info("Executing leg 1...")
        order1 = exchange.create_market_order(pair_a_q, "buy", TRADE_AMOUNT, {"quoteOrderQty": TRADE_AMOUNT})
        qty_a = float(order1["filled"])

        log.info("Executing leg 2...")
        order2 = exchange.create_market_order(pair_a_b, "sell", qty_a)
        qty_b = float(order2["filled"])

        log.info("Executing leg 3...")
        order3 = exchange.create_market_order(pair_b_q, "sell", qty_b)
        final = float(order3["cost"])

        profit = final - TRADE_AMOUNT
        log.info(f"EXECUTED | Profit: {profit:.4f} USDT")

    except Exception as e:
        log.error(f"Execution failed: {e}")


# ── Main Loop ──────────────────────────────────────────────────────────────────

def run():
    exchange = connect()
    scan_count = 0
    opportunities_found = 0

    log.info(f"Starting scan | Amount: {TRADE_AMOUNT} USDT | Min profit: {MIN_PROFIT_PC}% | Dry run: {DRY_RUN}")
    log.info(f"Scanning {len(TRIANGLES)} triangles: {[f'{a}-{b}-{q}' for a,b,q in TRIANGLES]}")
    log.info("-" * 60)

    while True:
        scan_count += 1
        log.info(f"Scan #{scan_count}")

        for triangle in TRIANGLES:
            tickers = get_prices(exchange, triangle)
            if not tickers:
                continue

            opp = calculate_profit(tickers, triangle, TRADE_AMOUNT)

            if opp["profit_pc"] > MIN_PROFIT_PC:
                opportunities_found += 1
                log.info(f"*** OPPORTUNITY FOUND #{opportunities_found} ***")
                log.info(f"    Triangle:  {triangle}")
                log.info(f"    Direction: {opp['direction']}")
                log.info(f"    Profit:    {opp['profit']} USDT ({opp['profit_pc']}%)")
                execute_triangle(exchange, opp, triangle)
            else:
                log.debug(f"  {'-'.join(triangle)} | {opp['direction']} | {opp['profit_pc']}% (below threshold)")

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    run()
