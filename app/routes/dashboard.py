from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.utils.database import get_db_connection
from app.models.task import Task

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard/admin', methods=['GET'])
@jwt_required()
def admin_dashboard():
    claims = get_jwt()
    if claims['role'] not in ['admin', 'marketing_head']:
        return jsonify({"error": "Unauthorized"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) as total FROM teams")
    total_teams = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM departments")
    total_departments = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM users WHERE role NOT IN ('admin','client')")
    total_employees = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as total FROM clients")
    total_clients = cursor.fetchone()['total']

    task_stats = Task.get_overview_stats()

    # Team performance
    cursor.execute("""
        SELECT t.name as team_name,
               COUNT(tk.id) as total_tasks,
               SUM(CASE WHEN tk.status='completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN tk.status='in_progress' THEN 1 ELSE 0 END) as in_progress,
               SUM(CASE WHEN tk.status='pending' THEN 1 ELSE 0 END) as pending
        FROM teams t
        LEFT JOIN tasks tk ON tk.team_id = t.id
        GROUP BY t.id
    """)
    team_performance = cursor.fetchall()

    # Department performance
    cursor.execute("""
        SELECT d.name as dept_name, t.name as team_name,
               COUNT(tk.id) as total_tasks,
               SUM(CASE WHEN tk.status='completed' THEN 1 ELSE 0 END) as completed
        FROM departments d
        JOIN teams t ON d.team_id = t.id
        LEFT JOIN tasks tk ON tk.department_id = d.id
        GROUP BY d.id
    """)
    dept_performance = cursor.fetchall()

    # Employee productivity
    cursor.execute("""
        SELECT u.name, u.role, t.name as team_name, d.name as dept_name,
               COUNT(tk.id) as assigned_tasks,
               SUM(CASE WHEN tk.status='completed' THEN 1 ELSE 0 END) as completed_tasks,
               SUM(CASE WHEN tk.due_date < CURDATE() AND tk.status != 'completed' THEN 1 ELSE 0 END) as overdue
        FROM users u
        LEFT JOIN teams t ON u.team_id = t.id
        LEFT JOIN departments d ON u.department_id = d.id
        LEFT JOIN tasks tk ON tk.assigned_to = u.id
        WHERE u.role NOT IN ('admin','client')
        GROUP BY u.id ORDER BY completed_tasks DESC
    """)
    employee_productivity = cursor.fetchall()

    cursor.close(); conn.close()

    return jsonify({
        "total_teams": total_teams,
        "total_departments": total_departments,
        "total_employees": total_employees,
        "total_clients": total_clients,
        "task_stats": task_stats,
        "team_performance": team_performance,
        "dept_performance": dept_performance,
        "employee_productivity": employee_productivity
    }), 200


@dashboard_bp.route('/dashboard/lead', methods=['GET'])
@jwt_required()
def lead_dashboard():
    claims = get_jwt()
    user_id = int(get_jwt_identity())
    if claims['role'] not in ['team_lead', 'crm_head', 'marketing_head']:
        return jsonify({"error": "Unauthorized"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Tasks assigned to this lead
    cursor.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) as in_progress,
               SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
               SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) as in_review
        FROM tasks WHERE assigned_to = %s OR assigned_by = %s
    """, (user_id, user_id))
    task_stats = cursor.fetchone()

    # Pending approvals (tasks in review assigned by this lead)
    cursor.execute("""
        SELECT t.*, u.name as assigned_name
        FROM tasks t LEFT JOIN users u ON t.assigned_to = u.id
        WHERE t.assigned_by = %s AND t.status = 'review'
        ORDER BY t.due_date ASC
    """, (user_id,))
    pending_approvals = cursor.fetchall()

    # Team member performance
    cursor.execute("""
        SELECT u.name, u.role,
               COUNT(t.id) as assigned,
               SUM(CASE WHEN t.status='completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN t.due_date < CURDATE() AND t.status != 'completed' THEN 1 ELSE 0 END) as overdue
        FROM users u
        LEFT JOIN tasks t ON t.assigned_to = u.id
        WHERE u.manager_id = %s
        GROUP BY u.id
    """, (user_id,))
    team_performance = cursor.fetchall()

    cursor.close(); conn.close()

    return jsonify({
        "task_stats": task_stats,
        "pending_approvals": pending_approvals,
        "team_performance": team_performance
    }), 200


@dashboard_bp.route('/dashboard/staff', methods=['GET'])
@jwt_required()
def staff_dashboard():
    user_id = int(get_jwt_identity())
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT COUNT(*) as total_tasks,
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed_tasks,
               SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) as in_progress_tasks,
               SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending_tasks,
               SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) as review_tasks
        FROM tasks WHERE assigned_to = %s
    """, (user_id,))
    task_stats = cursor.fetchone()

    cursor.execute("""
        SELECT t.*, c.company_name, tm.name as team_name, d.name as department_name,
               ab.name as assigned_by_name
        FROM tasks t
        LEFT JOIN clients c ON t.client_id = c.id
        LEFT JOIN teams tm ON t.team_id = tm.id
        LEFT JOIN departments d ON t.department_id = d.id
        LEFT JOIN users ab ON t.assigned_by = ab.id
        WHERE t.assigned_to = %s AND t.status != 'completed'
        ORDER BY t.priority DESC, t.due_date ASC LIMIT 10
    """, (user_id,))
    upcoming_tasks = cursor.fetchall()

    cursor.close(); conn.close()
    return jsonify({"task_stats": task_stats, "upcoming_tasks": upcoming_tasks}), 200


@dashboard_bp.route('/dashboard/reports', methods=['GET'])
@jwt_required()
def generate_report():
    claims = get_jwt()
    if claims['role'] not in ['admin', 'marketing_head']:
        return jsonify({"error": "Unauthorized"}), 403

    report_type = request.args.get('type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if report_type == 'employee_productivity':
        cursor.execute("""
            SELECT u.name, u.role, t.name as team_name, d.name as dept_name,
                   COUNT(DISTINCT wl.id) as work_logs,
                   SUM(wl.hours_worked) as total_hours,
                   COUNT(DISTINCT tk.id) as tasks_completed
            FROM users u
            LEFT JOIN teams t ON u.team_id = t.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN work_logs wl ON u.id = wl.user_id AND wl.log_date BETWEEN %s AND %s
            LEFT JOIN tasks tk ON u.id = tk.assigned_to AND tk.status = 'completed'
            WHERE u.role NOT IN ('admin','client')
            GROUP BY u.id
        """, (start_date, end_date))
    elif report_type == 'client_work':
        cursor.execute("""
            SELECT c.company_name, COUNT(DISTINCT t.id) as total_tasks,
                   SUM(CASE WHEN t.status='completed' THEN 1 ELSE 0 END) as completed_tasks,
                   SUM(t.time_spent) as total_hours, c.status
            FROM clients c LEFT JOIN tasks t ON c.id = t.client_id
            GROUP BY c.id
        """)
    elif report_type == 'department_performance':
        cursor.execute("""
            SELECT d.name as department, tm.name as team,
                   COUNT(t.id) as total_tasks,
                   SUM(CASE WHEN t.status='completed' THEN 1 ELSE 0 END) as completed,
                   SUM(t.time_spent) as total_hours
            FROM departments d
            JOIN teams tm ON d.team_id = tm.id
            LEFT JOIN tasks t ON t.department_id = d.id AND t.created_at BETWEEN %s AND %s
            GROUP BY d.id
        """, (start_date, end_date))
    else:
        cursor.close(); conn.close()
        return jsonify({"error": "Invalid report type"}), 400

    data = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(data), 200
