"""
PolygonScan API Client: On-chain funding traces.
Used to trace USDC funding sources on Polygon for Sybil detection.
"""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class PolygonScanClient:
    def __init__(self, api_key: str = "YourApiKeyToken"):
        import httpx

        self.http = httpx.Client(timeout=httpx.Timeout(60.0, connect=30.0, read=120.0))
        self.base = "https://api.polygonscan.com/api"
        self.api_key = api_key

    def _safe_get(self, params: Dict) -> Optional[Any]:
        try:
            params["apikey"] = self.api_key
            resp = self.http.get(self.base, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "1":
                    return data.get("result", [])
                return []
            return None
        except Exception as e:
            logger.error(f"PolygonScan error: {e}")
            return None

    def get_normal_transactions(
        self,
        address: str,
        startblock: int = 0,
        endblock: int = 99999999,
        limit: int = 100,
    ) -> List[Dict]:
        """Get normal transactions for an address."""
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": startblock,
            "endblock": endblock,
            "sort": "asc",
        }
        result = self._safe_get(params)
        if result and isinstance(result, list):
            return result[:limit]
        return []

    def get_internal_transactions(
        self,
        address: str,
        startblock: int = 0,
        endblock: int = 99999999,
        limit: int = 100,
    ) -> List[Dict]:
        """Get internal transactions for an address (USDC transfers)."""
        params = {
            "module": "account",
            "action": "txlistinternal",
            "address": address,
            "startblock": startblock,
            "endblock": endblock,
            "sort": "asc",
        }
        result = self._safe_get(params)
        if result and isinstance(result, list):
            return result[:limit]
        return []

    def get_erc20_transfers(
        self, address: str, contract_address: Optional[str] = None, limit: int = 100
    ) -> List[Dict]:
        """Get ERC20 token transfers (USDC on Polygon)."""
        USDC_POLYGON = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"

        params = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "contractaddress": contract_address or USDC_POLYGON,
            "sort": "asc",
        }
        result = self._safe_get(params)
        if result and isinstance(result, list):
            return result[:limit]
        return []

    def get_first_funding_source(self, address: str) -> Optional[Dict]:
        """Trace the first USDC funding source for an address."""
        erc20_transfers = self.get_erc20_transfers(address, limit=50)

        if not erc20_transfers:
            normal_txs = self.get_normal_transactions(address, limit=50)
            if normal_txs:
                return {
                    "from": normal_txs[0].get("from"),
                    "value": normal_txs[0].get("value"),
                    "timestamp": normal_txs[0].get("timeStamp"),
                    "hash": normal_txs[0].get("hash"),
                    "type": "native",
                }
            return None

        incoming = [
            tx for tx in erc20_transfers if tx.get("to", "").lower() == address.lower()
        ]

        if incoming:
            first_funding = incoming[0]
            return {
                "from": first_funding.get("from"),
                "value": first_funding.get("value"),
                "timestamp": first_funding.get("timeStamp"),
                "hash": first_funding.get("hash"),
                "token": first_funding.get("contractAddress"),
                "type": "erc20",
            }

        return None

    def get_funding_chain(self, address: str, depth: int = 3) -> List[Dict]:
        """Trace funding sources recursively (for detecting clusters)."""
        chain = []
        current_addr = address

        for _ in range(depth):
            funding = self.get_first_funding_source(current_addr)
            if (
                not funding
                or funding.get("from") == "0x0000000000000000000000000000000000000000"
            ):
                break
            chain.append(funding)
            current_addr = funding["from"]

        return chain

    def close(self):
        self.http.close()
