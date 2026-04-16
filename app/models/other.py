from app.utils.database import get_db_connection
import logging
from datetime import datetime as dt, date, timedelta

logger = logging.getLogger(__name__)

def _serialize(row):
    if row is None:
        return None
    result = {}
    for k, v in row.items():
        if isinstance(v, timedelta):
            total = int(v.total_seconds())
            result[k] = f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"
        elif isinstance(v, (dt, date)):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result

class WorkLog:
    @staticmethod
    def create(user_id, client_id, task_id, work_description, hours_worked, log_date,
               start_time=None, end_time=None, department=None,
               team_leader_id=None, duration_minutes=None, work_date=None, status='completed',
               lead_id=None):
        if start_time and end_time and not duration_minutes:
            try:
                s = dt.strptime(start_time[:5], '%H:%M')
                e = dt.strptime(end_time[:5], '%H:%M')
                duration_minutes = int((e - s).total_seconds() / 60)
            except ValueError as ex:
                logger.warning('Could not parse start/end time: %s', ex)
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO work_logs
                    (user_id, client_id, lead_id, task_id, work_description, hours_worked,
                     log_date, start_time, end_time, department,
                     team_leader_id, duration_minutes, work_date, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, client_id, lead_id, task_id, work_description, hours_worked,
                  log_date, start_time, end_time, department,
                  team_leader_id, duration_minutes, work_date or log_date, status))
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close(); conn.close()

    @staticmethod
    def get_by_user(user_id, start_date=None, end_date=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT wl.*, c.company_name, l.name as lead_name, l.company as lead_company,
                       t.title as task_title,
                       u.name as user_name, u.role as user_role,
                       d.name as department_name,
                       tl.name as team_leader_name,
                       ab.name as approved_by_name
                FROM work_logs wl
                LEFT JOIN clients c ON wl.client_id = c.id
                LEFT JOIN leads l ON wl.lead_id = l.id
                LEFT JOIN tasks t ON wl.task_id = t.id
                LEFT JOIN users u ON wl.user_id = u.id
                LEFT JOIN departments d ON u.department_id = d.id
                LEFT JOIN users tl ON wl.team_leader_id = tl.id
                LEFT JOIN users ab ON wl.approved_by = ab.id
                WHERE wl.user_id = %s
            """
            params = [user_id]
            if start_date:
                query += " AND wl.log_date >= %s"; params.append(start_date)
            if end_date:
                query += " AND wl.log_date <= %s"; params.append(end_date)
            query += " ORDER BY wl.log_date DESC, wl.start_time DESC"
            cursor.execute(query, params)
            return [_serialize(r) for r in cursor.fetchall()]
        finally:
            cursor.close(); conn.close()

    @staticmethod
    def get_by_client(client_id, start_date=None, end_date=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT wl.*, u.name as user_name, u.role as user_role,
                       t.title as task_title, t.department as task_department,
                       d.name as department_name, tm.name as team_name
                FROM work_logs wl
                JOIN users u ON wl.user_id = u.id
                LEFT JOIN tasks t ON wl.task_id = t.id
                LEFT JOIN departments d ON u.department_id = d.id
                LEFT JOIN teams tm ON u.team_id = tm.id
                WHERE wl.client_id = %s
            """
            params = [client_id]
            if start_date:
                query += " AND wl.log_date >= %s"; params.append(start_date)
            if end_date:
                query += " AND wl.log_date <= %s"; params.append(end_date)
            query += " ORDER BY wl.log_date DESC, wl.start_time DESC"
            cursor.execute(query, params)
            return [_serialize(r) for r in cursor.fetchall()]
        finally:
            cursor.close(); conn.close()

    @staticmethod
    def get_client_summary(client_id, start_date=None, end_date=None):
        """Full breakdown for admin: total hours per dept, per task, per employee"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        date_filter = ""
        params_base = [client_id]
        if start_date:
            date_filter += " AND wl.log_date >= %s"; params_base.append(start_date)
        if end_date:
            date_filter += " AND wl.log_date <= %s"; params_base.append(end_date)

        # Overall totals
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_entries,
                SUM(wl.hours_worked) as total_hours,
                MIN(wl.log_date) as first_log,
                MAX(wl.log_date) as last_log,
                COUNT(DISTINCT wl.user_id) as total_employees,
                COUNT(DISTINCT wl.task_id) as total_tasks
            FROM work_logs wl
            WHERE wl.client_id = %s {date_filter}
        """, params_base)
        overall = _serialize(cursor.fetchone())

        # By department
        cursor.execute(f"""
            SELECT
                COALESCE(d.name, wl.department, 'General') as department,
                tm.name as team_name,
                COUNT(*) as entries,
                SUM(wl.hours_worked) as total_hours,
                COUNT(DISTINCT wl.user_id) as employees,
                COUNT(DISTINCT wl.task_id) as tasks
            FROM work_logs wl
            LEFT JOIN users u ON wl.user_id = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN teams tm ON u.team_id = tm.id
            WHERE wl.client_id = %s {date_filter}
            GROUP BY COALESCE(d.name, wl.department, 'General'), tm.name
            ORDER BY total_hours DESC
        """, params_base)
        by_department = [_serialize(r) for r in cursor.fetchall()]

        # By task
        cursor.execute(f"""
            SELECT
                t.id as task_id,
                COALESCE(t.title, 'No Task') as task_title,
                t.status as task_status,
                t.priority,
                COALESCE(d.name, 'General') as department,
                COUNT(*) as entries,
                SUM(wl.hours_worked) as total_hours,
                COUNT(DISTINCT wl.user_id) as employees
            FROM work_logs wl
            LEFT JOIN tasks t ON wl.task_id = t.id
            LEFT JOIN users u ON wl.user_id = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE wl.client_id = %s {date_filter}
            GROUP BY t.id, t.title, t.status, t.priority, d.name
            ORDER BY total_hours DESC
        """, params_base)
        by_task = [_serialize(r) for r in cursor.fetchall()]

        # By employee
        cursor.execute(f"""
            SELECT
                u.name as employee_name,
                u.role,
                COALESCE(d.name, 'General') as department,
                tm.name as team_name,
                COUNT(*) as entries,
                SUM(wl.hours_worked) as total_hours,
                COUNT(DISTINCT wl.task_id) as tasks,
                MIN(wl.log_date) as first_log,
                MAX(wl.log_date) as last_log
            FROM work_logs wl
            JOIN users u ON wl.user_id = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN teams tm ON u.team_id = tm.id
            WHERE wl.client_id = %s {date_filter}
            GROUP BY u.id, d.name, tm.name
            ORDER BY total_hours DESC
        """, params_base)
        by_employee = [_serialize(r) for r in cursor.fetchall()]

        # Daily timeline
        cursor.execute(f"""
            SELECT
                wl.log_date,
                SUM(wl.hours_worked) as hours,
                COUNT(*) as entries,
                COUNT(DISTINCT wl.user_id) as employees_active
            FROM work_logs wl
            WHERE wl.client_id = %s {date_filter}
            GROUP BY wl.log_date
            ORDER BY wl.log_date ASC
        """, params_base)
        daily_timeline = [_serialize(r) for r in cursor.fetchall()]

        cursor.close(); conn.close()
        return {
            "overall": overall,
            "by_department": by_department,
            "by_task": by_task,
            "by_employee": by_employee,
            "daily_timeline": daily_timeline
        }

    @staticmethod
    def get_all_for_admin(start_date=None, end_date=None, client_id=None, department=None, user_id=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT wl.*, u.name as user_name, u.role as user_role,
                   c.company_name, l.name as lead_name, l.company as lead_company,
                   t.title as task_title,
                   d.name as department_name, tm.name as team_name,
                   tl.name as team_leader_name, ab.name as approved_by_name
            FROM work_logs wl
            JOIN users u ON wl.user_id = u.id
            LEFT JOIN clients c ON wl.client_id = c.id
            LEFT JOIN leads l ON wl.lead_id = l.id
            LEFT JOIN tasks t ON wl.task_id = t.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN teams tm ON u.team_id = tm.id
            LEFT JOIN users tl ON wl.team_leader_id = tl.id
            LEFT JOIN users ab ON wl.approved_by = ab.id
            WHERE 1=1
        """
        params = []
        if client_id:
            query += " AND wl.client_id = %s"; params.append(client_id)
        if user_id:
            query += " AND wl.user_id = %s"; params.append(user_id)
        if start_date:
            query += " AND wl.log_date >= %s"; params.append(start_date)
        if end_date:
            query += " AND wl.log_date <= %s"; params.append(end_date)
        if department:
            query += " AND (d.name = %s OR wl.department = %s)"; params.extend([department, department])
        query += " ORDER BY wl.log_date DESC, wl.start_time DESC"
        cursor.execute(query, params)
        logs = [_serialize(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return logs

    @staticmethod
    def get_by_team(team_leader_id, start_date=None, end_date=None, employee_id=None,
                    client_id=None, status=None):
        """Team leader views all logs from their subordinates"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT wl.*, u.name as user_name, u.role as user_role,
                   c.company_name, l.name as lead_name, l.company as lead_company,
                   t.title as task_title,
                   d.name as department_name, ab.name as approved_by_name
            FROM work_logs wl
            JOIN users u ON wl.user_id = u.id
            LEFT JOIN clients c ON wl.client_id = c.id
            LEFT JOIN leads l ON wl.lead_id = l.id
            LEFT JOIN tasks t ON wl.task_id = t.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN users ab ON wl.approved_by = ab.id
            WHERE (wl.team_leader_id = %s OR u.manager_id = %s)
        """
        params = [team_leader_id, team_leader_id]
        if employee_id:
            query += " AND wl.user_id = %s"; params.append(employee_id)
        if client_id:
            query += " AND wl.client_id = %s"; params.append(client_id)
        if start_date:
            query += " AND wl.log_date >= %s"; params.append(start_date)
        if end_date:
            query += " AND wl.log_date <= %s"; params.append(end_date)
        if status:
            query += " AND wl.status = %s"; params.append(status)
        query += " ORDER BY wl.log_date DESC, wl.start_time DESC"
        cursor.execute(query, params)
        logs = [_serialize(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return logs

    @staticmethod
    def approve(log_id, approver_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE work_logs SET status='approved', approved_by=%s, approved_at=NOW()
            WHERE id=%s
        """, (approver_id, log_id))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def reject(log_id, approver_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE work_logs SET status='rejected', approved_by=%s, approved_at=NOW()
            WHERE id=%s
        """, (approver_id, log_id))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_department_summary(department=None, start_date=None, end_date=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        date_filter = ""
        params = []
        if department:
            date_filter += " AND (d.name = %s OR wl.department = %s)"
            params.extend([department, department])
        if start_date:
            date_filter += " AND wl.log_date >= %s"; params.append(start_date)
        if end_date:
            date_filter += " AND wl.log_date <= %s"; params.append(end_date)

        cursor.execute(f"""
            SELECT
                COALESCE(d.name, wl.department, 'General') as department,
                u.name as employee_name, u.id as employee_id,
                COALESCE(t.title, 'No Task') as task_title,
                wl.log_date as work_date,
                COALESCE(wl.start_time, '') as start_time,
                COALESCE(wl.end_time, '') as end_time,
                wl.duration_minutes,
                wl.hours_worked,
                wl.status,
                c.company_name
            FROM work_logs wl
            JOIN users u ON wl.user_id = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN tasks t ON wl.task_id = t.id
            LEFT JOIN clients c ON wl.client_id = c.id
            WHERE 1=1 {date_filter}
            ORDER BY COALESCE(d.name, wl.department, 'General'), u.name, wl.log_date
        """, params)
        rows = [_serialize(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def get_employee_summary(employee_id, start_date=None, end_date=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT wl.*, c.company_name,
                   COALESCE(t.title, 'No Task') as task_title,
                   u.name as user_name,
                   COALESCE(d.name, wl.department, 'General') as department_name,
                   ab.name as approved_by_name
            FROM work_logs wl
            JOIN users u ON wl.user_id = u.id
            LEFT JOIN clients c ON wl.client_id = c.id
            LEFT JOIN tasks t ON wl.task_id = t.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN users ab ON wl.approved_by = ab.id
            WHERE wl.user_id = %s
        """
        params = [employee_id]
        if start_date:
            query += " AND wl.log_date >= %s"; params.append(start_date)
        if end_date:
            query += " AND wl.log_date <= %s"; params.append(end_date)
        query += " ORDER BY wl.log_date DESC"
        cursor.execute(query, params)
        logs = [_serialize(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return logs

    @staticmethod
    def get_full_company_summary(start_date, end_date):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT wl.*, u.name as user_name, u.role as user_role,
                   COALESCE(d.name, wl.department, 'General') as department_name,
                   tm.name as team_name,
                   c.company_name,
                   COALESCE(t.title, 'No Task') as task_title
            FROM work_logs wl
            JOIN users u ON wl.user_id = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN teams tm ON u.team_id = tm.id
            LEFT JOIN clients c ON wl.client_id = c.id
            LEFT JOIN tasks t ON wl.task_id = t.id
            WHERE wl.log_date BETWEEN %s AND %s
            ORDER BY tm.name, d.name, u.name, wl.log_date
        """, (start_date, end_date))
        logs = [_serialize(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return logs


class CompanySettings:
    @staticmethod
    def get():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM company_settings WHERE id = 1")
        settings = cursor.fetchone()
        cursor.close(); conn.close()
        return _serialize(settings) or {}

    @staticmethod
    def update(**kwargs):
        conn = get_db_connection()
        cursor = conn.cursor()
        fields = [f"{k} = %s" for k in kwargs]
        values = list(kwargs.values())
        cursor.execute(f"UPDATE company_settings SET {', '.join(fields)} WHERE id = 1", values)
        conn.commit()
        cursor.close(); conn.close()


class Notification:
    @staticmethod
    def create(user_id, title, message, type='info'):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, type)
                VALUES (%s, %s, %s, %s)
            """, (user_id, title, message, type))
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    @staticmethod
    def get_by_user(user_id, unread_only=False):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM notifications WHERE user_id = %s"
            if unread_only:
                query += " AND is_read = FALSE"
            query += " ORDER BY created_at DESC LIMIT 50"
            cursor.execute(query, (user_id,))
            notifications = [_serialize(r) for r in cursor.fetchall()]
            cursor.close()
            return notifications
        finally:
            conn.close()

    @staticmethod
    def mark_read(notification_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s", (notification_id,))
            conn.commit()
            cursor.close()
        finally:
            conn.close()


class Comment:
    @staticmethod
    def create(task_id, user_id, comment):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO comments (task_id, user_id, comment) VALUES (%s, %s, %s)",
                           (task_id, user_id, comment))
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    @staticmethod
    def get_by_task(task_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT c.*, u.name as user_name
                FROM comments c JOIN users u ON c.user_id = u.id
                WHERE c.task_id = %s ORDER BY c.created_at ASC
            """, (task_id,))
            comments = [_serialize(r) for r in cursor.fetchall()]
            cursor.close()
            return comments
        finally:
            conn.close()


class File:
    @staticmethod
    def create(client_id, file_name, file_path, file_type, uploaded_by, task_id=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO files (client_id, task_id, file_name, file_path, file_type, uploaded_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (client_id, task_id, file_name, file_path, file_type, uploaded_by))
            conn.commit()
            file_id = cursor.lastrowid
            cursor.close()
            return file_id
        finally:
            conn.close()

    @staticmethod
    def get_by_client(client_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT f.*, u.name as uploaded_by_name
                FROM files f JOIN users u ON f.uploaded_by = u.id
                WHERE f.client_id = %s ORDER BY f.created_at DESC
            """, (client_id,))
            files = [_serialize(r) for r in cursor.fetchall()]
            cursor.close()
            return files
        finally:
            conn.close()
