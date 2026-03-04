"""Quick performance test with minimal wallets."""

import asyncio
import time
import httpx
from poly.api.async_client import AsyncPolymarketClient
from poly.api.polymarket import PolymarketClient


def test_quick_old(num_wallets=5):
    """Quick test of old client."""
    print("\n" + "=" * 80)
    print(f"OLD CLIENT (Sequential) - {num_wallets} wallets")
    print("=" * 80)

    client = PolymarketClient()
    http = httpx.Client(timeout=30.0)

    # Get addresses
    resp = http.get("https://data-api.polymarket.com/trades", params={"limit": 50})
    addresses = list(set(t.get("proxyWallet") for t in resp.json()))[:num_wallets]
    http.close()

    print(f"\nFetching {len(addresses)} wallets sequentially...")
    start = time.time()

    total_trades = 0
    for addr in addresses:
        trades = client.get_full_trader_history(addr, max_trades=100)
        total_trades += len(trades)

    elapsed = time.time() - start
    client.close()

    print(f"  Time: {elapsed:.2f}s")
    print(f"  Trades: {total_trades:,}")
    print(f"  Avg: {elapsed / len(addresses):.2f}s/wallet")

    return elapsed


async def test_quick_new(num_wallets=5):
    """Quick test of new async client."""
    print("\n" + "=" * 80)
    print(f"NEW CLIENT (Async Parallel) - {num_wallets} wallets")
    print("=" * 80)

    http = httpx.Client(timeout=30.0)
    resp = http.get("https://data-api.polymarket.com/trades", params={"limit": 50})
    addresses = list(set(t.get("proxyWallet") for t in resp.json()))[:num_wallets]
    http.close()

    print(f"\nFetching {len(addresses)} wallets in parallel...")
    start = time.time()

    async with AsyncPolymarketClient() as client:
        histories = await client.fetch_trader_histories_batch(addresses, max_trades=100)
        total_trades = sum(len(h) for h in histories.values())

    elapsed = time.time() - start

    print(f"  Time: {elapsed:.2f}s")
    print(f"  Trades: {total_trades:,}")
    print(f"  Avg: {elapsed / len(addresses):.2f}s/wallet")

    return elapsed


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("QUICK PERFORMANCE TEST")
    print("=" * 80)

    NUM = 5

    old_time = test_quick_old(NUM)
    new_time = asyncio.run(test_quick_new(NUM))

    speedup = old_time / new_time if new_time > 0 else 0

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\n  Old: {old_time:.2f}s")
    print(f"  New: {new_time:.2f}s")
    print(f"\n  🚀 SPEEDUP: {speedup:.1f}x")
    print(f"  Time saved: {old_time - new_time:.2f}s")

    print(f"\n  Estimated for 100 wallets:")
    print(f"    Old: ~{old_time * 20:.1f}s")
    print(f"    New: ~{new_time * 20:.1f}s")
    print(f"    Saved: ~{(old_time - new_time) * 20:.1f}s")

    print("\n" + "=" * 80)
