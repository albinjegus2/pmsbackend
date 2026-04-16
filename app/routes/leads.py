from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.lead import Lead
from app.models.client import Client
from app.models.user import User
from app.models.finance import ClientPayment

leads_bp = Blueprint('leads', __name__)

ALLOWED_ROLES = ['admin', 'crm', 'crm_head', 'marketing_head', 'smm', 'team_lead']


@leads_bp.route('/leads', methods=['GET'])
@jwt_required()
def get_leads():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({"error": "Unauthorized"}), 403
    status      = request.args.get('status')
    assigned_to = request.args.get('assigned_to')
    leads = Lead.get_all(status=status, assigned_to=assigned_to)
    return jsonify(leads), 200


@leads_bp.route('/leads/stats', methods=['GET'])
@jwt_required()
def get_lead_stats():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(Lead.get_stats()), 200


@leads_bp.route('/leads/<int:lead_id>', methods=['GET'])
@jwt_required()
def get_lead(lead_id):
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({"error": "Unauthorized"}), 403
    lead = Lead.get_by_id(lead_id)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
    lead['followups'] = Lead.get_followups(lead_id)
    return jsonify(lead), 200


@leads_bp.route('/leads', methods=['POST'])
@jwt_required()
def create_lead():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    if not data.get('name'):
        return jsonify({"error": "name is required"}), 400
    try:
        created_by = int(get_jwt_identity())
        lead_id = Lead.create(
            name=data['name'],
            company=data.get('company', ''),
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            source=data.get('source', 'other'),
            service_interest=data.get('service_interest', ''),
            notes=data.get('notes', ''),
            assigned_to=data.get('assigned_to'),
            created_by=created_by
        )
        return jsonify({"message": "Lead created", "lead_id": lead_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@leads_bp.route('/leads/<int:lead_id>', methods=['PUT'])
@jwt_required()
def update_lead(lead_id):
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    allowed = ['name', 'company', 'phone', 'email', 'source', 'service_interest', 'status', 'notes', 'assigned_to']
    update_data = {k: v for k, v in data.items() if k in allowed}
    if not update_data:
        return jsonify({"error": "No valid fields to update"}), 400
    Lead.update(lead_id, **update_data)
    return jsonify({"message": "Lead updated"}), 200


@leads_bp.route('/leads/<int:lead_id>', methods=['DELETE'])
@jwt_required()
def delete_lead(lead_id):
    claims = get_jwt()
    if claims['role'] not in ['admin', 'marketing_head']:
        return jsonify({"error": "Unauthorized"}), 403
    Lead.delete(lead_id)
    return jsonify({"message": "Lead deleted"}), 200


@leads_bp.route('/leads/<int:lead_id>/followups', methods=['POST'])
@jwt_required()
def add_followup(lead_id):
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    if not data.get('note'):
        return jsonify({"error": "note is required"}), 400
    added_by = int(get_jwt_identity())
    fid = Lead.add_followup(
        lead_id=lead_id,
        note=data['note'],
        next_followup_date=data.get('next_followup_date'),
        added_by=added_by
    )
    # auto update lead status to follow_up if still new/contacted
    lead = Lead.get_by_id(lead_id)
    if lead and lead['status'] in ['new', 'contacted']:
        Lead.update(lead_id, status='follow_up')
    return jsonify({"message": "Follow-up added", "id": fid}), 201


@leads_bp.route('/leads/<int:lead_id>/convert', methods=['POST'])
@jwt_required()
def convert_to_client(lead_id):
    claims = get_jwt()
    if claims['role'] not in ['admin', 'crm_head', 'marketing_head']:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    lead = Lead.get_by_id(lead_id)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
    if lead['status'] == 'converted':
        return jsonify({"error": "Lead already converted"}), 400

    # total_amount is required to convert
    if not data.get('total_amount') or float(data['total_amount']) <= 0:
        return jsonify({"error": "total_amount is required to convert a lead to client"}), 400

    try:
        # Create client record
        user_id = None
        if lead.get('email'):
            existing = User.get_by_email(lead['email'])
            if existing:
                user_id = existing['id']
            else:
                user_id = User.create(
                    name=lead['name'],
                    email=lead['email'],
                    password='client123',
                    role='client',
                    phone=lead.get('phone')
                )

        client_id = Client.create(
            company_name=lead.get('company') or lead['name'],
            contact_person=lead['name'],
            phone=lead.get('phone', ''),
            email=lead.get('email', ''),
            package_purchased=data.get('package_purchased', lead.get('service_interest', '')),
            project_start_date=data.get('project_start_date'),
            deadline=data.get('deadline'),
            notes=lead.get('notes', ''),
            user_id=user_id,
            total_amount=data['total_amount']
        )

        # Record first payment if provided
        if data.get('initial_payment') and float(data['initial_payment']) > 0:
            added_by = int(get_jwt_identity())
            ClientPayment.add_payment(
                client_id=client_id,
                amount=data['initial_payment'],
                payment_date=data.get('payment_date') or __import__('datetime').date.today().isoformat(),
                payment_method=data.get('payment_method', 'bank_transfer'),
                reference=data.get('reference', ''),
                notes='Initial payment on conversion from lead',
                added_by=added_by
            )

        # Mark lead as converted
        Lead.convert_to_client(lead_id, client_id)

        return jsonify({"message": "Lead converted to client", "client_id": client_id}), 201
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 400
