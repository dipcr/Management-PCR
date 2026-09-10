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
                                 DESIGNATION_REGULAR, SLUG_ADMINISTRATIVE)
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


def build_ipcr_sections(cursor, targets, designation_type, term_id, academic_rank=None):
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
    """
    categories = get_ipcr_categories(cursor, designation_type)
    weights = get_applicable_weights(cursor, term_id, designation_type, academic_rank)
    type_to_category = get_type_to_category(cursor, designation_type)
    type_meta = _target_type_meta(cursor)

    admin_type_id = get_category_id(cursor, SLUG_ADMINISTRATIVE)
    admin_category_id = type_to_category.get(admin_type_id) if admin_type_id else None
    admin_type_name = type_meta.get(admin_type_id, ('Administrative Functions', 0))[0]

    # Group targets into category -> target type, matching how they are scored: an
    # administrative row belongs to the admin category whatever its own type says, and
    # prints as a single "Administrative Function" subsection — on the real DPCR, a
    # designated faculty's Strategic Priorities/Support items are their administrative
    # functions as a University-designated faculty member, not split by the target's own
    # type (Instruction/Support/etc.), which only matters for their Core Functions work.
    grouped = {}
    for t in targets:
        if t.get('is_admin_function') and admin_category_id:
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


def build_evidence_checklist_sections(cursor, targets, designation_type, term_id, academic_rank=None):
    """
    Same category -> target-type grouping as build_ipcr_sections, but for the Evidence
    Gathering checklist rather than the printed form: every committed target still owes
    an Add/View Evidence action regardless of whether it scores, so a target dropped by
    build_ipcr_sections (nothing maps its type to a weighted category) is appended here
    under a catch-all "Other" section instead of silently losing its evidence button.
    """
    sections = build_ipcr_sections(cursor, targets, designation_type, term_id, academic_rank)
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
        SELECT first_name, last_name, academic_rank, designation, specialization, college
        FROM tbl_employee_profiles WHERE emp_id = %s
    """, (emp_id,))
    profile = cursor.fetchone()
    if not profile:
        return None
    first_name, last_name, academic_rank, designation, specialization, college_code = profile

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

    sections = build_ipcr_sections(cursor, targets, designation_type, term_id, academic_rank)

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
        'designation_type': designation_type,
        'is_designated': designation_type != DESIGNATION_REGULAR,
        'specialization': specialization,
        'college': college,
        'academic_year': academic_year,
        'semester': semester,
        'rating_period': period,
        'commitment': build_commitment_sentence(full_name, designation, specialization,
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
