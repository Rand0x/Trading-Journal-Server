"""
Playbooks Router
Setup and strategy definition management.
"""

from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException
from server.database import get_connection
from server.models import PlaybookCreate, PlaybookUpdate, PlaybookResponse

router = APIRouter(prefix="/api/playbooks", tags=["Playbooks"])

@router.get("", response_model=List[PlaybookResponse])
def get_playbooks():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*,
                   COUNT(t.id) as trades_count,
                   ROUND(AVG(CASE WHEN t.net_profit > 0 THEN 100.0 ELSE 0.0 END), 1) as win_rate,
                   ROUND(SUM(COALESCE(t.net_profit, 0.0)), 2) as total_pnl
            FROM playbooks p
            LEFT JOIN trades t ON t.setup_id = p.id
            GROUP BY p.id
            ORDER BY p.id ASC;
        """)
        return [dict(r) for r in cursor.fetchall()]

@router.post("", response_model=PlaybookResponse)
def create_playbook(playbook: PlaybookCreate):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO playbooks (name, description, rules, color, created_at)
                VALUES (?, ?, ?, ?, ?);
            """, (playbook.name, playbook.description or "",
                  playbook.rules or "", playbook.color or "#3b82f6", now_str))
            p_id = cursor.lastrowid
            conn.commit()
            cursor.execute("SELECT *, 0 as trades_count, 0.0 as win_rate, 0.0 as total_pnl FROM playbooks WHERE id = ?;", (p_id,))
            return dict(cursor.fetchone())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error creating playbook: {str(e)}")

@router.put("/{playbook_id}", response_model=PlaybookResponse)
def update_playbook(playbook_id: int, playbook: PlaybookUpdate):
    changes = playbook.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No playbook changes supplied")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM playbooks WHERE id = ?;", (playbook_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Playbook not found")

        updates = [f"{field} = ?" for field in changes]
        values = list(changes.values())
        values.append(playbook_id)
        try:
            cursor.execute(
                f"UPDATE playbooks SET {', '.join(updates)} WHERE id = ?;",
                values
            )
            conn.commit()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error updating playbook: {str(e)}")

        cursor.execute("""
            SELECT p.*,
                   COUNT(t.id) as trades_count,
                   ROUND(AVG(CASE WHEN t.net_profit > 0 THEN 100.0 ELSE 0.0 END), 1) as win_rate,
                   ROUND(SUM(COALESCE(t.net_profit, 0.0)), 2) as total_pnl
            FROM playbooks p
            LEFT JOIN trades t ON t.setup_id = p.id
            WHERE p.id = ?
            GROUP BY p.id;
        """, (playbook_id,))
        return dict(cursor.fetchone())

@router.delete("/{playbook_id}")
def delete_playbook(playbook_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM playbooks WHERE id = ?;", (playbook_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Playbook not found")
        conn.commit()
    return {"message": "Playbook deleted successfully"}
