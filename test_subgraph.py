import httpx
import json

def test_pnl_subgraph():
    url = "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/pnl-subgraph/0.0.1/gn"
    
    # Query for top traders by total PnL
    query = """
    {
      userPnls(first: 5, orderBy: totalPnl, orderDirection: desc) {
        id
        totalPnl
        realizationPnl
        lpPnl
      }
    }
    """
    
    print("Testing PNL Subgraph...")
    try:
        resp = httpx.post(url, json={"query": query}, timeout=10.0)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2))
        else:
            print(resp.text)
    except Exception as e:
        print(f"Error: {e}")

def test_activity_subgraph():
    url = "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/activity-subgraph/0.0.1/gn"
    
    # Query for recent transactions
    query = """
    {
      transactions(first: 5, orderBy: timestamp, orderDirection: desc) {
        id
        user
        timestamp
        transactionHash
      }
    }
    """
    
    print("\nTesting Activity Subgraph...")
    try:
        resp = httpx.post(url, json={"query": query}, timeout=10.0)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2))
        else:
            print(resp.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_pnl_subgraph()
    test_activity_subgraph()
