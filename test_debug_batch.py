"""Debug batch market metadata endpoint."""

import httpx
import json

client = httpx.Client(timeout=30.0)

# Get some condition IDs
resp = client.get(
    "https://gamma-api.polymarket.com/markets", params={"limit": 5, "closed": False}
)
markets = resp.json()
condition_ids = [m.get("conditionId") for m in markets if m.get("conditionId")]

print(f"Condition IDs: {condition_ids}")
print(f"Joined: {','.join(condition_ids)}")

# Try different parameter names
print("\n--- Test 1: condition_ids (plural) ---")
resp1 = client.get(
    "https://gamma-api.polymarket.com/markets",
    params={"condition_ids": ",".join(condition_ids[:2])},
)
print(f"Status: {resp1.status_code}")
print(f"Response length: {len(resp1.text)}")
if resp1.status_code == 200:
    data = resp1.json()
    print(f"Type: {type(data)}")
    print(f"Length: {len(data) if isinstance(data, list) else 'N/A'}")
    if isinstance(data, list) and len(data) > 0:
        print(f"First item keys: {list(data[0].keys())[:10]}")

print("\n--- Test 2: condition_ids (no comma, single) ---")
resp2 = client.get(
    "https://gamma-api.polymarket.com/markets",
    params={"condition_ids": condition_ids[0]},
)
print(f"Status: {resp2.status_code}")
if resp2.status_code == 200:
    data = resp2.json()
    print(f"Type: {type(data)}")
    print(f"Length: {len(data) if isinstance(data, list) else 'N/A'}")

print("\n--- Test 3: condition_id (singular - should work) ---")
resp3 = client.get(
    "https://gamma-api.polymarket.com/markets",
    params={"condition_id": condition_ids[0]},
)
print(f"Status: {resp3.status_code}")
if resp3.status_code == 200:
    data = resp3.json()
    print(f"Type: {type(data)}")
    print(f"Length: {len(data) if isinstance(data, list) else 'N/A'}")

print("\n--- Test 4: Check OpenAPI spec for parameter name ---")
# From docs: condition_ids (array) is the correct parameter name
# Let's try with array notation
import urllib.parse

ids_param = ",".join(condition_ids[:2])
print(f"Encoded param: {ids_param}")

resp4 = client.get(
    f"https://gamma-api.polymarket.com/markets?condition_ids={ids_param}"
)
print(f"Status: {resp4.status_code}")
if resp4.status_code == 200:
    data = resp4.json()
    print(f"Type: {type(data)}")
    print(f"Length: {len(data) if isinstance(data, list) else 'N/A'}")
    if isinstance(data, list):
        print(f"Number of markets returned: {len(data)}")
        if len(data) > 0:
            print(f"First market: {data[0].get('question', 'N/A')[:50]}")

client.close()
