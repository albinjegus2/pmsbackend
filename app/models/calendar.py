from app.utils.database import get_db_connection

class CalendarEvent:
    @staticmethod
    def create(user_id, title, start_time, end_time, entry_type='event', description=None, all_day=False):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            sql = """
                INSERT INTO calendar_events (user_id, title, start_time, end_time, entry_type, description, all_day)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (user_id, title, start_time, end_time, entry_type, description, all_day))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    @staticmethod
    def get_by_user(user_id, month=None, year=None):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            if month and year:
                sql = "SELECT * FROM calendar_events WHERE user_id = %s AND MONTH(start_time) = %s AND YEAR(start_time) = %s"
                cursor.execute(sql, (user_id, month, year))
            else:
                sql = "SELECT * FROM calendar_events WHERE user_id = %s"
                cursor.execute(sql, (user_id,))
            return cursor.fetchall()
        finally:
            conn.close()

    @staticmethod
    def delete(event_id, user_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM calendar_events WHERE id = %s AND user_id = %s", (event_id, user_id))
            conn.commit()
        finally:
            conn.close()
