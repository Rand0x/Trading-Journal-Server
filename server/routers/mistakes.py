"""
Mistakes Router
Behavioral and psychological trading mistake management.
"""

from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException
from server.database import get_connection
from server.models import MistakeCreate, MistakeResponse

router = APIRouter(prefix="/api/mistakes", tags=["Mistakes"])

@router.get("", response_model=List[MistakeResponse])
def get_mistakes():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.*,
                   COUNT(t.id) as occurrence_count,
                   ROUND(SUM(CASE WHEN t.net_profit < 0 THEN ABS(t.net_profit) ELSE 0.0 END), 2) as total_loss
            FROM mistakes m
            LEFT JOIN trades t ON t.mistake_id = m.id
            GROUP BY m.id
            ORDER BY total_loss DESC;
        """)
        return [dict(r) for r in cursor.fetchall()]

@router.post("", response_model=MistakeResponse)
def create_mistake(mistake: MistakeCreate):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO mistakes (name, description, severity, color, created_at)
                VALUES (?, ?, ?, ?, ?);
            """, (mistake.name, mistake.description or "", mistake.severity or "MEDIUM",
                  mistake.color or "#ef4444", now_str))
            m_id = cursor.lastrowid
            conn.commit()
            cursor.execute("SELECT *, 0 as occurrence_count, 0.0 as total_loss FROM mistakes WHERE id = ?;", (m_id,))
            return dict(cursor.fetchone())
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error creating mistake: {str(e)}")

@router.delete("/{mistake_id}")
def delete_mistake(mistake_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mistakes WHERE id = ?;", (mistake_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mistake not found")
        conn.commit()
    return {"message": "Mistake deleted successfully"}
