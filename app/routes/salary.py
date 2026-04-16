from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.models.salary import Salary
from app.utils.database import get_db_connection

salary_bp = Blueprint('salary', __name__)

# ── Coin Rules ───────────────────────────────────────────────

@salary_bp.route('/salary/coin-rules', methods=['GET'])
@jwt_required()
def get_coin_rules():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM coin_rules ORDER BY id ASC')
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(rows), 200

@salary_bp.route('/salary/coin-rules/<int:rule_id>', methods=['PUT'])
@jwt_required()
def update_coin_rule(rule_id):
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    admin_id = int(get_jwt_identity())
    data = request.json
    coins = data.get('coins')
    is_active = data.get('is_active')
    description = data.get('description')
    if coins is not None and int(coins) < 0:
        return jsonify({'error': 'Coins cannot be negative'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    fields, values = [], []
    if coins is not None:
        fields.append('coins = %s'); values.append(int(coins))
    if is_active is not None:
        fields.append('is_active = %s'); values.append(int(is_active))
    if description is not None:
        fields.append('description = %s'); values.append(description)
    fields.append('updated_by = %s'); values.append(admin_id)
    values.append(rule_id)
    cursor.execute(f"UPDATE coin_rules SET {', '.join(fields)} WHERE id = %s", values)
    conn.commit(); cursor.close(); conn.close()
    return jsonify({'message': 'Rule updated'}), 200

# ── Coin Settings ─────────────────────────────────────────────

@salary_bp.route('/salary/coin-settings', methods=['GET'])
@jwt_required()
def get_coin_settings():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM coin_settings ORDER BY id DESC LIMIT 1')
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return jsonify(row or {'coin_value_rupees': 1.00}), 200

@salary_bp.route('/salary/coin-settings', methods=['PUT'])
@jwt_required()
def update_coin_settings():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    admin_id = int(get_jwt_identity())
    data = request.json
    value = data.get('coin_value_rupees')
    if value is None or float(value) <= 0:
        return jsonify({'error': 'coin_value_rupees must be a positive number'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE coin_settings SET coin_value_rupees = %s, updated_by = %s WHERE id = (SELECT id FROM (SELECT id FROM coin_settings ORDER BY id DESC LIMIT 1) t)', (float(value), admin_id))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({'message': 'Coin value updated'}), 200

# ── Award Coins ───────────────────────────────────────────────

@salary_bp.route('/salary/award-coins', methods=['POST'])
@jwt_required()
def award_coins():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    admin_id = int(get_jwt_identity())
    data = request.json
    user_id = data.get('user_id')
    amount = data.get('amount')
    reason = data.get('reason', 'Performance bonus')
    if not user_id or not amount or int(amount) <= 0:
        return jsonify({'error': 'user_id and positive amount are required'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO user_rewards (user_id, amount, reason, awarded_by) VALUES (%s, %s, %s, %s)',
                   (int(user_id), int(amount), reason, admin_id))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({'message': 'Coins awarded'}), 201

# ── Employee Coin Summary ─────────────────────────────────────

@salary_bp.route('/salary/coins-summary', methods=['GET'])
@jwt_required()
def get_coins_summary():
    claims = get_jwt()
    if claims.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT u.id as user_id, u.name, u.role,
               COALESCE(SUM(r.amount), 0) as total_coins,
               COUNT(r.id) as award_count
        FROM users u
        LEFT JOIN user_rewards r ON u.id = r.user_id
        WHERE u.role != 'client'
        GROUP BY u.id, u.name, u.role
        ORDER BY total_coins DESC
    ''')
    rows = cursor.fetchall()
    # Get coin value
    cursor.execute('SELECT coin_value_rupees FROM coin_settings ORDER BY id DESC LIMIT 1')
    setting = cursor.fetchone()
    coin_value = float(setting['coin_value_rupees']) if setting else 1.0
    for row in rows:
        row['rupee_value'] = round(float(row['total_coins']) * coin_value, 2)
    cursor.close(); conn.close()
    return jsonify({'employees': rows, 'coin_value_rupees': coin_value}), 200

@salary_bp.route('/salary/coin-history/<int:user_id>', methods=['GET'])
@jwt_required()
def get_coin_history(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT r.*, u.name as awarded_by_name
        FROM user_rewards r
        LEFT JOIN users u ON r.awarded_by = u.id
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
    ''', (user_id,))
    rows = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(rows), 200

# ── My Rewards (employee self-view) ──────────────────────────

@salary_bp.route('/user/rewards', methods=['GET'])
@jwt_required()
def get_user_rewards():
    user_id = int(get_jwt_identity())
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT COALESCE(SUM(amount),0) as total FROM user_rewards WHERE user_id = %s', (user_id,))
    total = cursor.fetchone()
    cursor.execute('SELECT r.*, u.name as awarded_by_name FROM user_rewards r LEFT JOIN users u ON r.awarded_by = u.id WHERE r.user_id = %s ORDER BY r.created_at DESC LIMIT 20', (user_id,))
    history = cursor.fetchall()
    cursor.execute('SELECT coin_value_rupees FROM coin_settings ORDER BY id DESC LIMIT 1')
    setting = cursor.fetchone()
    coin_value = float(setting['coin_value_rupees']) if setting else 1.0
    cursor.close(); conn.close()
    return jsonify({
        'total_coins': int(total['total']),
        'rupee_value': round(int(total['total']) * coin_value, 2),
        'coin_value_rupees': coin_value,
        'history': history
    }), 200

# ── Existing Salary Routes ────────────────────────────────────

@salary_bp.route('/salary/configs', methods=['GET'])
@jwt_required()
def get_salary_configs():
    claims = get_jwt()
    if claims.get('role') not in ['admin', 'marketing_head', 'crm_head', 'team_lead']:
        return jsonify({"error": "Unauthorized"}), 403
    
    configs = Salary.get_configs()
    return jsonify(configs), 200

@salary_bp.route('/salary/configs', methods=['POST'])
@jwt_required()
def update_salary_config():
    claims = get_jwt()
    if claims.get('role') not in ['admin', 'marketing_head']:
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json
    user_id = data.get('user_id')
    base_salary = data.get('base_salary', 0)
    allowance = data.get('allowance', 0)

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    Salary.update_config(user_id, base_salary, allowance)
    return jsonify({"message": "Salary configuration updated"}), 200

@salary_bp.route('/salary/pay', methods=['POST'])
@jwt_required()
def pay_salary():
    claims = get_jwt()
    if claims.get('role') not in ['admin', 'marketing_head']:
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json
    user_id = data.get('user_id')
    amount = data.get('amount')
    allowance = data.get('allowance', 0)
    month = data.get('month')
    year = data.get('year')

    if not all([user_id, amount, month, year]):
        return jsonify({"error": "Missing required fields"}), 400
    
    payment_id = Salary.record_payment(user_id, amount, allowance, month, year)
    return jsonify({"message": "Salary payment recorded", "id": payment_id}), 201

@salary_bp.route('/salary/history', methods=['GET'])
@jwt_required()
def get_salary_history():
    claims = get_jwt()
    if claims.get('role') not in ['admin', 'marketing_head', 'crm_head', 'team_lead']:
        return jsonify({"error": "Unauthorized"}), 403
    
    history = Salary.get_history()
    return jsonify(history), 200

@salary_bp.route('/salary/stats', methods=['GET'])
@jwt_required()
def get_salary_stats():
    # Admin & Marketing head common stats
    stats = Salary.get_stats()
    return jsonify(stats), 200

@salary_bp.route('/salary/calculate', methods=['GET'])
@jwt_required()
def calculate_expected_salary():
    user_id = request.args.get('user_id')
    month = request.args.get('month')
    year = request.args.get('year')
    
    if not all([user_id, month, year]):
        return jsonify({"error": "Missing user_id, month, or year"}), 400
        
    result = Salary.calculate_expected_salary(user_id, month, year)
    return jsonify(result), 200
