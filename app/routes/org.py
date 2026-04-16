from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.org import Team, Department
from app.models.user import User

org_bp = Blueprint('org', __name__)

# ── Teams ──────────────────────────────────────────────

@org_bp.route('/teams', methods=['GET'])
@jwt_required()
def get_teams():
    teams = Team.get_all()
    return jsonify(teams), 200

@org_bp.route('/teams', methods=['POST'])
@jwt_required()
def create_team():
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    team_id = Team.create(data['name'], data.get('description'))
    return jsonify({"message": "Team created", "team_id": team_id}), 201

@org_bp.route('/teams/<int:team_id>', methods=['DELETE'])
@jwt_required()
def delete_team(team_id):
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    Team.delete(team_id)
    return jsonify({"message": "Team deleted"}), 200

# ── Departments ────────────────────────────────────────

@org_bp.route('/departments', methods=['GET'])
@jwt_required()
def get_departments():
    team_id = request.args.get('team_id')
    depts = Department.get_all(int(team_id) if team_id else None)
    return jsonify(depts), 200

@org_bp.route('/departments', methods=['POST'])
@jwt_required()
def create_department():
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    dept_id = Department.create(data['name'], data['team_id'], data.get('description'))
    return jsonify({"message": "Department created", "dept_id": dept_id}), 201

@org_bp.route('/departments/<int:dept_id>', methods=['DELETE'])
@jwt_required()
def delete_department(dept_id):
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    Department.delete(dept_id)
    return jsonify({"message": "Department deleted"}), 200

# ── Users / Members ────────────────────────────────────

@org_bp.route('/members', methods=['GET'])
@jwt_required()
def get_members():
    role = request.args.get('role')
    team_id = request.args.get('team_id')
    department_id = request.args.get('department_id')
    users = User.get_all(
        role=role,
        team_id=int(team_id) if team_id else None,
        department_id=int(department_id) if department_id else None
    )
    return jsonify(users), 200

@org_bp.route('/members', methods=['POST'])
@jwt_required()
def create_member():
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    try:
        user_id = User.create(
            name=data['name'],
            email=data['email'],
            password=data.get('password', 'password123'),
            role=data['role'],
            phone=data.get('phone'),
            team_id=int(data['team_id']) if data.get('team_id') else None,
            department_id=int(data['department_id']) if data.get('department_id') else None,
            manager_id=int(data['manager_id']) if data.get('manager_id') else None
        )
        return jsonify({"message": "Member created", "user_id": user_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@org_bp.route('/members/<int:user_id>', methods=['PUT'])
@jwt_required()
def update_member(user_id):
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    data = request.json
    allowed = ['name', 'role', 'phone', 'team_id', 'department_id', 'manager_id']
    updates = {k: v for k, v in data.items() if k in allowed}
    User.update(user_id, **updates)
    return jsonify({"message": "Member updated"}), 200

@org_bp.route('/members/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_member(user_id):
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    User.delete(user_id)
    return jsonify({"message": "Member deleted"}), 200

@org_bp.route('/members/team-leads', methods=['GET'])
@jwt_required()
def get_team_leads():
    leads = User.get_team_leads()
    return jsonify(leads), 200

@org_bp.route('/members/<int:user_id>/subordinates', methods=['GET'])
@jwt_required()
def get_subordinates(user_id):
    users = User.get_subordinates(user_id)
    return jsonify(users), 200

# ── Org Chart ──────────────────────────────────────────

@org_bp.route('/org-chart', methods=['GET'])
@jwt_required()
def get_org_chart():
    teams = Team.get_all()
    result = []
    for team in teams:
        depts = Department.get_all(team['id'])
        team_leads = User.get_all(team_id=team['id'], role='team_lead')
        team_data = {
            **team,
            'leads': team_leads,
            'departments': []
        }
        for dept in depts:
            dept_leads = User.get_all(department_id=dept['id'], role='team_lead')
            dept_members = User.get_all(department_id=dept['id'])
            dept_members = [m for m in dept_members if m['role'] not in ('team_lead', 'crm_head')]
            team_data['departments'].append({
                **dept,
                'leads': dept_leads,
                'members': dept_members
            })
        result.append(team_data)
    return jsonify(result), 200
