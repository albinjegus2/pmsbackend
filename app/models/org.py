from app.utils.database import get_db_connection

class Team:
    @staticmethod
    def create(name, description=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO teams (name, description) VALUES (%s, %s)", (name, description))
        conn.commit()
        team_id = cursor.lastrowid
        cursor.close(); conn.close()
        return team_id

    @staticmethod
    def get_all():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.*, COUNT(DISTINCT u.id) as member_count
            FROM teams t
            LEFT JOIN users u ON u.team_id = t.id
            GROUP BY t.id ORDER BY t.created_at ASC
        """)
        teams = cursor.fetchall()
        cursor.close(); conn.close()
        return teams

    @staticmethod
    def get_by_id(team_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM teams WHERE id = %s", (team_id,))
        team = cursor.fetchone()
        cursor.close(); conn.close()
        return team

    @staticmethod
    def delete(team_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM teams WHERE id = %s", (team_id,))
        conn.commit()
        cursor.close(); conn.close()


class Department:
    @staticmethod
    def create(name, team_id, description=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO departments (name, team_id, description) VALUES (%s, %s, %s)", (name, team_id, description))
        conn.commit()
        dept_id = cursor.lastrowid
        cursor.close(); conn.close()
        return dept_id

    @staticmethod
    def get_all(team_id=None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if team_id:
            cursor.execute("""
                SELECT d.*, t.name as team_name, COUNT(DISTINCT u.id) as member_count
                FROM departments d
                JOIN teams t ON d.team_id = t.id
                LEFT JOIN users u ON u.department_id = d.id
                WHERE d.team_id = %s GROUP BY d.id
            """, (team_id,))
        else:
            cursor.execute("""
                SELECT d.*, t.name as team_name, COUNT(DISTINCT u.id) as member_count
                FROM departments d
                JOIN teams t ON d.team_id = t.id
                LEFT JOIN users u ON u.department_id = d.id
                GROUP BY d.id ORDER BY t.id, d.id
            """)
        depts = cursor.fetchall()
        cursor.close(); conn.close()
        return depts

    @staticmethod
    def get_by_id(dept_id):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT d.*, t.name as team_name FROM departments d
            JOIN teams t ON d.team_id = t.id WHERE d.id = %s
        """, (dept_id,))
        dept = cursor.fetchone()
        cursor.close(); conn.close()
        return dept

    @staticmethod
    def delete(dept_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM departments WHERE id = %s", (dept_id,))
        conn.commit()
        cursor.close(); conn.close()
