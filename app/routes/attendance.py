from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.attendance import Attendance, Break

attendance_bp = Blueprint('attendance', __name__)

LEAD_ROLES = ['admin', 'team_lead', 'crm_head', 'marketing_head']


# ── Check-in ──────────────────────────────────────────────────
@attendance_bp.route('/attendance/checkin', methods=['POST'])
@jwt_required()
def check_in():
    user_id = int(get_jwt_identity())
    data    = request.json or {}

    # Block double check-in
    existing = Attendance.get_today(user_id)
    if existing and existing.get('check_in_time'):
        return jsonify({'error': 'Already checked in today', 'attendance': existing}), 400

    record = Attendance.check_in(user_id, notes=data.get('notes'))
    return jsonify(record), 201


# ── Check-out ─────────────────────────────────────────────────
@attendance_bp.route('/attendance/checkout', methods=['POST'])
@jwt_required()
def check_out():
    user_id = int(get_jwt_identity())
    record, error = Attendance.check_out(user_id)
    if error and record is None:
        return jsonify({'error': error}), 400
    return jsonify(record), 200


# ── Today's record (own) ──────────────────────────────────────
@attendance_bp.route('/attendance/today', methods=['GET'])
@jwt_required()
def get_today():
    user_id = int(get_jwt_identity())
    record  = Attendance.get_today(user_id)
    breaks  = Break.get_today(user_id)
    return jsonify({'attendance': record, 'breaks': breaks}), 200


# ── My monthly history ────────────────────────────────────────
@attendance_bp.route('/attendance/my', methods=['GET'])
@jwt_required()
def get_my():
    user_id = int(get_jwt_identity())
    month   = request.args.get('month')
    year    = request.args.get('year')
    rows    = Attendance.get_by_user(user_id, month, year)
    return jsonify(rows), 200


# ── Admin: all employees for a date ──────────────────────────
@attendance_bp.route('/attendance/admin', methods=['GET'])
@jwt_required()
def get_admin():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    target_date = request.args.get('date')
    rows        = Attendance.get_all_for_date(target_date)
    absent      = Attendance.get_absent_today() if not target_date else []
    stats       = Attendance.get_today_stats()
    return jsonify({'records': rows, 'absent': absent, 'stats': stats}), 200


# ── Admin: attendance report ──────────────────────────────────
@attendance_bp.route('/attendance/report', methods=['GET'])
@jwt_required()
def get_report():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    start   = request.args.get('start')
    end     = request.args.get('end')
    user_id = request.args.get('user_id')
    dept_id = request.args.get('dept_id')
    if not start or not end:
        return jsonify({'error': 'start and end dates required'}), 400
    rows = Attendance.get_report(start, end, user_id, dept_id)
    return jsonify(rows), 200


# ── Start break ───────────────────────────────────────────────
@attendance_bp.route('/attendance/break/start', methods=['POST'])
@jwt_required()
def start_break():
    user_id    = int(get_jwt_identity())
    data       = request.json or {}
    break_type = data.get('break_type', 'short')
    if break_type not in ('lunch', 'short', 'meeting'):
        return jsonify({'error': 'Invalid break type'}), 400
    record, error = Break.start(user_id, break_type)
    if error:
        return jsonify({'error': error}), 400
    return jsonify(record), 201


# ── End break ─────────────────────────────────────────────────
@attendance_bp.route('/attendance/break/end', methods=['POST'])
@jwt_required()
def end_break():
    user_id = int(get_jwt_identity())
    record, error = Break.end(user_id)
    if error:
        return jsonify({'error': error}), 400
    return jsonify(record), 200


# ── Admin: breaks for a date ──────────────────────────────────
@attendance_bp.route('/attendance/breaks/admin', methods=['GET'])
@jwt_required()
def get_breaks_admin():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    target_date = request.args.get('date')
    rows = Break.get_all_for_date(target_date)
    return jsonify(rows), 200
