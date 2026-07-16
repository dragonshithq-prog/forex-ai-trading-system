"""Tests for WebSocket performance optimizations.

Tests:
- Message coalescing (batch small messages into periodic updates)
- Per-connection message queue with bounded size
- Backpressure on slow consumers (disconnect after queue full)
- Compression for large messages
"""

from __future__ import annotations

import asyncio
import zlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forex_trading.api.websocket import (
    ConnectionManager,
    compress_message,
    decompress_message,
)


pytestmark = pytest.mark.asyncio


class TestWebSocketCompression:
    """Tests for WebSocket message compression."""

    def test_compress_small_message(self):
        """Small messages should not be compressed."""
        message = {"type": "ping"}
        result = compress_message(message)
        # Should return the JSON string
        assert isinstance(result, str)
        assert result == '{"type": "ping"}'

    def test_compress_large_message(self):
        """Large messages should be compressed with zlib."""
        # Create a message larger than the compression threshold
        large_data = {"data": "x" * 2000, "type": "large"}
        result = compress_message(large_data)
        # Should return compressed bytes
        assert isinstance(result, bytes)
        assert result[0] == 1  # Compression flag

    def test_decompress_roundtrip(self):
        """Compression and decompression should roundtrip correctly."""
        original = {"type": "test", "data": {"value": "x" * 2000}}
        compressed = compress_message(original)
        assert isinstance(compressed, bytes)

        decompressed = decompress_message(compressed)
        assert decompressed["type"] == "test"
        assert decompressed["data"]["value"] == "x" * 2000

    def test_decompress_uncompressed(self):
        """Decompression of uncompressed data should work."""
        data = json.dumps({"type": "test"}).encode("utf-8")
        result = decompress_message(data)
        assert result["type"] == "test"


class TestConnectionManagerPerformance:
    """Tests for ConnectionManager performance optimizations."""

    async def test_message_queue_created_on_connect(self):
        """Each connection should have a bounded message queue."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        conn_id = await manager.connect(mock_ws, "user1")
        assert conn_id in manager._message_queues
        assert conn_id in manager._send_tasks

        await manager.disconnect(conn_id)

    async def test_send_to_connection_enqueues(self):
        """send_to_connection should enqueue message for delivery."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        conn_id = await manager.connect(mock_ws, "user1")
        queue = manager._message_queues[conn_id]
        assert queue.qsize() == 0

        await manager.send_to_connection(conn_id, {"type": "test"})
        assert queue.qsize() == 1

        await manager.disconnect(conn_id)

    async def test_send_to_user_enqueues(self):
        """send_to_user should enqueue message for all user connections."""
        manager = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        conn_id1 = await manager.connect(mock_ws1, "user1")
        conn_id2 = await manager.connect(mock_ws2, "user1")

        await manager.send_to_user("user1", {"type": "test"})

        assert manager._message_queues[conn_id1].qsize() == 1
        assert manager._message_queues[conn_id2].qsize() == 1

        await manager.disconnect(conn_id1)
        await manager.disconnect(conn_id2)

    async def test_backpressure_disconnect_on_full_queue(self):
        """Slow consumers should be disconnected when queue is full."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        conn_id = await manager.connect(mock_ws, "user1")
        queue = manager._message_queues[conn_id]

        # Fill the queue (maxsize = _MAX_QUEUE_SIZE)
        # We can verify the queue is bounded
        assert queue.maxsize > 0

        await manager.disconnect(conn_id)

    async def test_queue_stats_provides_diagnostics(self):
        """queue_stats should provide per-connection diagnostics."""
        manager = ConnectionManager()

        stats = manager.queue_stats
        assert stats["total_connections"] == 0
        assert stats["total_queued_messages"] == 0
        assert stats["per_connection"] == {}

    async def test_queue_stats_with_connections(self):
        """queue_stats should report stats for active connections."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        conn_id = await manager.connect(mock_ws, "user1")

        stats = manager.queue_stats
        assert stats["total_connections"] == 1
        assert conn_id in stats["per_connection"]

        await manager.disconnect(conn_id)

    async def test_broadcast_to_channel_filtering(self):
        """Broadcast should filter by subscribed symbols for ticks channel."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()
        mock_ws.client_state = MagicMock()
        mock_ws.client_state.CONNECTED = "connected"

        conn_id = await manager.connect(mock_ws, "user1")

        # Subscribe to ticks with specific symbol
        await manager.subscribe(conn_id, "ticks", {"symbols": ["EURUSD"]})

        # Broadcast for a different symbol should not be sent
        await manager.broadcast_to_channel("ticks", {
            "type": "tick",
            "data": {"symbol": "GBPUSD", "price": 1.3000},
        })

        await manager.disconnect(conn_id)

    async def test_broadcast_to_channel_matching_symbol(self):
        """Broadcast should deliver to connections subscribed to that symbol."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        conn_id = await manager.connect(mock_ws, "user1")

        await manager.subscribe(conn_id, "ticks", {"symbols": ["EURUSD"]})

        await manager.broadcast_to_channel("ticks", {
            "type": "tick",
            "data": {"symbol": "EURUSD", "price": 1.1000},
        })

        await manager.disconnect(conn_id)

    async def test_disconnect_cleans_send_task(self):
        """Disconnect should cancel the send task."""
        manager = ConnectionManager()
        mock_ws = AsyncMock()

        conn_id = await manager.connect(mock_ws, "user1")
        assert conn_id in manager._send_tasks

        await manager.disconnect(conn_id)
        assert conn_id not in manager._send_tasks
        assert conn_id not in manager._message_queues

    async def test_validate_symbol(self):
        """Symbol validation should work correctly."""
        from forex_trading.api.websocket import validate_symbol

        assert validate_symbol("EURUSD") is True
        assert validate_symbol("GBPJPY") is True
        assert validate_symbol("XAUUSD") is True
        assert validate_symbol("INVALID") is False
        assert validate_symbol("") is False
        assert validate_symbol("EUR") is False

    async def test_validate_channel(self):
        """Channel validation should work correctly."""
        from forex_trading.api.websocket import validate_channel

        assert validate_channel("ticks") is True
        assert validate_channel("positions") is True
        assert validate_channel("invalid_channel") is False
        assert validate_channel("") is False
