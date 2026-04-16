from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.client import Client
from app.models.user import User
from app.models.other import Notification

client_bp = Blueprint('client', __name__)

ALLOWED_ROLES = ['admin', 'crm_head', 'marketing_head', 'team_lead']

@client_bp.route('/clients', methods=['POST'])
@jwt_required()
def create_client():
    data = request.json
    claims = get_jwt()

    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({"error": "Unauthorized"}), 403

    try:
        user_id = None
        if data.get('email'):
            existing = User.get_by_email(data['email'])
            if existing:
                user_id = existing['id']
            else:
                user_id = User.create(
                    name=data['contact_person'],
                    email=data['email'],
                    password='client123',
                    role='client',
                    phone=data.get('phone')
                )

        client_id = Client.create(
            company_name=data['company_name'],
            contact_person=data['contact_person'],
            phone=data.get('phone'),
            email=data.get('email'),
            package_purchased=data.get('package_purchased'),
            project_start_date=data.get('project_start_date'),
            deadline=data.get('deadline'),
            notes=data.get('notes'),
            user_id=user_id,
            total_amount=data.get('total_amount')
        )

        if data.get('team_members'):
            Client.assign_team(client_id, data['team_members'])
            for member_id in data['team_members']:
                Notification.create(
                    member_id,
                    "New Client Assignment",
                    f"You have been assigned to {data['company_name']}",
                    "assignment"
                )

        return jsonify({"message": "Client created", "client_id": client_id}), 201
    except Exception as e:
        import traceback
        print(f"[CREATE CLIENT ERROR] {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 400


@client_bp.route('/clients', methods=['GET'])
@jwt_required()
def get_clients():
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    status = request.args.get('status')

    if claims['role'] == 'client':
        client = Client.get_by_user(user_id)
        return jsonify([client] if client else []), 200

    clients = Client.get_all(status)
    return jsonify(clients), 200


@client_bp.route('/clients/<int:client_id>', methods=['GET'])
@jwt_required()
def get_client(client_id):
    client = Client.get_by_id(client_id)
    if not client:
        return jsonify({"error": "Client not found"}), 404

    team = Client.get_team(client_id)
    client['team'] = team
    return jsonify(client), 200


@client_bp.route('/clients/<int:client_id>', methods=['PUT'])
@jwt_required()
def update_client(client_id):
    data = request.json
    claims = get_jwt()

    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({"error": "Unauthorized"}), 403

    try:
        Client.update(client_id, **data)

        if data.get('team_members'):
            Client.assign_team(client_id, data['team_members'])

        return jsonify({"message": "Client updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@client_bp.route('/clients/search', methods=['GET'])
@jwt_required()
def search_clients():
    query = request.args.get('q', '')
    clients = Client.search(query)
    return jsonify(clients), 200
