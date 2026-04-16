from app.utils.database import get_db_connection
from app.utils.timezone import now_ist, today_ist
from datetime import datetime, date
from decimal import Decimal
import json


def _s(row):
    if row is None:
        return None
    out = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, (bytes, bytearray)):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = v.decode('utf-8', errors='replace')
        else:
            out[k] = v
    return out


class Proposal:

    @staticmethod
    def create(created_by: int, **kwargs):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        fields = ['created_by']
        values = [created_by]
        json_fields = {'requirements', 'form_data'}
        allowed = {
            'client_id', 'lead_name', 'company_name', 'email', 'phone',
            'project_type', 'project_description', 'budget_range', 'timeline',
            'requirements', 'priority', 'form_data', 'proposal_text', 'status',
        }
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                fields.append(k)
                values.append(json.dumps(v) if k in json_fields else v)
        placeholders = ', '.join(['%s'] * len(fields))
        cols = ', '.join(fields)
        cursor.execute(
            f"INSERT INTO proposals ({cols}) VALUES ({placeholders})", values
        )
        conn.commit()
        pid = cursor.lastrowid
        cursor.execute("""
            SELECT p.*, u.name AS created_by_name
            FROM proposals p
            JOIN users u ON p.created_by = u.id
            WHERE p.id = %s
        """, (pid,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row

    @staticmethod
    def update(proposal_id: int, **kwargs):
        conn = get_db_connection()
        cursor = conn.cursor()
        json_fields = {'requirements', 'form_data'}
        allowed = {
            'lead_name', 'company_name', 'email', 'phone', 'project_type',
            'project_description', 'budget_range', 'timeline', 'requirements',
            'priority', 'form_data', 'proposal_text', 'status', 'client_id',
        }
        fields, values = [], []
        for k, v in kwargs.items():
            if k in allowed:
                fields.append(f"{k} = %s")
                values.append(json.dumps(v) if k in json_fields and v is not None else v)
        if not fields:
            cursor.close(); conn.close()
            return
        values.append(proposal_id)
        cursor.execute(f"UPDATE proposals SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_by_id(proposal_id: int):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.*, u.name AS created_by_name, c.company_name AS client_company
            FROM proposals p
            JOIN users u ON p.created_by = u.id
            LEFT JOIN clients c ON p.client_id = c.id
            WHERE p.id = %s
        """, (proposal_id,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row

    @staticmethod
    def get_all(created_by: int = None, status: str = None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT p.*, u.name AS created_by_name, c.company_name AS client_company
            FROM proposals p
            JOIN users u ON p.created_by = u.id
            LEFT JOIN clients c ON p.client_id = c.id
            WHERE 1=1
        """
        params = []
        if created_by:
            query += " AND p.created_by = %s"; params.append(created_by)
        if status:
            query += " AND p.status = %s"; params.append(status)
        query += " ORDER BY p.created_at DESC"
        cursor.execute(query, params)
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def delete(proposal_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM proposals WHERE id = %s", (proposal_id,))
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_by_client(client_id: int):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.*, u.name AS created_by_name
            FROM proposals p
            JOIN users u ON p.created_by = u.id
            WHERE p.client_id = %s
            ORDER BY p.created_at DESC
        """, (client_id,))
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def _build_proposal_pdf(proposal, template_name, line_items, total_amount, note):
        """Generate proposal PDF with letterpad (same as reports) and return BytesIO."""
        import io, os
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Image, Table, TableStyle, Spacer, Paragraph
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from PIL import Image as PILImage

        # Register Unicode font for ₹ support — works on Windows and Linux
        _FONT_CANDIDATES = [
            ('C:/Windows/Fonts/arial.ttf',   'C:/Windows/Fonts/arialbd.ttf'),
            ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
             '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
            ('/usr/share/fonts/dejavu/DejaVuSans.ttf',
             '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf'),
        ]
        FONT_NORMAL, FONT_BOLD = 'Helvetica', 'Helvetica-Bold'
        for np, bp in _FONT_CANDIDATES:
            if os.path.exists(np):
                try:
                    from reportlab.pdfbase import pdfmetrics
                    from reportlab.pdfbase.ttfonts import TTFont
                    pdfmetrics.registerFont(TTFont('UniFont', np))
                    pdfmetrics.registerFont(TTFont('UniFont-Bold', bp if os.path.exists(bp) else np))
                    FONT_NORMAL, FONT_BOLD = 'UniFont', 'UniFont-Bold'
                    break
                except Exception:
                    continue

        def img_path(filename):
            return os.path.normpath(
                os.path.join(os.path.dirname(__file__), '..', '..', '..', 'frontend', filename)
            )

        top_path    = img_path('letterpadtop.png')
        bottom_path = img_path('letterpadbottom.png')

        PAGE_W, PAGE_H = A4

        def img_dims(path):
            if not os.path.exists(path):
                return 0, 0
            pil = PILImage.open(path)
            iw, ih = pil.size
            return PAGE_W, PAGE_W * (ih / iw)

        top_w,    top_h    = img_dims(top_path)
        bottom_w, bottom_h = img_dims(bottom_path)

        SIDE_PAD = 14 * mm
        inner_w  = PAGE_W - 2 * SIDE_PAD

        title_style = ParagraphStyle('title', fontSize=14, fontName=FONT_BOLD,
                                     textColor=colors.HexColor('#2563eb'), spaceAfter=4)
        sub_style   = ParagraphStyle('sub',   fontSize=9,  fontName=FONT_NORMAL,
                                     textColor=colors.HexColor('#555555'), spaceAfter=3)
        body_style  = ParagraphStyle('body',  fontSize=9,  fontName=FONT_NORMAL,
                                     textColor=colors.HexColor('#374151'), spaceAfter=6)
        note_style  = ParagraphStyle('note',  fontSize=9,  fontName=FONT_NORMAL,
                                     textColor=colors.HexColor('#92400e'), spaceAfter=6)

        client_name  = proposal.get('lead_name') or proposal.get('contact_person', '')
        company_name = proposal.get('company_name', '')
        timeline     = proposal.get('timeline', 'TBD')
        INR          = '\u20b9'
        grand_total  = total_amount or 0

        # Line items table
        items_data = [['Service / Description', 'Qty', 'Unit Price', 'Total']]
        if line_items:
            for item in line_items:
                up = float(item.get('unit_price', 0))
                tt = float(item.get('total', 0))
                items_data.append([
                    item.get('description', ''),
                    str(item.get('quantity', 1)),
                    f"{INR}{up:,.2f}",
                    f"{INR}{tt:,.2f}",
                ])
        items_data.append(['', '', 'Grand Total', f"{INR}{grand_total:,.2f}"])

        col_widths = [inner_w * 0.50, inner_w * 0.10, inner_w * 0.20, inner_w * 0.20]
        tbl = Table(items_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0),  (-1, 0),  colors.HexColor('#dbeafe')),
            ('TEXTCOLOR',     (0, 0),  (-1, 0),  colors.HexColor('#1e3a8a')),
            ('FONTNAME',      (0, 0),  (-1, 0),  FONT_BOLD),
            ('FONTSIZE',      (0, 0),  (-1, -1), 8),
            ('TOPPADDING',    (0, 0),  (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0),  (-1, -1), 5),
            ('FONTNAME',      (0, 1),  (-1, -2), FONT_NORMAL),
            ('ROWBACKGROUNDS',(0, 1),  (-1, -2), [colors.white, colors.HexColor('#f9fafb')]),
            ('BACKGROUND',    (0, -1), (-1, -1), colors.HexColor('#f0f0f0')),
            ('FONTNAME',      (0, -1), (-1, -1), FONT_BOLD),
            ('ALIGN',         (1, 0),  (-1, -1), 'CENTER'),
            ('ALIGN',         (2, 0),  (-1, -1), 'RIGHT'),
            ('GRID',          (0, 0),  (-1, -1), 0.4, colors.HexColor('#cccccc')),
            ('VALIGN',        (0, 0),  (-1, -1), 'MIDDLE'),
        ]))

        elements_inner = [
            Paragraph(template_name or 'Project Proposal', title_style),
            Paragraph(f'Prepared for: {client_name}  |  Company: {company_name}', sub_style),
            Paragraph(f'Timeline: {timeline}', sub_style),
            Spacer(1, 4 * mm),
        ]
        if note:
            elements_inner.append(Paragraph(f'Note: {note}', note_style))
            elements_inner.append(Spacer(1, 3 * mm))

        elements_inner += [
            Paragraph('Investment Summary', ParagraphStyle('h2', fontSize=10,
                fontName=FONT_BOLD, textColor=colors.HexColor('#111827'), spaceAfter=4)),
            tbl,
            Spacer(1, 5 * mm),
            Paragraph(
                f'Generated on: {datetime.now().strftime("%d %B %Y, %H:%M")}',
                ParagraphStyle('ft', fontSize=8, fontName=FONT_NORMAL,
                               textColor=colors.HexColor('#888888'))
            ),
        ]

        wrapper = Table([[elements_inner]], colWidths=[inner_w])
        wrapper.setStyle(TableStyle([
            ('LEFTPADDING',   (0, 0), (-1, -1), SIDE_PAD),
            ('RIGHTPADDING',  (0, 0), (-1, -1), SIDE_PAD),
            ('TOPPADDING',    (0, 0), (-1, -1), 5 * mm),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4 * mm),
        ]))

        all_elements = [wrapper]
        if os.path.exists(bottom_path) and bottom_h > 0:
            all_elements += [Spacer(1, 4 * mm), Image(bottom_path, width=PAGE_W, height=bottom_h)]

        def on_page(canvas, doc):
            canvas.saveState()
            if os.path.exists(top_path) and top_h > 0:
                canvas.drawImage(top_path, 0, PAGE_H - top_h,
                                 width=PAGE_W, height=top_h,
                                 preserveAspectRatio=True, mask='auto')
            canvas.restoreState()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=0, rightMargin=0,
            topMargin=top_h, bottomMargin=0,
        )
        doc.build(all_elements, onFirstPage=on_page, onLaterPages=on_page)
        buf.seek(0)
        return buf

    @staticmethod
    def send(proposal_id: int, sent_by: int, note: str = None,
             template_id: str = None, template_name: str = None,
             line_items: list = None, total_amount: float = None):
        """Mark proposal as sent, store metadata, send email with letterpad PDF attached."""
        import smtplib, os
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication
        from datetime import datetime

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT p.*, c.email AS client_email, c.contact_person,
                   c.company_name AS client_company
            FROM proposals p
            LEFT JOIN clients c ON p.client_id = c.id
            WHERE p.id = %s
        """, (proposal_id,))
        proposal = cursor.fetchone()
        if not proposal:
            cursor.close(); conn.close()
            return None, "Proposal not found"

        now = now_ist()
        cursor.execute("""
            UPDATE proposals
            SET status='sent', sent_at=%s, sent_by=%s, note=%s,
                template_id=%s, template_name=%s
            WHERE id=%s
        """, (now, sent_by, note, template_id, template_name, proposal_id))
        conn.commit()

        recipient = proposal.get('email') or proposal.get('client_email')
        if recipient:
            try:
                company_name  = os.getenv('COMPANY_NAME', 'KairaFlow')
                company_email = os.getenv('COMPANY_EMAIL', 'info@kairaflow.com')
                smtp_host     = os.getenv('SMTP_HOST', 'smtp.gmail.com')
                smtp_port     = int(os.getenv('SMTP_PORT', '587'))
                smtp_user     = os.getenv('SMTP_USER', '')
                smtp_pass     = os.getenv('SMTP_PASS', '')

                client_name = proposal.get('lead_name') or proposal.get('contact_person', '')

                # Generate letterpad PDF
                pdf_buf = Proposal._build_proposal_pdf(
                    proposal, template_name, line_items, total_amount, note
                )

                # Simple plain email body
                html = f"""
                <div style="font-family:Inter,sans-serif;max-width:600px;margin:0 auto;background:#fff;padding:32px">
                  <p style="color:#374151">Dear <strong>{client_name}</strong>,</p>
                  <p style="color:#374151">
                    Thank you for your interest in <strong>{company_name}</strong>.<br>
                    Please find the attached proposal PDF for <strong>{template_name or 'your project'}</strong>.
                  </p>
                  {f'<p style="color:#92400e;background:#fffbeb;padding:12px;border-left:4px solid #F5C842;border-radius:4px">{note}</p>' if note else ''}
                  <p style="color:#6b7280;font-size:13px;margin-top:24px">
                    For any questions, reply to this email or reach us at {company_email}.
                  </p>
                  <p style="color:#374151">Warm regards,<br><strong>{company_name}</strong></p>
                </div>"""

                msg = MIMEMultipart('mixed')
                msg['Subject'] = f"Project Proposal — {template_name or company_name}"
                msg['From']    = f"{company_name} <{smtp_user or company_email}>"
                msg['To']      = recipient
                msg.attach(MIMEText(html, 'html'))

                # Attach the letterpad PDF
                pdf_bytes = pdf_buf.read()
                pdf_part  = MIMEApplication(pdf_bytes, _subtype='pdf')
                safe_name = (template_name or 'Proposal').replace(' ', '_')
                pdf_part.add_header('Content-Disposition', 'attachment',
                                    filename=f"{safe_name}_Proposal.pdf")
                msg.attach(pdf_part)

                if smtp_user and smtp_pass:
                    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.sendmail(smtp_user, recipient, msg.as_string())
            except Exception as e:
                print(f"Email send warning: {e}")

        cursor.execute("SELECT * FROM proposals WHERE id=%s", (proposal_id,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row, None

    @staticmethod
    def mark_viewed(proposal_id: int):
        from datetime import datetime
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE proposals SET status='viewed', viewed_at=%s
            WHERE id=%s AND status='sent'
        """, (now_ist(), proposal_id))
        conn.commit()
        cursor.close(); conn.close()


class Invoice:

    @staticmethod
    def _next_number():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM invoices")
        count = cursor.fetchone()[0]
        cursor.close(); conn.close()
        return f"INV-{today_ist().year}-{str(count + 1).zfill(4)}"

    @staticmethod
    def create(created_by: int, **kwargs):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        invoice_number = kwargs.get('invoice_number') or Invoice._next_number()
        json_fields = {'billed_to', 'billed_by', 'line_items'}
        fields = ['created_by', 'invoice_number']
        values = [created_by, invoice_number]
        allowed = {
            'proposal_id', 'client_id', 'invoice_date', 'due_date',
            'billed_to', 'billed_by', 'line_items', 'subtotal',
            'tax_percent', 'tax_amount', 'total_amount',
            'payment_terms', 'notes', 'status', 'email_body',
        }
        for k, v in kwargs.items():
            if k in allowed and v is not None and k != 'invoice_number':
                fields.append(k)
                values.append(json.dumps(v) if k in json_fields else v)
        placeholders = ', '.join(['%s'] * len(fields))
        cols = ', '.join(fields)
        cursor.execute(
            f"INSERT INTO invoices ({cols}) VALUES ({placeholders})", values
        )
        conn.commit()
        iid = cursor.lastrowid
        cursor.execute("""
            SELECT i.*, u.name AS created_by_name
            FROM invoices i
            JOIN users u ON i.created_by = u.id
            WHERE i.id = %s
        """, (iid,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row

    @staticmethod
    def update(invoice_id: int, **kwargs):
        conn = get_db_connection()
        cursor = conn.cursor()
        json_fields = {'billed_to', 'billed_by', 'line_items'}
        allowed = {
            'invoice_date', 'due_date', 'billed_to', 'billed_by', 'line_items',
            'subtotal', 'tax_percent', 'tax_amount', 'total_amount',
            'payment_terms', 'notes', 'status', 'email_body',
        }
        fields, values = [], []
        for k, v in kwargs.items():
            if k in allowed:
                fields.append(f"{k} = %s")
                values.append(json.dumps(v) if k in json_fields and v is not None else v)
        if not fields:
            cursor.close(); conn.close()
            return
        values.append(invoice_id)
        cursor.execute(f"UPDATE invoices SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()
        cursor.close(); conn.close()

    @staticmethod
    def get_by_id(invoice_id: int):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT i.*, u.name AS created_by_name
            FROM invoices i
            JOIN users u ON i.created_by = u.id
            WHERE i.id = %s
        """, (invoice_id,))
        row = _s(cursor.fetchone())
        cursor.close(); conn.close()
        return row

    @staticmethod
    def get_all(created_by: int = None, status: str = None, client_id: int = None):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT i.*, u.name AS created_by_name
            FROM invoices i
            JOIN users u ON i.created_by = u.id
            WHERE 1=1
        """
        params = []
        if created_by:
            query += " AND i.created_by = %s"; params.append(created_by)
        if status:
            query += " AND i.status = %s"; params.append(status)
        if client_id:
            query += " AND i.client_id = %s"; params.append(client_id)
        query += " ORDER BY i.created_at DESC"
        cursor.execute(query, params)
        rows = [_s(r) for r in cursor.fetchall()]
        cursor.close(); conn.close()
        return rows

    @staticmethod
    def delete(invoice_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM invoices WHERE id = %s", (invoice_id,))
        conn.commit()
        cursor.close(); conn.close()
