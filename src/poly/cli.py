"""
Event-Driven Intelligence Engine: Subgraph-Powered Discovery & Monitoring.
High-speed, real-time tracking of Polymarket "Smart Money".
"""

import argparse
import logging
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Set, Tuple

from poly.api.polymarket import PolymarketClient
from poly.intelligence.analyzer import ComprehensiveAnalyzer
from poly.intelligence.scorer import InsiderScorer
from poly.intelligence.clustering import SybilClusterer
from poly.discord.bot import DiscordBotClient

# Silence normal logs
logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("poly").setLevel(logging.CRITICAL)


class EngineState:
    """Manages global state for the event-driven engine."""

    def __init__(self):
        self.master_profiles = {}
        self.resolution_cache = {}
        self.alerted_wallets = set()
        self.processed_event_ids = set()
        self.total_scanned = 0
        self.total_trades_fetched = 0
        self.start_time = time.time()
        self.last_discord_update = 0
        self.last_notified_count = 0


def fetch_resolutions_optimized(
    client: PolymarketClient, condition_ids: Set[str], cache: Dict, workers: int = 64
) -> Dict:
    """Fetch resolutions in parallel with caching."""
    missing_cids = {cid for cid in condition_ids if cid not in cache}
    if not missing_cids:
        return cache

    def fetch_one(cid):
        try:
            return cid, client.get_market_resolution_state(cid)
        except:
            return cid, None

    with ThreadPoolExecutor(max_workers=workers) as executor:
        jobs = [executor.submit(fetch_one, cid) for cid in missing_cids]
        for f in as_completed(jobs):
            cid, res = f.result()
            if res:
                cache[cid] = res
    return cache


def discover_traders_from_events(
    client: PolymarketClient, state: EngineState
) -> List[str]:
    """Scans latest on-chain events via Subgraph to find active traders."""
    try:
        events = client.graphql.get_latest_events(limit=100)
        new_addresses = set()

        for event in events:
            eid = event["id"]
            if eid in state.processed_event_ids:
                continue
            state.processed_event_ids.add(eid)

            for role in ["maker", "taker"]:
                addr = event.get(role, "").lower()
                if addr and addr not in state.master_profiles:
                    new_addresses.add(addr)

        if len(state.processed_event_ids) > 2000:
            state.processed_event_ids = set(list(state.processed_event_ids)[-1000:])

        return list(new_addresses)
    except:
        return []


def analyze_and_score_trader(
    client, address, state, analyzer, scorer, alchemy_key=None, max_trades=200
):
    """Deep analysis of a single newly discovered trader."""
    try:
        # Fetch full history if max_trades is high, otherwise use limited fetch
        if max_trades >= 1000:
            trades = client.get_full_trader_history(address, max_trades=max_trades)
        else:
            trades = client.get_trader_history(address, limit=max_trades)

        if not trades:
            return None

        state.total_trades_fetched += len(trades)

        # 1. Identify markets
        cids = {t["conditionId"] for t in trades if t.get("conditionId")}
        fetch_resolutions_optimized(client, cids, state.resolution_cache)

        # 1b. Fetch market metadata for category detection
        market_metadata = {}
        for cid in cids:
            info = client.get_market_info(cid)
            if info:
                market_metadata[cid] = info

        # 2. Extract profile
        profile = analyzer.analyze_trader(
            address, trades, state.resolution_cache, market_metadata
        )
        true_count = client.get_user_traded_count(address)

        res_trades = [
            tr for tr in trades if tr.get("conditionId") in state.resolution_cache
        ]
        wins = sum(
            1
            for tr in res_trades
            if tr.get("outcomeIndex")
            == state.resolution_cache[tr["conditionId"]].get("winner_idx")
        )

        # We need a proxy for PnL if we don't have the Subgraph working for it yet
        # Using a simplified PnL estimate or leaderboard fallback
        # For now, we'll focus on Winrate and Whale metrics

        # Calculate PnL from resolved trades
        pnl = 0
        for tr in res_trades:
            cid = tr.get("conditionId")
            if not cid or cid not in state.resolution_cache:
                continue
            size = float(tr.get("size", 0))
            price = float(tr.get("price", 0))
            outcome_idx = tr.get("outcomeIndex")
            winner_idx = state.resolution_cache[cid].get("winner_idx")

            if outcome_idx is None or winner_idx is None:
                continue
            if int(outcome_idx) == int(winner_idx):
                pnl += size * (1 - price)  # Win: get (1 - price)
            else:
                pnl -= size * price  # Lose: lose the bet amount

        profile.update(
            {
                "total_trades": len(trades),
                "total_trades_actual": true_count,
                "winrate": wins / len(res_trades) if res_trades else 0,
                "pnl": pnl,
                "volume": sum(
                    float(t.get("size", 0)) * float(t.get("price", 0)) for t in trades
                ),
            }
        )

        # 3. Score
        clusterer = SybilClusterer()
        profile = clusterer.detect_clusters([profile])[0]
        scored_profile = scorer.fit_and_score([profile])[0]

        return scored_profile
    except:
        return None


def run_event_engine(args):
    """Main execution loop for the event-driven engine."""
    client = PolymarketClient()
    discord_bot = DiscordBotClient(token=args.discord_bot_token)
    analyzer = ComprehensiveAnalyzer()
    scorer = InsiderScorer()
    state = EngineState()

    print("\n🚀 EVENT-DRIVEN INTELLIGENCE HUB ONLINE", flush=True)
    print("---------------------------------------", flush=True)

    try:
        iteration = 0
        max_iterations = getattr(args, "max_iterations", None)
        while True:
            iteration += 1

            if max_iterations and iteration > max_iterations:
                print(f"\nReached max iterations ({max_iterations}), shutting down...")
                break

            # 1. EVENT DISCOVERY (Instant)
            new_addrs = discover_traders_from_events(client, state)

            if new_addrs:
                # Limit to configured number of wallets
                max_wallets = getattr(args, "wallets_per_iteration", 10)
                new_addrs = new_addrs[:max_wallets]
                print(
                    f"📦 Discovery: Found {len(new_addrs)} new active wallets. Analyzing..."
                )

                # Analyze new discoveries in parallel
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    jobs = [
                        executor.submit(
                            analyze_trader_wrapper,
                            client,
                            addr,
                            state,
                            analyzer,
                            scorer,
                            args.alchemy_api_key,
                            args.max_trades,
                        )
                        for addr in new_addrs
                    ]

            # 2. STATUS UPDATE
            print(
                f"\r📡 Monitoring {len(state.master_profiles)} High-Signal Traders | Total Trades Processed: {state.total_trades_fetched:,}",
                end="",
                flush=True,
            )

            # 3. Send periodic Discord update
            discord_interval = getattr(args, "discord_interval", 0)
            if discord_interval and discord_interval > 0:
                last_update = getattr(state, "last_discord_update", 0)
                if state.total_trades_fetched - last_update >= discord_interval:
                    if state.master_profiles:
                        discord_bot.send_summary_table(
                            list(state.master_profiles.values())
                        )
                    state.last_discord_update = state.total_trades_fetched

            # 4. Save resolution cache periodically (every iteration) - save after every 3 iterations
            if iteration and iteration % 3 == 0:
                client.save_resolution_cache()

            if new_addrs:
                # Limit to configured number of wallets
                max_wallets = getattr(args, "wallets_per_iteration", 10)
                new_addrs = new_addrs[:max_wallets]
                print(
                    f"📦 Discovery: Found {len(new_addrs)} new active wallets. Analyzing..."
                )

                # Analyze new discoveries in parallel
                with ThreadPoolExecutor(max_workers=args.workers) as executor:
                    jobs = [
                        executor.submit(
                            analyze_trader_wrapper,
                            client,
                            addr,
                            state,
                            analyzer,
                            scorer,
                            args.alchemy_api_key,
                            args.max_trades,
                        )
                        for addr in new_addrs
                    ]

            # 2. STATUS UPDATE
            print(
                f"\r📡 Monitoring {len(state.master_profiles)} High-Signal Traders | Total Trades Processed: {state.total_trades_fetched:,}",
                end="",
                flush=True,
            )

            # Short sleep to prevent CPU spinning
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Save resolution cache on shutdown
        client.save_resolution_cache()
        discord_bot.close()
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Event Intelligence Engine")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-trades", type=int, default=100000)
    parser.add_argument(
        "--alchemy-api-key",
        type=str,
        default=None,
        help="Alchemy API key for blockchain data (default: from ALCHEMY_API_KEY env var)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Max iterations for testing (default: infinite)",
    )
    parser.add_argument(
        "--discord-interval",
        type=int,
        default=0,
        help="Send Discord status update every N trades (default: 0, disabled)",
    )
    parser.add_argument(
        "--wallets-per-iteration",
        type=int,
        default=10,
        help="Number of wallets to analyze per iteration (default: 10)",
    )
    parser.add_argument(
        "--discord-bot-token",
        type=str,
        default=None,
        help="Discord bot token (default: from DISCORD_BOT_TOKEN env var)",
    )
    args = parser.parse_args()
    run_event_engine(args)


if __name__ == "__main__":
    main()
