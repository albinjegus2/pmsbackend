from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.feedback import Feedback, ReviewMeeting
from app.models.notification import Notification

feedback_bp = Blueprint('feedback', __name__)

LEAD_ROLES = ['admin', 'team_lead', 'crm_head', 'marketing_head']


def _notify(*args, **kwargs):
    try:
        Notification.push(*args, **kwargs)
    except Exception:
        pass


def _notify_admins(*args, **kwargs):
    try:
        Notification.push_to_admins(*args, **kwargs)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════
#  FEEDBACK ROUTES
# ════════════════════════════════════════════════════════════

@feedback_bp.route('/feedback', methods=['POST'])
@jwt_required()
def submit_feedback():
    user_id = int(get_jwt_identity())
    data = request.json or {}
    if not data.get('category') or not data.get('message'):
        return jsonify({'error': 'category and message required'}), 400
    rating = data.get('rating', 3)
    if not (1 <= int(rating) <= 5):
        return jsonify({'error': 'rating must be 1-5'}), 400

    row = Feedback.create(
        user_id, data['category'], data['message'],
        int(rating), data.get('visibility', 'named')
    )
    # Notify admins
    name = row.get('employee_name', 'Someone') if row.get('visibility') != 'anonymous' else 'Anonymous'
    _notify_admins(
        type='feedback',
        title='New Feedback Submitted',
        message=f"{name} submitted {data['category'].replace('_', ' ')} feedback",
        link='/dashboard/feedback',
        exclude_user_id=user_id,
    )
    return jsonify(row), 201


@feedback_bp.route('/feedback/my', methods=['GET'])
@jwt_required()
def my_feedback():
    user_id = int(get_jwt_identity())
    return jsonify(Feedback.get_my(user_id)), 200


@feedback_bp.route('/feedback/all', methods=['GET'])
@jwt_required()
def all_feedback():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    category = request.args.get('category')
    return jsonify(Feedback.get_all(category)), 200


@feedback_bp.route('/feedback/stats', methods=['GET'])
@jwt_required()
def feedback_stats():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(Feedback.get_stats()), 200


# ════════════════════════════════════════════════════════════
#  REVIEW MEETING ROUTES
# ════════════════════════════════════════════════════════════

@feedback_bp.route('/reviews', methods=['POST'])
@jwt_required()
def schedule_review():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    reviewer_id = int(get_jwt_identity())
    data = request.json or {}
    if not data.get('employee_id') or not data.get('meeting_date') or not data.get('meeting_type'):
        return jsonify({'error': 'employee_id, meeting_date, meeting_type required'}), 400

    row, err = ReviewMeeting.create(
        int(data['employee_id']), reviewer_id,
        data['meeting_date'], data['meeting_type'],
        data.get('notes'), data.get('improvement_points'), data.get('goals_set'),
    )
    if err:
        return jsonify({'error': err}), 400

    _notify(
        user_id=int(data['employee_id']),
        type='review_scheduled',
        title='Review Meeting Scheduled',
        message=f"A {data['meeting_type']} review has been scheduled for {data['meeting_date']}",
        link='/dashboard/feedback',
    )
    return jsonify(row), 201


@feedback_bp.route('/reviews/<int:review_id>/complete', methods=['PATCH'])
@jwt_required()
def complete_review(review_id):
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    reviewer_id = int(get_jwt_identity())
    data = request.json or {}
    if not data.get('rating'):
        return jsonify({'error': 'rating required'}), 400

    row, err = ReviewMeeting.complete(
        review_id, reviewer_id, int(data['rating']),
        data.get('notes'), data.get('improvement_points'), data.get('goals_set'),
    )
    if err:
        return jsonify({'error': err}), 400

    if row:
        _notify(
            user_id=row['employee_id'],
            type='review_completed',
            title='Review Meeting Completed',
            message=f"Your {row['meeting_type']} review has been completed. Rating: {data['rating']}/5",
            link='/dashboard/feedback',
        )
    return jsonify(row), 200


@feedback_bp.route('/reviews/<int:review_id>/cancel', methods=['PATCH'])
@jwt_required()
def cancel_review(review_id):
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    ReviewMeeting.cancel(review_id)
    return jsonify({'message': 'Review cancelled'}), 200


@feedback_bp.route('/reviews/my', methods=['GET'])
@jwt_required()
def my_reviews():
    employee_id = int(get_jwt_identity())
    return jsonify(ReviewMeeting.get_my(employee_id)), 200


@feedback_bp.route('/reviews/all', methods=['GET'])
@jwt_required()
def all_reviews():
    claims = get_jwt()
    if claims['role'] not in LEAD_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    status = request.args.get('status')
    employee_id = request.args.get('employee_id')
    return jsonify(ReviewMeeting.get_all(status, employee_id)), 200


# ════════════════════════════════════════════════════════════
#  NOTIFICATION ROUTES
# ════════════════════════════════════════════════════════════

@feedback_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    user_id = int(get_jwt_identity())
    unread_only = request.args.get('unread') == 'true'
    return jsonify(Notification.get_by_user(user_id, unread_only)), 200


@feedback_bp.route('/notifications/unread-count', methods=['GET'])
@jwt_required()
def unread_count():
    user_id = int(get_jwt_identity())
    return jsonify({'count': Notification.get_unread_count(user_id)}), 200


@feedback_bp.route('/notifications/<int:nid>/read', methods=['PATCH'])
@jwt_required()
def mark_read(nid):
    user_id = int(get_jwt_identity())
    Notification.mark_read(nid, user_id)
    return jsonify({'message': 'Marked as read'}), 200


@feedback_bp.route('/notifications/read-all', methods=['PATCH'])
@jwt_required()
def mark_all_read():
    user_id = int(get_jwt_identity())
    Notification.mark_all_read(user_id)
    return jsonify({'message': 'All marked as read'}), 200
