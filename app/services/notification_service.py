import os
import logging
from flask import render_template
from app.services.mail_service import send_async_email

logger = logging.getLogger(__name__)


def _get_base_url(custom_base_url: str = None) -> str:
    if custom_base_url and custom_base_url.strip():
        return custom_base_url.rstrip('/')
    env_url = os.getenv('APP_BASE_URL', '').strip()
    if env_url:
        return env_url.rstrip('/')
    try:
        from flask import request
        if request and request.host_url:
            return request.host_url.rstrip('/')
    except Exception:
        pass
    return "http://127.0.0.1:5000"


def _format_term_period(term_row: dict) -> str:
    if not term_row:
        return "Current Academic Term"
    ay = term_row.get('academic_year', '')
    sem = term_row.get('semester', '')
    p_start = term_row.get('period_start')
    p_end = term_row.get('period_end')
    
    parts = []
    if ay:
        parts.append(f"A.Y. {ay}")
    if sem:
        parts.append(f"({sem})")
    if p_start and p_end:
        try:
            parts.append(f"[{p_start.strftime('%b %Y')} - {p_end.strftime('%b %Y')}]")
        except Exception:
            pass
    return " ".join(parts) if parts else "Current Academic Term"


def _get_faculty_profile(cursor, emp_id: int):
    cursor.execute("""
        SELECT ep.first_name, ep.last_name, ep.academic_rank, ep.designation,
               ep.assigned_program, ep.specialization, ac.corporate_email
        FROM tbl_employee_profiles ep
        LEFT JOIN tbl_auth_credentials ac ON ep.emp_id = ac.emp_id
        WHERE ep.emp_id = %s
    """, (emp_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
            SELECT ep.first_name, ep.last_name, ep.academic_rank, ep.designation,
                   ep.assigned_program, ep.specialization, ac.corporate_email
            FROM tbl_auth_credentials ac
            LEFT JOIN tbl_employee_profiles ep ON ac.emp_id = ep.emp_id
            WHERE ac.emp_id = %s
        """, (emp_id,))
        row = cursor.fetchone()

    if not row:
        return {
            'emp_id': emp_id,
            'first_name': 'Faculty',
            'last_name': 'Member',
            'full_name': 'Faculty Member',
            'academic_rank': '',
            'designation': 'Regular Faculty',
            'assigned_program': 'CICT',
            'specialization': 'CICT',
            'department': 'CICT',
            'email': 'casptonetest@gmail.com'
        }

    first_name = row[0] or 'Faculty'
    last_name = row[1] or 'Member'
    full_name = f"{first_name} {last_name}".strip() if (row[0] or row[1]) else 'Faculty Member'
    return {
        'emp_id': emp_id,
        'first_name': first_name,
        'last_name': last_name,
        'full_name': full_name,
        'academic_rank': row[2] or '',
        'designation': row[3] or '',
        'assigned_program': row[4] or '',
        'specialization': row[5] or '',
        'department': row[5] or row[4] or 'CICT',
        'email': row[6] or 'casptonetest@gmail.com'
    }


def _get_term_info(cursor, term_id: int):
    cursor.execute("""
        SELECT academic_year, semester, period_start, period_end
        FROM tbl_academic_terms WHERE term_id = %s
    """, (term_id,))
    term_data = cursor.fetchone()
    if not term_data:
        return {'period_display': 'Current Academic Term'}
    d = {
        'academic_year': term_data[0],
        'semester': term_data[1],
        'period_start': term_data[2],
        'period_end': term_data[3]
    }
    d['period_display'] = _format_term_period(d)
    return d


def _get_dean_info(cursor):
    cursor.execute("""
        SELECT ep.first_name, ep.last_name, ac.corporate_email
        FROM tbl_system_access sa
        JOIN tbl_employee_profiles ep ON sa.emp_id = ep.emp_id
        LEFT JOIN tbl_auth_credentials ac ON ac.emp_id = ep.emp_id
        WHERE UPPER(sa.system_role) LIKE '%DEAN%'
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row and row[2]:
        return {
            'name': f"{row[0]} {row[1]}".strip() if row[0] else 'College Dean',
            'email': row[2]
        }
    cursor.execute("""
        SELECT ac.emp_id, ac.corporate_email
        FROM tbl_auth_credentials ac
        JOIN tbl_system_access sa ON ac.emp_id = sa.emp_id
        WHERE UPPER(sa.system_role) LIKE '%DEAN%'
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row and row[1]:
        return {'name': 'College Dean', 'email': row[1]}

    cursor.execute("""
        SELECT ep.first_name, ep.last_name, ac.corporate_email
        FROM tbl_auth_credentials ac
        LEFT JOIN tbl_employee_profiles ep ON ac.emp_id = ep.emp_id
        WHERE ac.corporate_email = 'deanacccount@gmail.com' 
           OR ac.corporate_email LIKE '%dean%'
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row and row[2]:
        return {
            'name': f"{row[0]} {row[1]}".strip() if (row[0] and row[1]) else 'College Dean',
            'email': row[2]
        }
    return {'name': 'College Dean', 'email': 'deanacccount@gmail.com'}


def _get_ret_chair_info(cursor):
    cursor.execute("""
        SELECT ep.first_name, ep.last_name, ac.corporate_email
        FROM tbl_system_access sa
        LEFT JOIN tbl_employee_profiles ep ON sa.emp_id = ep.emp_id
        LEFT JOIN tbl_auth_credentials ac ON ac.emp_id = sa.emp_id
        WHERE UPPER(sa.system_role) LIKE '%RET%'
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row and row[2]:
        return {
            'name': f"{row[0]} {row[1]}".strip() if (row[0] and row[1]) else 'RET Chair',
            'email': row[2]
        }
    cursor.execute("""
        SELECT ac.emp_id, ac.corporate_email
        FROM tbl_auth_credentials ac
        JOIN tbl_system_access sa ON ac.emp_id = sa.emp_id
        WHERE UPPER(sa.system_role) LIKE '%RET%'
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row and row[1]:
        return {'name': 'RET Chair', 'email': row[1]}

    cursor.execute("""
        SELECT ep.first_name, ep.last_name, ac.corporate_email
        FROM tbl_auth_credentials ac
        LEFT JOIN tbl_employee_profiles ep ON ac.emp_id = ep.emp_id
        WHERE ac.corporate_email = 'corazonlopez062041@gmail.com' 
           OR ac.corporate_email LIKE '%ret%'
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row and row[2]:
        return {
            'name': f"{row[0]} {row[1]}".strip() if (row[0] and row[1]) else 'RET Chair',
            'email': row[2]
        }
    return {'name': 'RET Chair', 'email': 'corazonlopez062041@gmail.com'}


def _get_program_chair_info(cursor, department: str = None):
    if department:
        cursor.execute("""
            SELECT ep.first_name, ep.last_name, ac.corporate_email
            FROM tbl_system_access sa
            LEFT JOIN tbl_employee_profiles ep ON sa.emp_id = ep.emp_id
            LEFT JOIN tbl_auth_credentials ac ON ac.emp_id = sa.emp_id
            WHERE (UPPER(sa.system_role) LIKE '%PROGRAM%' OR UPPER(sa.system_role) LIKE '%CHAIR%')
              AND UPPER(sa.system_role) NOT LIKE '%RET%'
              AND (ep.specialization = %s OR ep.assigned_program = %s)
            LIMIT 1
        """, (department, department))
        row = cursor.fetchone()
        if row and row[2]:
            return {
                'name': f"{row[0]} {row[1]}".strip() if (row[0] and row[1]) else 'Program Chair',
                'email': row[2]
            }
    cursor.execute("""
        SELECT ep.first_name, ep.last_name, ac.corporate_email
        FROM tbl_system_access sa
        LEFT JOIN tbl_employee_profiles ep ON sa.emp_id = ep.emp_id
        LEFT JOIN tbl_auth_credentials ac ON ac.emp_id = sa.emp_id
        WHERE (UPPER(sa.system_role) LIKE '%PROGRAM%' OR UPPER(sa.system_role) LIKE '%CHAIR%')
          AND UPPER(sa.system_role) NOT LIKE '%RET%'
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row and row[2]:
        return {
            'name': f"{row[0]} {row[1]}".strip() if (row[0] and row[1]) else 'Program Chair',
            'email': row[2]
        }
    cursor.execute("""
        SELECT ep.first_name, ep.last_name, ac.corporate_email
        FROM tbl_auth_credentials ac
        LEFT JOIN tbl_employee_profiles ep ON ac.emp_id = ep.emp_id
        WHERE ac.corporate_email = 'wstprogramchair@gmail.com' 
           OR ac.corporate_email LIKE '%chair%'
        LIMIT 1
    """)
    row = cursor.fetchone()
    if row and row[2]:
        return {
            'name': f"{row[0]} {row[1]}".strip() if (row[0] and row[1]) else 'Program Chair',
            'email': row[2]
        }
    return {'name': 'Program Chair', 'email': 'wstprogramchair@gmail.com'}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Target Phase: Faculty Submits Draft Targets (to RET or Program Chair)
# ─────────────────────────────────────────────────────────────────────────────

def send_target_submission_notification(conn, cursor, emp_id: int, term_id: int, base_url: str = None) -> tuple[bool, str]:
    """
    Notifies reviewer when a regular faculty member submits draft IPCR targets:
    - Step 1: RET Chair review (initial submission or rejected resubmission).
    - Step 2: Program Chair review (once RET Chair has approved).
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)

        # Check if RET Chair has already approved this IPCR
        cursor.execute("""
            SELECT overall_status FROM tbl_ipcr_ret_review
            WHERE emp_id = %s AND term_id = %s
        """, (emp_id, term_id))
        ret_row = cursor.fetchone()
        is_ret_approved = (ret_row and ret_row[0] == 'Approved')

        # If RET Chair has not yet approved, always notify RET Chair
        if not is_ret_approved:
            ret_info = _get_ret_chair_info(cursor)
            ret_email = ret_info.get('email') or 'corazonlopez062041@gmail.com'
            action_url = f"{resolved_base_url}/ret_chair"
            html_body = render_template('emails/target_submission_notice.html',
                reviewer_name=ret_info.get('name') or 'RET Chair',
                faculty_name=fac['full_name'],
                academic_rank=fac.get('academic_rank', ''),
                department=fac.get('department', 'CICT'),
                period_display=term['period_display'],
                review_stage="RET Research Target Verification (Step 1)",
                action_url=action_url
            )
            text_body = (
                f"Dear {ret_info.get('name') or 'RET Chair'},\n\n"
                f"Faculty member {fac['full_name']} ({fac.get('department', 'CICT')}) has submitted draft IPCR targets "
                f"for {term['period_display']} requiring RET research review.\n\n"
                f"Review targets at: {action_url}\n"
            )
            print(f"[TARGET SUBMISSION NOTIFICATION] Dispatching email to RET Chair ({ret_email}) for faculty {fac['full_name']} (emp_id={emp_id})...", flush=True)
            send_async_email(
                subject=f"[D-IPCR] Action Required: Review IPCR Research Targets - {fac['full_name']} ({term['period_display']})",
                recipients=[ret_email],
                html_body=html_body,
                text_body=text_body
            )
            logger.info(f"[TARGET SUBMISSION NOTIFICATION] Queued to RET Chair ({ret_email}) for emp_id={emp_id}")
            return True, "Notification sent to RET Chair."

        else:
            # Route to Program Chair
            chair_info = _get_program_chair_info(cursor, fac.get('department'))
            chair_email = chair_info.get('email') or 'wstprogramchair@gmail.com'
            action_url = f"{resolved_base_url}/prog_chair"
            html_body = render_template('emails/target_submission_notice.html',
                reviewer_name=chair_info.get('name') or 'Program Chair',
                faculty_name=fac['full_name'],
                academic_rank=fac.get('academic_rank', ''),
                department=fac.get('department', 'CICT'),
                period_display=term['period_display'],
                review_stage="Program Chair Target Verification",
                action_url=action_url
            )
            text_body = (
                f"Dear {chair_info.get('name') or 'Program Chair'},\n\n"
                f"Faculty member {fac['full_name']} ({fac.get('department', 'CICT')}) has submitted draft IPCR targets "
                f"for {term['period_display']} for your verification.\n\n"
                f"Review targets at: {action_url}\n"
            )
            print(f"[TARGET SUBMISSION NOTIFICATION] Dispatching email to Program Chair ({chair_email}) for faculty {fac['full_name']} (emp_id={emp_id})...", flush=True)
            send_async_email(
                subject=f"[D-IPCR] Action Required: Review IPCR Targets - {fac['full_name']} ({term['period_display']})",
                recipients=[chair_email],
                html_body=html_body,
                text_body=text_body
            )
            logger.info(f"[TARGET SUBMISSION NOTIFICATION] Queued to Program Chair ({chair_email}) for emp_id={emp_id}")
            return True, "Notification sent to Program Chair."

    except Exception as e:
        logger.error(f"Error in send_target_submission_notification: {e}")
        print(f"[TARGET SUBMISSION ERROR] {e}", flush=True)
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Target Phase: RET Chair Approves Research Targets
# ─────────────────────────────────────────────────────────────────────────────

def send_ret_approval_notifications(conn, cursor, emp_id: int, term_id: int, base_url: str = None) -> tuple[bool, str]:
    """
    Triggered when RET Chair approves research targets:
    1. Notifies Faculty that RET Chair has approved their research selections.
    2. Notifies Program Chair that RET review is complete and the IPCR is now ready for Chair review.
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        if not fac:
            return False, f"Faculty #{emp_id} not found."

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)

        # 1. Notify Faculty
        if fac['email']:
            fac_url = f"{resolved_base_url}/faculty"
            html_fac = render_template('emails/ret_approved_notice.html',
                recipient_name=fac['full_name'],
                faculty_name=fac['full_name'],
                department=fac['department'],
                period_display=term['period_display'],
                is_for_chair=False,
                action_url=fac_url
            )
            text_fac = (
                f"Dear {fac['full_name']},\n\n"
                f"Your research targets for {term['period_display']} have been approved by the RET Chair.\n"
                f"Your draft IPCR has advanced to the Program Chair for target review.\n\n"
                f"Dashboard: {fac_url}\n"
            )
            send_async_email(
                subject=f"[D-IPCR] Research Targets Approved by RET Chair - {term['period_display']}",
                recipients=[fac['email']],
                html_body=html_fac,
                text_body=text_fac
            )

        # 2. Notify Program Chair
        chair_info = _get_program_chair_info(cursor, fac['department'])
        if chair_info['email']:
            chair_url = f"{resolved_base_url}/prog_chair"
            html_chair = render_template('emails/ret_approved_notice.html',
                recipient_name=chair_info['name'],
                faculty_name=fac['full_name'],
                department=fac['department'],
                period_display=term['period_display'],
                is_for_chair=True,
                action_url=chair_url
            )
            text_chair = (
                f"Dear {chair_info['name']},\n\n"
                f"The RET Chair has approved research targets for {fac['full_name']} ({fac['department']}).\n"
                f"The draft IPCR is now ready for your Program Chair verification.\n\n"
                f"Review at: {chair_url}\n"
            )
            send_async_email(
                subject=f"[D-IPCR] Action Required: Ready for Program Chair Review - {fac['full_name']} ({term['period_display']})",
                recipients=[chair_info['email']],
                html_body=html_chair,
                text_body=text_chair
            )

        logger.info(f"[RET APPROVAL NOTIFICATIONS SENT] emp_id={emp_id}, term_id={term_id}")
        return True, "RET approval notifications sent to faculty and chair."

    except Exception as e:
        logger.error(f"Error in send_ret_approval_notifications: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Target Phase: Program Chair Approves Targets (Notice to Lock IPCR)
# ─────────────────────────────────────────────────────────────────────────────

def send_chair_approval_notification(conn, cursor, emp_id: int, term_id: int, base_url: str = None) -> tuple[bool, str]:
    """
    Triggered when Program Chair approves faculty targets:
    Notifies Faculty that their IPCR targets are approved and instructs them to LOCK IPCR.
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        if not fac:
            return False, f"Faculty #{emp_id} not found."

        if not fac['email']:
            return False, f"No email found for faculty #{emp_id}."

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)
        fac_url = f"{resolved_base_url}/faculty"

        html_body = render_template('emails/chair_approved_notice.html',
            faculty_name=fac['full_name'],
            academic_rank=fac['academic_rank'],
            department=fac['department'],
            period_display=term['period_display'],
            action_url=fac_url
        )
        text_body = (
            f"Dear {fac['full_name']},\n\n"
            f"Your IPCR targets for {term['period_display']} have been approved by the Program Chair.\n\n"
            f"NEXT ACTION REQUIRED:\n"
            f"Please log in and click 'Lock IPCR' to commit your approved targets and begin evidence gathering.\n\n"
            f"Dashboard: {fac_url}\n"
        )
        send_async_email(
            subject=f"[D-IPCR] IPCR Targets Approved by Program Chair - Please Lock IPCR ({term['period_display']})",
            recipients=[fac['email']],
            html_body=html_body,
            text_body=text_body
        )

        logger.info(f"[CHAIR APPROVAL NOTIFICATION SENT] emp_id={emp_id}, term_id={term_id}")
        return True, "Chair approval notification sent to faculty."

    except Exception as e:
        logger.error(f"Error in send_chair_approval_notification: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Target Phase: Return Notification (Program Chair or RET Chair)
# ─────────────────────────────────────────────────────────────────────────────

def send_return_notification(conn, cursor, reviewer_role: str, review_id: int, emp_id: int, term_id: int, overall_remarks: str = "", base_url: str = None) -> tuple[bool, str]:
    """
    Sends notification to faculty when draft targets are returned by either Chair or RET Chair.
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        if not fac or not fac['email']:
            return False, f"Faculty member #{emp_id} or email not found."

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)

        # Query item modifications and remarks
        modified_items = []
        if 'RET' in reviewer_role.upper():
            cursor.execute("""
                SELECT mi.indicator_description, ri.original_quantity, ri.reviewed_quantity, ri.item_remarks
                FROM tbl_ipcr_ret_review_items ri
                JOIN tbl_master_indicators mi ON ri.indicator_id = mi.indicator_id
                WHERE ri.review_id = %s
            """, (review_id,))
        else:
            cursor.execute("""
                SELECT mi.indicator_description, ri.original_quantity, ri.reviewed_quantity, ri.item_remarks
                FROM tbl_ipcr_chair_review_items ri
                JOIN tbl_master_indicators mi ON ri.indicator_id = mi.indicator_id
                WHERE ri.review_id = %s
            """, (review_id,))

        for row in cursor.fetchall():
            desc, orig_q, rev_q, remarks = row
            is_qty_changed = (orig_q != rev_q)
            has_remarks = bool(remarks and remarks.strip())
            if is_qty_changed or has_remarks:
                modified_items.append({
                    'indicator_description': desc,
                    'original_quantity': orig_q,
                    'reviewed_quantity': rev_q,
                    'is_qty_changed': is_qty_changed,
                    'item_remarks': remarks.strip() if remarks else None
                })

        action_url = f"{resolved_base_url}/faculty"
        html_body = render_template('emails/ipcr_returned.html',
            faculty_name=fac['full_name'],
            department=fac['department'],
            period_display=term['period_display'],
            reviewer_role=reviewer_role,
            overall_remarks=overall_remarks,
            modified_items=modified_items,
            action_url=action_url
        )

        text_items = ""
        if modified_items:
            text_items = "\nTarget Adjustments:\n" + "\n".join([
                f"- {item['indicator_description']}: Proposed {item['original_quantity']} -> Adjusted {item['reviewed_quantity']}" +
                (f" (Remark: {item['item_remarks']})" if item['item_remarks'] else "")
                for item in modified_items
            ])

        text_body = (
            f"Dear {fac['full_name']},\n\n"
            f"Your draft IPCR targets for {term['period_display']} were returned by the {reviewer_role}.\n"
            f"Overall Remarks: {overall_remarks or 'None'}\n"
            f"{text_items}\n\n"
            f"Please update your draft and resubmit at: {action_url}\n"
        )

        send_async_email(
            subject=f"[D-IPCR] Action Required: IPCR Targets Returned by {reviewer_role} - {term['period_display']}",
            recipients=[fac['email']],
            html_body=html_body,
            text_body=text_body
        )

        logger.info(f"[RETURN NOTIFICATION TRIGGERED] emp_id={emp_id}, term_id={term_id}, reviewer={reviewer_role}")
        return True, "Return notification dispatched successfully."

    except Exception as e:
        logger.error(f"Error triggering return notification: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Designated Faculty Flow: Target Submission & Dean Decision
# ─────────────────────────────────────────────────────────────────────────────

def send_designated_target_submission_notification(conn, cursor, emp_id: int, term_id: int, is_resubmission: bool = False, base_url: str = None) -> tuple[bool, str]:
    """
    Notifies the College Dean when a designated faculty member or Chair submits draft targets.
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        if not fac:
            return False, f"Designated faculty #{emp_id} not found."

        dean_info = _get_dean_info(cursor)
        if not dean_info['email']:
            return False, "No active Dean email found."

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)
        action_url = f"{resolved_base_url}/dean"

        cursor.execute("SELECT system_role FROM tbl_system_access WHERE emp_id = %s", (emp_id,))
        roles = [r[0].upper() for r in cursor.fetchall() if r[0]]
        desig = (fac.get('designation') or '').strip()

        if any('RET' in r for r in roles) or desig == 'RET Chair':
            sender_title = "RET Chair"
        elif any('PROGRAM' in r for r in roles) or desig == 'Program Chair':
            sender_title = "Program Chair"
        elif any('DEAN' in r for r in roles) or desig == 'Dean':
            sender_title = "Dean"
        elif desig:
            sender_title = desig
        else:
            sender_title = "Designated Faculty"

        suffix = " (Resubmission)" if is_resubmission else ""
        stage_name = f"Dean Review for {sender_title} Targets{suffix}"

        html_body = render_template('emails/target_submission_notice.html',
            reviewer_name=dean_info['name'],
            faculty_name=fac['full_name'],
            sender_title=sender_title,
            designation=sender_title,
            academic_rank=fac['academic_rank'] or desig,
            department=fac['department'],
            period_display=term['period_display'],
            review_stage=stage_name,
            action_url=action_url
        )
        text_body = (
            f"Dear {dean_info['name']},\n\n"
            f"{sender_title} {fac['full_name']} ({fac['department']}) "
            f"has submitted draft IPCR targets for {term['period_display']} for your review.\n\n"
            f"Review at: {action_url}\n"
        )
        send_async_email(
            subject=f"[D-IPCR] Action Required: {sender_title} IPCR Targets Submitted - {fac['full_name']} ({term['period_display']})",
            recipients=[dean_info['email']],
            html_body=html_body,
            text_body=text_body
        )
        logger.info(f"[DESIGNATED SUBMISSION NOTIFICATION] Sent to Dean for {sender_title} emp_id={emp_id}")
        return True, f"Target submission notification sent to Dean for {sender_title}."

    except Exception as e:
        logger.error(f"Error in send_designated_target_submission_notification: {e}")
        return False, str(e)


def send_designated_target_decision_notification(conn, cursor, emp_id: int, term_id: int, action: str, overall_remarks: str = "", base_url: str = None) -> tuple[bool, str]:
    """
    Notifies designated faculty member of Dean's review decision ('Approved' or 'Rejected').
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        if not fac or not fac['email']:
            return False, f"Designated faculty #{emp_id} or email not found."

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)
        action_url = f"{resolved_base_url}/designated"

        html_body = render_template('emails/designated_target_decision.html',
            faculty_name=fac['full_name'],
            designation=fac['designation'] or fac['department'],
            period_display=term['period_display'],
            action=action,
            overall_remarks=overall_remarks,
            action_url=action_url
        )
        text_body = (
            f"Dear {fac['full_name']},\n\n"
            f"The College Dean has {action.lower()} your draft IPCR targets for {term['period_display']}.\n"
            f"Remarks: {overall_remarks or 'None'}\n\n"
            f"Access your dashboard at: {action_url}\n"
        )
        send_async_email(
            subject=f"[D-IPCR] Dean's Decision: IPCR Targets {action} - {term['period_display']}",
            recipients=[fac['email']],
            html_body=html_body,
            text_body=text_body
        )
        logger.info(f"[DESIGNATED DECISION NOTIFICATION] Sent to {fac['email']} for emp_id={emp_id}, action={action}")
        return True, "Designated decision notification sent."

    except Exception as e:
        logger.error(f"Error in send_designated_target_decision_notification: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Accomplishment & Evidence Phase Notifications
# ─────────────────────────────────────────────────────────────────────────────

def send_evidence_submission_notification(conn, cursor, emp_id: int, term_id: int, base_url: str = None) -> tuple[bool, str]:
    """
    Triggered when faculty submits evidence files:
    - If Department Chair / Dean (self-IPCR): Notifies College Dean directly.
    - If Designated Faculty: Notifies Program Chair for evidence verification.
    - If Regular Faculty: Notifies Program Chair, who now approves all evidence
      (Instruction, Support, Research, Extension) — RET Chair no longer verifies it.
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        if not fac:
            return False, f"Faculty #{emp_id} not found."

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)

        cursor.execute("SELECT system_role FROM tbl_system_access WHERE emp_id = %s", (emp_id,))
        roles = [r[0].upper() for r in cursor.fetchall() if r[0]]
        desig = (fac.get('designation') or '').strip()

        # Every Designated Faculty member -- plain or a Program Chair/RET Chair/Dean's own
        # IPCR -- has no Program Chair review before the Dean, so all of them notify the
        # Dean directly on submission; only Regular Faculty notifies Program Chair/RET Chair.
        is_chair_or_dean = (
            any(r in ('PROGRAM_CHAIR', 'RET_CHAIR', 'DEAN') for r in roles)
            or desig in ('Program Chair', 'RET Chair', 'Dean')
            or any('DESIGNATED' in r for r in roles)
            or desig == 'Designated Faculty'
            or (desig and desig != 'Regular Faculty')
        )

        if any('RET' in r for r in roles) or desig == 'RET Chair':
            sender_title = "RET Chair"
        elif any('PROGRAM' in r for r in roles) or desig == 'Program Chair':
            sender_title = "Program Chair"
        elif any('DEAN' in r for r in roles) or desig == 'Dean':
            sender_title = "Dean"
        elif desig:
            sender_title = desig
        else:
            sender_title = "Faculty Member"

        if is_chair_or_dean:
            # 1. Chairs/Dean have no supervisor in department -> Notify Dean directly
            dean_info = _get_dean_info(cursor)
            if dean_info['email']:
                dean_url = f"{resolved_base_url}/dean"
                html_dean = render_template('emails/evidence_submission_notice.html',
                    reviewer_name=dean_info['name'],
                    faculty_name=fac['full_name'],
                    sender_title=sender_title,
                    designation=sender_title,
                    academic_rank=fac['academic_rank'] or desig,
                    department=fac['department'],
                    period_display=term['period_display'],
                    action_url=dean_url
                )
                text_dean = (
                    f"Dear {dean_info['name']},\n\n"
                    f"{sender_title} {fac['full_name']} ({fac['department']}) "
                    f"has submitted accomplishment evidence for {term['period_display']} for verification.\n\n"
                    f"Verify at: {dean_url}\n"
                )
                send_async_email(
                    subject=f"[D-IPCR] Evidence Submitted for Verification - {sender_title} {fac['full_name']} ({term['period_display']})",
                    recipients=[dean_info['email']],
                    html_body=html_dean,
                    text_body=text_dean
                )
                logger.info(f"[EVIDENCE SUBMISSION NOTIFICATION] Sent to Dean for {sender_title} emp_id={emp_id}")
            return True, f"Evidence submission notification sent to College Dean for {sender_title}."

        else:
            # 2. Regular Faculty: Notify Program Chair only — they now approve all evidence.
            chair_info = _get_program_chair_info(cursor, fac['department'])
            if chair_info['email']:
                chair_url = f"{resolved_base_url}/prog_chair"
                html_chair = render_template('emails/evidence_submission_notice.html',
                    reviewer_name=chair_info['name'],
                    faculty_name=fac['full_name'],
                    sender_title="Faculty Member",
                    designation=desig or "Regular Faculty",
                    academic_rank=fac['academic_rank'],
                    department=fac['department'],
                    period_display=term['period_display'],
                    action_url=chair_url
                )
                text_chair = (
                    f"Dear {chair_info['name']},\n\n"
                    f"Faculty member {fac['full_name']} ({fac['department']}) has submitted accomplishment evidence "
                    f"for {term['period_display']} for verification.\n\n"
                    f"Verify at: {chair_url}\n"
                )
                send_async_email(
                    subject=f"[D-IPCR] Evidence Submitted for Verification - {fac['full_name']} ({term['period_display']})",
                    recipients=[chair_info['email']],
                    html_body=html_chair,
                    text_body=text_chair
                )

            logger.info(f"[EVIDENCE SUBMISSION NOTIFICATION SENT] emp_id={emp_id}, term_id={term_id}")
            return True, "Evidence submission notification sent to Program Chair."

    except Exception as e:
        logger.error(f"Error in send_evidence_submission_notification: {e}")
        return False, str(e)


def send_evidence_package_to_dean_notification(conn, cursor, emp_id: int, term_id: int, base_url: str = None) -> tuple[bool, str]:
    """
    Triggered when Program Chair endorses and submits faculty evidence package to the Dean:
    1. Notifies College Dean (ready for final Tier 2 approval).
    2. Notifies Regular Faculty Member (notified that their package is submitted to the Dean for final approval).
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        if not fac:
            return False, f"Faculty #{emp_id} not found."

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)

        chair_info = _get_program_chair_info(cursor, fac['department'])
        chair_name = chair_info['name']

        # 1. Notify Dean
        dean_info = _get_dean_info(cursor)
        if dean_info['email']:
            dean_url = f"{resolved_base_url}/dean"
            html_dean = render_template('emails/evidence_package_to_dean.html',
                recipient_name=dean_info['name'],
                faculty_name=fac['full_name'],
                department=fac['department'],
                chair_name=chair_name,
                period_display=term['period_display'],
                is_for_dean=True,
                action_url=dean_url
            )
            text_dean = (
                f"Dear {dean_info['name']},\n\n"
                f"Program Chair {chair_name} has verified all accomplishment evidence for {fac['full_name']} "
                f"({fac['department']}) for {term['period_display']} and submitted the package for your final Tier 2 approval.\n\n"
                f"Review at: {dean_url}\n"
            )
            send_async_email(
                subject=f"[D-IPCR] Action Required: Evidence Package Submitted for Final Approval - {fac['full_name']} ({term['period_display']})",
                recipients=[dean_info['email']],
                html_body=html_dean,
                text_body=text_dean
            )

        # 2. Notify Regular Faculty Member (package is at final approval stage)
        if fac['email']:
            fac_url = f"{resolved_base_url}/faculty"
            html_fac = render_template('emails/evidence_package_to_dean.html',
                recipient_name=fac['full_name'],
                faculty_name=fac['full_name'],
                department=fac['department'],
                chair_name=chair_name,
                period_display=term['period_display'],
                is_for_dean=False,
                action_url=fac_url
            )
            text_fac = (
                f"Dear {fac['full_name']},\n\n"
                f"Your verified accomplishment evidence package for {term['period_display']} has been endorsed "
                f"by Program Chair {chair_name} and submitted to the College Dean for final Tier 2 approval.\n\n"
                f"View status at: {fac_url}\n"
            )
            send_async_email(
                subject=f"[D-IPCR] Update: Evidence Package Submitted to Dean for Final Approval - {term['period_display']}",
                recipients=[fac['email']],
                html_body=html_fac,
                text_body=text_fac
            )

        logger.info(f"[EVIDENCE PACKAGE TO DEAN NOTIFICATION SENT] emp_id={emp_id}, term_id={term_id}")
        return True, "Package submission notifications sent to Dean and Faculty."

    except Exception as e:
        logger.error(f"Error in send_evidence_package_to_dean_notification: {e}")
        return False, str(e)


def check_and_trigger_evidence_approved_notification(conn, cursor, evidence_id: int, reviewer_role: str, base_url: str = None) -> tuple[bool, str]:
    """
    Called after an evidence item is approved.
    - If reviewer is RET Chair: Checks if ALL Research & Extension evidence items submitted by the faculty member are Approved.
    - If reviewer is Program Chair: Checks if ALL Strategic Priority & Support evidence items are Approved.
    - If reviewer is College Dean: Checks if ALL designated faculty evidence items are Approved.
    
    Notification behavior:
    1. If only ONE chair has finished approving (the other chair still has unapproved/pending evidence):
       -> Sends single chair approval notification (chair_evidence_approved.html) stating that this chair's review
          is complete and the other chair's review is currently in progress.
    2. If BOTH chairs have finished approving (all submitted evidence files across all categories are approved):
       -> Sends all evidences approved notification (all_evidences_approved.html) stating that all evidence files
          across all categories are approved and compiled for final endorsement.
    """
    try:
        # Get target and faculty info from evidence_id
        cursor.execute("""
            SELECT ct.emp_id, mi.term_id
            FROM tbl_evidence_repo er
            JOIN tbl_committed_targets ct ON er.target_id = ct.target_id
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE er.evidence_id = %s
        """, (evidence_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Evidence target not found."
        emp_id, term_id = row

        # 1. Program Chair counts
        cursor.execute("""
            SELECT 
                COUNT(er.evidence_id) as total_evidences,
                SUM(CASE WHEN er.verification_status <> 'Approved' THEN 1 ELSE 0 END) as non_approved_count
            FROM tbl_evidence_repo er
            JOIN tbl_committed_targets ct ON er.target_id = ct.target_id
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
              AND (tc.review_lane = 'CHAIR' OR (tc.slug NOT IN ('research', 'extension') AND tc.category_name NOT LIKE '%%Research%%' AND tc.category_name NOT LIKE '%%Extension%%'))
        """, (emp_id, term_id))
        chair_counts = cursor.fetchone() or (0, 0)
        total_chair = chair_counts[0] or 0
        non_approved_chair = chair_counts[1] or 0

        # 2. RET Chair counts
        cursor.execute("""
            SELECT 
                COUNT(er.evidence_id) as total_evidences,
                SUM(CASE WHEN er.verification_status <> 'Approved' THEN 1 ELSE 0 END) as non_approved_count
            FROM tbl_evidence_repo er
            JOIN tbl_committed_targets ct ON er.target_id = ct.target_id
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
              AND (tc.review_lane = 'RET' OR tc.slug IN ('research', 'extension') OR tc.category_name LIKE '%%Research%%' OR tc.category_name LIKE '%%Extension%%')
        """, (emp_id, term_id))
        ret_counts = cursor.fetchone() or (0, 0)
        total_ret = ret_counts[0] or 0
        non_approved_ret = ret_counts[1] or 0

        # 3. Overall counts across all categories
        cursor.execute("""
            SELECT 
                COUNT(er.evidence_id) as total_evidences,
                SUM(CASE WHEN er.verification_status <> 'Approved' THEN 1 ELSE 0 END) as non_approved_count
            FROM tbl_evidence_repo er
            JOIN tbl_committed_targets ct ON er.target_id = ct.target_id
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
        """, (emp_id, term_id))
        all_counts = cursor.fetchone() or (0, 0)
        total_all = all_counts[0] or 0
        non_approved_all = all_counts[1] or 0

        logger.info(f"[EVIDENCE VERIFICATION CHECK] reviewer={reviewer_role}, emp_id={emp_id}, term_id={term_id}, chair=(total:{total_chair}, non_app:{non_approved_chair}), ret=(total:{total_ret}, non_app:{non_approved_ret}), all=(total:{total_all}, non_app:{non_approved_all})")

        # Check if the CURRENT reviewer's lane is completely approved
        if reviewer_role == 'RET Chair':
            if total_ret == 0 or non_approved_ret > 0:
                return False, "Not all Research & Extension evidences are approved yet."
        elif reviewer_role == 'Program Chair':
            if total_chair == 0 or non_approved_chair > 0:
                return False, "Not all Strategic Priorities & Support evidences are approved yet."
        else: # College Dean (Designated Faculty)
            if total_all == 0 or non_approved_all > 0:
                return False, "Not all evidences are approved yet."

        fac = _get_faculty_profile(cursor, emp_id)
        if not fac or not fac['email']:
            return False, "Faculty email not found."

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)
        action_url = f"{resolved_base_url}/faculty" if (fac.get('designation') == 'Regular Faculty' or not fac.get('designation')) else f"{resolved_base_url}/designated"

        # Check if ALL evidences overall across both chairs / all categories are approved
        all_completed = (total_all > 0 and non_approved_all == 0)

        if all_completed:
            # Check if all-evidences notification was already sent
            cursor.execute("""
                SELECT 1 FROM tbl_ipcr_approval_notifications
                WHERE emp_id = %s AND term_id = %s AND event_type = 'EVIDENCE_APPROVED_ALL' AND status = 'SENT'
                LIMIT 1
            """, (emp_id, term_id))
            if cursor.fetchone():
                return False, "All evidences approved notification was already sent."

            reviewer_summary = 'Program Chair & RET Chair' if (total_chair > 0 and total_ret > 0) else reviewer_role
            html_body = render_template('emails/all_evidences_approved.html',
                faculty_name=fac['full_name'],
                department=fac['department'],
                reviewer_role=reviewer_summary,
                scope_desc="All Accomplishment Evidences",
                period_display=term['period_display'],
                action_url=action_url
            )
            text_body = (
                f"Dear {fac['full_name']},\n\n"
                f"Good news! All of your submitted accomplishment evidence files for {term['period_display']} have been "
                f"reviewed and approved by the {reviewer_summary}.\n\n"
                f"Your verified accomplishments are now compiled for final package endorsement and rating computation.\n\n"
                f"View dashboard at: {action_url}\n"
            )
            send_async_email(
                subject=f"[D-IPCR] All Accomplishment Evidences Approved ({reviewer_summary}) - {term['period_display']}",
                recipients=[fac['email']],
                html_body=html_body,
                text_body=text_body
            )
            try:
                cursor.execute("""
                    INSERT INTO tbl_ipcr_approval_notifications 
                    (emp_id, term_id, tier, event_type, recipient_emails, status)
                    VALUES (%s, %s, 'TIER1_EVIDENCE', 'EVIDENCE_APPROVED_ALL', %s, 'SENT')
                """, (emp_id, term_id, fac['email']))
                if conn:
                    conn.commit()
            except Exception as rec_err:
                logger.warning(f"Could not record ALL evidence notification: {rec_err}")

            logger.info(f"[ALL EVIDENCES APPROVED NOTIFICATION SENT] emp_id={emp_id}, term_id={term_id}")
            return True, "All evidences approved notification sent to faculty."

        else:
            # Only the current chair has finished; the other chair is still pending!
            if reviewer_role == 'Program Chair':
                event_type = 'EVIDENCE_APPROVED_CHAIR'
                scope_desc = "Strategic Priorities & Support"
                pending_reviewer = "RET Chair"
                pending_scope = "Research & Extension"
            elif reviewer_role == 'RET Chair':
                event_type = 'EVIDENCE_APPROVED_RET'
                scope_desc = "Research & Extension"
                pending_reviewer = "Program Chair"
                pending_scope = "Strategic Priorities & Support"
            else:
                event_type = 'EVIDENCE_APPROVED_DEAN'
                scope_desc = "Accomplishment"
                pending_reviewer = None
                pending_scope = None

            # Check if this chair's approval notice was already sent
            cursor.execute("""
                SELECT 1 FROM tbl_ipcr_approval_notifications
                WHERE emp_id = %s AND term_id = %s AND event_type = %s AND status = 'SENT'
                LIMIT 1
            """, (emp_id, term_id, event_type))
            if cursor.fetchone():
                return False, f"{reviewer_role} evidence approval notification was already sent."

            html_body = render_template('emails/chair_evidence_approved.html',
                faculty_name=fac['full_name'],
                department=fac['department'],
                reviewer_role=reviewer_role,
                scope_desc=scope_desc,
                pending_reviewer=pending_reviewer,
                pending_scope=pending_scope,
                period_display=term['period_display'],
                action_url=action_url
            )
            text_body = (
                f"Dear {fac['full_name']},\n\n"
                f"Good news! Your submitted {scope_desc} evidence files for {term['period_display']} have been "
                f"reviewed and approved by the {reviewer_role}.\n\n"
                f"Evidence verification for {pending_scope} by the {pending_reviewer} is currently in progress.\n\n"
                f"View dashboard at: {action_url}\n"
            )
            send_async_email(
                subject=f"[D-IPCR] {scope_desc} Evidences Approved by {reviewer_role} - {term['period_display']}",
                recipients=[fac['email']],
                html_body=html_body,
                text_body=text_body
            )
            try:
                cursor.execute("""
                    INSERT INTO tbl_ipcr_approval_notifications 
                    (emp_id, term_id, tier, event_type, recipient_emails, status)
                    VALUES (%s, %s, 'TIER1_EVIDENCE', %s, %s, 'SENT')
                """, (emp_id, term_id, event_type, fac['email']))
                if conn:
                    conn.commit()
            except Exception as rec_err:
                logger.warning(f"Could not record {reviewer_role} evidence notification: {rec_err}")

            logger.info(f"[{reviewer_role.upper()} EVIDENCE APPROVAL NOTIFICATION SENT] emp_id={emp_id}, term_id={term_id}")
            return True, f"{reviewer_role} evidence approved notification sent to faculty."

    except Exception as e:
        logger.error(f"Error in check_and_trigger_evidence_approved_notification: {e}")
        return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Tier 2 Final Approval (Dean Grants Final Approval)
# ─────────────────────────────────────────────────────────────────────────────

def check_and_trigger_tier2_notification(conn, cursor, emp_id: int, term_id: int, base_url: str = None) -> tuple[bool, str]:
    """
    Checks if the Dean has granted final approval on the faculty member's IPCR.
    If so, sends Tier 2 (Final) notification asynchronously ONLY to the Faculty Member (owner of the IPCR).
    """
    try:
        fac = _get_faculty_profile(cursor, emp_id)
        if not fac:
            return False, f"Faculty member #{emp_id} not found."

        # Fetch Scores if available, or compute on the fly
        cursor.execute("""
            SELECT final_score, adjectival_rating
            FROM tbl_final_scores
            WHERE emp_id = %s AND term_id = %s
        """, (emp_id, term_id))
        score_row = cursor.fetchone()
        if score_row and score_row[0] is not None:
            final_score = f"{score_row[0]:.4f}"
            adjectival_rating = score_row[1]
        else:
            try:
                from app.models.scoring import save_final_score, compute_ipcr_score
                save_final_score(conn, cursor, emp_id, term_id)
                score_calc = compute_ipcr_score(cursor, emp_id, term_id)
                final_score = f"{score_calc['final_weighted_rating']:.4f}" if score_calc.get('final_weighted_rating') is not None else None
                adjectival_rating = score_calc.get('adjectival_rating')
            except Exception as score_err:
                logger.warning(f"Could not compute final score for emp_id={emp_id}: {score_err}")
                final_score = None
                adjectival_rating = None

        term = _get_term_info(cursor, term_id)
        resolved_base_url = _get_base_url(base_url)
        action_url = f"{resolved_base_url}/faculty/print_ipcr" if (fac.get('designation') == 'Regular Faculty' or not fac.get('designation')) else f"{resolved_base_url}/designated/print_ipcr"

        # Send strictly to Faculty Member (IPCR Owner)
        if fac['email']:
            html_fac = render_template('emails/tier2_final.html',
                recipient_name=fac['full_name'],
                faculty_name=fac['full_name'],
                academic_rank=fac['academic_rank'],
                department=fac['department'],
                period_display=term['period_display'],
                final_score=final_score,
                adjectival_rating=adjectival_rating,
                action_url=action_url
            )
            text_fac = (
                f"Dear {fac['full_name']},\n\n"
                f"Your IPCR for {term['period_display']} has been approved by the College Dean and is ready for print.\n"
                f"Final Score: {final_score or 'N/A'} ({adjectival_rating or 'N/A'})\n\n"
                f"View and print your finalized IPCR at: {action_url}\n"
            )
            send_async_email(
                subject=f"[D-IPCR] IPCR is approved by Dean and is ready for print - {fac['full_name']} ({term['period_display']})",
                recipients=[fac['email']],
                html_body=html_fac,
                text_body=text_fac
            )
            print(f"[TIER 2 NOTIFICATION] Dispatched final approval email to IPCR owner ({fac['email']})", flush=True)

        logger.info(f"[TIER 2 NOTIFICATION TRIGGERED] emp_id={emp_id}, term_id={term_id}")
        return True, "Tier 2 notification dispatched successfully to Faculty Member."

    except Exception as e:
        logger.error(f"Error triggering Tier 2 notification: {e}")
        return False, str(e)


# Alias for backward compatibility
check_and_trigger_tier1_notification = check_and_trigger_evidence_approved_notification
