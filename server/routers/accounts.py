"""
Accounts Router
Manages trading accounts (MT4, MT5, cTrader, Manual) and API Keys.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from server.database import get_connection
from server.models import AccountCreate, AccountUpdate, AccountResponse

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])

@router.get("", response_model=List[AccountResponse])
def get_accounts():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts ORDER BY id ASC;")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE id = ?;", (account_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Account not found")
        return dict(row)

@router.post("", response_model=AccountResponse)
def create_account(account: AccountCreate):
    now_str = datetime.now(timezone.utc).isoformat()
    api_key = f"key_{uuid.uuid4().hex[:16]}"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO accounts (
                name, broker, platform, account_number, currency,
                initial_balance, current_balance, equity, margin, free_margin, leverage,
                api_key, server_name, password, metaapi_token, auto_sync_enabled, sync_interval_minutes,
                ctrader_client_id, ctrader_client_secret, ctrader_access_token, ctrader_account_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            account.name, account.broker or "", account.platform, account.account_number or "",
            account.currency or "USD", account.initial_balance or 10000.0,
            account.current_balance or account.initial_balance or 10000.0,
            account.equity or account.initial_balance or 10000.0,
            account.margin or 0.0, account.free_margin or account.initial_balance or 10000.0,
            account.leverage or 100, api_key,
            account.server_name or "", account.password or "", account.metaapi_token or "",
            1 if account.auto_sync_enabled else 0, account.sync_interval_minutes or 5,
            account.ctrader_client_id or "", account.ctrader_client_secret or "",
            account.ctrader_access_token or "", account.ctrader_account_id or "",
            now_str, now_str
        ))
        acc_id = cursor.lastrowid

        # Insert initial equity point
        cursor.execute("""
            INSERT INTO equity_history (account_id, timestamp, balance, equity)
            VALUES (?, ?, ?, ?);
        """, (acc_id, now_str, account.initial_balance or 10000.0, account.equity or 10000.0))

        conn.commit()

        cursor.execute("SELECT * FROM accounts WHERE id = ?;", (acc_id,))
        return dict(cursor.fetchone())

@router.put("/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, account: AccountUpdate):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE id = ?;", (account_id,))
        existing = cursor.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Account not found")

        updates = []
        values = []
        for field, val in account.model_dump(exclude_unset=True).items():
            updates.append(f"{field} = ?")
            values.append(val)

        if updates:
            updates.append("updated_at = ?")
            values.append(now_str)
            values.append(account_id)
            cursor.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?;", values)
            conn.commit()

        cursor.execute("SELECT * FROM accounts WHERE id = ?;", (account_id,))
        return dict(cursor.fetchone())

@router.post("/{account_id}/regenerate-key")
def regenerate_api_key(account_id: int):
    new_key = f"key_{uuid.uuid4().hex[:16]}"
    now_str = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE accounts SET api_key = ?, updated_at = ? WHERE id = ?;", (new_key, now_str, account_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
        conn.commit()
    return {"api_key": new_key}

@router.delete("/{account_id}")
def delete_account(account_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE id = ?;", (account_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Account not found")
        conn.commit()
    return {"message": "Account deleted successfully"}
