"""Broker discovery service - auto-detect MT4/MT5 terminals and test connections."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Candidate MetaTrader installation roots on Windows
_MT4_ROOTS: list[str] = [
    r"C:\Program Files\MetaTrader 4",
    r"C:\Program Files (x86)\MetaTrader 4",
    r"C:\Program Files\FXCM MetaTrader 4",
    r"C:\Program Files\IC Markets MetaTrader 4",
]

_MT5_ROOTS: list[str] = [
    r"C:\Program Files\MetaTrader 5",
    r"C:\Program Files (x86)\MetaTrader 5",
    r"C:\Program Files\MetaQuotes\MetaTrader 5",
]

# MetaQuotes roaming profile (contains installed terminals)
_ROAMING_MT_BASE = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"

# Bridge EA listens on these ports (configurable in EA settings, scan all)
_BRIDGE_PORTS: list[int] = list(range(3000, 3011))

_CONNECT_TIMEOUT = 1.0  # seconds per port probe


class BrokerDiscoveryService:
    """
    Auto-discover MT4/MT5 terminals and test broker connections.

    Discovery strategy:
    1. Scan well-known Windows installation paths for MetaTrader executables.
    2. Scan MetaQuotes roaming profile for all installed terminal data directories.
    3. Probe TCP ports 3000-3010 on localhost; respond to ``ping`` command.
    """

    # ------------------------------------------------------------------
    # Terminal discovery
    # ------------------------------------------------------------------

    async def discover_mt_terminals(self) -> list[dict[str, Any]]:
        """
        Discover running MT4/MT5 terminals on the local machine.

        Returns:
            List of dicts with keys: version, path, port, status, bridge_active.
        """
        found: list[dict[str, Any]] = []

        # 1. Static installation paths
        for path_str in _MT4_ROOTS:
            info = _check_static_path(path_str, "MT4")
            if info:
                found.append(info)

        for path_str in _MT5_ROOTS:
            info = _check_static_path(path_str, "MT5")
            if info:
                found.append(info)

        # 2. MetaQuotes roaming profile (covers all broker-branded installs)
        if _ROAMING_MT_BASE.exists():
            for terminal_dir in _ROAMING_MT_BASE.iterdir():
                if not terminal_dir.is_dir():
                    continue
                info = _check_roaming_terminal(terminal_dir)
                if info:
                    found.append(info)

        # 3. Probe bridge ports concurrently
        bridge_results = await self._probe_bridge_ports()

        # 4. Merge bridge status into discovered terminals
        active_ports = {r["port"] for r in bridge_results if r["bridge_active"]}
        for terminal in found:
            terminal["bridge_ports"] = [p for p in active_ports]
            terminal["bridge_active"] = bool(active_ports)

        # 5. Also add synthetic entries for active bridges not matched to a path
        for bridge in bridge_results:
            if bridge["bridge_active"]:
                already_present = any(
                    bridge["port"] in t.get("bridge_ports", []) for t in found
                )
                if not already_present:
                    found.append({
                        "version": "unknown",
                        "path": None,
                        "port": bridge["port"],
                        "bridge_active": True,
                        "status": "connected",
                        "bridge_ports": [bridge["port"]],
                    })

        logger.info("mt_terminals_discovered", count=len(found))
        return found

    # ------------------------------------------------------------------
    # Bridge port probing
    # ------------------------------------------------------------------

    async def _probe_bridge_ports(self) -> list[dict[str, Any]]:
        tasks = [self._probe_port(port) for port in _BRIDGE_PORTS]
        return await asyncio.gather(*tasks)

    async def _probe_port(self, port: int) -> dict[str, Any]:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port),
                timeout=_CONNECT_TIMEOUT,
            )
        except (OSError, asyncio.TimeoutError):
            return {"port": port, "bridge_active": False}

        try:
            writer.write(b'{"cmd":"ping"}\n')
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=_CONNECT_TIMEOUT)
            data = json.loads(line.decode().strip())
            active = data.get("status") == "ok"
        except Exception:  # noqa: BLE001
            active = False
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

        logger.debug("bridge_port_probe", port=port, active=active)
        return {"port": port, "bridge_active": active}

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    async def test_broker_connection(
        self, broker_type: str, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Test a broker connection with the given credentials.

        Args:
            broker_type: "mt4" | "mt5" | "oanda"
            credentials: Dict matching BrokerCredentials fields.

        Returns:
            Dict with keys: success (bool), latency_ms (float|None),
            account_id (str|None), error (str|None).
        """
        broker_type = broker_type.lower()

        if broker_type in ("mt4", "mt5"):
            return await self._test_mt_connection(broker_type, credentials)
        if broker_type == "oanda":
            return await self._test_oanda_connection(credentials)

        return {"success": False, "error": f"Unsupported broker type: {broker_type}"}

    # ------------------------------------------------------------------
    # MT bridge connection test
    # ------------------------------------------------------------------

    async def _test_mt_connection(
        self, broker_type: str, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        host = credentials.get("host", "127.0.0.1")
        port = int(credentials.get("port", 3001 if broker_type == "mt5" else 3000))

        import time
        t0 = time.monotonic()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=5.0,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            return {"success": False, "error": str(exc), "latency_ms": None, "account_id": None}

        try:
            writer.write(b'{"cmd":"account_info"}\n')
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            data = json.loads(line.decode().strip())
            if data.get("status") == "ok":
                account_id = str(data.get("data", {}).get("login", ""))
                return {
                    "success": True,
                    "latency_ms": latency_ms,
                    "account_id": account_id,
                    "error": None,
                }
            return {
                "success": False,
                "error": data.get("error", "unknown"),
                "latency_ms": latency_ms,
                "account_id": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc), "latency_ms": None, "account_id": None}
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # OANDA connection test
    # ------------------------------------------------------------------

    async def _test_oanda_connection(
        self, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        api_key = credentials.get("api_key", "")
        account_id = credentials.get("account_id", "")
        environment = credentials.get("environment", "practice")

        if not api_key or not account_id:
            return {
                "success": False,
                "error": "api_key and account_id are required",
                "latency_ms": None,
                "account_id": None,
            }

        try:
            import oandapyV20  # type: ignore[import]
            import oandapyV20.endpoints.accounts as accounts  # type: ignore[import]
        except ImportError:
            return {
                "success": False,
                "error": "oandapyV20 not installed",
                "latency_ms": None,
                "account_id": None,
            }

        import time

        def _test() -> dict[str, Any]:
            t0 = time.monotonic()
            api = oandapyV20.API(access_token=api_key, environment=environment)
            req = accounts.AccountSummary(account_id)
            api.request(req)
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            return {"success": True, "latency_ms": latency_ms, "account_id": account_id, "error": None}

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _test)
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "error": str(exc),
                "latency_ms": None,
                "account_id": None,
            }


# ---------------------------------------------------------------------------
# Path-check helpers
# ---------------------------------------------------------------------------

def _check_static_path(path_str: str, version: str) -> dict[str, Any] | None:
    p = Path(path_str)
    exe_name = "terminal.exe" if version == "MT4" else "terminal64.exe"
    if (p / exe_name).exists():
        return {
            "version": version,
            "path": str(p),
            "status": "installed",
            "bridge_active": False,
            "bridge_ports": [],
        }
    return None


def _check_roaming_terminal(terminal_dir: Path) -> dict[str, Any] | None:
    """Identify MT version from roaming profile directory."""
    # MT5 profile has MQL5/ subdirectory
    if (terminal_dir / "MQL5").exists():
        version = "MT5"
    elif (terminal_dir / "MQL4").exists():
        version = "MT4"
    else:
        return None

    # Try to read origin.txt for the installation path
    origin = terminal_dir / "origin.txt"
    install_path: str | None = None
    if origin.exists():
        try:
            install_path = origin.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            pass

    return {
        "version": version,
        "path": install_path or str(terminal_dir),
        "profile_dir": str(terminal_dir),
        "status": "installed",
        "bridge_active": False,
        "bridge_ports": [],
    }
