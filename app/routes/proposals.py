from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models.proposal import Proposal, Invoice
from app.models.other import CompanySettings
import os, json, urllib.request, urllib.error

proposals_bp = Blueprint('proposals', __name__)

ALLOWED_ROLES = ['admin', 'crm_head']

# ── AI helper ─────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a smart business assistant integrated into a CRM system.
You handle the complete flow from lead data to proposal to invoice.

RULES:
- For JSON tasks (extract_lead, fill_form, generate_invoice): return raw JSON only. No markdown, no explanation.
- For text tasks (generate_proposal, generate_invoice_email): return clean professional text only.
- If a field is unknown, use null.
- Never mix JSON and text in the same response."""

TASK_INSTRUCTIONS = {
    "extract_lead": """Extract lead info from raw input. Return JSON:
{ lead_name, company_name, email, phone, project_type, project_description, budget_range, timeline, requirements[], priority }""",

    "fill_form": """Pre-fill project form from CRM lead JSON. Return JSON:
{ client_name, client_email, client_phone, project_title, project_scope, deliverables[], estimated_duration_weeks, budget_estimate, special_notes }""",

    "generate_proposal": """Write a professional proposal in markdown with sections:
Executive Summary, Scope of Work, Deliverables, Timeline, Pricing, Terms & Conditions, Next Steps.""",

    "generate_invoice": """Generate invoice. Return JSON:
{ invoice_number, invoice_date, due_date, billed_to{name,company,email}, billed_by{company,email}, line_items[{description,quantity,unit_price,total}], subtotal, tax_percent, tax_amount, total_amount, payment_terms, notes }""",

    "generate_invoice_email": """Write a short professional email to the client with invoice details and payment instructions.""",
}


def _call_ai(task: str, input_data: str, company_settings: dict) -> str:
    api_key = os.getenv('OPENAI_API_KEY') or os.getenv('AI_API_KEY')
    if not api_key:
        raise ValueError("AI_API_KEY not configured in .env")

    company_ctx = (
        f"Company: {company_settings.get('company_name', 'KairaFlow')}, "
        f"Email: {company_settings.get('company_email', '')}, "
        f"Phone: {company_settings.get('company_phone', '')}, "
        f"Address: {company_settings.get('company_address', '')}"
    )

    user_message = (
        f"TASK: {task}\n\n"
        f"INSTRUCTIONS: {TASK_INSTRUCTIONS.get(task, '')}\n\n"
        f"COMPANY INFO: {company_ctx}\n\n"
        f"INPUT DATA:\n{input_data}"
    )

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    return result['choices'][0]['message']['content'].strip()


# ── AI endpoint ───────────────────────────────────────────────

@proposals_bp.route('/proposals/ai', methods=['POST'])
@jwt_required()
def ai_assist():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized — admin and crm_head only'}), 403

    data = request.json or {}
    task       = data.get('task', '').strip()
    input_data = data.get('input_data', '').strip()

    if task not in TASK_INSTRUCTIONS:
        return jsonify({'error': f'Unknown task. Options: {list(TASK_INSTRUCTIONS.keys())}'}), 400
    if not input_data:
        return jsonify({'error': 'input_data is required'}), 400

    try:
        settings = CompanySettings.get()
        result   = _call_ai(task, input_data, settings)
    except ValueError as e:
        return jsonify({'error': str(e)}), 503
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return jsonify({'error': f'AI API error {e.code}', 'detail': body}), 502
    except Exception as e:
        return jsonify({'error': f'AI request failed: {str(e)}'}), 500

    # For JSON tasks, parse and return as object; for text tasks return as string
    json_tasks = {'extract_lead', 'fill_form', 'generate_invoice'}
    if task in json_tasks:
        try:
            # Strip markdown code fences if model wraps in ```json
            clean = result.strip().lstrip('`').lstrip('json').strip('`').strip()
            parsed = json.loads(clean)
            return jsonify({'task': task, 'result': parsed}), 200
        except json.JSONDecodeError:
            return jsonify({'task': task, 'result': result, 'raw': True}), 200
    else:
        return jsonify({'task': task, 'result': result}), 200


# ── Proposal CRUD ─────────────────────────────────────────────

@proposals_bp.route('/proposals', methods=['POST'])
@jwt_required()
def create_proposal():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    user_id = int(get_jwt_identity())
    data    = request.json or {}
    row = Proposal.create(created_by=user_id, **data)
    return jsonify(row), 201


@proposals_bp.route('/proposals', methods=['GET'])
@jwt_required()
def get_proposals():
    claims  = get_jwt()
    user_id = int(get_jwt_identity())
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    # admin sees all; crm_head sees own
    by = None if claims['role'] == 'admin' else user_id
    status = request.args.get('status')
    rows = Proposal.get_all(created_by=by, status=status)
    return jsonify(rows), 200


@proposals_bp.route('/proposals/<int:pid>', methods=['GET'])
@jwt_required()
def get_proposal(pid):
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    row = Proposal.get_by_id(pid)
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(row), 200


@proposals_bp.route('/proposals/<int:pid>', methods=['PUT'])
@jwt_required()
def update_proposal(pid):
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    Proposal.update(pid, **request.json)
    return jsonify(Proposal.get_by_id(pid)), 200


@proposals_bp.route('/proposals/<int:pid>', methods=['DELETE'])
@jwt_required()
def delete_proposal(pid):
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    Proposal.delete(pid)
    return jsonify({'message': 'Deleted'}), 200


@proposals_bp.route('/proposals/send', methods=['POST'])
@jwt_required()
def send_proposal():
    claims   = get_jwt()
    user_id  = int(get_jwt_identity())
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json or {}
    required = ['client_id', 'template_id', 'template_name', 'line_items', 'total_amount']
    if not all(data.get(k) is not None for k in required):
        return jsonify({'error': 'client_id, template_id, template_name, line_items, total_amount required'}), 400

    client_id = int(data['client_id'])

    # CRM can only send to their assigned leads
    if claims['role'] == 'crm_head':
        from app.models.client import Client
        client = Client.get_by_id(client_id)
        if not client:
            return jsonify({'error': 'Client not found'}), 404
        # Check assignment via team_assignments
        from app.utils.database import get_db_connection
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id FROM team_assignments WHERE client_id=%s AND user_id=%s",
            (client_id, user_id)
        )
        assigned = cur.fetchone()
        cur.close(); conn.close()
        if not assigned:
            return jsonify({'error': 'You can only send proposals to your assigned leads'}), 403

    # Create proposal record first
    from app.models.client import Client
    client = Client.get_by_id(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404

    proposal = Proposal.create(
        created_by   = user_id,
        client_id    = client_id,
        lead_name    = client.get('contact_person'),
        company_name = client.get('company_name'),
        email        = client.get('email'),
        phone        = client.get('phone'),
        project_type = data.get('template_name'),
        status       = 'draft',
    )

    row, err = Proposal.send(
        proposal_id   = proposal['id'],
        sent_by       = user_id,
        note          = data.get('note'),
        template_id   = data['template_id'],
        template_name = data['template_name'],
        line_items    = data['line_items'],
        total_amount  = float(data['total_amount']),
    )
    if err:
        return jsonify({'error': err}), 400
    return jsonify(row), 201


@proposals_bp.route('/proposals/client/<int:client_id>', methods=['GET'])
@jwt_required()
def proposals_by_client(client_id):
    claims  = get_jwt()
    user_id = int(get_jwt_identity())
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    rows = Proposal.get_by_client(client_id)
    return jsonify(rows), 200


@proposals_bp.route('/proposals/<int:pid>/viewed', methods=['PATCH'])
def mark_proposal_viewed(pid):
    """Called when client opens the proposal email link — no auth needed."""
    Proposal.mark_viewed(pid)
    return jsonify({'message': 'Marked as viewed'}), 200


# ── Invoice CRUD ──────────────────────────────────────────────

@proposals_bp.route('/invoices', methods=['POST'])
@jwt_required()
def create_invoice():
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    user_id = int(get_jwt_identity())
    data    = request.json or {}
    row = Invoice.create(created_by=user_id, **data)
    return jsonify(row), 201


@proposals_bp.route('/invoices', methods=['GET'])
@jwt_required()
def get_invoices():
    claims  = get_jwt()
    user_id = int(get_jwt_identity())
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    by        = None if claims['role'] == 'admin' else user_id
    status    = request.args.get('status')
    client_id = request.args.get('client_id')
    rows = Invoice.get_all(
        created_by=by,
        status=status,
        client_id=int(client_id) if client_id else None,
    )
    return jsonify(rows), 200


@proposals_bp.route('/invoices/<int:iid>', methods=['GET'])
@jwt_required()
def get_invoice(iid):
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    row = Invoice.get_by_id(iid)
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(row), 200


@proposals_bp.route('/invoices/<int:iid>', methods=['PUT'])
@jwt_required()
def update_invoice(iid):
    claims = get_jwt()
    if claims['role'] not in ALLOWED_ROLES:
        return jsonify({'error': 'Unauthorized'}), 403
    Invoice.update(iid, **request.json)
    return jsonify(Invoice.get_by_id(iid)), 200


@proposals_bp.route('/invoices/<int:iid>', methods=['DELETE'])
@jwt_required()
def delete_invoice(iid):
    claims = get_jwt()
    if claims['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    Invoice.delete(iid)
    return jsonify({'message': 'Deleted'}), 200
