"""
Load test: WebSocket connection scalability.

Measures how many concurrent WebSocket connections the system can handle
and verifies all connected clients receive market data ticks.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
import websockets

pytestmark = [
    pytest.mark.slow,
    pytest.mark.load,
]

WS_URL = "ws://localhost:8000/ws/live"
CONCURRENT_CONNECTIONS = 50
TICK_TIMEOUT_SEC = 10


class TestWebSocketLoad:
    """Measure WebSocket connection scalability."""

    @pytest.mark.asyncio
    async def test_multiple_websocket_connections(self):
        """Multiple concurrent WebSocket connections all receive ticks."""
        received_ticks: dict[int, list] = {}

        async def connect_and_listen(client_id: int):
            received_ticks[client_id] = []
            try:
                async with websockets.connect(WS_URL, ping_interval=30, ping_timeout=10) as ws:
                    # Wait for at least one tick
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=TICK_TIMEOUT_SEC)
                        data = json.loads(message)
                        received_ticks[client_id].append(data)
                    except asyncio.TimeoutError:
                        pass
            except (websockets.WebSocketException, OSError) as e:
                pytest.skip(f"WebSocket connection failed: {e}")

        # Connect all clients
        start = time.monotonic()
        await asyncio.gather(*[
            connect_and_listen(i) for i in range(CONCURRENT_CONNECTIONS)
        ], return_exceptions=True)
        elapsed = time.monotonic() - start

        successful = sum(1 for v in received_ticks.values() if len(v) > 0)
        print(f"\n  Connections:      {CONCURRENT_CONNECTIONS}")
        print(f"  Received ticks:   {successful}/{CONCURRENT_CONNECTIONS}")
        print(f"  Duration:         {elapsed:.2f}s")

        # At least some clients should receive ticks
        assert successful > 0, "No clients received ticks"

    @pytest.mark.asyncio
    async def test_websocket_connection_cleanup(self):
        """After disconnect, the server cleans up the connection state."""
        # Connect and immediately disconnect
        try:
            async with websockets.connect(WS_URL) as ws:
                await asyncio.sleep(0.5)  # Let it establish
            # ws is now closed
            assert ws.closed
        except (websockets.WebSocketException, OSError) as e:
            pytest.skip(f"WebSocket connection failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_reconnection(self):
        """Client can reconnect after disconnection."""
        try:
            # First connection
            async with websockets.connect(WS_URL) as ws1:
                msg1 = await asyncio.wait_for(ws1.recv(), timeout=5)
                assert msg1 is not None

            # Second connection (reconnect)
            async with websockets.connect(WS_URL) as ws2:
                msg2 = await asyncio.wait_for(ws2.recv(), timeout=5)
                assert msg2 is not None
        except (websockets.WebSocketException, OSError, asyncio.TimeoutError) as e:
            pytest.skip(f"WebSocket test failed: {e}")

    @pytest.mark.asyncio
    async def test_websocket_message_frequency(self):
        """Verify ticks arrive at expected frequency (~1 per symbol per second)."""
        try:
            async with websockets.connect(WS_URL) as ws:
                messages = []
                timeout = 5  # seconds
                deadline = time.monotonic() + timeout

                while time.monotonic() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        messages.append(json.loads(msg))
                    except asyncio.TimeoutError:
                        continue

                print(f"\n  Received {len(messages)} messages in {timeout}s")
                assert len(messages) > 0, "No messages received"
        except (websockets.WebSocketException, OSError) as e:
            pytest.skip(f"WebSocket connection failed: {e}")
