from app.utils.database import get_db_connection
from app.utils.auth import hash_password

class User:
    @staticmethod
    def create(name, email, password, role, phone=None, team_id=None, department_id=None, manager_id=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            hashed_pwd = hash_password(password)
            cursor.execute(
                "INSERT INTO users (name, email, password, role, phone, team_id, department_id, manager_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (name, email, hashed_pwd, role, phone, team_id, department_id, manager_id)
            )
            conn.commit()
            user_id = cursor.lastrowid
            cursor.close()
            return user_id
        finally:
            conn.close()

    @staticmethod
    def get_by_email(email):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            cursor.close()
            return user
        finally:
            conn.close()

    @staticmethod
    def get_by_id(user_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT u.id, u.name, u.email, u.role, u.phone, u.team_id, u.department_id, u.manager_id,
                       t.name as team_name, d.name as department_name,
                       m.name as manager_name, u.created_at
                FROM users u
                LEFT JOIN teams t ON u.team_id = t.id
                LEFT JOIN departments d ON u.department_id = d.id
                LEFT JOIN users m ON u.manager_id = m.id
                WHERE u.id = %s
            """, (user_id,))
            user = cursor.fetchone()
            cursor.close()
            return user
        finally:
            conn.close()

    @staticmethod
    def get_all(role=None, team_id=None, department_id=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT u.id, u.name, u.email, u.role, u.phone, u.team_id, u.department_id, u.manager_id,
                       t.name as team_name, d.name as department_name, m.name as manager_name
                FROM users u
                LEFT JOIN teams t ON u.team_id = t.id
                LEFT JOIN departments d ON u.department_id = d.id
                LEFT JOIN users m ON u.manager_id = m.id
                WHERE u.role != 'client'
            """
            params = []
            if role:
                query += " AND u.role = %s"
                params.append(role)
            if team_id:
                query += " AND u.team_id = %s"
                params.append(team_id)
            if department_id:
                query += " AND u.department_id = %s"
                params.append(department_id)
            query += " ORDER BY u.role, u.name"
            cursor.execute(query, params)
            users = cursor.fetchall()
            cursor.close()
            return users
        finally:
            conn.close()

    @staticmethod
    def get_subordinates(manager_id):
        """Get all users who report to this manager"""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT u.id, u.name, u.email, u.role, u.team_id, u.department_id,
                       t.name as team_name, d.name as department_name
                FROM users u
                LEFT JOIN teams t ON u.team_id = t.id
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE u.manager_id = %s
            """, (manager_id,))
            users = cursor.fetchall()
            cursor.close()
            return users
        finally:
            conn.close()

    @staticmethod
    def get_team_leads():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT u.id, u.name, u.email, u.role, u.team_id, u.department_id,
                       t.name as team_name, d.name as department_name
                FROM users u
                LEFT JOIN teams t ON u.team_id = t.id
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE u.role IN ('team_lead', 'crm_head', 'marketing_head', 'crm')
            """)
            leads = cursor.fetchall()
            cursor.close()
            return leads
        finally:
            conn.close()

    @staticmethod
    def update(user_id, **kwargs):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            fields, values = [], []
            for key, value in kwargs.items():
                fields.append(f"{key} = %s")
                values.append(value)
            values.append(user_id)
            cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", values)
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    @staticmethod
    def delete(user_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
            cursor.close()
        finally:
            conn.close()
