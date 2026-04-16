from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.hr import Leave, Permission
from app.models.notification import Notification

hr_bp = Blueprint('hr', __name__)

LEAD_ROLES = ['admin', 'team_lead', 'crm_head', 'marketing_head']


def _notify(*args, **kwargs):
    """Non-fatal notification push."""
    try:
        Notification.push(*args, **kwargs)
    except Exception:
        pass


def _notify_admins(*args, **kwargs):
    """Non-fatal push_to_admins."""
    try:
        Notification.push_to_admins(*args, **kwargs)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════
#  LEAVE ROUTES
# ════════════════════════════════════════════════════════════

@hr_bp.route('/leaves', methods=['POST'])
@jwt_required()
def apply_leave():
    user_id = int(get_jwt_identity())
    data    = request.json or {}
    required = ['leave_type', 'start_date', 'end_date', 'reason']
    if not all(data.get(f) for f in required):
        return jsonify({'error': 'leave_type, start_date, end_date, reason required'}), 400

    row, err = Leave.create(
        user_id,
        data['leave_type'],
        data['start_date'],
        data['end_date'],
        data['reason'],
    )
    if err:
        return jsonify({'error': err}), 400

    _notify_admins('leave_request', 'New Leave Request',
        f"{row.get('employee_name','Employee')} applied for {data['leave_type']} leave "
        f"({data['start_date']} – {data['end_date']})",
        '/dashboard/leaves', exclude_user_id=user_id)
    return jsonify(row), 201


@hr_bp.route('/leaves/my', methods=['GET'])
@jwt_required()
def my_leaves():
    user_id = int(get_jwt_identity())
    return jsonify(Leave.get_by_user(user_id)), 200


@hr_bp.route('/leaves/pending', methods=['GET'])
@jwt_required()
def pending_leaves():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    approver_id = int(get_jwt_identity())
    return jsonify(Leave.get_pending(approver_id)), 200


@hr_bp.route('/leaves/all', methods=['GET'])
@jwt_required()
def all_leaves():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    status  = request.args.get('status')
    user_id = request.args.get('user_id')
    month   = request.args.get('month')
    year    = request.args.get('year')
    return jsonify(Leave.get_all(status, user_id, month, year)), 200


@hr_bp.route('/leaves/calendar', methods=['GET'])
@jwt_required()
def leave_calendar():
    year  = request.args.get('year',  str(__import__('datetime').date.today().year))
    month = request.args.get('month', str(__import__('datetime').date.today().month))
    return jsonify(Leave.get_calendar(year, month)), 200


@hr_bp.route('/leaves/stats', methods=['GET'])
@jwt_required()
def leave_stats():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(Leave.get_stats()), 200


@hr_bp.route('/leaves/<int:leave_id>/approve', methods=['PATCH'])
@jwt_required()
def approve_leave(leave_id):
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    approver_id = int(get_jwt_identity())
    row, err    = Leave.approve(leave_id, approver_id)
    if err:
        return jsonify({'error': err}), 400
    if row:
        _notify(row['user_id'], 'leave_approved', 'Leave Approved',
            f"Your {row['leave_type']} leave ({row['start_date']} – {row['end_date']}) has been approved.",
            '/dashboard/leaves')
    return jsonify(row), 200


@hr_bp.route('/leaves/<int:leave_id>/reject', methods=['PATCH'])
@jwt_required()
def reject_leave(leave_id):
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    approver_id = int(get_jwt_identity())
    note        = (request.json or {}).get('note')
    row, err    = Leave.reject(leave_id, approver_id, note)
    if err:
        return jsonify({'error': err}), 400
    if row:
        _notify(row['user_id'], 'leave_rejected', 'Leave Rejected',
            f"Your {row['leave_type']} leave request was rejected.",
            '/dashboard/leaves')
    return jsonify(row), 200


# ════════════════════════════════════════════════════════════
#  PERMISSION ROUTES
# ════════════════════════════════════════════════════════════

@hr_bp.route('/permissions', methods=['POST'])
@jwt_required()
def apply_permission():
    user_id = int(get_jwt_identity())
    data    = request.json or {}
    required = ['date', 'from_time', 'to_time', 'reason']
    if not all(data.get(f) for f in required):
        return jsonify({'error': 'date, from_time, to_time, reason required'}), 400

    row, err = Permission.create(
        user_id,
        data['date'],
        data['from_time'],
        data['to_time'],
        data['reason'],
    )
    if err:
        return jsonify({'error': err}), 400

    _notify_admins('permission_request', 'New Permission Request',
        f"{row.get('employee_name','Employee')} requested permission on {data['date']} "
        f"({data['from_time']} – {data['to_time']})",
        '/dashboard/permissions', exclude_user_id=user_id)
    return jsonify(row), 201


@hr_bp.route('/permissions/my', methods=['GET'])
@jwt_required()
def my_permissions():
    user_id = int(get_jwt_identity())
    return jsonify(Permission.get_by_user(user_id)), 200


@hr_bp.route('/permissions/pending', methods=['GET'])
@jwt_required()
def pending_permissions():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(Permission.get_pending()), 200


@hr_bp.route('/permissions/all', methods=['GET'])
@jwt_required()
def all_permissions():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    status  = request.args.get('status')
    user_id = request.args.get('user_id')
    return jsonify(Permission.get_all(status, user_id)), 200


@hr_bp.route('/permissions/<int:perm_id>/approve', methods=['PATCH'])
@jwt_required()
def approve_permission(perm_id):
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    approver_id = int(get_jwt_identity())
    row, err    = Permission.approve(perm_id, approver_id)
    if err:
        return jsonify({'error': err}), 400
    if row:
        _notify(row['user_id'], 'permission_approved', 'Permission Approved',
            f"Your permission request for {row['date']} has been approved.",
            '/dashboard/permissions')
    return jsonify(row), 200


@hr_bp.route('/permissions/<int:perm_id>/reject', methods=['PATCH'])
@jwt_required()
def reject_permission(perm_id):
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    approver_id = int(get_jwt_identity())
    row, err    = Permission.reject(perm_id, approver_id)
    if err:
        return jsonify({'error': err}), 400
    if row:
        _notify(row['user_id'], 'permission_rejected', 'Permission Rejected',
            f"Your permission request for {row['date']} was rejected.",
            '/dashboard/permissions')
    return jsonify(row), 200
