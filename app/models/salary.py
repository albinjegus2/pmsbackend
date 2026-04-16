from app.utils.database import get_db_connection

class Salary:
    @staticmethod
    def get_configs():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT u.id as user_id, u.name, u.email, u.role, 
                       sc.base_salary, sc.allowance
                FROM users u
                LEFT JOIN salary_configs sc ON u.id = sc.user_id
                WHERE u.role != 'client'
                ORDER BY u.name ASC
            """)
            configs = cursor.fetchall()
            cursor.close()
            return configs
        finally:
            conn.close()

    @staticmethod
    def update_config(user_id, base_salary, allowance):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO salary_configs (user_id, base_salary, allowance)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                base_salary = VALUES(base_salary), 
                allowance = VALUES(allowance)
            """, (user_id, base_salary, allowance))
            conn.commit()
            cursor.close()
            return True
        finally:
            conn.close()

    @staticmethod
    def record_payment(user_id, amount, allowance, month, year):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            total = amount + allowance
            cursor.execute("""
                INSERT INTO salary_payments (user_id, amount, allowance, total, month, year)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, amount, allowance, total, month, year))
            conn.commit()
            payment_id = cursor.lastrowid
            cursor.close()
            return payment_id
        finally:
            conn.close()

    @staticmethod
    def get_history(limit=50):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT sp.*, u.name, u.email
                FROM salary_payments sp
                JOIN users u ON sp.user_id = u.id
                ORDER BY sp.paid_at DESC
                LIMIT %s
            """, (limit,))
            history = cursor.fetchall()
            cursor.close()
            return history
        finally:
            conn.close()

    @staticmethod
    def get_stats():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # Total salary spent (lifetime)
            cursor.execute("SELECT SUM(total) as total_spent FROM salary_payments")
            total_spent = cursor.fetchone()['total_spent'] or 0
            
            # This month's salary
            import datetime
            now = datetime.datetime.now()
            cursor.execute("""
                SELECT SUM(total) as month_spent 
                FROM salary_payments 
                WHERE month = %s AND year = %s
            """, (now.month, now.year))
            month_spent = cursor.fetchone()['month_spent'] or 0
            
            cursor.close()
            return {
                "total_spent": float(total_spent),
                "month_spent": float(month_spent)
            }
        finally:
            conn.close()

    @staticmethod
    def calculate_expected_salary(user_id, month, year):
        import calendar
        from datetime import date, datetime
        from app.models.attendance import Attendance
        
        # 1. Get salary config
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT base_salary, allowance FROM salary_configs WHERE user_id = %s", (user_id,))
            config = cursor.fetchone()
            if not config:
                return {
                    "base_salary": 0, "allowance": 0, "expected_salary": 0, 
                    "leaves": 0, "present_days": 0, "total_working_days": 0
                }

            base_salary = float(config['base_salary'] or 0)
            allowance = float(config['allowance'] or 0)

            # 2. Get attendance for the month
            attendance_records = Attendance.get_by_user(user_id, month, year)
            
            # Count present and half days
            present_days = 0.0
            for rec in attendance_records:
                status = rec.get('status')
                if status in ['present', 'late']:
                    present_days += 1.0
                elif status == 'half_day':
                    present_days += 0.5
            
            # 3. Calculate total working days in month (Mon-Sat)
            total_days_in_month = calendar.monthrange(int(year), int(month))[1]
            
            today = datetime.now().date()
            if int(year) == today.year and int(month) == today.month:
                days_to_count = today.day
            else:
                days_to_count = total_days_in_month
            
            working_days = 0
            for d in range(1, days_to_count + 1):
                if date(int(year), int(month), d).weekday() < 6: # 0-5 = Mon-Sat
                    working_days += 1
            
            # Total working days for the ENTIRE month (to calculate daily rate)
            total_working_days_in_month = 0
            for d in range(1, total_days_in_month + 1):
                if date(int(year), int(month), d).weekday() < 6:
                    total_working_days_in_month += 1

            # 4. Calculate Salary
            if total_working_days_in_month > 0:
                daily_rate = base_salary / total_working_days_in_month
                calc_base = daily_rate * present_days
            else:
                calc_base = 0

            # 5. Coin bonus for this month
            cursor.execute('''
                SELECT COALESCE(SUM(r.amount), 0) as total_coins
                FROM user_rewards r
                WHERE r.user_id = %s
                AND MONTH(r.created_at) = %s AND YEAR(r.created_at) = %s
            ''', (user_id, int(month), int(year)))
            coin_row = cursor.fetchone()
            total_coins = int(coin_row['total_coins']) if coin_row else 0

            cursor.execute('SELECT coin_value_rupees FROM coin_settings ORDER BY id DESC LIMIT 1')
            coin_setting = cursor.fetchone()
            coin_value = float(coin_setting['coin_value_rupees']) if coin_setting else 1.0
            coin_bonus = round(total_coins * coin_value, 2)

            return {
                "base_salary": base_salary,
                "allowance": allowance,
                "present_days": present_days,
                "working_days_so_far": working_days,
                "total_working_days": total_working_days_in_month,
                "expected_salary": round(calc_base + allowance + coin_bonus, 2),
                "leaves": working_days - present_days,
                "total_coins": total_coins,
                "coin_value_rupees": coin_value,
                "coin_bonus": coin_bonus
            }
        finally:
            conn.close()
