"""
WebSocket client for real-time Polymarket events.
Provides streaming updates instead of polling.
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Any
import websockets

logger = logging.getLogger(__name__)


class PolymarketWebSocketClient:
    """WebSocket client for real-time market updates."""

    def __init__(
        self,
        on_trade: Optional[Callable] = None,
        on_market_update: Optional[Callable] = None,
    ):
        self.ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self.ws = None
        self.on_trade = on_trade
        self.on_market_update = on_market_update
        self.running = False
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0

    async def connect(self):
        """Connect to WebSocket server."""
        try:
            self.ws = await websockets.connect(
                self.ws_url, ping_interval=20, ping_timeout=10
            )
            logger.info("WebSocket connected")
            self.reconnect_delay = 1.0  # Reset on successful connection
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False

    async def subscribe(self, channel: str = "market", markets: list = None):
        """Subscribe to a channel."""
        if not self.ws:
            return False

        try:
            subscribe_msg = {
                "type": "subscribe",
                "channel": channel,
            }

            if markets:
                subscribe_msg["markets"] = markets
            else:
                subscribe_msg["markets"] = ["all"]

            await self.ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to channel: {channel}")
            return True
        except Exception as e:
            logger.error(f"Subscribe failed: {e}")
            return False

    async def listen(self):
        """Listen for messages from WebSocket."""
        if not self.ws:
            return

        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received: {message}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket listen error: {e}")

    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket message."""
        msg_type = data.get("type")

        if msg_type == "trade" and self.on_trade:
            await self.on_trade(data)
        elif msg_type == "market" and self.on_market_update:
            await self.on_market_update(data)
        elif msg_type == "subscribed":
            logger.info(f"Subscription confirmed: {data.get('channel')}")
        elif msg_type == "error":
            logger.error(f"WebSocket error: {data.get('message')}")

    async def start(self, auto_reconnect: bool = True):
        """Start WebSocket client with auto-reconnect."""
        self.running = True

        while self.running:
            connected = await self.connect()

            if connected:
                await self.subscribe()
                await self.listen()

            if not self.running:
                break

            if auto_reconnect:
                logger.info(f"Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)

                # Exponential backoff
                self.reconnect_delay = min(
                    self.reconnect_delay * 2, self.max_reconnect_delay
                )
            else:
                break

    async def stop(self):
        """Stop WebSocket client."""
        self.running = False

        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass

        logger.info("WebSocket client stopped")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()


class WebSocketTradeMonitor:
    """Monitor trades via WebSocket instead of polling."""

    def __init__(self, on_new_address: Optional[Callable] = None):
        self.on_new_address = on_new_address
        self.seen_addresses = set()
        self.ws_client = None

    async def handle_trade(self, trade_data: Dict[str, Any]):
        """Handle incoming trade event."""
        try:
            # Extract maker and taker addresses
            maker = trade_data.get("maker", "").lower()
            taker = trade_data.get("taker", "").lower()

            new_addresses = []

            if maker and maker not in self.seen_addresses:
                self.seen_addresses.add(maker)
                new_addresses.append(maker)

            if taker and taker not in self.seen_addresses:
                self.seen_addresses.add(taker)
                new_addresses.append(taker)

            # Notify callback of new addresses
            if new_addresses and self.on_new_address:
                await self.on_new_address(new_addresses)

        except Exception as e:
            logger.error(f"Error handling trade: {e}")

    async def start(self):
        """Start monitoring trades via WebSocket."""
        self.ws_client = PolymarketWebSocketClient(on_trade=self.handle_trade)
        await self.ws_client.start()

    async def stop(self):
        """Stop monitoring."""
        if self.ws_client:
            await self.ws_client.stop()
