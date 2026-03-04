"""Test script to verify batch API endpoints work correctly."""

import httpx
import time
import json


def test_batch_market_metadata():
    """Test if we can fetch multiple markets in one request using condition_ids."""
    print("=" * 80)
    print("TEST 1: Batch Market Metadata Fetching")
    print("=" * 80)

    # Sample condition IDs (we'll get real ones first)
    client = httpx.Client(timeout=30.0)

    # First, get some real condition IDs from active markets
    print("\n1. Fetching sample markets to get condition IDs...")
    resp = client.get(
        "https://gamma-api.polymarket.com/markets",
        params={"limit": 10, "closed": False},
    )

    if resp.status_code != 200:
        print(f"❌ Failed to fetch markets: {resp.status_code}")
        return False

    markets = resp.json()
    condition_ids = [m.get("conditionId") for m in markets if m.get("conditionId")]

    print(f"   ✓ Got {len(condition_ids)} condition IDs")
    print(f"   Sample IDs: {condition_ids[:3]}")

    # Test 1: Single market fetch (baseline)
    print("\n2. Testing SINGLE market fetch (baseline)...")
    start = time.time()
    single_market = client.get(
        "https://gamma-api.polymarket.com/markets",
        params={"condition_id": condition_ids[0]},
    )
    single_time = time.time() - start
    print(f"   Time: {single_time:.3f}s")
    print(f"   Status: {single_market.status_code}")
    print(
        f"   Data keys: {len(single_market.json()) if single_market.status_code == 200 else 0}"
    )

    # Test 2: Batch fetch with condition_ids parameter
    print("\n3. Testing BATCH market fetch with 'condition_ids' parameter...")
    start = time.time()
    batch_resp = client.get(
        "https://gamma-api.polymarket.com/markets",
        params={"condition_ids": ",".join(condition_ids)},
    )
    batch_time = time.time() - start

    print(f"   Time: {batch_time:.3f}s")
    print(f"   Status: {batch_resp.status_code}")

    if batch_resp.status_code == 200:
        batch_data = batch_resp.json()
        print(
            f"   ✓ Received {len(batch_data) if isinstance(batch_data, list) else 'NOT A LIST'} markets"
        )
        print(
            f"   Speedup: {single_time * len(condition_ids) / batch_time:.1f}x faster"
        )

        if isinstance(batch_data, list) and len(batch_data) > 0:
            print(
                f"   First market question: {batch_data[0].get('question', 'N/A')[:60]}..."
            )
            return True
        else:
            print(f"   ⚠️  Unexpected response format: {type(batch_data)}")
            return False
    else:
        print(f"   ❌ Request failed: {batch_resp.text}")
        return False


def test_batch_holders():
    """Test if we can fetch holders for multiple markets."""
    print("\n" + "=" * 80)
    print("TEST 2: Batch Holders Fetching")
    print("=" * 80)

    client = httpx.Client(timeout=30.0)

    # Get some condition IDs
    print("\n1. Getting sample condition IDs...")
    resp = client.get("https://data-api.polymarket.com/trades", params={"limit": 100})

    if resp.status_code != 200:
        print(f"   ❌ Failed to fetch trades: {resp.status_code}")
        return False

    trades = resp.json()
    condition_ids = list(
        set(t.get("conditionId") for t in trades if t.get("conditionId"))
    )[:5]

    print(f"   ✓ Got {len(condition_ids)} unique condition IDs")

    # Test batch holders
    print("\n2. Testing batch holders endpoint...")
    start = time.time()
    holders_resp = client.get(
        "https://data-api.polymarket.com/holders",
        params={"market": ",".join(condition_ids), "limit": 20},
    )

    if holders_resp.status_code == 200:
        holders_data = holders_resp.json()
        print(f"   ✓ Success! Received {len(holders_data)} holder groups")
        if len(holders_data) > 0:
            print(
                f"   First group has {len(holders_data[0].get('holders', []))} holders"
            )
        return True
    else:
        print(f"   ⚠️  Status: {holders_resp.status_code}")
        print(f"   Response: {holders_resp.text[:200]}")
        return False


def test_trades_filters():
    """Test server-side filtering with min_size."""
    print("\n" + "=" * 80)
    print("TEST 3: Server-Side Filtering")
    print("=" * 80)

    client = httpx.Client(timeout=30.0)

    # Get a sample user address
    print("\n1. Getting sample user address...")
    resp = client.get("https://data-api.polymarket.com/trades", params={"limit": 10})

    if resp.status_code != 200:
        print(f"   ❌ Failed to fetch trades")
        return False

    trades = resp.json()
    if not trades:
        print("   ❌ No trades found")
        return False

    sample_user = trades[0].get("proxyWallet")
    print(f"   ✓ Sample user: {sample_user}")

    # Test without filter
    print("\n2. Testing WITHOUT min_size filter...")
    start = time.time()
    all_trades = client.get(
        "https://data-api.polymarket.com/trades",
        params={"user": sample_user, "limit": 100},
    )
    all_time = time.time() - start

    if all_trades.status_code == 200:
        all_data = all_trades.json()
        print(f"   Received {len(all_data)} trades")
        print(f"   Time: {all_time:.3f}s")

    # Test with filter
    print("\n3. Testing WITH min_size=1000 filter (whales only)...")
    start = time.time()
    filtered_trades = client.get(
        "https://data-api.polymarket.com/trades",
        params={"user": sample_user, "limit": 100, "min_size": 1000},
    )
    filtered_time = time.time() - start

    if filtered_trades.status_code == 200:
        filtered_data = filtered_trades.json()
        print(f"   ✓ Received {len(filtered_data)} trades (large only)")
        print(f"   Time: {filtered_time:.3f}s")
        print(
            f"   Data reduction: {100 * (1 - len(filtered_data) / len(all_data)):.1f}% less data"
        )
        return True
    else:
        print(f"   ⚠️  Status: {filtered_trades.status_code}")
        return False


def test_leaderboard_api():
    """Test the leaderboard API for pre-computed PnL."""
    print("\n" + "=" * 80)
    print("TEST 4: Leaderboard API (Pre-computed PnL)")
    print("=" * 80)

    client = httpx.Client(timeout=30.0)

    print("\n1. Fetching leaderboard (top 50 by PnL)...")
    start = time.time()
    resp = client.get(
        "https://data-api.polymarket.com/v1/leaderboard",
        params={
            "category": "OVERALL",
            "timePeriod": "ALL",
            "orderBy": "PNL",
            "limit": 50,
        },
    )

    if resp.status_code == 200:
        data = resp.json()
        elapsed = time.time() - start
        print(f"   ✓ Success! Received {len(data)} traders")
        print(f"   Time: {elapsed:.3f}s")

        if len(data) > 0:
            print(f"\n   Top 3 Traders:")
            for i, trader in enumerate(data[:3], 1):
                print(f"   {i}. {trader.get('userName', 'Unknown')[:30]}")
                print(f"      PnL: ${trader.get('pnl', 0):,.2f}")
                print(f"      Volume: ${trader.get('vol', 0):,.2f}")
                print(f"      Address: {trader.get('proxyWallet', 'N/A')[:20]}...")
        return True
    else:
        print(f"   ❌ Failed: {resp.status_code}")
        return False


if __name__ == "__main__":
    print("\n🧪 POLYMARKET API BATCH ENDPOINT TESTS")
    print("=" * 80)

    results = {
        "Batch Market Metadata": test_batch_market_metadata(),
        "Batch Holders": test_batch_holders(),
        "Server-Side Filtering": test_trades_filters(),
        "Leaderboard API": test_leaderboard_api(),
    }

    print("\n" + "=" * 80)
    print("TEST RESULTS SUMMARY")
    print("=" * 80)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:.<50} {status}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Ready to implement batch optimizations.")
    else:
        print("\n⚠️  Some tests failed. Check API compatibility before proceeding.")
