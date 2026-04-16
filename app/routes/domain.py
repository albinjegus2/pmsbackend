from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.domain import Domain

domain_bp = Blueprint('domain', __name__)

ALLOWED_ROLES = ['admin', 'crm_head', 'marketing_head', 'team_lead']


@domain_bp.route('/domains/alerts', methods=['GET'])
@jwt_required()
def get_domain_alerts():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    from datetime import date
    today = date.today()
    all_domains = Domain.get_all()
    expired  = [d for d in all_domains if d['renewal_date'] < today.isoformat()]
    critical = [d for d in all_domains if today.isoformat() <= d['renewal_date'] <= (today.replace(day=today.day+7) if today.day <= 24 else today).isoformat()]
    # simpler approach
    from datetime import timedelta
    in7  = (today + timedelta(days=7)).isoformat()
    in30 = (today + timedelta(days=30)).isoformat()
    expired  = [d for d in all_domains if d['renewal_date'] < today.isoformat()]
    critical = [d for d in all_domains if today.isoformat() <= d['renewal_date'] <= in7]
    upcoming = [d for d in all_domains if in7 < d['renewal_date'] <= in30]
    return jsonify({
        'expired': expired,
        'critical': critical,
        'upcoming': upcoming,
        'total_alerts': len(expired) + len(critical)
    }), 200


@domain_bp.route('/domains', methods=['GET'])
@jwt_required()
def get_domains():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(Domain.get_all()), 200


@domain_bp.route('/domains', methods=['POST'])
@jwt_required()
def create_domain():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.json
    if not data.get('domain_name') or not data.get('renewal_date'):
        return jsonify({'error': 'domain_name and renewal_date are required'}), 400
    try:
        added_by = int(get_jwt_identity())
        domain_id = Domain.create(
            domain_name=data['domain_name'],
            domain_url=data.get('domain_url', ''),
            client_id=data.get('client_id'),
            renewal_date=data['renewal_date'],
            registrar=data.get('registrar', ''),
            notes=data.get('notes', ''),
            added_by=added_by
        )
        return jsonify({'message': 'Domain added', 'domain_id': domain_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@domain_bp.route('/domains/<int:domain_id>', methods=['PUT'])
@jwt_required()
def update_domain(domain_id):
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.json
    allowed = ['domain_name', 'domain_url', 'client_id', 'renewal_date', 'registrar', 'notes']
    update_data = {k: v for k, v in data.items() if k in allowed}
    if not update_data:
        return jsonify({'error': 'No valid fields'}), 400
    Domain.update(domain_id, **update_data)
    return jsonify({'message': 'Domain updated'}), 200


@domain_bp.route('/domains/<int:domain_id>', methods=['DELETE'])
@jwt_required()
def delete_domain(domain_id):
    claims = get_jwt()
    if claims['role'] not in ['admin', 'marketing_head']:
        return jsonify({'error': 'Unauthorized'}), 403
    Domain.delete(domain_id)
    return jsonify({'message': 'Domain deleted'}), 200
