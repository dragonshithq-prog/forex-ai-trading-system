"""WebSocket endpoints for real-time streaming."""

import asyncio
import random
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from forex_trading.market_data.services.demo_data import generate_demo_tick

router = APIRouter()


@router.websocket("/ws/live")
async def live_stream(websocket: WebSocket):
    await websocket.accept()
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "GBPJPY"]
    tick_cache = {s: {"close": 1.0} for s in symbols}
    try:
        while True:
            for sym in symbols:
                tick = generate_demo_tick(sym)
                tick["type"] = "tick"
                await websocket.send_json(tick)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
