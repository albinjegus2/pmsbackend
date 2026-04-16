from app.utils.database import get_db_connection
from app.utils.timezone import now_ist, today_ist
from datetime import datetime, date, timedelta
from decimal import Decimal


def _s(row):
    if row is None:
        return None
    out = {}
    for k, v in row.items():
        if isinstance(v, timedelta):
            total = int(v.total_seconds())
            out[k] = f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
        elif isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


class Leave:

    # ── Apply for leave ───────────────────────────────────────
    @staticmethod
    def create(user_id: int, leave_type: str, start_date: str,
               end_date: str, reason: str):
        from datetime import date as dt_date
        s = dt_date.fromisoformat(start_date)
        e = dt_date.fromisoformat(end_date)
        total_days = max(1, (e - s).days + 1)

        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Block overlapping pending/approved leaves
        cursor.execute("""
            SELECT id FROM leave_requests
            WHERE user_id = %s AND status != 'rejected'
              AND NOT (end_date < %s OR start_date > %s)
        """, (user_id, start_date, end_date))
        if cursor.fetchone():
            cursor.close(); conn.close()
            return None, "You already have a leave request overlapping these dates"

        cursor.execute("""
            INSERT INTO leave_requests
                (user_id, leave_type, start_date, end_date, total_days, reason)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, leave_type, start_date, end_date, total_days, reason))
        conn.commit()
        lid = cursor.lastrowid

        cursor.execute("""
            SELECT lr.*, u.name AS employee_name, u.role AS employee_role,
                   t.name AS team_name
            FROM leave_requests lr
            JOIN users u ON lr.user_id = u.id
            LEFT JOIN teams t ON u.team_id = t.id
            WHERE lr.id = %s
        """, (lid,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None

    # ── My leave history ──────────────────────────────────────
    @staticmethod
    def get_by_user(user_id: int):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT lr.*,
                   ab.name AS approved_by_name
            FROM leave_requests lr
            LEFT JOIN users ab ON lr.approved_by = ab.id
            WHERE lr.user_id = %s
            ORDER BY lr.created_at DESC
        """, (user_id,))
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    # ── Pending leaves for admin/lead ─────────────────────────
    @staticmethod
    def get_pending(approver_id: int = None):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT lr.*, u.name AS employee_name, u.role AS employee_role,
                   t.name AS team_name, dp.name AS department_name
            FROM leave_requests lr
            JOIN users u ON lr.user_id = u.id
            LEFT JOIN teams t ON u.team_id = t.id
            LEFT JOIN departments dp ON u.department_id = dp.id
            WHERE lr.status = 'pending'
            ORDER BY lr.created_at ASC
        """)
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    # ── All leaves (admin view with filters) ──────────────────
    @staticmethod
    def get_all(status: str = None, user_id: int = None,
                month: str = None, year: str = None):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query  = """
            SELECT lr.*, u.name AS employee_name, u.role AS employee_role,
                   t.name AS team_name, dp.name AS department_name,
                   ab.name AS approved_by_name
            FROM leave_requests lr
            JOIN users u ON lr.user_id = u.id
            LEFT JOIN teams t ON u.team_id = t.id
            LEFT JOIN departments dp ON u.department_id = dp.id
            LEFT JOIN users ab ON lr.approved_by = ab.id
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND lr.status = %s"; params.append(status)
        if user_id:
            query += " AND lr.user_id = %s"; params.append(user_id)
        if month and year:
            query += " AND MONTH(lr.start_date)=%s AND YEAR(lr.start_date)=%s"
            params += [month, year]
        query += " ORDER BY lr.created_at DESC"
        cursor.execute(query, params)
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    # ── Approve ───────────────────────────────────────────────
    @staticmethod
    def approve(leave_id: int, approver_id: int):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM leave_requests WHERE id=%s", (leave_id,))
        leave = cursor.fetchone()
        if not leave:
            cursor.close(); conn.close()
            return None, "Leave not found"
        if leave['user_id'] == approver_id:
            cursor.close(); conn.close()
            return None, "Cannot approve your own leave"

        cursor.execute("""
            UPDATE leave_requests
            SET status='approved', approved_by=%s, approved_at=%s
            WHERE id=%s
        """, (approver_id, now_ist(), leave_id))

        # Auto-mark attendance as on_leave for each day
        from datetime import date as dt_date
        s = leave['start_date'] if isinstance(leave['start_date'], dt_date) \
            else dt_date.fromisoformat(str(leave['start_date']))
        e = leave['end_date'] if isinstance(leave['end_date'], dt_date) \
            else dt_date.fromisoformat(str(leave['end_date']))
        d = s
        while d <= e:
            cursor.execute("""
                INSERT INTO attendance (user_id, date, status)
                VALUES (%s, %s, 'on_leave')
                ON DUPLICATE KEY UPDATE status = 'on_leave'
            """, (leave['user_id'], d))
            d += timedelta(days=1)

        conn.commit()
        cursor.execute("SELECT * FROM leave_requests WHERE id=%s", (leave_id,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None

    # ── Reject ────────────────────────────────────────────────
    @staticmethod
    def reject(leave_id: int, approver_id: int, note: str = None):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, user_id FROM leave_requests WHERE id=%s", (leave_id,))
        leave = cursor.fetchone()
        if not leave:
            cursor.close(); conn.close()
            return None, "Leave not found"
        if leave['user_id'] == approver_id:
            cursor.close(); conn.close()
            return None, "Cannot reject your own leave"

        cursor.execute("""
            UPDATE leave_requests
            SET status='rejected', approved_by=%s, approved_at=%s, rejection_note=%s
            WHERE id=%s
        """, (approver_id, now_ist(), note, leave_id))
        conn.commit()
        cursor.execute("SELECT * FROM leave_requests WHERE id=%s", (leave_id,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None

    # ── Calendar data (all approved/pending for a month) ──────
    @staticmethod
    def get_calendar(year: str, month: str):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT lr.*, u.name AS employee_name
            FROM leave_requests lr
            JOIN users u ON lr.user_id = u.id
            WHERE lr.status IN ('approved','pending')
              AND (
                (YEAR(lr.start_date)=%s AND MONTH(lr.start_date)=%s) OR
                (YEAR(lr.end_date)=%s   AND MONTH(lr.end_date)=%s)
              )
            ORDER BY lr.start_date
        """, (year, month, year, month))
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    # ── Leave stats for admin dashboard ───────────────────────
    @staticmethod
    def get_stats():
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                SUM(status='pending')  AS pending,
                SUM(status='approved') AS approved,
                SUM(status='rejected') AS rejected,
                COUNT(*)               AS total
            FROM leave_requests
            WHERE MONTH(created_at) = MONTH(CURDATE())
              AND YEAR(created_at)  = YEAR(CURDATE())
        """)
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row or {}


class Permission:

    # ── Request permission ────────────────────────────────────
    @staticmethod
    def create(user_id: int, req_date: str, from_time: str,
               to_time: str, reason: str):
        from datetime import datetime as dt2
        try:
            ft = dt2.strptime(from_time[:5], '%H:%M').time()
            tt = dt2.strptime(to_time[:5],   '%H:%M').time()
            duration = int(
                (dt2.combine(today_ist(), tt) -
                 dt2.combine(today_ist(), ft)).total_seconds() / 60
            )
            if duration <= 0:
                return None, "to_time must be after from_time"
        except ValueError:
            return None, "Invalid time format"

        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            INSERT INTO permission_requests
                (user_id, date, from_time, to_time, duration_minutes, reason)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, req_date, from_time, to_time, duration, reason))
        conn.commit()
        pid = cursor.lastrowid

        cursor.execute("""
            SELECT pr.*, u.name AS employee_name, u.role AS employee_role,
                   t.name AS team_name
            FROM permission_requests pr
            JOIN users u ON pr.user_id = u.id
            LEFT JOIN teams t ON u.team_id = t.id
            WHERE pr.id = %s
        """, (pid,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None

    # ── My permissions ────────────────────────────────────────
    @staticmethod
    def get_by_user(user_id: int):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT pr.*, ab.name AS approved_by_name
            FROM permission_requests pr
            LEFT JOIN users ab ON pr.approved_by = ab.id
            WHERE pr.user_id = %s
            ORDER BY pr.created_at DESC
        """, (user_id,))
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    # ── Pending permissions ───────────────────────────────────
    @staticmethod
    def get_pending():
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT pr.*, u.name AS employee_name, u.role AS employee_role,
                   t.name AS team_name, dp.name AS department_name
            FROM permission_requests pr
            JOIN users u ON pr.user_id = u.id
            LEFT JOIN teams t ON u.team_id = t.id
            LEFT JOIN departments dp ON u.department_id = dp.id
            WHERE pr.status = 'pending'
            ORDER BY pr.date ASC, pr.from_time ASC
        """)
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    # ── All permissions (admin) ───────────────────────────────
    @staticmethod
    def get_all(status: str = None, user_id: int = None):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query  = """
            SELECT pr.*, u.name AS employee_name, u.role AS employee_role,
                   t.name AS team_name, ab.name AS approved_by_name
            FROM permission_requests pr
            JOIN users u ON pr.user_id = u.id
            LEFT JOIN teams t ON u.team_id = t.id
            LEFT JOIN users ab ON pr.approved_by = ab.id
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND pr.status=%s"; params.append(status)
        if user_id:
            query += " AND pr.user_id=%s"; params.append(user_id)
        query += " ORDER BY pr.created_at DESC"
        cursor.execute(query, params)
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    # ── Approve ───────────────────────────────────────────────
    @staticmethod
    def approve(perm_id: int, approver_id: int):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, user_id FROM permission_requests WHERE id=%s", (perm_id,))
        perm = cursor.fetchone()
        if not perm:
            cursor.close(); conn.close()
            return None, "Permission request not found"
        if perm['user_id'] == approver_id:
            cursor.close(); conn.close()
            return None, "Cannot approve your own request"

        cursor.execute("""
            UPDATE permission_requests
            SET status='approved', approved_by=%s, approved_at=%s
            WHERE id=%s
        """, (approver_id, now_ist(), perm_id))
        conn.commit()
        cursor.execute("SELECT * FROM permission_requests WHERE id=%s", (perm_id,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None

    # ── Reject ────────────────────────────────────────────────
    @staticmethod
    def reject(perm_id: int, approver_id: int):
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, user_id FROM permission_requests WHERE id=%s", (perm_id,))
        perm = cursor.fetchone()
        if not perm:
            cursor.close(); conn.close()
            return None, "Permission request not found"
        if perm['user_id'] == approver_id:
            cursor.close(); conn.close()
            return None, "Cannot reject your own request"

        cursor.execute("""
            UPDATE permission_requests
            SET status='rejected', approved_by=%s, approved_at=%s
            WHERE id=%s
        """, (approver_id, now_ist(), perm_id))
        conn.commit()
        cursor.execute("SELECT * FROM permission_requests WHERE id=%s", (perm_id,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None
