from app.utils.database import get_db_connection
from datetime import datetime, date
from decimal import Decimal


def _s(row):
    if row is None:
        return None
    out = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


class Notification:

    @staticmethod
    def push(user_id: int, type: str, title: str, message: str, link: str = None):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO notifications (user_id, type, title, message, link)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, type, title, message, link))
        conn.commit()
        nid = cursor.lastrowid
        cursor.close(); conn.close()
        return nid

    @staticmethod
    def push_to_admins(type: str, title: str, message: str, link: str = None,
                       exclude_user_id: int = None):
        """Push notification to all admin/lead users."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id FROM users
            WHERE role IN ('admin','team_lead','marketing_head','crm')
        """)
        admins = cursor.fetchall()
        for a in admins:
            if a['id'] == exclude_user_id:
                continue
            cursor.execute("""
                INSERT INTO notifications (user_id, type, title, message, link)
                VALUES (%s, %s, %s, %s, %s)
            """, (a['id'], type, title, message, link))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_by_user(user_id: int, unread_only: bool = False):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM notifications WHERE user_id = %s"
        if unread_only:
            query += " AND is_read = 0"
        query += " ORDER BY created_at DESC LIMIT 50"
        cursor.execute(query, (user_id,))
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def mark_read(notification_id: int, user_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE notifications SET is_read=1 WHERE id=%s AND user_id=%s",
            (notification_id, user_id)
        )
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def mark_all_read(user_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE notifications SET is_read=1 WHERE user_id=%s", (user_id,)
        )
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=0",
            (user_id,)
        )
        count = cursor.fetchone()[0]
        cursor.close(); conn.close()
        return count
