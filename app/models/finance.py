from app.utils.database import get_db_connection


class ClientPayment:
    @staticmethod
    def add_payment(client_id, amount, payment_date, payment_method, reference, notes, added_by):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO client_payments (client_id, amount, payment_date, payment_method, reference, notes, added_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (client_id, amount, payment_date, payment_method, reference, notes, added_by))
            conn.commit()
            payment_id = cursor.lastrowid
            cursor.close()
            return payment_id
        finally:
            conn.close()

    @staticmethod
    def get_payments_by_client(client_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT cp.*, u.name as added_by_name
                FROM client_payments cp
                LEFT JOIN users u ON cp.added_by = u.id
                WHERE cp.client_id = %s
                ORDER BY cp.payment_date DESC
            """, (client_id,))
            payments = cursor.fetchall()
            cursor.close()
            return payments
        finally:
            conn.close()

    @staticmethod
    def get_client_finance_summary(client_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT 
                    c.id, c.company_name, c.contact_person, c.email, c.phone,
                    c.deadline, c.status, c.total_amount,
                    COALESCE(SUM(cp.amount), 0) AS paid_amount
                FROM clients c
                LEFT JOIN client_payments cp ON c.id = cp.client_id
                WHERE c.id = %s
                GROUP BY c.id
            """, (client_id,))
            row = cursor.fetchone()
            cursor.close()
            if row:
                row['pending_amount'] = float(row['total_amount'] or 0) - float(row['paid_amount'] or 0)
            return row
        finally:
            conn.close()

    @staticmethod
    def get_all_finance_summary():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT 
                    c.id, c.company_name, c.contact_person, c.email, c.phone,
                    c.deadline, c.status, c.total_amount,
                    COALESCE(SUM(cp.amount), 0) AS paid_amount
                FROM clients c
                LEFT JOIN client_payments cp ON c.id = cp.client_id
                GROUP BY c.id
                ORDER BY c.created_at DESC
            """)
            rows = cursor.fetchall()
            cursor.close()
            for row in rows:
                row['pending_amount'] = float(row['total_amount'] or 0) - float(row['paid_amount'] or 0)
            return rows
        finally:
            conn.close()

    @staticmethod
    def delete_payment(payment_id):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM client_payments WHERE id = %s", (payment_id,))
            conn.commit()
            cursor.close()
        finally:
            conn.close()

    @staticmethod
    def get_overall_stats():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    COALESCE(SUM(c.total_amount), 0)        AS total_contract,
                    COALESCE(SUM(cp_sum.paid), 0)           AS total_collected,
                    COALESCE(SUM(c.total_amount), 0) - COALESCE(SUM(cp_sum.paid), 0) AS total_pending,
                    COUNT(DISTINCT CASE 
                        WHEN c.deadline < CURDATE() 
                        AND COALESCE(cp_sum.paid, 0) < COALESCE(c.total_amount, 0) 
                        THEN c.id END) AS overdue_count
                FROM clients c
                LEFT JOIN (
                    SELECT client_id, SUM(amount) AS paid FROM client_payments GROUP BY client_id
                ) cp_sum ON c.id = cp_sum.client_id
            """)
            stats = cursor.fetchone()
            cursor.close()
            return stats
        finally:
            conn.close()
