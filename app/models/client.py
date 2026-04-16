from app.utils.database import get_db_connection

class Client:
    @staticmethod
    def create(company_name, contact_person, phone, email, package_purchased, 
               project_start_date, deadline, notes, user_id=None, total_amount=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO clients (company_name, contact_person, phone, email, 
                package_purchased, project_start_date, deadline, notes, user_id, total_amount)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (company_name, contact_person, phone, email, package_purchased, 
                  project_start_date, deadline, notes, user_id, total_amount or 0))
            conn.commit()
            client_id = cursor.lastrowid
            cursor.close()
            return client_id
        finally:
            conn.close()
    
    @staticmethod
    def get_by_id(client_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
            client = cursor.fetchone()
            cursor.close()
            return client
        finally:
            conn.close()
    
    @staticmethod
    def get_all(status=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if status:
                cursor.execute("SELECT * FROM clients WHERE status = %s ORDER BY created_at DESC", (status,))
            else:
                cursor.execute("SELECT * FROM clients ORDER BY created_at DESC")
            clients = cursor.fetchall()
            cursor.close()
            return clients
        finally:
            conn.close()
    
    @staticmethod
    def get_by_user(user_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM clients WHERE user_id = %s", (user_id,))
            client = cursor.fetchone()
            cursor.close()
            return client
        finally:
            conn.close()
    
    @staticmethod
    def update(client_id, **kwargs):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            fields = []
            values = []
            for key, value in kwargs.items():
                if value is not None:
                    fields.append(f"{key} = %s")
                    values.append(value)
            values.append(client_id)
            query = f"UPDATE clients SET {', '.join(fields)} WHERE id = %s"
            cursor.execute(query, values)
            conn.commit()
            cursor.close()
        finally:
            conn.close()
    
    @staticmethod
    def assign_team(client_id, user_ids):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM team_assignments WHERE client_id = %s", (client_id,))
            for user_id in user_ids:
                cursor.execute("INSERT INTO team_assignments (client_id, user_id) VALUES (%s, %s)", 
                             (client_id, user_id))
            conn.commit()
            cursor.close()
        finally:
            conn.close()
    
    @staticmethod
    def get_team(client_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT u.id, u.name, u.email, u.role 
                FROM users u 
                JOIN team_assignments ta ON u.id = ta.user_id 
                WHERE ta.client_id = %s
            """, (client_id,))
            team = cursor.fetchall()
            cursor.close()
            return team
        finally:
            conn.close()
    
    @staticmethod
    def search(query):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            search_term = f"%{query}%"
            cursor.execute("""
                SELECT * FROM clients 
                WHERE company_name LIKE %s OR contact_person LIKE %s OR email LIKE %s
            """, (search_term, search_term, search_term))
            clients = cursor.fetchall()
            cursor.close()
            return clients
        finally:
            conn.close()
