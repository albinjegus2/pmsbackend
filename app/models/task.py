from app.utils.database import get_db_connection
from app.utils.timezone import now_ist
from datetime import datetime

class Task:
    @staticmethod
    def create(title, description, assigned_by, assigned_to=None, team_id=None,
               department_id=None, client_id=None, department='general',
               status='pending', priority='medium', due_date=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (title, description, assigned_by, assigned_to, team_id,
            department_id, client_id, department, status, priority, due_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (title, description, assigned_by, assigned_to, team_id,
              department_id, client_id, department, status, priority, due_date))
        conn.commit()
        task_id = cursor.lastrowid
        # Log activity
        cursor.execute("""
            INSERT INTO task_activity (task_id, user_id, action, new_value)
            VALUES (%s, %s, 'created', %s)
        """, (task_id, assigned_by, f"Task created and assigned"))
        conn.commit()
        cursor.close(); conn.close()
        return task_id

    @staticmethod
    def get_by_id(task_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.*,
                   u.name as assigned_name, u.role as assigned_role,
                   ab.name as assigned_by_name,
                   c.company_name,
                   tm.name as team_name,
                   d.name as department_name
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to = u.id
            LEFT JOIN users ab ON t.assigned_by = ab.id
            LEFT JOIN clients c ON t.client_id = c.id
            LEFT JOIN teams tm ON t.team_id = tm.id
            LEFT JOIN departments d ON t.department_id = d.id
            WHERE t.id = %s
        """, (task_id,))
        task = cursor.fetchone()
        cursor.close(); conn.close()
        return task

    @staticmethod
    def get_all(team_id=None, department_id=None, status=None, assigned_to=None, assigned_by=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT t.*,
                   u.name as assigned_name, u.role as assigned_role,
                   ab.name as assigned_by_name,
                   c.company_name,
                   tm.name as team_name,
                   d.name as department_name
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to = u.id
            LEFT JOIN users ab ON t.assigned_by = ab.id
            LEFT JOIN clients c ON t.client_id = c.id
            LEFT JOIN teams tm ON t.team_id = tm.id
            LEFT JOIN departments d ON t.department_id = d.id
            WHERE 1=1
        """
        params = []
        if team_id:
            query += " AND t.team_id = %s"
            params.append(team_id)
        if department_id:
            query += " AND t.department_id = %s"
            params.append(department_id)
        if status:
            query += " AND t.status = %s"
            params.append(status)
        if assigned_to:
            query += " AND t.assigned_to = %s"
            params.append(assigned_to)
        if assigned_by:
            query += " AND t.assigned_by = %s"
            params.append(assigned_by)
        query += " ORDER BY t.created_at DESC"
        cursor.execute(query, params)
        tasks = cursor.fetchall()
        cursor.close(); conn.close()
        return tasks

    @staticmethod
    def get_by_user(user_id):
        """Tasks assigned to user OR where user is a participant."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT DISTINCT t.*,
                   u.name as assigned_name, u.role as assigned_role,
                   ab.name as assigned_by_name,
                   c.company_name,
                   tm.name as team_name,
                   d.name as department_name
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to = u.id
            LEFT JOIN users ab ON t.assigned_by = ab.id
            LEFT JOIN clients c ON t.client_id = c.id
            LEFT JOIN teams tm ON t.team_id = tm.id
            LEFT JOIN departments d ON t.department_id = d.id
            LEFT JOIN task_participants tp ON t.id = tp.task_id
            WHERE t.assigned_to = %s OR tp.user_id = %s
            ORDER BY t.created_at DESC
        """, (user_id, user_id))
        tasks = cursor.fetchall()
        cursor.close(); conn.close()
        return tasks

    @staticmethod
    def get_by_client(client_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.*, u.name as assigned_name, ab.name as assigned_by_name,
                   tm.name as team_name, d.name as department_name
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to = u.id
            LEFT JOIN users ab ON t.assigned_by = ab.id
            LEFT JOIN teams tm ON t.team_id = tm.id
            LEFT JOIN departments d ON t.department_id = d.id
            WHERE t.client_id = %s ORDER BY t.created_at DESC
        """, (client_id,))
        tasks = cursor.fetchall()
        cursor.close(); conn.close()
        return tasks

    @staticmethod
    def get_for_team_lead(lead_id):
        """Tasks assigned TO this lead + tasks assigned BY this lead"""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.*,
                   u.name as assigned_name, u.role as assigned_role,
                   ab.name as assigned_by_name,
                   c.company_name, tm.name as team_name, d.name as department_name
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to = u.id
            LEFT JOIN users ab ON t.assigned_by = ab.id
            LEFT JOIN clients c ON t.client_id = c.id
            LEFT JOIN teams tm ON t.team_id = tm.id
            LEFT JOIN departments d ON t.department_id = d.id
            WHERE t.assigned_to = %s OR t.assigned_by = %s
            ORDER BY t.created_at DESC
        """, (lead_id, lead_id))
        tasks = cursor.fetchall()
        cursor.close(); conn.close()
        return tasks

    @staticmethod
    def update(task_id, updated_by, **kwargs):
        conn = get_db_connection()
        cursor = conn.cursor()
        fields, values = [], []
        for key, value in kwargs.items():
            fields.append(f"{key} = %s")
            values.append(value)
        if 'status' in kwargs and kwargs['status'] == 'completed':
            fields.append("completed_at = %s")
            values.append(now_ist())
        values.append(task_id)
        cursor.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = %s", values)
        # Log activity
        action_desc = ', '.join([f"{k}={v}" for k, v in kwargs.items()])
        cursor.execute("""
            INSERT INTO task_activity (task_id, user_id, action, new_value)
            VALUES (%s, %s, 'updated', %s)
        """, (task_id, updated_by, action_desc))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_activity(task_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT ta.*, u.name as user_name
            FROM task_activity ta
            JOIN users u ON ta.user_id = u.id
            WHERE ta.task_id = %s ORDER BY ta.created_at ASC
        """, (task_id,))
        activity = cursor.fetchall()
        cursor.close(); conn.close()
        return activity

    @staticmethod
    def get_stats_by_client(client_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                department
            FROM tasks WHERE client_id = %s GROUP BY department
        """, (client_id,))
        stats = cursor.fetchall()
        cursor.close(); conn.close()
        return stats

    @staticmethod
    def get_overview_stats():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) as in_review,
                SUM(CASE WHEN due_date < CURDATE() AND status != 'completed' THEN 1 ELSE 0 END) as overdue
            FROM tasks
        """)
        stats = cursor.fetchone()
        cursor.close(); conn.close()
        return stats

    @staticmethod
    def get_participants(task_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.id, u.name, u.role, u.email
            FROM task_participants tp
            JOIN users u ON tp.user_id = u.id
            WHERE tp.task_id = %s
        """, (task_id,))
        res = cursor.fetchall()
        cursor.close(); conn.close()
        return res

    @staticmethod
    def add_participant(task_id, user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT IGNORE INTO task_participants (task_id, user_id) VALUES (%s, %s)", (task_id, user_id))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def remove_participant(task_id, user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_participants WHERE task_id = %s AND user_id = %s", (task_id, user_id))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_observers(task_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.id, u.name, u.role, u.email
            FROM task_observers tobs
            JOIN users u ON tobs.user_id = u.id
            WHERE tobs.task_id = %s
        """, (task_id,))
        res = cursor.fetchall()
        cursor.close(); conn.close()
        return res

    @staticmethod
    def add_observer(task_id, user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT IGNORE INTO task_observers (task_id, user_id) VALUES (%s, %s)", (task_id, user_id))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def remove_observer(task_id, user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_observers WHERE task_id = %s AND user_id = %s", (task_id, user_id))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_messages(task_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT tm.*, u.name as user_name, u.role as user_role
            FROM task_messages tm
            JOIN users u ON tm.user_id = u.id
            WHERE tm.task_id = %s ORDER BY tm.created_at ASC
        """, (task_id,))
        messages = cursor.fetchall()
        cursor.close(); conn.close()
        return messages

    @staticmethod
    def send_message(task_id, user_id, content, message_type='text', file_url=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO task_messages (task_id, user_id, content, message_type, file_url)
            VALUES (%s, %s, %s, %s, %s)
        """, (task_id, user_id, content, message_type, file_url))
        conn.commit()
        msg_id = cursor.lastrowid
        cursor.close(); conn.close()
        return msg_id
