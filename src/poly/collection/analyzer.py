"""
Numba-optimized trader analysis with IAX (Information Asymmetry Index)
"""

import numpy as np
from numba import jit
from typing import List, Dict, Tuple


@jit(nopython=True, cache=True)
def analyze_trader_by_trades(
    condition_ids: np.ndarray,
    sides: np.ndarray,
    sizes: np.ndarray,
    prices: np.ndarray,
) -> Tuple[int, int, int, float, float, float, float]:
    """
    Analyze trader with numba optimization.
    Returns: (total_trades, total_markets, profitable_trades, winrate, volume, profit, roi)
    """
    n = len(condition_ids)
    if n == 0:
        return (0, 0, 0, 0.0, 0.0, 0.0, 0.0)

    unique_markets = np.unique(condition_ids)
    n_markets = len(unique_markets)

    market_qty = np.zeros(n_markets, dtype=np.float64)
    market_invested = np.zeros(n_markets, dtype=np.float64)
    market_avg_buy = np.zeros(n_markets, dtype=np.float64)

    profitable_trades = 0
    total_volume = 0.0
    total_profit = 0.0

    for i in range(n):
        market_id = condition_ids[i]
        side = sides[i]
        size = sizes[i]
        price = prices[i]

        trade_volume = size * price
        total_volume += trade_volume

        m_idx = -1
        for j in range(n_markets):
            if unique_markets[j] == market_id:
                m_idx = j
                break

        if m_idx < 0:
            continue

        if side == 0:  # BUY
            new_qty = market_qty[m_idx] + size
            new_invested = market_invested[m_idx] + (size * price)
            new_avg_buy = new_invested / new_qty if new_qty > 0 else 0
            market_qty[m_idx] = new_qty
            market_invested[m_idx] = new_invested
            market_avg_buy[m_idx] = new_avg_buy
        else:  # SELL
            if market_qty[m_idx] > 0:
                pnl = (price - market_avg_buy[m_idx]) * size
                total_profit += pnl
                if pnl > 0:
                    profitable_trades += 1

            sell_qty = min(size, market_qty[m_idx])
            new_qty = market_qty[m_idx] - sell_qty
            new_invested = market_invested[m_idx] - (sell_qty * market_avg_buy[m_idx])
            market_qty[m_idx] = new_qty
            market_invested[m_idx] = new_invested
            market_avg_buy[m_idx] = market_avg_buy[m_idx] if new_qty > 0 else 0

    winrate = profitable_trades / n if n > 0 else 0.0
    roi = (total_profit / total_volume) if total_volume > 0 else 0.0

    return (n, n_markets, profitable_trades, winrate, total_volume, total_profit, roi)


def analyze_trader(trades: List[Dict]) -> Dict:
    """Analyze single trader from trade list"""
    if not trades:
        return {"total_trades": 0, "winrate": 0.0, "roi": 0.0, "qualified": False}

    n = len(trades)
    cid_to_int = {}
    int_condition_ids = np.zeros(n, dtype=np.int64)
    sides = np.zeros(n, dtype=np.int32)
    sizes = np.zeros(n, dtype=np.float64)
    prices = np.zeros(n, dtype=np.float64)

    for i, trade in enumerate(trades):
        cid = trade.get("conditionId", "")
        if cid not in cid_to_int:
            cid_to_int[cid] = len(cid_to_int)
        int_condition_ids[i] = cid_to_int[cid]
        sides[i] = 0 if trade.get("side") == "BUY" else 1
        sizes[i] = float(trade.get("size", 0))
        prices[i] = float(trade.get("price", 0))

    total_trades, total_markets, profitable_trades, winrate, volume, profit, roi = (
        analyze_trader_by_trades(int_condition_ids, sides, sizes, prices)
    )

    return {
        "total_trades": int(total_trades),
        "total_markets": int(total_markets),
        "profitable_trades": int(profitable_trades),
        "winrate": float(winrate),
        "total_volume": float(volume),
        "total_profit": float(profit),
        "roi": float(roi),
    }


def get_qualified_traders(
    traders_trades: Dict[str, List[Dict]],
    min_trades: int = 20,
    min_winrate: float = 0.60,
) -> List[Dict]:
    """Filter qualified traders"""
    qualified = []
    for addr, trades in traders_trades.items():
        result = analyze_trader(trades)
        if result["total_trades"] >= min_trades and result["winrate"] >= min_winrate:
            result["address"] = addr
            result["qualified"] = True
            qualified.append(result)
        else:
            result["address"] = addr
            result["qualified"] = False
    return qualified


def get_top_roi_traders(
    market_trades: Dict[str, List[Dict]],
    top_n: int = 200,
) -> List[Dict]:
    """Get top ROI traders per market"""
    results = []

    for market_id, trades in market_trades.items():
        trader_data = {}
        for trade in trades:
            addr = trade.get("proxyWallet", "")
            if addr:
                if addr not in trader_data:
                    trader_data[addr] = []
                trader_data[addr].append(trade)

        trader_rois = []
        for addr, trader_trades in trader_data.items():
            if len(trader_trades) < 1:
                continue

            n = len(trader_trades)
            int_condition_ids = np.zeros(n, dtype=np.int64)
            sides = np.zeros(n, dtype=np.int32)
            sizes = np.zeros(n, dtype=np.float64)
            prices = np.zeros(n, dtype=np.float64)

            for i, t in enumerate(trader_trades):
                int_condition_ids[i] = 0
                sides[i] = 0 if t.get("side") == "BUY" else 1
                sizes[i] = float(t.get("size", 0))
                prices[i] = float(t.get("price", 0))

            _, _, _, winrate, volume, profit, roi = analyze_trader_by_trades(
                int_condition_ids, sides, sizes, prices
            )

            trader_rois.append({
                "address": addr,
                "market_id": market_id,
                "roi": float(roi),
                "winrate": float(winrate),
                "total_trades": n,
            })

        trader_rois.sort(key=lambda x: x["roi"], reverse=True)
        results.extend(trader_rois[:top_n])

    return results
