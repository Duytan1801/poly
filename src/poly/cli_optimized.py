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
from poly.monitoring import RealTimeTradeMonitor, PositionMonitor, MarketVolumeMonitor
from poly.cache import RedisCache

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
        self.critical_count = 0
        self.start_time = time.time()
        self.last_discord_update = 0
        self.last_notified_count = 0
        self.next_notification_threshold = (
            10  # Notify when CRITICAL count >= 10, then advance to 20, 30, etc.
        )


async def analyze_and_score_traders_batch(
    async_client: AsyncPolymarketClient,
    addresses: List[str],
    state: OptimizedEngineState,
    analyzer: ComprehensiveAnalyzer,
    scorer: InsiderScorer,
    max_trades: int = 200,
    min_trade_size: float = 1000.0,
    leaderboard_cache: Dict = {},
):
    """Analyze multiple traders in parallel with batch operations."""
    try:
        # 1. BATCH: Fetch all trader histories concurrently with server-side filtering
        print(
            f"\n  ⚡ Fetching histories for {len(addresses)} wallets (min_size=${min_trade_size})..."
        )
        start = time.time()
        histories = await async_client.fetch_trader_histories_batch(
            addresses, max_trades=max_trades, min_size=min_trade_size
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

        # 4. BATCH: Fetch all market metadata concurrently (with liquidity filtering and prioritization)
        new_cids = [cid for cid in all_cids if cid not in state.market_metadata_cache]
        if new_cids:
            print(f"  📁 Fetching {len(new_cids)} market metadata...")
            start = time.time()
            new_metadata = await async_client.get_market_info_batch(new_cids)

            # Filter by liquidity threshold (>= $50k)
            liquid_metadata = {
                cid: meta
                for cid, meta in new_metadata.items()
                if meta.get("liquidity", 0) >= 50000
            }

            filtered_count = len(new_metadata) - len(liquid_metadata)
            if filtered_count > 0:
                print(
                    f"     Filtered out {filtered_count} low-liquidity markets (<$50k)"
                )

            state.market_metadata_cache.update(liquid_metadata)
            meta_time = time.time() - start
            print(f"     Metadata fetched in {meta_time:.2f}s")

        # 4b. Prioritize markets by signal strength (optional optimization)
        # Only analyze top 70% of markets by liquidity + volume + category score
        from poly.intelligence.prioritization import prioritize_markets

        prioritized_cids = prioritize_markets(
            list(all_cids), state.market_metadata_cache, top_percent=0.7
        )

        if len(prioritized_cids) < len(all_cids):
            print(
                f"  🎯 Prioritized {len(prioritized_cids)}/{len(all_cids)} markets by signal strength"
            )

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

            # Use pre-computed PnL from leaderboard if available
            addr_lower = addr.lower()
            if leaderboard_cache and addr_lower in leaderboard_cache:
                pnl = leaderboard_cache[addr_lower].get("pnl", 0)
                print(f"     Using cached PnL for {addr[:8]}... = ${pnl:,.2f}")
            else:
                # Fallback: Calculate PnL manually
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
    """Main execution loop with batch optimizations and real-time monitoring."""
    # Initialize Redis cache (optional, but enabled by default)
    redis_cache = None
    if getattr(args, "use_redis", True):  # Default to True if not specified
        print("\n🗄️  Initializing Redis cache...")
        redis_cache = RedisCache(
            host=getattr(args, "redis_host", "localhost"),
            port=getattr(args, "redis_port", 6379),
            enabled=True,
        )
        if redis_cache.enabled:
            print("   ✅ Redis cache connected")
        else:
            print("   ⚠️  Redis unavailable, running without cache")
            redis_cache = None
    else:
        print("\n   Redis caching disabled by user")
    if args.use_redis:
        print("\n🗄️  Initializing Redis cache...")
        redis_cache = RedisCache(
            host=args.redis_host, port=args.redis_port, enabled=True
        )
        if redis_cache.enabled:
            print("   ✅ Redis cache connected")
        else:
            print("   ⚠️  Redis unavailable, running without cache")
            redis_cache = None

    async with AsyncPolymarketClient(redis_cache=redis_cache) as async_client:
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

        # Initialize monitors if Discord is available
        trade_monitor = None
        position_monitor = None
        market_volume_monitor = None

        if discord_bot:
            trade_monitor = RealTimeTradeMonitor(
                discord_bot, state, poll_interval=args.trade_poll_interval
            )
            position_monitor = PositionMonitor(
                discord_bot, state, poll_interval=args.position_poll_interval
            )
            market_volume_monitor = MarketVolumeMonitor(
                discord_bot,
                state,
                poll_interval=args.market_monitor_interval,
                market_refresh_interval=args.market_refresh_interval,
            )

        print("\n🚀 OPTIMIZED EVENT-DRIVEN INTELLIGENCE HUB ONLINE")
        print("=" * 80)
        print(f"Batch size: {args.wallets_per_iteration}")
        print(f"Max trades per wallet: {args.max_trades}")
        if trade_monitor:
            print(f"Real-time trade monitoring: {args.trade_poll_interval}s")
        if position_monitor:
            print(f"Position monitoring: {args.position_poll_interval}s")
        if market_volume_monitor:
            print(f"Market volume monitoring: {args.market_monitor_interval}s")
        print("=" * 80)

        # Create asyncio tasks for concurrent monitoring
        tasks = []

        # Create monitor tasks
        if trade_monitor:
            trade_monitor_task = asyncio.create_task(
                trade_monitor.monitor_continuously(), name="trade_monitor"
            )
            tasks.append(trade_monitor_task)

        if position_monitor:
            position_monitor_task = asyncio.create_task(
                position_monitor.monitor_continuously(), name="position_monitor"
            )
            tasks.append(position_monitor_task)

        if market_volume_monitor:
            market_volume_task = asyncio.create_task(
                market_volume_monitor.monitor_continuously(), name="market_volume"
            )
            tasks.append(market_volume_task)

        # Create discovery loop task
        discovery_task = asyncio.create_task(
            discovery_loop(
                args, async_client, graphql_client, analyzer, scorer, state, discord_bot
            ),
            name="discovery",
        )
        tasks.append(discovery_task)

        # Wait for all tasks or cancellation
        try:
            # Wait for discovery task (this is the main one)
            await discovery_task
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down gracefully...")
        finally:
            # Cancel all background tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            if discord_bot:
                discord_bot.close()
            graphql_client.close()

            print("\n✅ All monitors stopped")


async def discovery_loop(
    args, async_client, graphql_client, analyzer, scorer, state, discord_bot
):
    """Main discovery and analysis loop with WebSocket streaming option."""
    iteration = 0
    max_iterations = getattr(args, "max_iterations", None)

    # Fetch leaderboard once for PnL caching
    print("\n📊 Fetching leaderboard for PnL caching...")
    leaderboard_data = await async_client.get_leaderboard(limit=2000)
    leaderboard_cache = {
        entry.get("proxyWallet", "").lower(): entry
        for entry in leaderboard_data
        if entry.get("proxyWallet")
    }
    print(f"   Cached PnL for {len(leaderboard_cache)} traders from leaderboard")

    # Use WebSocket streaming if available, otherwise fall back to GraphQL polling
    use_websocket = getattr(args, "use_websocket", True)  # Default to True
    websocket_monitor = None
    address_queue = None  # Initialize here to avoid unbound variable

    if use_websocket:
        print("\n🔌 Initializing WebSocket streaming...")
        try:
            from poly.api.websocket_client import WebSocketTradeMonitor

            # Queue to store new addresses from WebSocket events
            address_queue = asyncio.Queue()

            async def handle_new_addresses(addresses):
                """Handle new addresses from WebSocket events."""
                if address_queue:
                    for addr in addresses:
                        await address_queue.put(addr)

            websocket_monitor = WebSocketTradeMonitor(
                on_new_address=handle_new_addresses
            )
            print("   ✅ WebSocket initialized, connecting...")

            # Start WebSocket in background
            websocket_task = asyncio.create_task(websocket_monitor.start())
        except ImportError:
            print(
                "   ⚠️  WebSocket module not available, falling back to GraphQL polling"
            )
            use_websocket = False
        except Exception as e:
            print(f"   ⚠️  WebSocket error: {e}, falling back to GraphQL polling")
            use_websocket = False

    try:
        # If WebSocket is being used, ensure we have an address queue
        if use_websocket and address_queue is None:
            address_queue = asyncio.Queue()

        while True:
            iteration += 1

            if max_iterations and iteration > max_iterations:
                print(
                    f"\n✅ Reached max iterations ({max_iterations}), shutting down..."
                )
                break

            # 1. DISCOVER new wallets - use WebSocket or GraphQL
            print(f"\n🔄 Iteration {iteration}")

            new_addrs = []
            if use_websocket and address_queue:
                # Get addresses from WebSocket queue (non-blocking)
                try:
                    # Collect addresses from WebSocket queue
                    while True:
                        try:
                            addr = address_queue.get_nowait()
                            new_addrs.append(addr)
                        except asyncio.QueueEmpty:
                            break
                except:
                    pass  # No addresses available

            # If no addresses from WebSocket, or WebSocket not used, fall back to GraphQL
            if not new_addrs:
                if use_websocket:
                    # Still need some addresses occasionally, fall back to GraphQL briefly
                    new_addrs = await discover_traders_from_events(
                        graphql_client,
                        state,
                        limit=20,  # Smaller limit for backup
                    )
                else:
                    # Traditional GraphQL polling
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
                    min_trade_size=args.min_trade_size,
                    leaderboard_cache=leaderboard_cache,
                )

                batch_time = time.time() - batch_start

                # 3. Process results
                for profile in profiles:
                    state.total_scanned += 1
                    level = profile.get("level", "NONE")

                    # Add CRITICAL to monitoring
                    if level == "CRITICAL":
                        addr = profile["address"].lower()
                        state.master_profiles[addr] = profile
                        state.critical_count += 1

                        # Log detection
                        score = profile.get("risk_score", profile.get("total_score", 0))
                        print(
                            f"  🎯 DETECTED: {addr[:20]}... | "
                            f"Score: {score:.1f}/10 | Level: {level}"
                        )

                print(f"\n  ⏱️  Batch time: {batch_time:.2f}s")
                print(f"  📈 Throughput: {len(new_addrs) / batch_time:.1f} wallets/s")

            # 5. Status update
            elapsed = time.time() - state.start_time
            print(
                f"\n📡 Monitoring {state.critical_count} CRITICAL Traders | "
                f"Total Trades: {state.total_trades_fetched:,} | "
                f"Elapsed: {elapsed:.0f}s"
            )

            # Sleep to prevent CPU spinning (faster response by default)
            sleep_time = 0.5 if use_websocket else 1  # Faster polling by default
            await asyncio.sleep(sleep_time)

            # 6. Discord notification when CRITICAL count passes multiples of 10
            # Run on EVERY iteration (not just when new_addrs > 0)
            # This ensures notification triggers when count >= 10, >= 20, >= 30, etc.
            if discord_bot:
                current_count = state.critical_count

                # Notify if count has passed the next threshold (10, 20, 30, 40...)
                should_notify = (
                    current_count > 0
                    and current_count >= state.next_notification_threshold
                    and state.last_notified_count < current_count
                )

                print(
                    f"   Discord check: CRITICAL={current_count}, threshold={state.next_notification_threshold}, last_notified={state.last_notified_count}, should_notify={should_notify}"
                )

                if should_notify:
                    state.last_notified_count = current_count

                    # Advance threshold to next multiple of 10
                    state.next_notification_threshold = ((current_count // 10) + 1) * 10

                    print(
                        f"\n📱 Discord: Sending update ({current_count} CRITICAL monitored)...",
                        flush=True,
                    )
                    try:
                        discord_bot.send_summary_table(
                            list(state.master_profiles.values())
                        )
                        print(
                            f"   ✅ Discord notification sent successfully (next threshold: {state.next_notification_threshold})"
                        )
                    except Exception as e:
                        print(f"\n❌ Discord error: {e}", flush=True)

    except asyncio.CancelledError:
        print("Discovery loop cancelled")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Optimized Event Intelligence Engine with Batch Operations"
    )
    parser.add_argument(
        "--wallets-per-iteration",
        type=int,
        default=20,  # Increased default for better throughput
        help="Number of wallets to analyze per batch (default: 20)",
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
    parser.add_argument(
        "--trade-poll-interval",
        type=int,
        default=10,  # Faster by default for real-time monitoring
        help="Seconds between trade polls for real-time notifications (default: 10)",
    )
    parser.add_argument(
        "--position-poll-interval",
        type=int,
        default=120,  # Faster by default for position monitoring
        help="Seconds between position polls (default: 120 = 2 minutes)",
    )
    parser.add_argument(
        "--market-monitor-interval",
        type=int,
        default=15,  # Reduced from 60 to 15 for 4x faster detection
        help="Seconds between market volume checks (default: 15)",
    )
    parser.add_argument(
        "--market-refresh-interval",
        type=int,
        default=120,  # Reduced from 300 to 120 for faster market list updates
        help="Seconds between refreshing top markets list (default: 120 = 2 minutes)",
    )
    parser.add_argument(
        "--min-trade-size",
        type=float,
        default=1000.0,
        help="Minimum trade size for server-side filtering (default: 1000.0)",
    )
    parser.add_argument(
        "--use-redis",
        action="store_true",
        default=True,  # Enable Redis caching by default for maximum performance
        help="Enable Redis caching for market metadata and resolutions (default: True)",
    )
    parser.add_argument(
        "--no-redis",
        action="store_false",
        dest="use_redis",
        help="Disable Redis caching (default: Redis enabled)",
    )
    parser.add_argument(
        "--use-websocket",
        action="store_true",
        default=True,  # Enable WebSocket by default for real-time performance
        help="Use WebSocket streaming instead of GraphQL polling for real-time events (default: True)",
    )
    parser.add_argument(
        "--no-websocket",
        action="store_false",
        dest="use_websocket",
        help="Disable WebSocket streaming, use GraphQL polling (default: WebSocket enabled)",
    )
    parser.add_argument(
        "--redis-host",
        type=str,
        default="localhost",
        help="Redis host (default: localhost)",
    )
    parser.add_argument(
        "--redis-port",
        type=int,
        default=6379,
        help="Redis port (default: 6379)",
    )
    args = parser.parse_args()

    asyncio.run(run_optimized_event_engine(args))


if __name__ == "__main__":
    main()
