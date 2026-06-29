"""
Triangular Arbitrage Bot — Alpaca (Forex)
Scans 3 forex pairs for profitable triangular loops.

Flow: USD -> EUR -> GBP -> USD (or any combo)
Uses Alpaca's paper/live trading API.
"""

import time
import logging
import requests
from config import (
    API_KEY, API_SECRET, PAPER, DRY_RUN,
    TRADE_AMOUNT, FEE_RATE, MIN_PROFIT_PC,
    SCAN_INTERVAL, TRIANGLES
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Alpaca base URLs
BASE_DATA        = "https://data.alpaca.markets/v1beta3/forex/snapshots"
BASE_TRADE_PAPER = "https://paper-api.alpaca.markets/v2"
BASE_TRADE_LIVE  = "https://api.alpaca.markets/v2"


# ── API Helpers ────────────────────────────────────────────────────────────────

def headers() -> dict:
    return {
        "APCA-API-KEY-ID":     API_KEY,
        "APCA-API-SECRET-KEY": API_SECRET,
        "Content-Type":        "application/json",
    }

def trade_url() -> str:
    return BASE_TRADE_PAPER if PAPER else BASE_TRADE_LIVE


# ── Connection Check ───────────────────────────────────────────────────────────

def check_connection():
    url = f"{trade_url()}/account"
    r = requests.get(url, headers=headers())
    if r.status_code != 200:
        raise Exception(f"Alpaca connection failed: {r.status_code} {r.text}")
    acct = r.json()
    mode = "PAPER" if PAPER else "LIVE"
    log.info(f"Connected to Alpaca [{mode}]")
    log.info(f"Account: {acct.get('id','?')} | Buying power: ${float(acct.get('buying_power',0)):,.2f}")
    return acct


# ── Price Fetcher ──────────────────────────────────────────────────────────────

def get_forex_rate(from_ccy: str, to_ccy: str) -> dict | None:
    """
    Fetch live bid/ask from Alpaca forex data feed.
    Returns {"bid": float, "ask": float} or None.
    """
    pair = f"{from_ccy}{to_ccy}"   # Alpaca format: EURUSD (no slash)
    params = {"symbols": pair}
    try:
        r = requests.get(BASE_DATA, headers=headers(), params=params, timeout=5)
        if r.status_code != 200:
            log.warning(f"Price fetch failed for {pair}: {r.status_code} {r.text}")
            return None
        data = r.json()
        snapshots = data.get("snapshots", {})
        if pair not in snapshots:
            log.warning(f"No rate returned for {pair}")
            return None
        quote = snapshots[pair].get("latestQuote", {})
        bid = float(quote.get("bp", 0))
        ask = float(quote.get("ap", 0))
        if bid == 0 or ask == 0:
            log.warning(f"Zero price for {pair}")
            return None
        return {
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2,
        }
    except Exception as e:
        log.warning(f"Error fetching {pair}: {e}")
        return None


def get_triangle_prices(triangle: tuple) -> dict | None:
    """Fetch all 3 rates needed for a triangle."""
    a, b, base = triangle

    # Pairs needed:
    #   base/a   e.g. USD/EUR
    #   a/b      e.g. EUR/GBP
    #   b/base   e.g. GBP/USD
    r1 = get_forex_rate(base, a)    # USD -> A
    r2 = get_forex_rate(a, b)       # A   -> B
    r3 = get_forex_rate(b, base)    # B   -> USD

    if not all([r1, r2, r3]):
        return None

    return {
        f"{base}/{a}": r1,
        f"{a}/{b}":    r2,
        f"{b}/{base}": r3,
    }


# ── Arbitrage Calculator ───────────────────────────────────────────────────────

def calculate_profit(rates: dict, triangle: tuple, amount_usd: float) -> dict:
    """
    Check both directions of the triangle.
    Direction 1: USD -> A -> B -> USD
    Direction 2: USD -> B -> A -> USD
    Returns best opportunity.
    """
    a, b, base = triangle
    fee = 1 - FEE_RATE
    results = []

    # ── Direction 1: USD -> A -> B -> USD ────────────────────────────────────
    # Buy A with USD  (pay ask of USD/A)
    r_base_a = rates[f"{base}/{a}"]
    r_a_b    = rates[f"{a}/{b}"]
    r_b_base = rates[f"{b}/{base}"]

    qty_a    = (amount_usd * r_base_a["bid"]) * fee    # USD -> A (buy A, USD weakens → use bid)
    qty_b    = (qty_a     * r_a_b["bid"])    * fee     # A   -> B
    final    = (qty_b     * r_b_base["bid"]) * fee     # B   -> USD

    profit_pc = ((final - amount_usd) / amount_usd) * 100
    results.append({
        "direction": f"USD->{a}->{b}->USD",
        "start":     amount_usd,
        "end":       round(final, 4),
        "profit":    round(final - amount_usd, 4),
        "profit_pc": round(profit_pc, 6),
        "steps": [
            f"Convert USD → {a}  @ {r_base_a['bid']}  → {round(qty_a, 4)} {a}",
            f"Convert {a}  → {b}  @ {r_a_b['bid']}    → {round(qty_b, 4)} {b}",
            f"Convert {b}  → USD @ {r_b_base['bid']}  → ${round(final, 4)}",
        ]
    })

    # ── Direction 2: USD -> B -> A -> USD ────────────────────────────────────
    # Reverse: buy B first, then convert to A, then back to USD
    r_base_b = {"bid": 1 / r_b_base["ask"], "ask": 1 / r_b_base["bid"]}  # invert GBP/USD -> USD/GBP
    r_b_a    = {"bid": 1 / r_a_b["ask"],    "ask": 1 / r_a_b["bid"]}     # invert EUR/GBP -> GBP/EUR
    r_a_base = {"bid": 1 / r_base_a["ask"], "ask": 1 / r_base_a["bid"]}  # invert USD/EUR -> EUR/USD

    qty_b2   = (amount_usd * r_base_b["bid"]) * fee
    qty_a2   = (qty_b2     * r_b_a["bid"])    * fee
    final2   = (qty_a2     * r_a_base["bid"]) * fee

    profit_pc2 = ((final2 - amount_usd) / amount_usd) * 100
    results.append({
        "direction": f"USD->{b}->{a}->USD",
        "start":     amount_usd,
        "end":       round(final2, 4),
        "profit":    round(final2 - amount_usd, 4),
        "profit_pc": round(profit_pc2, 6),
        "steps": [
            f"Convert USD → {b}  @ {r_base_b['bid']:.6f} → {round(qty_b2, 4)} {b}",
            f"Convert {b}  → {a}  @ {r_b_a['bid']:.6f}   → {round(qty_a2, 4)} {a}",
            f"Convert {a}  → USD @ {r_a_base['bid']:.6f} → ${round(final2, 4)}",
        ]
    })

    return max(results, key=lambda x: x["profit_pc"])


# ── Order Executor ─────────────────────────────────────────────────────────────

def place_forex_order(from_ccy: str, to_ccy: str, qty: float, side: str):
    """Place a market order on Alpaca forex."""
    symbol = f"{from_ccy}{to_ccy}"
    payload = {
        "symbol":        symbol,
        "qty":           str(round(qty, 2)),
        "side":          side,
        "type":          "market",
        "time_in_force": "ioc",   # immediate or cancel
    }
    r = requests.post(f"{trade_url()}/orders", headers=headers(), json=payload)
    if r.status_code not in (200, 201):
        raise Exception(f"Order failed {symbol}: {r.status_code} {r.text}")
    return r.json()


def execute_triangle(opportunity: dict, triangle: tuple):
    a, b, base = triangle

    if DRY_RUN:
        log.info("--- DRY RUN (no real orders placed) ---")
        for step in opportunity["steps"]:
            log.info(f"  SIMULATE: {step}")
        log.info(
            f"  NET: ${opportunity['start']} → ${opportunity['end']} "
            f"| Profit: ${opportunity['profit']} ({opportunity['profit_pc']}%)"
        )
        return

    try:
        log.info("Executing leg 1...")
        o1 = place_forex_order(base, a, TRADE_AMOUNT, "buy")
        qty_a = float(o1.get("filled_qty", 0))

        log.info("Executing leg 2...")
        o2 = place_forex_order(a, b, qty_a, "buy")
        qty_b = float(o2.get("filled_qty", 0))

        log.info("Executing leg 3...")
        o3 = place_forex_order(b, base, qty_b, "sell")

        log.info(f"Triangle executed | Orders: {o1['id']}, {o2['id']}, {o3['id']}")

    except Exception as e:
        log.error(f"Execution error: {e}")


# ── Main Loop ──────────────────────────────────────────────────────────────────

def run():
    check_connection()

    scan_count = 0
    opportunities_found = 0
    mode = "PAPER" if PAPER else "LIVE"

    log.info(f"Starting scan | ${TRADE_AMOUNT} per cycle | Min profit: {MIN_PROFIT_PC}% | {mode} | Dry run: {DRY_RUN}")
    log.info(f"Scanning {len(TRIANGLES)} triangles")
    log.info("-" * 60)

    while True:
        scan_count += 1
        log.info(f"--- Scan #{scan_count} ---")

        for triangle in TRIANGLES:
            a, b, base = triangle
            label = f"{base}-{a}-{b}"

            rates = get_triangle_prices(triangle)
            if not rates:
                log.warning(f"  {label} | Could not fetch prices, skipping")
                continue

            opp = calculate_profit(rates, triangle, TRADE_AMOUNT)

            if opp["profit_pc"] > MIN_PROFIT_PC:
                opportunities_found += 1
                log.info(f"*** OPPORTUNITY #{opportunities_found} | {label} ***")
                log.info(f"    Direction: {opp['direction']}")
                log.info(f"    Profit:    ${opp['profit']} ({opp['profit_pc']}%)")
                execute_triangle(opp, triangle)
            else:
                log.info(f"  {label} | {opp['direction']} | {opp['profit_pc']}% (below {MIN_PROFIT_PC}%)")

        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    run()
