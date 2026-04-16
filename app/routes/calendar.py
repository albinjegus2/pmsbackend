from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.calendar import CalendarEvent
import logging

calendar_bp = Blueprint('calendar', __name__)

@calendar_bp.route('/calendar/events', methods=['POST'])
@jwt_required()
def create_event():
    user_id = int(get_jwt_identity())
    data = request.json
    try:
        event_id = CalendarEvent.create(
            user_id=user_id,
            title=data['title'],
            start_time=data['start_time'],
            end_time=data['end_time'],
            entry_type=data.get('entry_type', 'event'),
            description=data.get('description'),
            all_day=data.get('all_day', False)
        )
        return jsonify({"message": "Event created", "id": event_id}), 201
    except Exception as e:
        logging.error(f"Error creating event: {e}")
        return jsonify({"error": str(e)}), 400

@calendar_bp.route('/calendar/events', methods=['GET'])
@jwt_required()
def get_events():
    user_id = int(get_jwt_identity())
    month = request.args.get('month')
    year = request.args.get('year')
    try:
        events = CalendarEvent.get_by_user(user_id, month, year)
        return jsonify(events), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@calendar_bp.route('/calendar/events/user/<int:target_user_id>', methods=['GET'])
@jwt_required()
def get_user_events(target_user_id):
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    if claims.get('role') not in ['admin', 'marketing_head']:
        return jsonify({'error': 'Unauthorized'}), 403
    month = request.args.get('month')
    year  = request.args.get('year')
    try:
        events = CalendarEvent.get_by_user(target_user_id, month, year)
        return jsonify(events), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@calendar_bp.route('/calendar/events/<int:event_id>', methods=['DELETE'])
@jwt_required()
def delete_event(event_id):
    user_id = int(get_jwt_identity())
    try:
        CalendarEvent.delete(event_id, user_id)
        return jsonify({"message": "Event deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400
