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


class Feedback:

    @staticmethod
    def create(user_id: int, category: str, message: str,
               rating: int, visibility: str = 'named'):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            INSERT INTO feedback (user_id, category, message, rating, visibility)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, category, message, rating, visibility))
        conn.commit()
        fid = cursor.lastrowid
        cursor.execute("""
            SELECT f.*, u.name AS employee_name, u.role AS employee_role
            FROM feedback f
            JOIN users u ON f.user_id = u.id
            WHERE f.id = %s
        """, (fid,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row

    @staticmethod
    def get_my(user_id: int):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM feedback WHERE user_id = %s ORDER BY created_at DESC
        """, (user_id,))
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def get_all(category: str = None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT f.*,
                CASE WHEN f.visibility='anonymous' THEN 'Anonymous' ELSE u.name END AS employee_name,
                CASE WHEN f.visibility='anonymous' THEN NULL ELSE u.role END AS employee_role
            FROM feedback f
            JOIN users u ON f.user_id = u.id
            WHERE 1=1
        """
        params = []
        if category:
            query += " AND f.category = %s"; params.append(category)
        query += " ORDER BY f.created_at DESC"
        cursor.execute(query, params)
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def get_stats():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                ROUND(AVG(rating), 1) AS avg_rating,
                SUM(category='work_environment') AS work_environment,
                SUM(category='team_issue') AS team_issue,
                SUM(category='suggestion') AS suggestion,
                SUM(category='general') AS general
            FROM feedback
            WHERE MONTH(created_at) = MONTH(CURDATE())
              AND YEAR(created_at)  = YEAR(CURDATE())
        """)
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row or {}


class ReviewMeeting:

    @staticmethod
    def create(employee_id: int, reviewer_id: int, meeting_date: str,
               meeting_type: str, notes: str = None,
               improvement_points: str = None, goals_set: str = None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            INSERT INTO review_meetings
                (employee_id, reviewer_id, meeting_date, meeting_type,
                 notes, improvement_points, goals_set)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (employee_id, reviewer_id, meeting_date, meeting_type,
              notes, improvement_points, goals_set))
        conn.commit()
        rid = cursor.lastrowid
        cursor.execute("""
            SELECT rm.*, e.name AS employee_name, r.name AS reviewer_name
            FROM review_meetings rm
            JOIN users e ON rm.employee_id = e.id
            JOIN users r ON rm.reviewer_id = r.id
            WHERE rm.id = %s
        """, (rid,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None

    @staticmethod
    def complete(review_id: int, reviewer_id: int, rating: int,
                 notes: str = None, improvement_points: str = None,
                 goals_set: str = None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, reviewer_id FROM review_meetings WHERE id=%s", (review_id,))
        rev = cursor.fetchone()
        if not rev:
            cursor.close(); conn.close()
            return None, "Review not found"
        if rev['reviewer_id'] != reviewer_id:
            cursor.close(); conn.close()
            return None, "Only the assigned reviewer can complete this review"

        cursor.execute("""
            UPDATE review_meetings
            SET status='completed', rating=%s, notes=%s,
                improvement_points=%s, goals_set=%s
            WHERE id=%s
        """, (rating, notes, improvement_points, goals_set, review_id))
        conn.commit()
        cursor.execute("""
            SELECT rm.*, e.name AS employee_name, r.name AS reviewer_name
            FROM review_meetings rm
            JOIN users e ON rm.employee_id = e.id
            JOIN users r ON rm.reviewer_id = r.id
            WHERE rm.id = %s
        """, (review_id,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None

    @staticmethod
    def get_my(employee_id: int):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT rm.*, r.name AS reviewer_name
            FROM review_meetings rm
            JOIN users r ON rm.reviewer_id = r.id
            WHERE rm.employee_id = %s
            ORDER BY rm.meeting_date DESC
        """, (employee_id,))
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def get_all(status: str = None, employee_id: int = None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT rm.*, e.name AS employee_name, r.name AS reviewer_name,
                   t.name AS team_name
            FROM review_meetings rm
            JOIN users e ON rm.employee_id = e.id
            JOIN users r ON rm.reviewer_id = r.id
            LEFT JOIN teams t ON e.team_id = t.id
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND rm.status=%s"; params.append(status)
        if employee_id:
            query += " AND rm.employee_id=%s"; params.append(employee_id)
        query += " ORDER BY rm.meeting_date DESC"
        cursor.execute(query, params)
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def cancel(review_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE review_meetings SET status='cancelled' WHERE id=%s", (review_id,)
        )
        conn.commit()
        cursor.close(); conn.close()
