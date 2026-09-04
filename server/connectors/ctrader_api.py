"""
Read-only cTrader Open API connector.

cTrader account data is exchanged over the Open API JSON WebSocket endpoint;
the REST token endpoint is only for OAuth token exchange.  This module uses
the JSON endpoint on port 5036 and never sends an order request.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import websockets

from server.database import get_connection

logger = logging.getLogger(__name__)

APPLICATION_AUTH_REQ = 2100
APPLICATION_AUTH_RES = 2101
ACCOUNT_AUTH_REQ = 2102
ACCOUNT_AUTH_RES = 2103
SYMBOLS_LIST_REQ = 2114
SYMBOLS_LIST_RES = 2115
TRADER_REQ = 2121
TRADER_RES = 2122
RECONCILE_REQ = 2124
RECONCILE_RES = 2125
DEAL_LIST_REQ = 2133
DEAL_LIST_RES = 2134
ERROR_RES = 2142


class CTraderConnector:
    """Fetch cTrader account, position, symbol and deal data read-only."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str,
        account_id: str,
        is_live: bool = False,
    ):
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.access_token = (access_token or "").strip()
        self.account_id = (account_id or "").strip()
        self.is_live = bool(is_live)
        self.host = "live.ctraderapi.com" if self.is_live else "demo.ctraderapi.com"

    def sync_account_and_trades(self, local_account_id: int) -> Dict[str, Any]:
        """Synchronize the configured cTrader account without simulation."""
        missing = [
            name
            for name, value in (
                ("Client ID", self.client_id),
                ("Client Secret", self.client_secret),
                ("Access Token", self.access_token),
                ("cTrader Account ID", self.account_id),
            )
            if not value or value.startswith("demo_")
        ]
        if missing:
            return {
                "status": "error",
                "error": "Real cTrader credentials are required: " + ", ".join(missing) + ".",
            }

        try:
            remote = asyncio.run(self._fetch_remote_data())
            return self._persist_synced_data(local_account_id, remote)
        except ValueError as exc:
            logger.error("cTrader sync rejected: %s", exc)
            return {"status": "error", "error": str(exc)}
        except Exception as exc:
            logger.error("cTrader sync failed: %s", type(exc).__name__)
            return {
                "status": "error",
                "error": "Unable to reach or decode the cTrader Open API response.",
            }

    async def _fetch_remote_data(self) -> Dict[str, Any]:
        """Run the read-only Open API authentication and data requests."""
        try:
            account_id = int(self.account_id)
        except ValueError as exc:
            raise ValueError("cTrader Account ID must be numeric.") from exc

        uri = f"wss://{self.host}:5036"
        async with websockets.connect(uri, open_timeout=15, close_timeout=5, max_size=8 * 1024 * 1024) as socket:
            await self._request(
                socket,
                APPLICATION_AUTH_REQ,
                {"clientId": self.client_id, "clientSecret": self.client_secret},
                APPLICATION_AUTH_RES,
            )
            await self._request(
                socket,
                ACCOUNT_AUTH_REQ,
                {"ctidTraderAccountId": account_id, "accessToken": self.access_token},
                ACCOUNT_AUTH_RES,
            )

            trader_response = await self._request(
                socket,
                TRADER_REQ,
                {"ctidTraderAccountId": account_id},
                TRADER_RES,
            )
            symbols_response = await self._request(
                socket,
                SYMBOLS_LIST_REQ,
                {"ctidTraderAccountId": account_id, "includeArchivedSymbols": False},
                SYMBOLS_LIST_RES,
            )
            reconcile_response = await self._request(
                socket,
                RECONCILE_REQ,
                {"ctidTraderAccountId": account_id, "returnProtectionOrders": False},
                RECONCILE_RES,
            )

            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            from_ms = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp() * 1000)
            deals_response = await self._request(
                socket,
                DEAL_LIST_REQ,
                {
                    "ctidTraderAccountId": account_id,
                    "fromTimestamp": from_ms,
                    "toTimestamp": now_ms,
                    "maxRows": 1000,
                },
                DEAL_LIST_RES,
            )

        trader = trader_response.get("trader") or {}
        money_digits = int(trader.get("moneyDigits", 2))
        divisor = 10 ** money_digits
        return {
            "trader": trader,
            "money_digits": money_digits,
            "balance": float(trader.get("balance", 0)) / divisor,
            "equity": float(trader.get("balance", 0)) / divisor,
            "leverage": max(1, round(float(trader.get("leverageInCents", 10000)) / 100)),
            "positions": (reconcile_response.get("position") or []),
            "symbols": {
                str(symbol.get("symbolId")): symbol.get("symbolName", "")
                for symbol in (symbols_response.get("symbol") or [])
            },
            "deals": deals_response.get("deal") or [],
        }

    async def _request(
        self,
        socket: Any,
        payload_type: int,
        payload: Dict[str, Any],
        expected_type: int,
    ) -> Dict[str, Any]:
        client_msg_id = uuid.uuid4().hex
        await socket.send(
            json.dumps(
                {
                    "clientMsgId": client_msg_id,
                    "payloadType": payload_type,
                    "payload": payload,
                }
            )
        )
        while True:
            raw = await asyncio.wait_for(socket.recv(), timeout=20)
            message = json.loads(raw)
            message_type = int(message.get("payloadType", 0))
            if message_type == ERROR_RES:
                error = message.get("payload") or {}
                code = error.get("errorCode", "unknown error")
                description = error.get("description", "")
                raise ValueError(f"cTrader API error {code}: {description}".rstrip(": "))
            if message_type == expected_type:
                return message.get("payload") or {}

    def _persist_synced_data(self, local_account_id: int, remote: Dict[str, Any]) -> Dict[str, Any]:
        now_str = datetime.now(timezone.utc).isoformat()
        inserted = 0
        updated = 0
        money_digits = int(remote.get("money_digits", 2))
        divisor = 10 ** money_digits
        balance = float(remote["balance"])
        equity = float(remote["equity"])

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM accounts WHERE id = ?;", (local_account_id,))
            if not cursor.fetchone():
                raise ValueError(f"Account {local_account_id} not found.")

            cursor.execute(
                """
                UPDATE accounts
                SET current_balance = ?, equity = ?, leverage = ?,
                    last_synced_at = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    balance,
                    equity,
                    remote.get("leverage", 100),
                    now_str,
                    now_str,
                    local_account_id,
                ),
            )

            symbols = remote.get("symbols", {})
            for deal in remote.get("deals", []):
                close_detail = deal.get("closePositionDetail") or {}
                if not close_detail:
                    continue
                ticket = str(deal.get("dealId") or "").strip()
                symbol = str(symbols.get(str(deal.get("symbolId")), "")).upper().strip()
                if not ticket or not symbol:
                    continue

                deal_digits = int(close_detail.get("moneyDigits", money_digits))
                deal_divisor = 10 ** deal_digits
                gross_profit = float(close_detail.get("grossProfit", 0)) / deal_divisor
                swap = float(close_detail.get("swap", 0)) / deal_divisor
                commission = float(close_detail.get("commission", 0)) / deal_divisor
                net_profit = gross_profit + swap + commission
                status = "WIN" if net_profit > 0.001 else ("LOSS" if net_profit < -0.001 else "BE")
                execution_time = datetime.fromtimestamp(
                    float(deal.get("executionTimestamp", 0)) / 1000,
                    tz=timezone.utc,
                ).isoformat()
                direction = "BUY" if int(deal.get("tradeSide", 2)) == 1 else "SELL"
                volume = float(deal.get("filledVolume", 0)) / 100.0
                close_price = float(deal.get("executionPrice", 0))
                open_price = float(close_detail.get("entryPrice", close_price))

                cursor.execute(
                    "SELECT id FROM trades WHERE account_id = ? AND ticket = ?;",
                    (local_account_id, ticket),
                )
                if cursor.fetchone():
                    updated += 1
                    continue

                cursor.execute(
                    """
                    INSERT INTO trades (
                        account_id, ticket, symbol, direction, volume,
                        open_time, close_time, open_price, close_price,
                        commission, swap, gross_profit, net_profit, status,
                        notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        local_account_id,
                        ticket,
                        symbol,
                        direction,
                        volume,
                        execution_time,
                        execution_time,
                        open_price,
                        close_price,
                        commission,
                        swap,
                        gross_profit,
                        net_profit,
                        status,
                        "Synced via cTrader Open API",
                        now_str,
                        now_str,
                    ),
                )
                inserted += 1

            cursor.execute(
                """
                INSERT INTO equity_history (account_id, timestamp, balance, equity, margin)
                VALUES (?, ?, ?, ?, 0.0);
                """,
                (local_account_id, now_str, balance, equity),
            )
            conn.commit()

        return {
            "status": "success",
            "account_id": local_account_id,
            "balance": balance,
            "equity": equity,
            "inserted_trades": inserted,
            "updated_trades": updated,
            "message": "cTrader account synchronized via Open API.",
            "synced_at": now_str,
        }


def sync_ctrader_account(account_id: int) -> Dict[str, Any]:
    """Load cTrader credentials from the database and synchronize."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, ctrader_client_id, ctrader_client_secret,
                   ctrader_access_token, ctrader_account_id, ctrader_is_live
            FROM accounts WHERE id = ?;
            """,
            (account_id,),
        )
        account = cursor.fetchone()
        if not account:
            return {"status": "error", "error": f"Account {account_id} not found."}

    return CTraderConnector(
        client_id=account["ctrader_client_id"] or "",
        client_secret=account["ctrader_client_secret"] or "",
        access_token=account["ctrader_access_token"] or "",
        account_id=account["ctrader_account_id"] or "",
        is_live=bool(account["ctrader_is_live"]),
    ).sync_account_and_trades(account_id)


def sync_all_active_ctrader_accounts() -> Dict[str, Any]:
    """Synchronize auto-sync-enabled cTrader accounts only.

    MetaTrader accounts are updated by their locally running MQL expert
    advisors through ``/api/sync/mql`` and therefore are not polled here.
    """
    with get_connection() as conn:
        account_ids = [
            row["id"]
            for row in conn.execute(
                """
                SELECT id FROM accounts
                WHERE auto_sync_enabled = 1 AND platform = 'cTrader';
                """
            ).fetchall()
        ]

    details = [sync_ctrader_account(account_id) for account_id in account_ids]
    return {
        "status": "success",
        "synced_count": sum(detail.get("status") == "success" for detail in details),
        "details": details,
    }
