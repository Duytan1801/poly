"""Test GraphQL batch query performance."""

import time
import sys
from poly.api.graphql import GraphQLClient


def test_single_positions():
    """Test fetching positions one-by-one (baseline)."""
    print("\n" + "=" * 80)
    print("TEST: Single Position Queries (Baseline)")
    print("=" * 80)

    client = GraphQLClient()

    # Get sample addresses
    sample_addresses = [
        "0x56687bf447db6ffa42ffe2204a05edaa20f55839",  # Top trader
        "0x1f2dd6d473f3e824cd6fca6ddae8a1adfa6a9c86",
        "0x6a72f61820b26b1fe4e6bd63fdfebde6ef6e0a0b",
        "0x4d0a7f3f3d7e5c8a9b0d1e2f3a4b5c6d7e8f9a0b",
        "0x7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c",
    ][:5]

    print(f"\nFetching positions for {len(sample_addresses)} users sequentially...")
    start = time.time()

    positions = {}
    for addr in sample_addresses:
        pos = client.get_user_positions(addr)
        positions[addr] = pos

    elapsed = time.time() - start

    total_positions = sum(len(p) for p in positions.values())
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Total positions: {total_positions}")
    print(f"  Average per user: {elapsed / len(sample_addresses):.2f}s")

    client.close()
    return elapsed, total_positions


def test_batch_positions():
    """Test batch GraphQL query."""
    print("\n" + "=" * 80)
    print("TEST: Batch GraphQL Position Queries")
    print("=" * 80)

    client = GraphQLClient()

    sample_addresses = [
        "0x56687bf447db6ffa42ffe2204a05edaa20f55839",
        "0x1f2dd6d473f3e824cd6fca6ddae8a1adfa6a9c86",
        "0x6a72f61820b26b1fe4e6bd63fdfebde6ef6e0a0b",
        "0x4d0a7f3f3d7e5c8a9b0d1e2f3a4b5c6d7e8f9a0b",
        "0x7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c",
    ][:5]

    print(f"\nFetching positions for {len(sample_addresses)} users in ONE request...")
    start = time.time()

    positions = client.get_user_positions_batch(sample_addresses)

    elapsed = time.time() - start

    total_positions = sum(len(p) for p in positions.values())
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Total positions: {total_positions}")
    print(f"  Average per user: {elapsed / len(sample_addresses):.2f}s")

    client.close()
    return elapsed, total_positions


def test_condition_payouts_batch():
    """Test batch condition payouts query."""
    print("\n" + "=" * 80)
    print("TEST: Batch Condition Payouts Query")
    print("=" * 80)

    client = GraphQLClient()

    # Get some condition IDs
    from poly.api.polymarket import PolymarketClient

    pm_client = PolymarketClient()

    trades = pm_client.get_trader_history(
        "0x56687bf447db6ffa42ffe2204a05edaa20f55839", limit=50
    )
    condition_ids = list(
        set(t.get("conditionId") for t in trades if t.get("conditionId"))
    )[:5]

    print(f"\nFetching payouts for {len(condition_ids)} conditions...")

    # Single queries
    print("\n1. Single queries (baseline):")
    start = time.time()
    payouts_single = {}
    for cid in condition_ids:
        payout = client.get_condition_payouts(cid)
        payouts_single[cid] = payout
    single_time = time.time() - start
    print(f"  Time: {single_time:.2f}s")
    print(f"  Payouts fetched: {len([p for p in payouts_single.values() if p])}")

    # Batch query
    print("\n2. Batch query:")
    start = time.time()
    payouts_batch = client.get_condition_payouts_batch(condition_ids)
    batch_time = time.time() - start
    print(f"  Time: {batch_time:.2f}s")
    print(f"  Payouts fetched: {len([p for p in payouts_batch.values() if p])}")

    speedup = single_time / batch_time if batch_time > 0 else 0
    print(f"\n  Speedup: {speedup:.1f}x faster")

    pm_client.close()
    client.close()

    return single_time, batch_time


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("GRAPHQL BATCH QUERY PERFORMANCE TESTS")
    print("=" * 80)

    # Test positions
    single_time, single_positions = test_single_positions()
    batch_time, batch_positions = test_batch_positions()

    if batch_time > 0:
        speedup = single_time / batch_time
        print(f"\n📊 Position Query Speedup: {speedup:.1f}x faster")
        print(f"   Single: {single_time:.2f}s | Batch: {batch_time:.2f}s")

    # Test condition payouts
    single_payout_time, batch_payout_time = test_condition_payouts_batch()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if batch_time > 0 and batch_payout_time > 0:
        avg_speedup = (
            single_time / batch_time + single_payout_time / batch_payout_time
        ) / 2
        print(f"\n🎯 Average GraphQL Speedup: {avg_speedup:.1f}x faster")

        if avg_speedup >= 10:
            print("\n✅ GraphQL batch queries achieve 10x+ speedup!")
        elif avg_speedup >= 5:
            print("\n✅ GraphQL batch queries achieve 5x+ speedup!")
        else:
            print("\n⚠️  GraphQL speedup is lower than expected")
