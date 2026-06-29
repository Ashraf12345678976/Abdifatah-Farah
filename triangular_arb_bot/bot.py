"""
Triangular Arbitrage Bot — Alpaca (Crypto)
Scans 3 crypto pairs for profitable triangular loops.

Flow: USD -> BTC -> ETH -> USD (or any combo)
Uses Alpaca's free crypto data + paper/live trading API.
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
BASE_DATA        = "https://data.alpaca.markets/v1beta3/crypto/us/latest/orderbooks"
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

def get_crypto_price(symbol: str) -> dict | None:
    """
    Fetch best bid/ask for a crypto symbol from Alpaca.
    Symbol format: BTC/USD, ETH/USD, ETH/BTC etc.
    """
    params = {"symbols": symbol}
    try:
        r = requests.get(BASE_DATA, headers=headers(), params=params, timeout=5)
        if r.status_code != 200:
            log.warning(f"Price fetch failed for {symbol}: {r.status_code} {r.text}")
            return None
        data = r.json()
        orderbooks = data.get("orderbooks", {})
        if symbol not in orderbooks:
            log.warning(f"No orderbook for {symbol}")
            return None
        ob = orderbooks[symbol]
        bids = ob.get("b", [])
        asks = ob.get("a", [])
        if not bids or not asks:
            log.warning(f"Empty orderbook for {symbol}")
            return None
        bid = float(bids[0]["p"])
        ask = float(asks[0]["p"])
        return {
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2,
        }
    except Exception as e:
        log.warning(f"Error fetching {symbol}: {e}")
        return None


def get_triangle_prices(triangle: tuple) -> dict | None:
    """
    Fetch A/USD and B/USD only — derive A/B cross rate mathematically.
    Alpaca crypto only supports USD-quoted pairs.
    """
    a, b, quote = triangle
    sym_a_q = f"{a}/{quote}"   # e.g. BTC/USD
    sym_b_q = f"{b}/{quote}"   # e.g. ETH/USD

    r1 = get_crypto_price(sym_a_q)
    r2 = get_crypto_price(sym_b_q)

    if not all([r1, r2]):
        return None

    # Derive A/B cross rate from USD quotes
    # BTC/ETH bid = BTC/USD bid / ETH/USD ask  (selling BTC, buying ETH)
    # BTC/ETH ask = BTC/USD ask / ETH/USD bid  (buying BTC, selling ETH)
    sym_a_b = f"{a}/{b}"
    r3 = {
        "bid": r1["bid"] / r2["ask"],
        "ask": r1["ask"] / r2["bid"],
        "mid": r1["mid"] / r2["mid"],
    }

    return {
        sym_a_q: r1,
        sym_b_q: r2,
        sym_a_b: r3,
    }


# ── Arbitrage Calculator ───────────────────────────────────────────────────────

def calculate_profit(prices: dict, triangle: tuple, amount_usd: float) -> dict:
    """
    Check both directions of the triangle.
    Direction 1: USD -> A -> B -> USD
    Direction 2: USD -> B -> A -> USD
    Returns best opportunity.
    """
    a, b, quote = triangle
    sym_a_q = f"{a}/{quote}"
    sym_b_q = f"{b}/{quote}"
    sym_a_b = f"{a}/{b}"
    fee = 1 - FEE_RATE
    results = []

    # ── Direction 1: USD -> A -> B -> USD ────────────────────────────────────
    # Step 1: Buy A with USD    (pay ask of A/USD)
    qty_a  = (amount_usd / prices[sym_a_q]["ask"]) * fee
    # Step 2: Sell A, get B    (sell at bid of A/B)
    qty_b  = (qty_a * prices[sym_a_b]["bid"]) * fee
    # Step 3: Sell B for USD   (sell at bid of B/USD)
    final  = (qty_b * prices[sym_b_q]["bid"]) * fee

    profit_pc = ((final - amount_usd) / amount_usd) * 100
    results.append({
        "direction": f"USD->{a}->{b}->USD",
        "start":     amount_usd,
        "end":       round(final, 4),
        "profit":    round(final - amount_usd, 4),
        "profit_pc": round(profit_pc, 6),
        "steps": [
            f"Buy  {a}  @ ${prices[sym_a_q]['ask']:,.4f}  → {round(qty_a, 6)} {a}",
            f"Sell {a} for {b} @ {prices[sym_a_b]['bid']:.6f} → {round(qty_b, 6)} {b}",
            f"Sell {b}  @ ${prices[sym_b_q]['bid']:,.4f}  → ${round(final, 4)}",
        ]
    })

    # ── Direction 2: USD -> B -> A -> USD ────────────────────────────────────
    # Step 1: Buy B with USD    (pay ask of B/USD)
    qty_b2 = (amount_usd / prices[sym_b_q]["ask"]) * fee
    # Step 2: Buy A with B      (pay ask of A/B)
    qty_a2 = (qty_b2 / prices[sym_a_b]["ask"]) * fee
    # Step 3: Sell A for USD    (sell at bid of A/USD)
    final2 = (qty_a2 * prices[sym_a_q]["bid"]) * fee

    profit_pc2 = ((final2 - amount_usd) / amount_usd) * 100
    results.append({
        "direction": f"USD->{b}->{a}->USD",
        "start":     amount_usd,
        "end":       round(final2, 4),
        "profit":    round(final2 - amount_usd, 4),
        "profit_pc": round(profit_pc2, 6),
        "steps": [
            f"Buy  {b}  @ ${prices[sym_b_q]['ask']:,.4f}  → {round(qty_b2, 6)} {b}",
            f"Buy  {a} with {b} @ {prices[sym_a_b]['ask']:.6f} → {round(qty_a2, 6)} {a}",
            f"Sell {a}  @ ${prices[sym_a_q]['bid']:,.4f}  → ${round(final2, 4)}",
        ]
    })

    return max(results, key=lambda x: x["profit_pc"])


# ── Order Executor ─────────────────────────────────────────────────────────────

def place_order(symbol: str, side: str, qty: float):
    """Place a market order on Alpaca crypto."""
    payload = {
        "symbol":        symbol,
        "qty":           str(round(qty, 8)),
        "side":          side,
        "type":          "market",
        "time_in_force": "ioc",
    }
    r = requests.post(f"{trade_url()}/orders", headers=headers(), json=payload)
    if r.status_code not in (200, 201):
        raise Exception(f"Order failed {symbol} {side}: {r.status_code} {r.text}")
    return r.json()


def execute_triangle(opportunity: dict, triangle: tuple):
    a, b, quote = triangle
    sym_a_q = f"{a}/{quote}"
    sym_b_q = f"{b}/{quote}"
    sym_a_b = f"{a}/{b}"

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
        if opportunity["direction"].startswith(f"USD->{a}"):
            log.info("Leg 1: Buy A with USD")
            o1 = place_order(sym_a_q, "buy", TRADE_AMOUNT / opportunity["start"])
            qty_a = float(o1.get("filled_qty", 0))

            log.info("Leg 2: Sell A for B")
            o2 = place_order(sym_a_b, "sell", qty_a)
            qty_b = float(o2.get("filled_qty", 0))

            log.info("Leg 3: Sell B for USD")
            o3 = place_order(sym_b_q, "sell", qty_b)
        else:
            log.info("Leg 1: Buy B with USD")
            o1 = place_order(sym_b_q, "buy", TRADE_AMOUNT / opportunity["start"])
            qty_b = float(o1.get("filled_qty", 0))

            log.info("Leg 2: Buy A with B")
            o2 = place_order(sym_a_b, "buy", qty_b)
            qty_a = float(o2.get("filled_qty", 0))

            log.info("Leg 3: Sell A for USD")
            o3 = place_order(sym_a_q, "sell", qty_a)

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
            a, b, quote = triangle
            label = f"{quote}-{a}-{b}"

            prices = get_triangle_prices(triangle)
            if not prices:
                log.warning(f"  {label} | Could not fetch prices, skipping")
                continue

            opp = calculate_profit(prices, triangle, TRADE_AMOUNT)

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
