"""
Assembles a faculty member's committed IPCR into the shape of the printed form.

The printed IPCR is not simply a list of targets — it is organised the way the paper form
is: numbered categories carrying their weight, each broken into lettered sub-sections by
target type, then a summary box and four signature blocks. Which categories appear, what
they are worth, and even the wording of the opening sentence all differ between a Regular
Faculty form and a Designated Faculty one.

This module produces that structure; the template only lays it out.
"""

import re

from app.models.criteria import (get_ipcr_categories, get_type_to_category, get_category_id,
                                 get_applicable_weights, resolve_designation_type,
                                 display_designation, DESIGNATION_REGULAR, SLUG_ADMINISTRATIVE, SLUG_SUPPORT,
                                 SLUG_INSTRUCTION)
from app.models.institution import get_institution_settings, resolve_signatories
from app.models.scoring import compute_ipcr_score

ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII']
LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

# The status a target reaches once the Dean has approved the whole package.
STATUS_DEAN_APPROVED = 'Dean Approved'


def format_rating_period(period_start, period_end):
    """
    The period phrase on the IPCR header, e.g. 'JANUARY to JUNE 2026'.

    Returns None when the term has no period set, so the form renders the blank the paper
    version carries rather than inventing dates.
    """
    if not period_start or not period_end:
        return None
    start_month = period_start.strftime('%B').upper()
    end_month = period_end.strftime('%B').upper()
    if period_start.year == period_end.year:
        return f"{start_month} to {end_month} {period_end.year}"
    return f"{start_month} {period_start.year} to {end_month} {period_end.year}"


def build_commitment_sentence(full_name, designation, specialization, college, period):
    """
    The opening paragraph, which names the ratee's role differently per designation —
    a Program Chair commits "of the BSDS program", a regular faculty simply as a member.
    """
    title = (designation or '').strip()
    if not title or title == DESIGNATION_REGULAR:
        role = f"faculty member of the {college}"
    elif title == 'Program Chair':
        program = (specialization or '').replace(' Program', '').strip()
        role = (f"Program Chairperson of the {program} program of the {college}"
                if program else f"Program Chairperson of the {college}")
    else:
        role = f"{title} of the {college}"

    period_text = period or "__________"
    return (f"I, {full_name}, {role}, commit to deliver and agree to be rated in the targets "
            f"in accordance with the attainment of the following indicated measures for the "
            f"period {period_text}.")


_LEADING_LETTER = re.compile(r'^\s*[A-H]\.\s*')


def _strip_leading_letter(name):
    """
    Target type names are stored with the letter the DPCR gives them ('A. Research').
    The printed form numbers its own sub-sections, so the stored prefix would double up
    as 'A. A. Research'.
    """
    return _LEADING_LETTER.sub('', name or '').strip()


def _target_type_meta(cursor):
    """{category_id: (display_name, display_order)} for every target type."""
    cursor.execute("SELECT category_id, category_name, display_order FROM tbl_target_categories")
    return {row[0]: (_strip_leading_letter(row[1]), row[2] or 0) for row in cursor.fetchall()}


def build_ipcr_sections(cursor, targets, designation_type, term_id, academic_rank=None,
                        job_title=None):
    """
    Group committed targets into the printed IPCR's numbered category -> lettered
    target-type sections, in the order the paper form numbers them (Strategic
    Priorities -> Core Functions -> Support Functions). Shared by the printed IPCR
    (build_ipcr_form, below) and the Evidence Gathering checklist, which mirrors the
    same layout.

    Targets whose type isn't mapped to any weighted IPCR category (e.g. an ad-hoc
    Custom item) are dropped, same as the scoring roll-up drops them from the
    average -- there is nowhere for them to weigh in. Callers that must keep every
    target visible regardless of scoring (the Evidence Gathering checklist) should use
    build_evidence_checklist_sections instead.

    job_title: the employee's raw designation ('Dean', 'Program Chair', ...), not the
    designation_type weight table. Only consulted for one special case -- see below.
    """
    categories = get_ipcr_categories(cursor, designation_type)
    weights = get_applicable_weights(cursor, term_id, designation_type, academic_rank)
    type_to_category = get_type_to_category(cursor, designation_type)
    type_meta = _target_type_meta(cursor)

    admin_type_id = get_category_id(cursor, SLUG_ADMINISTRATIVE)
    admin_category_id = type_to_category.get(admin_type_id) if admin_type_id else None
    admin_type_name = type_meta.get(admin_type_id, ('Administrative Functions', 0))[0]

    # The Dean's own real filled-out IPCR puts their college-wide Support-Functions oversight
    # (professional meetings, faculty advisers, client satisfaction surveys, etc.) under Core
    # Functions, alongside Instruction -- not under Strategic Priorities/Support Functions like
    # every other designated faculty member's oversight. Resolved off the same
    # type_to_category mapping used everywhere else (never a hardcoded category id), and scoped
    # strictly to the Dean: Program Chair/RET Chair oversight of the same slug is untested
    # against a real Chair IPCR and TEST_SCRIPT.md currently asserts the opposite for them.
    support_type_id = get_category_id(cursor, SLUG_SUPPORT)
    instruction_type_id = get_category_id(cursor, SLUG_INSTRUCTION)
    dean_core_category_id = type_to_category.get(instruction_type_id) if instruction_type_id else None

    # Group targets into category -> target type, matching how they are scored: an
    # administrative row belongs to the admin category whatever its own type says, and
    # prints as a single "Administrative Function" subsection — on the real DPCR, a
    # designated faculty's Strategic Priorities/Support items are their administrative
    # functions as a University-designated faculty member, not split by the target's own
    # type (Instruction/Support/etc.), which only matters for their Core Functions work.
    grouped = {}
    for t in targets:
        if (job_title == 'Dean' and t.get('is_admin_function')
                and t.get('category_id') == support_type_id and dean_core_category_id):
            cat_id = dean_core_category_id
            type_id = t.get('category_id')
            meta = type_meta.get(type_id)
            type_label = meta[0] if meta else _strip_leading_letter(t.get('category_name')) or 'Support Functions'
        elif t.get('is_admin_function') and admin_category_id:
            cat_id = admin_category_id
            type_id, type_label = admin_type_id, admin_type_name
        else:
            cat_id = type_to_category.get(t.get('category_id'))
            type_id = t.get('category_id')
            meta = type_meta.get(type_id)
            type_label = (meta[0] if meta
                          else _strip_leading_letter(t.get('category_name')) or 'Other')
        if not cat_id:
            continue
        order = type_meta.get(type_id, ('', 0))[1]
        grouped.setdefault(cat_id, {}).setdefault((order, type_id, type_label), []).append(t)

    # Sections in the order the paper form numbers them.
    sections = []
    for idx, cat in enumerate(categories):
        cat_id = cat['ipcr_category_id']
        by_type = grouped.get(cat_id, {})
        subsections = []
        # Sub-sections follow the target types' configured order, so Research precedes
        # Extension the way the DPCR and the paper IPCR list them.
        for sub_idx, ((_, _, type_label), rows) in enumerate(
                sorted(by_type.items(), key=lambda kv: (kv[0][0], kv[0][2]))):
            subsections.append({
                'letter': LETTERS[sub_idx] if sub_idx < len(LETTERS) else '',
                'label': type_label,
                'targets': rows,
            })
        sections.append({
            'numeral': ROMAN[idx] if idx < len(ROMAN) else str(idx + 1),
            'name': cat['category_name'],
            'weight_pct': weights.get(cat_id),
            'subsections': subsections,
            'target_count': sum(len(sub['targets']) for sub in subsections),
        })
    return sections


def build_evidence_checklist_sections(cursor, targets, designation_type, term_id,
                                      academic_rank=None, job_title=None):
    """
    Same category -> target-type grouping as build_ipcr_sections, but for the Evidence
    Gathering checklist rather than the printed form: every committed target still owes
    an Add/View Evidence action regardless of whether it scores, so a target dropped by
    build_ipcr_sections (nothing maps its type to a weighted category) is appended here
    under a catch-all "Other" section instead of silently losing its evidence button.
    """
    sections = build_ipcr_sections(cursor, targets, designation_type, term_id, academic_rank,
                                   job_title=job_title)
    covered_ids = {t['target_id'] for sec in sections for sub in sec['subsections'] for t in sub['targets']}
    leftover = [t for t in targets if t.get('target_id') not in covered_ids]
    if leftover:
        sections.append({
            'numeral': '', 'name': 'Other', 'weight_pct': None,
            'subsections': [{'letter': '', 'label': 'Other', 'targets': leftover}],
            'target_count': len(leftover),
        })
    return sections


def build_ipcr_form(cursor, emp_id, term_id, force_final=False):
    """
    Everything the printed IPCR needs for one employee and term.

    Returns None when the employee has no committed targets — there is nothing to print
    before an IPCR is locked.

    force_final: skips the "all targets are Dean Approved" gate on is_final. Used by the
    Dean's own Final Verification review, where the package has already reached the Dean
    (status 'Submitted to Dean' or later) and the scores computed below are exactly what the
    Dean is being asked to approve -- withholding them until after approval would show the
    reviewer the wrong form. Faculty-facing print views must NOT pass this: for them,
    "Final Evaluation" genuinely means the Dean has already approved.
    """
    cursor.execute("""
        SELECT first_name, last_name, academic_rank, designation, specialization, college,
               designation_title
        FROM tbl_employee_profiles WHERE emp_id = %s
    """, (emp_id,))
    profile = cursor.fetchone()
    if not profile:
        return None
    (first_name, last_name, academic_rank, designation, specialization, college_code,
     designation_title) = profile

    cursor.execute("""
        SELECT academic_year, semester, period_start, period_end
        FROM tbl_academic_terms WHERE term_id = %s
    """, (term_id,))
    term = cursor.fetchone()
    if not term:
        return None
    academic_year, semester, period_start, period_end = term

    settings = get_institution_settings(cursor)
    college = settings.get('college_full_name') or college_code or ''
    designation_type = resolve_designation_type(designation) or DESIGNATION_REGULAR

    # The scoring roll-up is the single source of the summary numbers, so the printed form
    # can never disagree with what the dashboard showed.
    score = compute_ipcr_score(cursor, emp_id, term_id)

    from app.models.faculty import get_faculty_committed_targets
    targets = get_faculty_committed_targets(cursor, emp_id, term_id)

    sections = build_ipcr_sections(cursor, targets, designation_type, term_id, academic_rank,
                                   job_title=designation)

    full_name = f"{first_name} {last_name}".strip().upper()
    period = format_rating_period(period_start, period_end)

    # Only a Dean-approved IPCR is final; anything earlier prints as a locked commitment --
    # except for the Dean's own review of a package already submitted for final verification,
    # where the ratings being reviewed are exactly this term's final scores.
    is_final = bool(targets) and (force_final or all(
        (t.get('status') or '') == STATUS_DEAN_APPROVED for t in targets))
    form_stage = 'final_evaluation' if is_final else 'commitment'
    stage_title = 'INDIVIDUAL PERFORMANCE COMMITMENT AND REVIEW (IPCR)'

    return {
        'emp_id': emp_id,
        'term_id': term_id,
        'full_name': full_name,
        'academic_rank': academic_rank,
        'designation': designation,
        'designation_title': display_designation(designation, designation_title),
        'designation_type': designation_type,
        'is_designated': designation_type != DESIGNATION_REGULAR,
        'specialization': specialization,
        'college': college,
        'academic_year': academic_year,
        'semester': semester,
        'rating_period': period,
        'commitment': build_commitment_sentence(
            full_name, display_designation(designation, designation_title), specialization,
            college, period),
        # 'MFO/PAP' on the regular form, 'Output' on the designated one.
        'output_column_label': 'Output' if designation_type != DESIGNATION_REGULAR else 'MFO/PAP',
        'sections': sections,
        'signatories': resolve_signatories(cursor, emp_id, designation_type, specialization),
        'score': score,
        'is_final': is_final,
        'form_stage': form_stage,
        'stage_title': stage_title,
        'has_targets': bool(targets),
    }


def get_employee_accomplished_ipcrs(cursor, emp_id):
    """
    Returns all IPCRs for a faculty member that have been finalized and approved by the Dean,
    ordered with the most recent term first.
    """
    query = """
        SELECT 
            t.term_id,
            t.academic_year,
            t.semester,
            t.period_start,
            t.period_end,
            t.is_active,
            fs.final_score,
            fs.adjectival_rating,
            fs.dean_approval_status,
            COUNT(ct.target_id) AS total_targets,
            SUM(CASE WHEN ct.status = 'Dean Approved' THEN 1 ELSE 0 END) AS approved_targets,
            MAX(dr.reviewed_at) AS approved_at
        FROM tbl_academic_terms t
        JOIN tbl_master_indicators mi ON mi.term_id = t.term_id
        JOIN tbl_committed_targets ct ON ct.indicator_id = mi.indicator_id AND ct.emp_id = %s
        LEFT JOIN tbl_final_scores fs ON fs.emp_id = ct.emp_id AND fs.term_id = t.term_id
        LEFT JOIN tbl_ipcr_dean_review dr ON dr.emp_id = ct.emp_id AND dr.term_id = t.term_id
        WHERE ct.assigned_quantity > 0
        GROUP BY t.term_id, t.academic_year, t.semester, t.period_start, t.period_end, t.is_active,
                 fs.final_score, fs.adjectival_rating, fs.dean_approval_status
        HAVING total_targets > 0 AND (approved_targets = total_targets OR fs.dean_approval_status = 'Approved')
        ORDER BY t.period_end DESC, t.term_id DESC
    """
    cursor.execute(query, (emp_id,))
    rows = cursor.fetchall()
    results = []
    for r in rows:
        term_id = r[0]
        ay = r[1]
        sem = r[2]
        p_start = r[3]
        p_end = r[4]
        is_active = r[5]
        score = float(r[6]) if r[6] is not None else None
        adjectival = r[7]
        approval_status = r[8]
        total_targets = r[9]
        approved_targets = r[10]
        approved_at = r[11]

        # If score is missing from tbl_final_scores, compute it live
        if score is None:
            computed = compute_ipcr_score(cursor, emp_id, term_id)
            score = computed.get('final_weighted_rating')
            adjectival = computed.get('adjectival_rating') or 'N/A'

        results.append({
            'term_id': term_id,
            'academic_year': ay,
            'semester': sem,
            'period_start': p_start,
            'period_end': p_end,
            'rating_period': format_rating_period(p_start, p_end) or f"{sem}, {ay}",
            'is_active': bool(is_active),
            'final_score': score,
            'adjectival_rating': adjectival or 'N/A',
            'total_targets': total_targets,
            'approved_targets': approved_targets,
            'approved_at': approved_at,
            'status': 'Dean Approved',
        })
    return results


def get_all_accomplished_ipcrs(cursor, specialization=None, program=None):
    """
    Returns all Dean-approved accomplished IPCRs across faculty members,
    optionally filtered by specialization or assigned program.
    """
    params = []
    where_extra = ""
    if specialization:
        where_extra += " AND (ep.specialization = %s OR ep.assigned_program = %s)"
        params.extend([specialization, specialization])
    elif program:
        where_extra += " AND ep.assigned_program = %s"
        params.append(program)

    query = f"""
        SELECT 
            t.term_id,
            t.academic_year,
            t.semester,
            t.period_start,
            t.period_end,
            t.is_active,
            ep.emp_id,
            ep.employee_id_number,
            ep.first_name,
            ep.last_name,
            ep.academic_rank,
            ep.designation,
            ep.assigned_program,
            ep.specialization,
            ep.college,
            fs.final_score,
            fs.adjectival_rating,
            fs.dean_approval_status,
            COUNT(ct.target_id) AS total_targets,
            SUM(CASE WHEN ct.status = 'Dean Approved' THEN 1 ELSE 0 END) AS approved_targets,
            MAX(dr.reviewed_at) AS approved_at
        FROM tbl_academic_terms t
        JOIN tbl_master_indicators mi ON mi.term_id = t.term_id
        JOIN tbl_committed_targets ct ON ct.indicator_id = mi.indicator_id
        JOIN tbl_employee_profiles ep ON ep.emp_id = ct.emp_id
        LEFT JOIN tbl_final_scores fs ON fs.emp_id = ct.emp_id AND fs.term_id = t.term_id
        LEFT JOIN tbl_ipcr_dean_review dr ON dr.emp_id = ct.emp_id AND dr.term_id = t.term_id
        WHERE ct.assigned_quantity > 0 {where_extra}
        GROUP BY t.term_id, t.academic_year, t.semester, t.period_start, t.period_end, t.is_active,
                 ep.emp_id, ep.employee_id_number, ep.first_name, ep.last_name, ep.academic_rank,
                 ep.designation, ep.assigned_program, ep.specialization, ep.college,
                 fs.final_score, fs.adjectival_rating, fs.dean_approval_status
        HAVING total_targets > 0 AND (approved_targets = total_targets OR fs.dean_approval_status = 'Approved')
        ORDER BY t.period_end DESC, t.term_id DESC, ep.last_name ASC, ep.first_name ASC
    """
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    results = []
    for r in rows:
        term_id = r[0]
        ay = r[1]
        sem = r[2]
        p_start = r[3]
        p_end = r[4]
        is_active = r[5]
        emp_id = r[6]
        id_num = r[7]
        first_name = r[8]
        last_name = r[9]
        academic_rank = r[10]
        designation = r[11]
        assigned_program = r[12]
        spec = r[13]
        college = r[14]
        score = float(r[15]) if r[15] is not None else None
        adjectival = r[16]
        approval_status = r[17]
        total_targets = r[18]
        approved_targets = r[19]
        approved_at = r[20]

        if score is None:
            computed = compute_ipcr_score(cursor, emp_id, term_id)
            score = computed.get('final_weighted_rating')
            adjectival = computed.get('adjectival_rating') or 'N/A'

        results.append({
            'term_id': term_id,
            'academic_year': ay,
            'semester': sem,
            'period_start': p_start,
            'period_end': p_end,
            'rating_period': format_rating_period(p_start, p_end) or f"{sem}, {ay}",
            'is_active': bool(is_active),
            'emp_id': emp_id,
            'employee_id_number': id_num,
            'faculty_name': f"{first_name} {last_name}".strip(),
            'academic_rank': academic_rank or 'Instructor I',
            'designation': designation or 'Regular Faculty',
            'department': assigned_program or spec or college,
            'final_score': score,
            'adjectival_rating': adjectival or 'N/A',
            'total_targets': total_targets,
            'approved_targets': approved_targets,
            'approved_at': approved_at,
            'status': 'Dean Approved',
        })
    return results

