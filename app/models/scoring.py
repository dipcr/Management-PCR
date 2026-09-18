"""Helpers for SPMS target durations and accomplishment reporting.

Timeliness in the SPMS rating scale is computed as RT = 1 - (Actual T / Target T),
which requires the target's duration as a *number* plus a unit, not the free-text
label that tbl_*.target_deadline historically carried. These helpers keep the
structured value/unit pair and the human-readable label in sync.
"""

# Units a target duration can be expressed in. Actual duration is always entered in
# the same unit as its target, so the ratio in RT is unit-safe.
import re
from decimal import Decimal, ROUND_HALF_UP

DURATION_UNITS = ['days', 'weeks', 'months', 'semesters']


def round2(value):
    """
    Round to 2 decimals half-up, the way the paper IPCR is computed.

    Python's built-in round() is banker's rounding on a binary float, so
    round(2.275, 2) yields 2.27 — the printed form expects 2.28. Ratings must agree
    with a hand-computed IPCR, so all score rounding goes through here.
    """
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

# Non-numeric timeliness outcomes from the SPMS scale (they bypass the RT formula).
COMPLETION_COMPLETED = 'COMPLETED'
COMPLETION_PARTIAL = 'PARTIAL_AT_DEADLINE'   # "Partially completed at deadline" -> 2
COMPLETION_NOT_BEGUN = 'NOT_BEGUN'           # "Not yet begun at target time"    -> 1
COMPLETION_STATUSES = [COMPLETION_COMPLETED, COMPLETION_PARTIAL, COMPLETION_NOT_BEGUN]

# Efficiency (E) is obtained differently depending on the indicator's efficiency_type:
#   Client Satisfaction -> the faculty/verifier reports a rating from this scale
#   Adjectival          -> the target itself names the standard; achieving it scores 5
#   otherwise           -> derived from the achievement ratio (RQn) at roll-up time
EFFICIENCY_CLIENT_SATISFACTION = 'Client Satisfaction'
EFFICIENCY_ADJECTIVAL = 'Adjectival'

CLIENT_SATISFACTION_SCALE = [
    ('Excellent', 5),
    ('Very Satisfactory', 4),
    ('Satisfactory', 3),
    ('Unsatisfactory', 2),
    ('Poor', 1),
]


def client_satisfaction_label(score):
    """Reverse-lookup the adjectival label for a stored client-satisfaction score."""
    for label, value in CLIENT_SATISFACTION_SCALE:
        if value == score:
            return label
    return None


def normalize_duration_unit(unit):
    """Return a valid duration unit, or None when unrecognized."""
    u = (unit or '').strip().lower()
    if not u:
        return None
    if not u.endswith('s'):
        u += 's'
    return u if u in DURATION_UNITS else None


def format_duration(value, unit):
    """
    Human-readable label for a structured duration — the text stored in
    target_deadline so existing displays keep working.

        (6, 'months')   -> '6 months'
        (1, 'semesters') -> '1 semester'
    """
    unit = normalize_duration_unit(unit)
    if value in (None, '') or unit is None:
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    label = unit[:-1] if value == 1 else unit
    return f"{value} {label}"


# Matches the leading target quantity ("6 report of grades…", "100% report of grades…")
_LEADING_QTY = re.compile(r'^\s*(\d+(?:\.\d+)?)(%?)')
# Matches a duration phrase anywhere after the opening ("… in 6 months", "… 10 days after")
_DURATION_PHRASE = re.compile(
    r'\b(\d+)\s*(day|days|week|weeks|month|months|semester|semesters)\b', re.IGNORECASE)
# Matches the efficiency rating phrase that the blank form leaves open ("with satisfactory rating")
_RATING_PHRASE = re.compile(r'\bwith\s+[A-Za-z ]{3,40}?\s+rating\b', re.IGNORECASE)

BLANK = '____'


def build_actual_accomplishment(target_description, actual_quantity=None,
                                actual_duration_value=None, duration_unit=None,
                                efficiency_label=None, raw_indicator_description=None,
                                is_auto_description=None):
    """
    Compose the IPCR "Actual Accomplishments" sentence from the target's success
    indicator, substituting what the faculty actually achieved.

    The printed IPCR renders the accomplishment as the target sentence with three
    slots filled in — quantity, duration, and (where the target names one) the
    efficiency rating. Values that have not been reported yet render as blanks, which
    mirrors how the paper form is issued.

    Best-effort by design: target descriptions are free text, so an unusual phrasing
    may leave a slot unsubstituted rather than guessing wrong. The one exception is a
    row still on Auto (`is_auto_description` true/None) whose master indicator uses the
    {qty}/{duration} placeholder convention (see ipcr_description.py): pass its raw,
    un-substituted `raw_indicator_description` and the actual values are substituted
    directly into the template, deterministically, regardless of where the quantity
    sits in the sentence — this is what a plain regex guess on the already-generated
    `target_description` can't safely do for an indicator like
    "Submit {qty} accurate report of grades..." (see target_desc.md's redesign section
    for why: the quantity isn't at the start of the string, so the regex below never
    finds it). Customized text (`is_auto_description` false), or an indicator that
    doesn't use placeholders, always falls through to the regex-based approach below.
    """
    treated_as_auto = is_auto_description is None or is_auto_description == 1 or is_auto_description is True
    if treated_as_auto and raw_indicator_description:
        from app.models.ipcr_description import _format_placeholders, has_placeholders
        if has_placeholders(raw_indicator_description):
            text = _format_placeholders(raw_indicator_description, actual_quantity, actual_duration_value, duration_unit)
            return _RATING_PHRASE.sub(f"with {efficiency_label or BLANK} rating", text, count=1)

    text = (target_description or '').strip()
    if not text:
        return ''

    # 1) Leading quantity -> actual accomplished quantity. actual_quantity is NOT NULL
    # DEFAULT 0 in the DB (it's the running sum of accepted evidence, recalculated on
    # upload — see recalculate_target_accomplished_quantity in faculty.py), so a target
    # with nothing reported yet is 0, never None. _format_quantity already treats 0 the
    # same as "not yet reported" for the placeholder path above; match that convention
    # here instead of only checking for None, or an unreported target prints "0" instead
    # of the paper form's blank.
    from app.models.ipcr_description import _format_quantity
    qty_text = _format_quantity(actual_quantity) or BLANK

    def _sub_qty(m):
        return f"{qty_text}{m.group(2)}"

    text = _LEADING_QTY.sub(_sub_qty, text, count=1)

    # 2) Duration phrase -> actual time taken. Prefer the target's structured unit; fall
    # back to whatever unit the sentence itself uses, so legacy targets that predate the
    # structured duration fields still read correctly.
    def _sub_duration(m):
        unit = normalize_duration_unit(duration_unit) or normalize_duration_unit(m.group(2))
        if actual_duration_value not in (None, ''):
            return format_duration(actual_duration_value, unit) or str(actual_duration_value)
        return f"{BLANK} {unit}" if unit else BLANK

    text = _DURATION_PHRASE.sub(_sub_duration, text, count=1)

    # 3) Efficiency rating phrase -> achieved rating (or a blank, as on the paper form)
    text = _RATING_PHRASE.sub(f"with {efficiency_label or BLANK} rating", text, count=1)

    return text


# ─────────────────────────────────────────────
# Rating scales (SPMS) — each returns 1..5
# ─────────────────────────────────────────────

# Final Weighted Rating -> adjectival band
ADJECTIVAL_BANDS = [
    (4.75, 'Outstanding'),
    (3.75, 'Very Satisfactory'),
    (3.00, 'Satisfactory'),
    (2.01, 'Unsatisfactory'),
    (0.00, 'Poor'),
]


def achievement_ratio(actual_quantity, target_quantity):
    """RQn = Actual Qn / Target Qn. None when there is no usable target."""
    try:
        target = float(target_quantity or 0)
        if target <= 0:
            return None
        return float(actual_quantity or 0) / target
    except (TypeError, ValueError):
        return None


def rate_quantity(actual_quantity, target_quantity):
    """Quantity (Q) rating from RQn."""
    ratio = achievement_ratio(actual_quantity, target_quantity)
    if ratio is None:
        return None
    if ratio >= 1.30:
        return 5
    if ratio >= 1.15:
        return 4
    if ratio >= 1.00:
        return 3
    if ratio > 0.50:
        return 2
    return 1


def rate_efficiency(efficiency_type, efficiency_rating_E, actual_quantity, target_quantity):
    """
    Efficiency (E) rating. Three variants per the SPMS guide:
      Client Satisfaction -> the reported rating (already 1..5)
      Adjectival          -> achieving a target that names a quality standard scores 5
      otherwise           -> derived from achievement of the target quantity
    """
    if efficiency_type == EFFICIENCY_CLIENT_SATISFACTION:
        return int(efficiency_rating_E) if efficiency_rating_E else None

    ratio = achievement_ratio(actual_quantity, target_quantity)
    if ratio is None:
        return None

    if efficiency_type == EFFICIENCY_ADJECTIVAL and ratio >= 1.00:
        return 5

    # "Based on Achievement of Target Quantity"
    if ratio >= 1.00:
        return 5
    if ratio > 0.50:
        return 2
    return 1


def timeliness_ratio(actual_duration_value, target_duration_value):
    """RT = 1 - (Actual T / Target T). None when the target duration is unknown."""
    try:
        target = float(target_duration_value or 0)
        if target <= 0:
            return None
        if actual_duration_value in (None, ''):
            return None
        return 1 - (float(actual_duration_value) / target)
    except (TypeError, ValueError):
        return None


def rate_timeliness(actual_duration_value, target_duration_value, completion_status=None):
    """
    Timeliness (T) rating. The two non-numeric outcomes short-circuit the RT formula.
    A negative RT (finished later than the target) scores 2 — the guide only bands
    RT from .00 upward, and a late-but-delivered target is treated as the same tier
    as "partially completed at deadline".
    """
    if completion_status == COMPLETION_NOT_BEGUN:
        return 1
    if completion_status == COMPLETION_PARTIAL:
        return 2

    rt = timeliness_ratio(actual_duration_value, target_duration_value)
    if rt is None:
        return None
    if rt >= 0.30:
        return 5
    if rt >= 0.15:
        return 4
    if rt >= 0.00:
        return 3
    return 2


def compute_target_rating(target):
    """
    Q / E / T / Average for one committed target (a dict from
    get_faculty_committed_targets). Sub-scores that cannot be computed yet are None,
    and the average is taken over whichever are available.

    A target with no evidence uploaded at all (evidence_count == 0) can't support any
    of Q/E/T on the 1..5 scale, so all three are forced to 0 rather than left None —
    None would get silently dropped from the average, masking a non-performing target
    behind whatever partial score its neighbors happened to compute.
    """
    if not target.get('evidence_count'):
        return {'q': 0, 'e': 0, 't': 0, 'average': 0.0, 'is_complete': True}

    q = rate_quantity(target.get('actual_quantity'), target.get('assigned_quantity'))
    e = rate_efficiency(target.get('efficiency_type'), target.get('efficiency_rating_E'),
                        target.get('actual_quantity'), target.get('assigned_quantity'))
    t = rate_timeliness(target.get('actual_duration_value'),
                        target.get('target_duration_value'),
                        target.get('completion_status'))

    parts = [s for s in (q, e, t) if s is not None]
    average = round2(sum(parts) / len(parts)) if parts else None
    return {
        'q': q, 'e': e, 't': t,
        'average': average,
        'is_complete': None not in (q, e, t),
    }


def adjectival_rating(final_weighted_rating):
    """Map a Final Weighted Rating onto its adjectival band."""
    if final_weighted_rating is None:
        return None
    for threshold, label in ADJECTIVAL_BANDS:
        if final_weighted_rating >= threshold:
            return label
    return 'Poor'


# ─────────────────────────────────────────────
# IPCR roll-up: targets -> criterion groups -> Final Weighted Rating
# ─────────────────────────────────────────────

def compute_ipcr_score(cursor, emp_id, term_id):
    """
    Roll a faculty member's committed targets up into the IPCR summary:
    per-target Q/E/T average -> per criterion-group average -> weighted by the
    group's configured percentage -> Final Weighted Rating -> adjectival rating.

    Returns a dict with the per-group breakdown plus totals. Nothing is persisted;
    call save_final_score() to record it.
    """
    from app.models.faculty import get_faculty_committed_targets
    from app.models.criteria import (get_applicable_weights, get_type_to_category,
                                     get_ipcr_categories, resolve_designation_type,
                                     get_category_id, DESIGNATION_REGULAR,
                                     SLUG_ADMINISTRATIVE, SLUG_SUPPORT, SLUG_INSTRUCTION)

    cursor.execute(
        "SELECT designation, academic_rank FROM tbl_employee_profiles WHERE emp_id = %s",
        (emp_id,))
    row = cursor.fetchone()
    if row:
        if isinstance(row, dict):
            job_title = row.get('designation')
            academic_rank = row.get('academic_rank')
        else:
            job_title = row[0]
            academic_rank = row[1]
    else:
        job_title = None
        academic_rank = None

    # 'Program Chair', 'RET Chair', 'Dean' etc. are job titles, not weight tables — resolve
    # to the table they are rated against before looking anything up.
    designation = resolve_designation_type(job_title) or DESIGNATION_REGULAR

    targets = get_faculty_committed_targets(cursor, emp_id, term_id)
    weights = get_applicable_weights(cursor, term_id, designation, academic_rank)

    # Which weighted IPCR category each target type belongs to *for this designation*.
    type_to_category = get_type_to_category(cursor, designation)
    categories = get_ipcr_categories(cursor, designation)
    category_names = {c['ipcr_category_id']: c['category_name'] for c in categories}

    # A chair's oversight targets carry their department's whole cascaded quota and rate as
    # an administrative function, regardless of the target's own type — the same indicator
    # can sit under Core Functions as their personal teaching work at the same time. The
    # administrative category is the one holding the Administrative Functions target type.
    admin_category_id = None
    support_type_id = None
    dean_core_category_id = None
    if designation != DESIGNATION_REGULAR:
        admin_type_id = get_category_id(cursor, SLUG_ADMINISTRATIVE)
        if admin_type_id:
            admin_category_id = type_to_category.get(admin_type_id)
        # Mirrors app/models/ipcr_form.py's build_ipcr_sections: the Dean's own real IPCR scores
        # college-wide Support-Functions oversight (professional meetings, faculty advisers,
        # client satisfaction surveys, etc.) under Core Functions, not Strategic
        # Priorities/Support Functions like every other designated faculty member's oversight.
        # Scoped strictly to job_title == 'Dean' -- see that module for why.
        support_type_id = get_category_id(cursor, SLUG_SUPPORT)
        instruction_type_id = get_category_id(cursor, SLUG_INSTRUCTION)
        if instruction_type_id:
            dean_core_category_id = type_to_category.get(instruction_type_id)

    # Average each category's per-target ratings. Targets whose type isn't mapped to any
    # category (e.g. ad-hoc custom items) are excluded from the weighted summary.
    by_category = {}
    for t in targets:
        if (job_title == 'Dean' and t.get('is_admin_function')
                and t.get('category_id') == support_type_id and dean_core_category_id):
            cat_id = dean_core_category_id
        elif t.get('is_admin_function') and admin_category_id:
            cat_id = admin_category_id
        else:
            cat_id = type_to_category.get(t.get('category_id'))
        avg = (t.get('rating') or {}).get('average')
        if not cat_id or avg is None:
            continue
        by_category.setdefault(cat_id, []).append(avg)

    # The summary box lists categories in the order the printed form numbers them
    # (I. Strategic Priorities, II. Core Functions, III. Support Functions), which is the
    # configured display order — not alphabetical.
    category_order = {c['ipcr_category_id']: idx for idx, c in enumerate(categories)}

    breakdown = []
    total_overall = 0.0
    final_weighted = 0.0
    for cat_id, pct in sorted(weights.items(),
                              key=lambda kv: (category_order.get(kv[0], 999),
                                              category_names.get(kv[0], ''))):
        averages = by_category.get(cat_id, [])
        raw_avg = round2(sum(averages) / len(averages)) if averages else None
        weighted = round2(raw_avg * (pct / 100.0)) if raw_avg is not None else None
        if raw_avg is not None:
            total_overall += raw_avg
            final_weighted += weighted
        breakdown.append({
            'ipcr_category_id': cat_id,
            'category_name': category_names.get(cat_id, 'Uncategorised'),
            'weight_pct': pct,
            'raw_avg': raw_avg,
            'weighted_value': weighted,
            'target_count': len(averages),
        })

    has_scores = any(b['raw_avg'] is not None for b in breakdown)
    final_weighted = round2(final_weighted) if has_scores else None

    return {
        'emp_id': emp_id,
        'term_id': term_id,
        'designation': designation,
        'academic_rank': academic_rank,
        'weights_configured': bool(weights),
        'breakdown': breakdown,
        'total_overall_rating': round2(total_overall) if has_scores else None,
        'final_weighted_rating': final_weighted,
        'adjectival_rating': adjectival_rating(final_weighted),
        'target_count': len(targets),
    }


def save_final_score(conn, cursor, emp_id, term_id):
    """
    Persist the computed IPCR score for a faculty member/term into tbl_final_scores
    and tbl_final_score_breakdown, replacing any previous computation for that term.
    """
    result = compute_ipcr_score(cursor, emp_id, term_id)
    if not result['weights_configured']:
        return False, "No weight allocation configured for this term and designation.", result
    if result['final_weighted_rating'] is None:
        return False, "No ratable targets yet — nothing to score.", result

    try:
        cursor.execute(
            "SELECT score_id FROM tbl_final_scores WHERE emp_id = %s AND term_id = %s",
            (emp_id, term_id))
        existing = cursor.fetchone()
        if existing:
            score_id = existing[0]
            cursor.execute("""
                UPDATE tbl_final_scores SET final_score = %s, adjectival_rating = %s
                WHERE score_id = %s
            """, (result['final_weighted_rating'], result['adjectival_rating'], score_id))
            cursor.execute("DELETE FROM tbl_final_score_breakdown WHERE score_id = %s", (score_id,))
        else:
            cursor.execute("""
                INSERT INTO tbl_final_scores (emp_id, term_id, final_score, adjectival_rating)
                VALUES (%s, %s, %s, %s)
            """, (emp_id, term_id, result['final_weighted_rating'], result['adjectival_rating']))
            score_id = cursor.lastrowid

        for b in result['breakdown']:
            if b['raw_avg'] is None:
                continue
            cursor.execute("""
                INSERT INTO tbl_final_score_breakdown (score_id, weight_group, raw_avg, weight_pct, weighted_value)
                VALUES (%s, %s, %s, %s, %s)
            """, (score_id, b['category_name'], b['raw_avg'], b['weight_pct'], b['weighted_value']))

        conn.commit()
        return True, (f"Final Weighted Rating: {result['final_weighted_rating']} "
                      f"({result['adjectival_rating']})"), result
    except Exception as e:
        conn.rollback()
        return False, str(e), result


def parse_duration_fields(form, value_key, unit_key):
    """
    Pull a (value, unit, label) triple out of submitted form data.
    Returns (None, None, None) when the duration was left blank.
    """
    raw_value = (form.get(value_key) or '').strip()
    unit = normalize_duration_unit(form.get(unit_key))
    if not raw_value or unit is None:
        return None, None, None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None, None, None
    if value <= 0:
        return None, None, None
    return value, unit, format_duration(value, unit)
