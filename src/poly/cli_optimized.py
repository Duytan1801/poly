"""
Optimized Event-Driven Intelligence Engine with batch operations.
High-speed trader analysis using async batch fetching.
"""

import argparse
import logging
import time
import asyncio
from typing import List, Dict, Set
from poly.api.async_client import AsyncPolymarketClient
from poly.intelligence.analyzer import ComprehensiveAnalyzer
from poly.intelligence.scorer import InsiderScorer
from poly.intelligence.clustering import SybilClusterer
from poly.discord.bot import DiscordBotClient
from poly.api.graphql import GraphQLClient

logging.getLogger("httpx").setLevel(logging.CRITICAL)
logging.getLogger("poly").setLevel(logging.CRITICAL)


class OptimizedEngineState:
    """State manager for the optimized engine."""

    def __init__(self):
        self.master_profiles = {}
        self.resolution_cache = {}
        self.market_metadata_cache = {}
        self.alerted_wallets = set()
        self.processed_event_ids = set()
        self.total_scanned = 0
        self.total_trades_fetched = 0
        self.start_time = time.time()
        self.last_discord_update = 0
        self.last_notified_count = 0


async def analyze_and_score_traders_batch(
    async_client: AsyncPolymarketClient,
    addresses: List[str],
    state: OptimizedEngineState,
    analyzer: ComprehensiveAnalyzer,
    scorer: InsiderScorer,
    max_trades: int = 200,
):
    """Analyze multiple traders in parallel with batch operations."""
    try:
        # 1. BATCH: Fetch all trader histories concurrently
        print(f"\n  ⚡ Fetching histories for {len(addresses)} wallets...")
        start = time.time()
        histories = await async_client.fetch_trader_histories_batch(
            addresses, max_trades=max_trades
        )
        fetch_time = time.time() - start
        total_trades = sum(len(h) for h in histories.values())
        print(f"     Fetched {total_trades:,} trades in {fetch_time:.2f}s")
        state.total_trades_fetched += total_trades

        # 2. BATCH: Collect all unique condition IDs
        all_cids = set()
        for trades in histories.values():
            all_cids.update(
                t.get("conditionId") for t in trades if t.get("conditionId")
            )

        # 3. BATCH: Fetch all resolutions concurrently
        if all_cids:
            print(f"  📊 Fetching {len(all_cids)} market resolutions...")
            start = time.time()
            await async_client.get_market_resolutions_batch(
                list(all_cids), state.resolution_cache
            )
            res_time = time.time() - start
            print(f"     Resolutions fetched in {res_time:.2f}s")

        # 4. BATCH: Fetch all market metadata concurrently
        new_cids = [cid for cid in all_cids if cid not in state.market_metadata_cache]
        if new_cids:
            print(f"  📁 Fetching {len(new_cids)} market metadata...")
            start = time.time()
            new_metadata = await async_client.get_market_info_batch(new_cids)
            state.market_metadata_cache.update(new_metadata)
            meta_time = time.time() - start
            print(f"     Metadata fetched in {meta_time:.2f}s")

        # 5. Analyze each trader (can be done in parallel with ThreadPool)
        print(f"  🧠 Analyzing {len(addresses)} traders...")
        start = time.time()
        profiles = []
        for addr in addresses:
            trades = histories.get(addr, [])
            if not trades:
                continue

            profile = analyzer.analyze_trader(
                addr, trades, state.resolution_cache, state.market_metadata_cache
            )

            # Calculate winrate and PnL
            res_trades = [
                tr for tr in trades if tr.get("conditionId") in state.resolution_cache
            ]
            wins = sum(
                1
                for tr in res_trades
                if tr.get("outcomeIndex")
                == state.resolution_cache.get(tr["conditionId"], {}).get("winner_idx")
            )

            # Calculate PnL
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
                    pnl += size * (1 - price)
                else:
                    pnl -= size * price

            profile.update(
                {
                    "total_trades": len(trades),
                    "winrate": wins / len(res_trades) if res_trades else 0,
                    "pnl": pnl,
                    "volume": sum(
                        float(t.get("size", 0)) * float(t.get("price", 0))
                        for t in trades
                    ),
                }
            )

            # 6. Score with clustering (optional, can be batched too)
            # Skip clustering for speed in this optimized version
            scored_profile = scorer.fit_and_score([profile])[0]
            profiles.append(scored_profile)

        analyze_time = time.time() - start
        print(f"     Analyzed in {analyze_time:.2f}s")

        return profiles

    except Exception as e:
        print(f"  ❌ Error in batch analysis: {e}")
        return []


async def discover_traders_from_events(
    graphql_client: GraphQLClient, state: OptimizedEngineState, limit: int = 100
) -> List[str]:
    """Discover new traders from recent on-chain events."""
    try:
        events = graphql_client.get_latest_events(limit=limit)
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

        # Limit event IDs cache
        if len(state.processed_event_ids) > 2000:
            state.processed_event_ids = set(list(state.processed_event_ids)[-1000:])

        return list(new_addresses)
    except Exception as e:
        print(f"Discovery error: {e}")
        return []


async def run_optimized_event_engine(args):
    """Main execution loop with batch optimizations."""
    async with AsyncPolymarketClient() as async_client:
        graphql_client = GraphQLClient()
        analyzer = ComprehensiveAnalyzer()
        scorer = InsiderScorer()
        state = OptimizedEngineState()

        # Make Discord optional for testing
        try:
            discord_bot = DiscordBotClient()
        except ValueError:
            print("\n⚠️  Discord bot not configured (DISCORD_BOT_TOKEN not set)")
            print("   Running in analysis-only mode...\n")
            discord_bot = None

        print("\n🚀 OPTIMIZED EVENT-DRIVEN INTELLIGENCE HUB ONLINE")
        print("=" * 60)
        print(f"Batch size: {args.wallets_per_iteration}")
        print(f"Max trades per wallet: {args.max_trades}")
        print("=" * 60)

        try:
            iteration = 0
            max_iterations = getattr(args, "max_iterations", None)

            while True:
                iteration += 1

                if max_iterations and iteration > max_iterations:
                    print(
                        f"\nReached max iterations ({max_iterations}), shutting down..."
                    )
                    break

                # 1. DISCOVER new wallets
                print(f"\n🔄 Iteration {iteration}")
                new_addrs = await discover_traders_from_events(
                    graphql_client, state, limit=100
                )

                if new_addrs:
                    # Limit to configured batch size
                    new_addrs = new_addrs[: args.wallets_per_iteration]

                    # 2. BATCH ANALYZE
                    print(f"\n📦 Analyzing batch of {len(new_addrs)} wallets...")
                    batch_start = time.time()

                    profiles = await analyze_and_score_traders_batch(
                        async_client,
                        new_addrs,
                        state,
                        analyzer,
                        scorer,
                        args.max_trades,
                    )

                    batch_time = time.time() - batch_start

                    # 3. Process results
                    for profile in profiles:
                        state.total_scanned += 1
                        level = profile.get("level", "NONE")

                        # Add HIGH/CRITICAL to monitoring
                        if level in ["HIGH", "CRITICAL"]:
                            addr = profile["address"].lower()
                            state.master_profiles[addr] = profile

                            # Log detection
                            score = profile.get(
                                "risk_score", profile.get("total_score", 0)
                            )
                            print(
                                f"  🎯 DETECTED: {addr[:20]}... | "
                                f"Score: {score:.1f}/10 | Level: {level}"
                            )

                    print(f"\n  ⏱️  Batch time: {batch_time:.2f}s")
                    print(
                        f"  📈 Throughput: {len(new_addrs) / batch_time:.1f} wallets/s"
                    )

                    # 4. Discord notification every 10 high-signal traders
                    if discord_bot:
                        current_count = len(state.master_profiles)
                        if (
                            current_count > 0
                            and current_count % 10 == 0
                            and state.last_notified_count < current_count
                        ):
                            state.last_notified_count = current_count
                            print(
                                f"\n📱 Discord: Sending update ({current_count} monitored)...",
                                flush=True,
                            )
                            try:
                                discord_bot.send_summary_table(
                                    list(state.master_profiles.values())
                                )
                            except Exception as e:
                                print(f"\n❌ Discord error: {e}", flush=True)

                # 5. Status update
                elapsed = time.time() - state.start_time
                print(
                    f"\n📡 Monitoring {len(state.master_profiles)} High-Signal Traders | "
                    f"Total Trades: {state.total_trades_fetched:,} | "
                    f"Elapsed: {elapsed:.0f}s"
                )

                # Sleep to prevent CPU spinning
                await asyncio.sleep(2)

        except KeyboardInterrupt:
            print("\n\nShutting down...")
        finally:
            if discord_bot:
                discord_bot.close()
            graphql_client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Optimized Event Intelligence Engine with Batch Operations"
    )
    parser.add_argument(
        "--wallets-per-iteration",
        type=int,
        default=10,
        help="Number of wallets to analyze per batch (default: 10)",
    )
    parser.add_argument(
        "--max-trades",
        type=int,
        default=100000,
        help="Max trades per wallet (default: 100000)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Max iterations for testing (default: infinite)",
    )
    args = parser.parse_args()

    asyncio.run(run_optimized_event_engine(args))


if __name__ == "__main__":
    main()
