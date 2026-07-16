"""
Robinhood Agentic Trading MCP client.

Talks to Robinhood's official MCP server at https://agent.robinhood.com/mcp/trading
using the streamable-HTTP transport, authenticated by an OAuth 2.0 access token
that you obtain by connecting an agent in the Robinhood mobile app and copying
the token.

Trade modes (set via TRADE_MODE env var):
  SIGNAL_ONLY      — never place any orders. Just for testing rules + notifier.
  PREVIEW_APPROVAL — submit orders in "preview" mode; you approve in Robinhood app.
  FULL_AUTO        — submit and execute without approval (only after paper-validation).

Because the Agentic Trading MCP surface is evolving, this client is a thin
adapter around the standard MCP client — it discovers tools at runtime and
calls them by name. If Robinhood renames a tool, adjust the constants below.
"""

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from config import TRADE_MODE, ROBINHOOD_MCP_URL

# --- Tool names on the Robinhood MCP server (verify against latest docs) ---
TOOL_PLACE_ORDER = "place_equity_order"
TOOL_PREVIEW_ORDER = "preview_equity_order"
TOOL_CANCEL_ORDER = "cancel_order"
TOOL_GET_POSITIONS = "get_positions"
TOOL_GET_ACCOUNT = "get_account"
TOOL_GET_QUOTE = "get_quote"


@dataclass
class OrderResult:
    ok: bool
    mode: str
    order_id: str | None = None
    message: str = ""
    raw: dict | None = None


def _get_token() -> str:
    token = os.environ.get("ROBINHOOD_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "ROBINHOOD_ACCESS_TOKEN not set. Connect the agent in Robinhood app → "
            "Agentic Trading tab, then copy the token into your .env file."
        )
    return token


async def _call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Call an MCP tool over streamable HTTP.
    Uses the `mcp` python package (added to requirements.txt).
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with streamablehttp_client(ROBINHOOD_MCP_URL, headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            # MCP returns list of content blocks; extract the JSON payload
            if result.content and hasattr(result.content[0], "text"):
                import json
                try:
                    return json.loads(result.content[0].text)
                except json.JSONDecodeError:
                    return {"raw_text": result.content[0].text}
            return {"raw": str(result)}


def _run(coro):
    """Run an async coroutine from sync context, works both inside and outside event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a running loop — schedule and wait synchronously.
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


# ---------- Public interface ----------


def place_order(
    ticker: str,
    side: str,        # "buy" | "sell"
    shares: int,
    limit_price: float | None = None,
    stop_loss: float | None = None,
    target_price: float | None = None,
) -> OrderResult:
    """
    Route an order through the configured TRADE_MODE.

    SIGNAL_ONLY: does nothing, returns ok=True with mode note.
    PREVIEW_APPROVAL: calls the preview tool — user gets a push and taps approve.
    FULL_AUTO: calls the place tool directly.
    """
    if side not in ("buy", "sell"):
        return OrderResult(ok=False, mode=TRADE_MODE, message=f"Invalid side: {side}")
    if shares < 1:
        return OrderResult(ok=False, mode=TRADE_MODE, message="Shares must be >= 1")

    if TRADE_MODE == "SIGNAL_ONLY":
        return OrderResult(
            ok=True,
            mode=TRADE_MODE,
            message=f"[SIGNAL_ONLY] Would {side} {shares} {ticker}",
        )

    order_args: dict[str, Any] = {
        "symbol": ticker,
        "side": side,
        "quantity": shares,
        "order_type": "limit" if limit_price else "market",
        "time_in_force": "day",
    }
    if limit_price:
        order_args["limit_price"] = round(float(limit_price), 2)
    if stop_loss:
        order_args["stop_loss_price"] = round(float(stop_loss), 2)
    if target_price:
        order_args["take_profit_price"] = round(float(target_price), 2)

    tool = TOOL_PREVIEW_ORDER if TRADE_MODE == "PREVIEW_APPROVAL" else TOOL_PLACE_ORDER

    try:
        result = _run(_call_mcp_tool(tool, order_args))
        order_id = result.get("id") or result.get("order_id")
        return OrderResult(
            ok=True,
            mode=TRADE_MODE,
            order_id=order_id,
            message=f"Order submitted via {tool}",
            raw=result,
        )
    except Exception as e:
        return OrderResult(
            ok=False, mode=TRADE_MODE, message=f"MCP call failed: {e}"
        )


def get_positions() -> dict:
    try:
        return _run(_call_mcp_tool(TOOL_GET_POSITIONS, {}))
    except Exception as e:
        return {"error": str(e)}


def get_account() -> dict:
    try:
        return _run(_call_mcp_tool(TOOL_GET_ACCOUNT, {}))
    except Exception as e:
        return {"error": str(e)}


def get_quote(ticker: str) -> dict:
    try:
        return _run(_call_mcp_tool(TOOL_GET_QUOTE, {"symbol": ticker}))
    except Exception as e:
        return {"error": str(e)}


def cancel_order(order_id: str) -> dict:
    try:
        return _run(_call_mcp_tool(TOOL_CANCEL_ORDER, {"order_id": order_id}))
    except Exception as e:
        return {"error": str(e)}
