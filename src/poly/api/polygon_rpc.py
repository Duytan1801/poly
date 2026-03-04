"""
Polygon RPC Client: Direct on-chain data from Polygon PoS via Alchemy.
Provides token balances, transfer tracing, and on-chain analysis.
"""

import logging
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

USDC_POLYGON = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
WMATIC_POLYGON = "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270"


@dataclass
class AlchemyConfig:
    api_key: str
    network: str = "polygon-mainnet"

    @property
    def base_url(self) -> str:
        return f"https://{self.network}.g.alchemy.com/v2/{self.api_key}"


class PolygonRPCClient:
    """
    Alchemy-powered Polygon RPC client for on-chain analysis.
    Provides USDC balance checks, transfer tracing, and funding source detection.
    """

    def __init__(self, alchemy_api_key: str, rpc_url: Optional[str] = None):
        self.config = AlchemyConfig(alchemy_api_key)
        self.rpc_url = (
            rpc_url or f"https://polygon-mainnet.g.alchemy.com/v2/{alchemy_api_key}"
        )
        self.session = requests.Session()
        self._latest_block_cache = None

    def _call(self, method: str, params: List = None) -> Optional[Dict]:
        """Make an Alchemy JSON-RPC call."""
        try:
            response = self.session.post(
                self.config.base_url,
                json={
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params or [],
                    "id": 1,
                },
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            result = response.json().get("result")
            if response.json().get("error"):
                logger.warning(f"Alchemy error: {response.json()['error']}")
                return None
            return result
        except Exception as e:
            logger.warning(f"Failed to call {method}: {e}")
            return None

    def get_latest_block(self) -> int:
        """Get the latest block number."""
        if self._latest_block_cache:
            return self._latest_block_cache
        result = self._call("eth_blockNumber")
        if result:
            self._latest_block_cache = int(result, 16)
            return self._latest_block_cache
        return 0

    def get_block(self, block_number: int) -> Optional[Dict]:
        """Get block details including timestamp."""
        result = self._call("eth_getBlockByNumber", [hex(block_number), False])
        return result

    def get_block_timestamp(self, block_number: int) -> Optional[int]:
        """Get timestamp for a specific block."""
        block = self.get_block(block_number)
        if block:
            return int(block.get("timestamp", "0x0"), 16)
        return None

    def get_current_timestamp(self) -> int:
        """Get current Unix timestamp."""
        latest = self.get_latest_block()
        return self.get_block_timestamp(latest)

    def is_contract(self, address: str) -> bool:
        """Check if an address is a contract (has code)."""
        result = self._call("eth_getCode", [address.lower(), "latest"])
        if result:
            return result != "0x"
        return False

    def get_usdc_balance(self, address: str) -> float:
        """Get USDC balance for an address (in human-readable format)."""
        try:
            result = self._call("alchemy_getTokenBalances", [address, [USDC_POLYGON]])
            if result and result.get("tokenBalances"):
                raw_balance = result["tokenBalances"][0].get("tokenBalance", "0x0")
                if raw_balance == "0x0" or not raw_balance:
                    return 0.0
                return int(raw_balance, 16) / 1e6
            return 0.0
        except Exception as e:
            logger.warning(f"Failed to get USDC balance for {address}: {e}")
            return 0.0

    def get_token_balances(
        self, address: str, tokens: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """Get balances for multiple tokens."""
        if tokens is None:
            tokens = [USDC_POLYGON, WMATIC_POLYGON]

        try:
            result = self._call("alchemy_getTokenBalances", [address, tokens])
            balances = {}
            if result and result.get("tokenBalances"):
                for tb in result["tokenBalances"]:
                    raw = tb.get("tokenBalance", "0x0")
                    if raw and raw != "0x0":
                        addr = tb.get("contractAddress", "").lower()
                        balances[addr] = int(raw, 16) / 1e6
            return balances
        except Exception as e:
            logger.warning(f"Failed to get token balances for {address}: {e}")
            return {}

    def get_usdc_transfers(
        self,
        address: str,
        from_block: Optional[int] = None,
        to_block: Optional[str] = "latest",
        max_count: int = 100,
    ) -> List[Dict]:
        """
        Get USDC transfers for an address (incoming and outgoing).
        Uses Alchemy's enhanced tracing API.
        """
        transfers = []

        try:
            # Build the filter params
            params = {
                "category": ["erc20"],
                "contractAddresses": [USDC_POLYGON],
                "maxCount": hex(min(max_count, 1000)),
            }

            if from_block:
                params["fromBlock"] = hex(from_block)
            if to_block:
                params["toBlock"] = to_block if to_block == "latest" else hex(to_block)

            # Get incoming transfers
            incoming_params = {**params, "toAddress": address}
            result = self._call("alchemy_getAssetTransfers", [incoming_params])

            if result and result.get("transfers"):
                for t in result["transfers"]:
                    transfers.append(
                        {
                            "from": t.get("from", "").lower(),
                            "to": t.get("to", "").lower(),
                            "value": t.get("value", 0),
                            "blockNumber": int(t.get("blockNum", "0x0"), 16),
                            "hash": t.get("hash", ""),
                            "direction": "incoming",
                        }
                    )

            # Get outgoing transfers
            outgoing_params = {**params, "fromAddress": address}
            result = self._call("alchemy_getAssetTransfers", [outgoing_params])

            if result and result.get("transfers"):
                for t in result["transfers"]:
                    transfers.append(
                        {
                            "from": t.get("from", "").lower(),
                            "to": t.get("to", "").lower(),
                            "value": t.get("value", 0),
                            "blockNumber": int(t.get("blockNum", "0x0"), 16),
                            "hash": t.get("hash", ""),
                            "direction": "outgoing",
                        }
                    )

            # Sort by block number
            transfers.sort(key=lambda x: x["blockNumber"])

        except Exception as e:
            logger.warning(f"Failed to get USDC transfers for {address}: {e}")

        return transfers

    def get_incoming_funding(
        self, address: str, from_block: Optional[int] = None, max_transfers: int = 10
    ) -> List[Dict]:
        """Get incoming USDC transfers (funding sources)."""
        try:
            params = {
                "category": ["erc20"],
                "contractAddresses": [USDC_POLYGON],
                "toAddress": address,
                "maxCount": hex(min(max_transfers, 100)),
            }

            if from_block:
                params["fromBlock"] = hex(from_block)

            result = self._call("alchemy_getAssetTransfers", [params])

            if result and result.get("transfers"):
                transfers = []
                for t in result["transfers"]:
                    transfers.append(
                        {
                            "from": t.get("from", "").lower(),
                            "to": t.get("to", "").lower(),
                            "value": t.get("value", 0),
                            "blockNumber": int(t.get("blockNum", "0x0"), 16),
                            "hash": t.get("hash", ""),
                        }
                    )
                return transfers.sort(key=lambda x: x["blockNumber"])

        except Exception as e:
            logger.warning(f"Failed to get funding for {address}: {e}")

        return []

    def get_first_usdc_funding(
        self, address: str, max_blocks: int = 500000
    ) -> Optional[Dict]:
        """
        Find the first/earliest USDC funding source for an address.
        Traces back to find where the wallet got its initial USDC.
        """
        try:
            latest_block = self.get_latest_block()
            from_block = max(0, latest_block - max_blocks)

            transfers = self.get_usdc_transfers(
                address, from_block=from_block, max_count=500
            )

            # Filter to incoming only and get earliest
            incoming = [t for t in transfers if t["direction"] == "incoming"]

            if not incoming:
                return None

            # Get the earliest transfer
            first = incoming[0]

            return {
                "from": first["from"],
                "to": first["to"],
                "value": first["value"],
                "blockNumber": first["blockNumber"],
                "transactionHash": first["hash"],
                "type": "usdc_transfer",
            }

        except Exception as e:
            logger.warning(f"Failed to get first USDC funding for {address}: {e}")
            return None

    def trace_funding(self, address: str, depth: int = 3) -> List[Dict]:
        """
        Trace funding sources recursively through multiple hops.
        Returns a chain of funding sources.
        """
        chain = []
        current_addr = address.lower()

        for i in range(depth):
            funding = self.get_first_usdc_funding(current_addr)

            if not funding:
                break

            source = funding["from"]

            # Stop if we hit a zero address or contract (likely a CEX or liquidity pool)
            if (
                source == "0x0000000000000000000000000000000000000000"
                or self.is_contract(source)
            ):
                break

            chain.append(funding)
            current_addr = source

            # Avoid infinite loops
            if source in [c.get("from") for c in chain[:-1]]:
                break

        return chain

    def get_address_info(self, address: str) -> Dict:
        """Get comprehensive on-chain info about an address."""
        try:
            addr = address.lower()

            usdc_balance = self.get_usdc_balance(addr)
            token_balances = self.get_token_balances(addr)
            is_contract = self.is_contract(addr)
            latest_block = self.get_latest_block()

            # Get recent transfers
            transfers = self.get_usdc_transfers(
                addr, from_block=max(0, latest_block - 10000), max_count=50
            )

            incoming = [t for t in transfers if t["direction"] == "incoming"]
            outgoing = [t for t in transfers if t["direction"] == "outgoing"]

            total_incoming = sum(t["value"] for t in incoming)
            total_outgoing = sum(t["value"] for t in outgoing)

            return {
                "address": addr,
                "is_contract": is_contract,
                "usdc_balance": usdc_balance,
                "token_balances": token_balances,
                "incoming_transfer_count": len(incoming),
                "outgoing_transfer_count": len(outgoing),
                "total_incoming_usdc": total_incoming,
                "total_outgoing_usdc": total_outgoing,
                "latest_block": latest_block,
            }

        except Exception as e:
            logger.warning(f"Failed to get address info for {address}: {e}")
            return {"address": address, "error": str(e)}

    def get_funding_with_timing(
        self,
        address: str,
        market_resolution_time: Optional[int] = None,
        max_blocks: int = 200000,
    ) -> Dict:
        """
        Get funding info with timing analysis relative to market resolution.
        Useful for detecting "just-in-time" funding before market resolves.
        """
        try:
            addr = address.lower()
            latest_block = self.get_latest_block()
            from_block = max(0, latest_block - max_blocks)

            transfers = self.get_usdc_transfers(
                addr, from_block=from_block, max_count=200
            )

            incoming = [t for t in transfers if t["direction"] == "incoming"]

            result = {
                "address": addr,
                "total_funding_events": len(incoming),
                "first_funding": None,
                "largest_funding": None,
                "last_funding_before_resolution": None,
                "just_in_time_funding": False,
            }

            if not incoming:
                return result

            # First funding
            result["first_funding"] = incoming[0]

            # Largest funding
            result["largest_funding"] = max(incoming, key=lambda x: x["value"])

            # If we have market resolution time, check for "just-in-time" funding
            if market_resolution_time:
                # Find transfers before resolution
                before_resolution = []
                for t in incoming:
                    blk_time = self.get_block_timestamp(t["blockNumber"])
                    if blk_time and blk_time < market_resolution_time:
                        before_resolution.append({**t, "timestamp": blk_time})

                if before_resolution:
                    # Check if any funding was very close to resolution (< 1 hour)
                    result["last_funding_before_resolution"] = max(
                        before_resolution, key=lambda x: x["timestamp"]
                    )

                    last_ts = result["last_funding_before_resolution"]["timestamp"]
                    time_diff = market_resolution_time - last_ts

                    # Funding within 1 hour of resolution is suspicious
                    if time_diff < 3600:
                        result["just_in_time_funding"] = True
                        result["minutes_before_resolution"] = time_diff / 60

            return result

        except Exception as e:
            logger.warning(f"Failed to get funding with timing for {address}: {e}")
            return {"address": address, "error": str(e)}

    def get_multiple_addresses_funding_sources(
        self, addresses: List[str], max_depth: int = 2
    ) -> Dict[str, List[Dict]]:
        """
        Get funding sources for multiple addresses.
        Returns a dict mapping address -> list of funding chain.
        """
        results = {}

        for addr in addresses:
            try:
                chain = self.trace_funding(addr, depth=max_depth)
                results[addr.lower()] = chain
            except Exception as e:
                logger.warning(f"Failed to trace funding for {addr}: {e}")
                results[addr.lower()] = []

        return results

    def find_common_funding_sources(
        self, addresses: List[str], max_depth: int = 3
    ) -> Dict[str, List[str]]:
        """
        Find common funding sources across multiple addresses.
        Returns dict of funding_address -> [trader_addresses]
        """
        funding_map = defaultdict(list)

        for addr in addresses:
            chain = self.trace_funding(addr.lower(), depth=max_depth)

            for hop in chain:
                source = hop.get("from", "").lower()
                if source and source != "0x0000000000000000000000000000000000000000":
                    funding_map[source].append(addr.lower())

        # Only return sources that fund multiple addresses
        return {
            source: wallets
            for source, wallets in funding_map.items()
            if len(wallets) > 1
        }

    def close(self):
        """Close the session."""
        self.session.close()
