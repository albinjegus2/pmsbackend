from app.utils.database import get_db_connection


class Lead:
    @staticmethod
    def create(name, company, phone, email, source, service_interest, notes, assigned_to, created_by):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO leads (name, company, phone, email, source, service_interest, notes, assigned_to, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (name, company, phone, email, source, service_interest, notes, assigned_to, created_by))
            conn.commit()
            lead_id = cursor.lastrowid
            cursor.close()
            return lead_id
        finally:
            conn.close()

    @staticmethod
    def get_all(status=None, assigned_to=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT l.*, 
                    u.name AS assigned_to_name,
                    cb.name AS created_by_name
                FROM leads l
                LEFT JOIN users u  ON l.assigned_to = u.id
                LEFT JOIN users cb ON l.created_by  = cb.id
                WHERE 1=1
            """
            params = []
            if status:
                query += " AND l.status = %s"
                params.append(status)
            if assigned_to:
                query += " AND l.assigned_to = %s"
                params.append(assigned_to)
            query += " ORDER BY l.created_at DESC"
            cursor.execute(query, params)
            leads = cursor.fetchall()
            cursor.close()
            return leads
        finally:
            conn.close()

    @staticmethod
    def get_by_id(lead_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT l.*, 
                    u.name AS assigned_to_name,
                    cb.name AS created_by_name
                FROM leads l
                LEFT JOIN users u  ON l.assigned_to = u.id
                LEFT JOIN users cb ON l.created_by  = cb.id
                WHERE l.id = %s
            """, (lead_id,))
            lead = cursor.fetchone()
            cursor.close()
            return lead
        finally:
            conn.close()

    @staticmethod
    def update(lead_id, **kwargs):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            fields, values = [], []
            for key, value in kwargs.items():
                fields.append(f"{key} = %s")
                values.append(value)
            values.append(lead_id)
            cursor.execute(f"UPDATE leads SET {', '.join(fields)} WHERE id = %s", values)
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    @staticmethod
    def delete(lead_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM leads WHERE id = %s", (lead_id,))
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    @staticmethod
    def add_followup(lead_id, note, next_followup_date, added_by):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lead_followups (lead_id, note, next_followup_date, added_by)
                VALUES (%s, %s, %s, %s)
            """, (lead_id, note, next_followup_date, added_by))
            conn.commit()
            fid = cursor.lastrowid
            cursor.close()
            return fid
        finally:
            conn.close()

    @staticmethod
    def get_followups(lead_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT lf.*, u.name AS added_by_name
                FROM lead_followups lf
                LEFT JOIN users u ON lf.added_by = u.id
                WHERE lf.lead_id = %s
                ORDER BY lf.created_at DESC
            """, (lead_id,))
            followups = cursor.fetchall()
            cursor.close()
            return followups
        finally:
            conn.close()

    @staticmethod
    def get_stats():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(status = 'new')         AS new_count,
                    SUM(status = 'contacted')   AS contacted_count,
                    SUM(status = 'follow_up')   AS follow_up_count,
                    SUM(status = 'negotiation') AS negotiation_count,
                    SUM(status = 'converted')   AS converted_count,
                    SUM(status = 'lost')        AS lost_count
                FROM leads
            """)
            stats = cursor.fetchone()
            cursor.close()
            return stats
        finally:
            conn.close()

    @staticmethod
    def convert_to_client(lead_id, client_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE leads SET status = 'converted', converted_client_id = %s WHERE id = %s
            """, (client_id, lead_id))
            conn.commit()
            cursor.close()
        finally:
            conn.close()
