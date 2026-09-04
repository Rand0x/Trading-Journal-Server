"""
Demo Seed Data Generator
Generates realistic trading history for demonstration purposes,
including winning trades, losing trades, setups, mistakes, notes, and equity growth.
"""

from datetime import datetime, timezone, timedelta
import random
from server.database import get_connection

def seed_demo_trades(account_id: int = 1, count: int = 35):
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if trades already exist
        cursor.execute("SELECT COUNT(*) FROM trades WHERE account_id = ?;", (account_id,))
        if cursor.fetchone()[0] > 5:
            print("Account already has trades, skipping demo seed.")
            return

        # Fetch playbooks and mistakes
        cursor.execute("SELECT id FROM playbooks;")
        playbook_ids = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT id FROM mistakes;")
        mistake_ids = [r[0] for r in cursor.fetchall()]

        symbols_data = [
            ("EURUSD", 1.0850, 0.0001, 1.0),
            ("GBPUSD", 1.2950, 0.0001, 1.0),
            ("XAUUSD", 2480.0, 0.1, 0.5),
            ("US30", 40500.0, 1.0, 0.2),
            ("BTCUSD", 62000.0, 10.0, 0.1),
            ("USDJPY", 152.50, 0.01, 1.0)
        ]

        now = datetime.now(timezone.utc)
        base_time = now - timedelta(days=28)
        running_balance = 50000.0

        for i in range(count):
            day_offset = int((i / count) * 26)
            trade_dt = base_time + timedelta(days=day_offset, hours=random.randint(7, 18), minutes=random.randint(0, 59))
            close_dt = trade_dt + timedelta(minutes=random.randint(15, 240))

            sym, base_p, pip_val, default_lot = random.choice(symbols_data)
            direction = random.choice(["BUY", "SELL"])
            lots = round(default_lot * random.uniform(0.5, 2.0), 2)
            
            # 62% win rate distribution
            is_win = random.random() < 0.62
            
            p_mult = 1 if direction == "BUY" else -1

            if is_win:
                pips = random.randint(15, 55)
                net_pnl = round(pips * lots * 10.0, 2)
                status = "WIN"
                setup_id = random.choice(playbook_ids) if playbook_ids else None
                mistake_id = None
                emotion = random.choice(["Disciplined", "Confident", "Disciplined", "Patient"])
                rating = random.choice([4, 5])
            else:
                pips = random.randint(10, 35)
                net_pnl = round(-pips * lots * 10.0, 2)
                status = "LOSS"
                setup_id = random.choice(playbook_ids) if random.random() < 0.5 and playbook_ids else None
                mistake_id = random.choice(mistake_ids) if mistake_ids else None
                emotion = random.choice(["Anxious", "FOMO", "Frustrated", "Disciplined"])
                rating = random.choice([2, 3])

            open_price = round(base_p + (random.uniform(-50, 50) * pip_val), 4 if base_p < 100 else 2)
            close_price = round(open_price + (p_mult * pips * pip_val if is_win else -p_mult * pips * pip_val), 4 if base_p < 100 else 2)
            
            # SL and TP
            if direction == "BUY":
                sl = round(open_price - (25 * pip_val), 4 if base_p < 100 else 2)
                tp = round(open_price + (50 * pip_val), 4 if base_p < 100 else 2)
            else:
                sl = round(open_price + (25 * pip_val), 4 if base_p < 100 else 2)
                tp = round(open_price - (50 * pip_val), 4 if base_p < 100 else 2)

            commission = round(lots * 7.0, 2)
            swap = 0.0
            gross_pnl = net_pnl + commission

            running_balance += net_pnl
            open_str = trade_dt.strftime("%Y-%m-%d %H:%M:%S")
            close_str = close_dt.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
                INSERT INTO trades (
                    account_id, ticket, symbol, direction, volume,
                    open_time, close_time, open_price, close_price,
                    stop_loss, take_profit, commission, swap,
                    gross_profit, net_profit, pnl_percent, status,
                    setup_id, mistake_id, notes, emotions, rating,
                    tags, timeframe, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                account_id, f"demo_{1000+i}", sym, direction, lots,
                open_str, close_str, open_price, close_price,
                sl, tp, commission, swap, gross_pnl, net_pnl,
                round((net_pnl / 50000.0) * 100, 2), status,
                setup_id, mistake_id,
                f"Trade execution review: {sym} {direction} {lots} lots following market structure.",
                emotion, rating, "LondonSession,Breakout", "M15",
                open_str, close_str
            ))

            # Add equity history snapshot every 5 trades
            if i % 5 == 0:
                cursor.execute("""
                    INSERT INTO equity_history (account_id, timestamp, balance, equity)
                    VALUES (?, ?, ?, ?);
                """, (account_id, close_str, round(running_balance, 2), round(running_balance, 2)))

        # Update final balance on account
        cursor.execute("""
            UPDATE accounts
            SET current_balance = ?, equity = ?, updated_at = ?
            WHERE id = ?;
        """, (round(running_balance, 2), round(running_balance, 2), now.isoformat(), account_id))

        conn.commit()
        print(f"Successfully seeded {count} demo trades. Final account balance: ${running_balance:,.2f}")

if __name__ == "__main__":
    seed_demo_trades()
