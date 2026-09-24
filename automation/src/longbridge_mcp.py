"""Longbridge MCP (Model Context Protocol) client wrapper.

Provides a thin Python client for the Longbridge OpenAPI MCP service at
https://mcp.longbridge.com. Authentication uses an OAuth 2 Bearer token
(env LBP_ACCESS_TOKEN or LONGBRIDGE_ACCESS_TOKEN).

The MCP exposes 162 tools covering:
  - Market data: quote, candlesticks, history_candlesticks, tick_data, trades
  - Account: account_balance, stock_positions, fund_positions, short_positions
  - Trading: submit_order, cancel_order, replace_order, today_orders, history_orders
  - Reference: option_chain, calc_indexes, watchlist, alert_*, capital_flow, ...

This wrapper:
  - Handles JSON-RPC 2.0 framing over HTTP POST
  - Parses the SSE (`text/event-stream`) responses Longbridge returns
  - Exposes a generic call_tool(name, arguments) entry point
  - Provides typed convenience helpers for the most-used tools (quote, candlesticks)
  - Caches the access token from /workspace/secrets/longbridge_token.json if env empty
  - Auto-refresh hint via the refresh_token field (currently manual — call /agent/authenticate
    with a fresh auth-code to mint a new pair when token expires)

v1 — 2026-09-24 — initial Longbridge integration.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

log = logging.getLogger("longbridge_mcp")

# MCP service endpoints
MCP_MAIN_URL = os.environ.get("LBP_MCP_URL", "https://mcp.longbridge.com")
MCP_AUTH_URL = os.environ.get("LBP_AUTH_URL", "https://mcp.longbridge.com/agent")
MCP_TIMEOUT = 30  # seconds

# Token source order:
#   1. LBP_ACCESS_TOKEN env (preferred, matches GHA secret name)
#   2. LONGBRIDGE_ACCESS_TOKEN env (alternative)
#   3. /workspace/secrets/longbridge_token.json (sandbox persist fallback)
_TOKEN_FILE = Path("/workspace/secrets/longbridge_token.json")


def _load_access_token() -> str:
    """Load OAuth access token from env or fallback file."""
    tok = os.environ.get("LBP_ACCESS_TOKEN") or os.environ.get("LONGBRIDGE_ACCESS_TOKEN")
    if tok:
        return tok.strip()
    if _TOKEN_FILE.exists():
        try:
            d = json.loads(_TOKEN_FILE.read_text())
            return d.get("access_token", "").strip()
        except Exception as e:
            log.warning(f"[longbridge] token file read failed: {e}")
    raise RuntimeError(
        "Longbridge access token not found. Set LBP_ACCESS_TOKEN env, "
        "or place longbridge_token.json at /workspace/secrets/."
    )


def _post_tool_call(name: str, arguments: dict, timeout: int = MCP_TIMEOUT) -> Any:
    """Send a tools/call JSON-RPC request and return the structuredContent or text payload."""
    access_token = _load_access_token()
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 10_000_000,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        # Longbridge MCP insists on accepting both JSON + SSE per MCP spec
        "Accept": "application/json, text/event-stream",
    }
    r = requests.post(MCP_MAIN_URL, json=payload, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"Longbridge MCP HTTP {r.status_code}: {r.text[:300]}")
    return _parse_sse_response(r.text)


def _parse_sse_response(raw: str) -> Any:
    """Parse Longbridge MCP SSE response into the result payload.

    Longbridge returns `data: {jsonrpc...}` lines. We extract the first
    JSON-RPC response object.
    """
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            obj = json.loads(line[5:].strip())
            if "result" in obj:
                # MCP wraps result.content[0].text as a stringified JSON for most tools
                res = obj["result"]
                sc = res.get("structuredContent")
                if sc:
                    return sc
                # Fallback: parse content[0].text as JSON
                content = res.get("content", [])
                if content and content[0].get("type") == "text":
                    try:
                        return json.loads(content[0]["text"])
                    except json.JSONDecodeError:
                        return content[0]["text"]
                return res
            if "error" in obj:
                raise RuntimeError(f"Longbridge MCP error: {obj['error']}")
    raise RuntimeError(f"Longbridge MCP empty response: {raw[:200]}")


# ---------------------------------------------------------------------------
# Public client API
# ---------------------------------------------------------------------------


class LongbridgeMCP:
    """Thin client for the Longbridge MCP service.

    Usage:
        lb = LongbridgeMCP()
        quote = lb.quote(["NVDA.US", "BTC-USD"])
        bars = lb.candlesticks("BTC-USD", period="minute", count=300)
    """

    def __init__(self, access_token: Optional[str] = None, base_url: str = MCP_MAIN_URL):
        if access_token:
            os.environ["LBP_ACCESS_TOKEN"] = access_token
        self.base_url = base_url

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        """Generic tool invocation. Returns parsed result (dict / list / str)."""
        return _post_tool_call(name, arguments or {})

    # ---- Convenience wrappers for common tools ----

    def quote(self, symbols: list[str]) -> list[dict]:
        """Real-time quote for one or more symbols (e.g. ['NVDA.US', 'BTC-USD'])."""
        res = self.call_tool("quote", {"symbols": symbols})
        if isinstance(res, list):
            return res
        if isinstance(res, dict) and "list" in res:
            return res["list"]
        return []

    def candlesticks(
        self,
        symbol: str,
        period: str = "minute",
        count: int = 300,
        adjust_type: str = "no_adjust",
    ) -> list[dict]:
        """Most-recent N candlesticks.

        Args:
            symbol: ticker like 'BTC-USD' or 'NVDA.US'
            period: minute | hour | day | week | month | year
            count: number of bars back from now
            adjust_type: no_adjust | forward_adjust
        """
        res = self.call_tool("candlesticks", {
            "symbol": symbol,
            "period": period,
            "count": count,
            "adjust_type": adjust_type,
        })
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            for k in ("candles", "list", "data"):
                if k in res:
                    return res[k]
        return []

    def history_candlesticks(
        self,
        symbol: str,
        period: str = "5m",
        start: Optional[str] = None,
        end: Optional[str] = None,
        adjust_type: str = "no_adjust",
    ) -> list[dict]:
        """Historical candlesticks between [start, end] ISO timestamps.

        Args:
            symbol: ticker like 'IBIT.US' or 'BTC-USD'
            period: 1m, 5m, 15m, 30m, 60m, 1d, etc.
            start: ISO timestamp (UTC recommended)
            end: ISO timestamp (UTC recommended)

        If start/end omitted, returns last 1000 bars.

        Note: Longbridge MCP exposes two history tools:
          - history_candlesticks_by_date  (date range)
          - history_candlesticks_by_offset (offset from now)
        We default to by_date; pass `offset=True` to use by_offset.
        """
        if start or end:
            args = {"symbol": symbol, "period": period, "adjust_type": adjust_type}
            if start:
                args["start_date"] = start
            if end:
                args["end_date"] = end
            res = self.call_tool("history_candlesticks_by_date", args)
        else:
            # Default to by_offset with no offset (most recent)
            res = self.call_tool(
                "history_candlesticks_by_offset",
                {"symbol": symbol, "period": period, "adjust_type": adjust_type, "offset": 0},
            )
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            for k in ("candles", "list", "data"):
                if k in res:
                    return res[k]
        return []

    def account_balance(self, currency: Optional[str] = None) -> dict:
        args = {}
        if currency:
            args["currency"] = currency
        return self.call_tool("account_balance", args)

    def stock_positions(self) -> dict:
        return self.call_tool("stock_positions", {})

    def today_orders(self) -> list:
        return self.call_tool("today_orders", {})

    # ---- Health check ----

    def ping(self) -> bool:
        """Quick health probe via a tiny quote call."""
        try:
            self.quote(["NVDA.US"])
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_client: Optional[LongbridgeMCP] = None


def get_client() -> LongbridgeMCP:
    """Get the module-level singleton client."""
    global _default_client
    if _default_client is None:
        _default_client = LongbridgeMCP()
    return _default_client


if __name__ == "__main__":
    # Quick smoke test
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    lb = get_client()
    print("Ping:", lb.ping())
    q = lb.quote(["NVDA.US", "BTC-USD"])
    for r in q[:3]:
        print(f"  {r.get('symbol')}: ${r.get('last_done')}")
    bars = lb.candlesticks("BTC-USD", period="minute", count=10)
    print(f"BTC-USD last 10 minute bars: {len(bars)}")
    for b in bars[-3:]:
        print(f"  {b}")
