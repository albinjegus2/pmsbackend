from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.activity import ActivityLog

activity_bp = Blueprint('activity', __name__)

ADMIN_ROLES = ['admin', 'team_lead', 'crm_head', 'marketing_head']


# ── Heartbeat (every 30s from every logged-in employee) ───────
@activity_bp.route('/activity/heartbeat', methods=['POST'])
@jwt_required()
def heartbeat():
    user_id      = int(get_jwt_identity())
    data         = request.json or {}
    status       = data.get('status', 'active')       # 'active' | 'idle'
    idle_seconds = int(data.get('idle_seconds', 0))
    events       = data.get('events', [])

    if status not in ('active', 'idle', 'away'):
        status = 'active'

    ActivityLog.heartbeat(user_id, status, idle_seconds, events)
    return jsonify({'ok': True}), 200


# ── Admin: live status of all employees ───────────────────────
@activity_bp.route('/activity/live', methods=['GET'])
@jwt_required()
def get_live():
    claims = get_jwt()
    if claims['role'] not in ADMIN_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    rows = ActivityLog.get_live_all()
    return jsonify(rows), 200


# ── Summary for one employee ──────────────────────────────────
@activity_bp.route('/activity/summary', methods=['GET'])
@jwt_required()
def get_summary():
    claims      = get_jwt()
    current_uid = int(get_jwt_identity())
    user_id     = request.args.get('user_id', current_uid)

    # Employees can only see their own summary
    if claims['role'] not in ADMIN_ROLES and int(user_id) != current_uid:
        return jsonify({'error': 'Unauthorized'}), 403

    target_date = request.args.get('date')
    data        = ActivityLog.get_summary(int(user_id), target_date)
    return jsonify(data), 200


# ── Productivity report (admin) ───────────────────────────────
@activity_bp.route('/activity/productivity', methods=['GET'])
@jwt_required()
def get_productivity():
    claims = get_jwt()
    if claims['role'] not in ADMIN_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    start   = request.args.get('start')
    end     = request.args.get('end')
    user_id = request.args.get('user_id')
    if not start or not end:
        return jsonify({'error': 'start and end required'}), 400
    rows = ActivityLog.get_productivity_report(start, end, user_id)
    return jsonify(rows), 200


# ── Mark offline (called on logout / checkout) ────────────────
@activity_bp.route('/activity/offline', methods=['POST'])
@jwt_required()
def go_offline():
    user_id = int(get_jwt_identity())
    ActivityLog.set_offline(user_id)
    return jsonify({'ok': True}), 200
