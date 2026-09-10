def get_designated_selectable_indicators(cursor, term_id, exclude_claimed=True, emp_id=None):
    """
    The pool a designated faculty / chair member can add targets from.
    - If RET Chair: only Research and Extension (review_lane = 'RET').
    - If Program Chair / Designated Faculty: Instruction and Support (review_lane = 'CHAIR' AND is_core = 1).
    """
    from app.models.connection import timed_query
    
    is_ret = False
    if emp_id:
        cursor.execute("SELECT designation FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
        row = cursor.fetchone()
        if row and (row[0] or '').strip() == 'RET Chair':
            is_ret = True

    if is_ret:
        query = """
            SELECT mi.indicator_id, mi.indicator_description, tc.category_name
            FROM tbl_master_indicators mi
            JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            WHERE mi.term_id = %s
              AND mi.is_custom = 0
              AND tc.review_lane = 'RET'
            ORDER BY tc.category_name, mi.indicator_id
        """
        rows = timed_query(cursor, query, (term_id,), label="get_designated_selectable_indicators_ret")
        if exclude_claimed:
            # An indicator the Dean cascades to "RET / Extension" is already carried whole
            # as the RET Chair's oversight target (get_oversight_targets) — unlike Instruction,
            # there is no personal-allocation table for RET, so there's no legitimate reason
            # for it to also appear as a free pick here. Leaving it in let the same indicator
            # be selected twice under two different categories (see submit_designated_ipcr).
            claimed = get_claimed_indicator_ids(cursor, term_id)
            rows = [r for r in rows if r['indicator_id'] not in claimed]
        return rows

    query = """
        SELECT mi.indicator_id, mi.indicator_description, tc.category_name
        FROM tbl_master_indicators mi
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE mi.term_id = %s
          AND mi.is_custom = 0
          AND mi.indicator_description NOT LIKE '%%Teaching Load%%'
          AND tc.review_lane = 'CHAIR' AND tc.is_core = 1
        ORDER BY tc.category_name, mi.indicator_id
    """
    rows = timed_query(cursor, query, (term_id,), label="get_designated_selectable_indicators")
    if exclude_claimed:
        claimed = get_claimed_indicator_ids(cursor, term_id)

        # An indicator the Program Chair explicitly allocated to *this* person stays in the
        # list even though the department also holds it. The claimed rule exists to stop
        # someone picking up work that already has an owner — but for their own allocated
        # share they are the owner. Dropping it left the allocation with no row to attach
        # to, so a chair's Core Functions showed only the teaching load.
        allocated = set()
        if emp_id:
            cursor.execute(
                "SELECT da.indicator_id "
                "FROM tbl_draft_allocation da "
                "JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id "
                "WHERE da.emp_id = %s AND mi.term_id = %s "
                "  AND COALESCE(da.assigned_quantity, 0) > 0",
                (emp_id, term_id))
            allocated = {r[0] for r in cursor.fetchall()}

        rows = [r for r in rows
                if r['indicator_id'] not in claimed or r['indicator_id'] in allocated]
    return rows


def get_oversight_cascade_role(cursor, emp_id):
    """
    Which cascade bucket this person is accountable for overseeing, or None.

    A Program Chair oversees everything the Dean cascaded to their department; the RET Chair
    oversees the RET / Extension bucket. Other designated faculty (and the Dean, pending a
    decision on what the Dean's own oversight set should be) oversee nothing.
    """
    from app.models.institution import ROLE_RET
    cursor.execute(
        "SELECT designation, specialization FROM tbl_employee_profiles WHERE emp_id = %s",
        (emp_id,))
    row = cursor.fetchone()
    if not row:
        return None
    designation, specialization = (row[0] or '').strip(), (row[1] or '').strip()

    if designation == 'RET Chair':
        return ROLE_RET
    if designation == 'Program Chair' and specialization:
        return specialization
    return None


def get_claimed_indicator_ids(cursor, term_id):
    """
    Indicators already spoken for by a chair's oversight accountability.

    Anything the Dean cascaded to a department or to RET is automatically carried by that
    chair, so it must not also be offered in the pool other designated faculty pick from.
    College-Wide quotas are not claimed — the Dean assigns those explicitly.
    """
    from app.models.institution import ROLE_RET, get_departments

    # Department names are read separately rather than joined: tbl_departments was created
    # with a different collation from tbl_cascaded_quotas, so comparing the two columns
    # directly raises "Illegal mix of collations". Binding them as parameters sidesteps it.
    owners = [d['department_name'] for d in get_departments(cursor, active_only=False)]
    owners.append(ROLE_RET)
    if not owners:
        return set()

    placeholders = ','.join(['%s'] * len(owners))
    cursor.execute(f"""
        SELECT DISTINCT cq.indicator_id
        FROM tbl_cascaded_quotas cq
        JOIN tbl_master_indicators mi ON cq.indicator_id = mi.indicator_id
        WHERE cq.term_id = %s
          AND mi.term_id = %s
          AND cq.total_target_value > 0
          AND cq.assigned_to_role IN ({placeholders})
    """, tuple([term_id, term_id] + owners))
    return {r[0] for r in cursor.fetchall()}


def get_core_instruction_allocation(cursor, emp_id, term_id):
    """
    This person's own personal Instruction share: cascaded to their program by the Dean, then
    distributed to them specifically by the Program Chair in Phase 1 Target Allocation
    (tbl_draft_allocation). Rates under Core Functions, never Strategic Priorities/Support —
    unlike a chair's departmental oversight quota for the same indicator (get_oversight_targets),
    which is the department's whole number, not a personal share.

    Used both to classify a submitted target as Core (submit_designated_ipcr) and, for a
    Dean-formulated draft (see save_and_issue_designated_draft_ipcr in app/models/dean.py), to
    fold this share into tbl_draft_targets at Lock & Commit time — see
    lock_and_commit_designated_ipcr for why that has to happen there rather than at issue time.
    """
    from app.models.connection import timed_query
    query = """
        SELECT da.allocation_id, da.indicator_id, da.assigned_quantity, da.custom_description,
               da.target_deadline, da.target_duration_value, da.target_duration_unit,
               da.is_auto_description, mi.indicator_description, tc.category_name
        FROM tbl_draft_allocation da
        JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE da.emp_id = %s AND mi.term_id = %s
          AND tc.slug = 'instruction' AND tc.review_lane = 'CHAIR'
          AND COALESCE(da.assigned_quantity, 0) > 0
          AND EXISTS (
              -- A JOIN here (rather than EXISTS) would fan this row out once per matching
              -- tbl_cascaded_quotas row -- e.g. an indicator cascaded to several departments,
              -- each getting its own non-College-Wide quota row for it -- silently duplicating
              -- this person's single personal allocation. The old inline version of this
              -- query (before it became a shared helper) got away with a JOIN here because its
              -- only caller collapsed the result into a Python set; every caller now consumes
              -- full rows, so the duplication is no longer harmless.
              SELECT 1 FROM tbl_cascaded_quotas cq
              WHERE cq.indicator_id = mi.indicator_id AND cq.term_id = mi.term_id
                AND cq.assigned_to_role != 'College-Wide'
          )
        ORDER BY mi.indicator_id
    """
    return timed_query(cursor, query, (emp_id, term_id), label="get_core_instruction_allocation")


def describe_core_instruction_allocation(r):
    """
    (description, deadline, is_auto_description) for one get_core_instruction_allocation() row.

    Mirrors the is_auto_description convention used everywhere else: None (never explicitly
    set) or 1 both mean "still auto-mirroring" -- only an explicit 0, paired with real
    hand-typed text, means the Program Chair customized this allocation and it must not be
    silently regenerated. Never falls back to the bare indicator_description on its own --
    that's the master indicator's own placeholder/example text (e.g. a stale embedded
    quantity), not this person's real assigned_quantity.
    """
    from app.models.ipcr_description import format_ipcr_target_description
    from app.models.scoring import format_duration
    dur_value = r.get('target_duration_value')
    dur_unit = r.get('target_duration_unit')
    is_auto = r.get('is_auto_description')
    is_auto = 1 if (is_auto is None or is_auto == 1 or not r.get('custom_description')) else 0
    if is_auto:
        desc = format_ipcr_target_description(
            r['indicator_description'], r['assigned_quantity'], dur_value, dur_unit)
    else:
        desc = r['custom_description']
    deadline = r.get('target_deadline') or format_duration(dur_value, dur_unit)
    return desc, deadline, is_auto


def get_oversight_targets(cursor, emp_id, term_id):
    """
    The cascaded quotas a chair carries on their own IPCR as an administrative function.

    These are their department's (or RET's) numbers taken *whole*, not a share: the Dean
    cascades 5 of "Instruction 1" to WST, the WST chair divides that 5 among their faculty,
    and separately answers for the full 5 themselves. They rate under Strategic Priorities/
    Support Functions rather than by target type, which is what is_admin_function records.

    A chair may also hold the same indicator as their own allocated teaching work; that is a
    separate row with the flag clear, rating under Core Functions.
    """
    from app.models.connection import timed_query
    role = get_oversight_cascade_role(cursor, emp_id)
    if not role:
        return []

    query = """
        SELECT cq.indicator_id,
               cq.total_target_value,
               mi.indicator_description,
               mi.efficiency_type,
               tc.category_name,
               tc.slug,
               dt.draft_id,
               dt.proposed_quantity,
               dt.target_description,
               dt.target_deadline,
               dt.target_duration_value,
               dt.target_duration_unit,
               dt.review_status
        FROM tbl_cascaded_quotas cq
        JOIN tbl_master_indicators mi ON cq.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        LEFT JOIN tbl_draft_targets dt
               ON dt.emp_id = %s AND dt.indicator_id = cq.indicator_id
              AND dt.is_admin_function = 1
        WHERE cq.term_id = %s
          AND mi.term_id = %s
          AND cq.assigned_to_role = %s
          AND cq.total_target_value > 0
        ORDER BY tc.display_order, mi.indicator_id
    """
    rows = timed_query(cursor, query, (emp_id, term_id, term_id, role),
                       label="get_oversight_targets")

    from app.models.ipcr_description import format_ipcr_target_description

    for r in rows:
        # Pre-filled from the cascade; a saved draft value wins so an edit survives a reload.
        r['total_target_value'] = r.get('proposed_quantity') or r['total_target_value']
        # Always regenerated from the indicator + the department's full quota — never
        # user-customizable (there's no description input for an oversight row at all), so
        # unlike a personal target there's no "customized text" to preserve. Falling back to
        # the raw indicator_description (the old behavior) showed the indicator's own
        # embedded default number instead of the department's actual cascaded quota, which is
        # wrong whenever they differ (e.g. Dean cascades 5, but the indicator was authored
        # with "{qty:1}" as a placeholder example).
        r['target_description'] = format_ipcr_target_description(
            r['indicator_description'], r['total_target_value'],
            r.get('target_duration_value'), r.get('target_duration_unit'))
        r['is_auto_description'] = True
        r['target_deadline'] = r.get('target_deadline') or ''
        r['status'] = r.get('review_status') or 'Draft'
        r['is_admin_function'] = True
        # Narrower than is_admin_function: this row is specifically a chair's departmental
        # oversight quota (not just "not Core Function" — a freely-picked pool item is also
        # is_admin_function=1 after submission). The template uses this one for anything
        # UI-specific to the oversight row: the badge, locking the quantity, and picking the
        # `_adm`-suffixed deadline field name that avoids colliding with a personal Core
        # Function row that happens to share this indicator_id.
        r['is_oversight_cascade'] = True
        r['is_cascaded'] = True
        r['is_selected'] = True
        r['is_core'] = False
        # The quantity is fixed (the department's/RET's whole cascaded quota, not a share
        # the chair can adjust), but the deadline is real chair-provided input the Timeliness
        # score needs — see the duration handling in submit_designated_ipcr.
        r['is_locked'] = False
        r['is_custom'] = False
    return rows


def get_oversight_indicator_ids(cursor, emp_id, term_id):
    """
    The set of indicator_ids cascaded to this chair's oversight role this term (see
    get_oversight_cascade_role) -- narrower than is_admin_function, which is also 1 for any
    freely-picked Strategic Priorities/Support pool item, not just a genuine departmental
    oversight quota. Shared by get_designated_committed_targets (to tag committed rows) and
    routes/designated.py (to badge draft rows) so both stay in sync off one query.
    """
    from app.models.connection import timed_query
    role = get_oversight_cascade_role(cursor, emp_id)
    if not role:
        return set()
    query = """
        SELECT cq.indicator_id
        FROM tbl_cascaded_quotas cq
        JOIN tbl_master_indicators mi ON cq.indicator_id = mi.indicator_id
        WHERE cq.term_id = %s AND mi.term_id = %s
          AND cq.assigned_to_role = %s AND cq.total_target_value > 0
    """
    rows = timed_query(cursor, query, (term_id, term_id, role), label="get_oversight_indicator_ids")
    return {r['indicator_id'] for r in rows}


def get_oversight_evidence(cursor, emp_id, term_id, indicator_id):
    """
    Aggregates the real work behind one of this chair's Departmental Oversight rows: the
    scoped faculty who hold their own personal committed target for the same indicator_id
    (never another chair's own oversight copy -- is_admin_function = 0 excludes that), summed
    from their already-verification-clean actual_quantity (see
    recalculate_target_accomplished_quantity, which already nets out Rejected/Returned
    evidence there); their MAX actual_duration_value (the department isn't done until its
    last contributor is) and rounded-average efficiency_rating_E (for Client Satisfaction
    indicators only -- see the aggregation rule inline below); plus the evidence files behind
    those numbers for a read-only viewer.

    Scope mirrors get_program_chair_evidence_faculty / get_ret_chair_evidence_faculty exactly:
    a Program Chair's oversight role is their own specialization string; the RET Chair's is
    ROLE_RET, which has no specialization -- college-wide instead.
    """
    from app.models.connection import timed_query
    from app.models.institution import ROLE_RET

    empty = {
        'total_actual_quantity': 0,
        'max_actual_duration_value': None,
        'avg_efficiency_rating': None,
        'evidence_count': 0,
        'evidence_breakdown': [],
    }

    role = get_oversight_cascade_role(cursor, emp_id)
    if not role:
        return empty

    params = [indicator_id, term_id]
    scope_clause = ""
    if role != ROLE_RET:
        scope_clause = "AND ep.specialization = %s"
        params.append(role)

    query = f"""
        SELECT ct.target_id, ct.actual_quantity, ct.actual_duration_value, ct.efficiency_rating_E,
               ep.first_name, ep.last_name
        FROM tbl_committed_targets ct
        JOIN tbl_employee_profiles ep ON ct.emp_id = ep.emp_id
        JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
        WHERE ct.indicator_id = %s
          AND mi.term_id = %s
          AND ct.is_admin_function = 0
          AND (ep.designation IS NULL OR ep.designation = ''
               OR ep.designation NOT IN ('Designated Faculty', 'Program Chair', 'RET Chair', 'Dean'))
          {scope_clause}
    """
    rows = timed_query(cursor, query, tuple(params), label="get_oversight_evidence_targets")
    if not rows:
        return empty

    total_actual_quantity = sum(r.get('actual_quantity') or 0 for r in rows)
    # actual_duration_value/efficiency_rating_E are not cleared when a target's only evidence
    # gets Returned/Rejected after having once been reported
    # (recalculate_target_accomplished_quantity nets the quantity back to 0 but only
    # _clear_accomplishment_details_if_unaccomplished, called from the delete path, clears
    # these) -- guard on actual_quantity > 0 here so a faculty member whose evidence was
    # returned can't still inflate the department's MAX Timeliness input, or skew its average
    # Client Satisfaction rating, with values that no longer have any accomplishment behind them.
    reported_rows = [r for r in rows if (r.get('actual_quantity') or 0) > 0]
    durations = [r['actual_duration_value'] for r in reported_rows if r.get('actual_duration_value') is not None]
    max_actual_duration_value = max(durations) if durations else None

    # Client Satisfaction rating (efficiency_rating_E) has no single-value semantic across
    # multiple contributors the way a summed quantity does -- averaged, rounded to the
    # nearest whole point on the 1-5 scale (round-half-up, not Python's round-half-to-even,
    # since a report-facing score rounding 4.5 down to 4 would read as a silent understatement).
    # Inert for indicators not rated by Client Satisfaction: rate_efficiency() only consults
    # efficiency_rating_E for that efficiency_type, so setting it here is harmless otherwise.
    ratings = [r['efficiency_rating_E'] for r in reported_rows if r.get('efficiency_rating_E') is not None]
    avg_efficiency_rating = int(sum(ratings) / len(ratings) + 0.5) if ratings else None

    faculty_by_target = {r['target_id']: f"{r['first_name']} {r['last_name']}".strip() for r in rows}

    target_ids = list(faculty_by_target.keys())
    placeholders = ','.join(['%s'] * len(target_ids))
    ev_query = f"""
        SELECT evidence_id, target_id, file_path, actual_qty_Q, verification_status
        FROM tbl_evidence_repo
        WHERE target_id IN ({placeholders})
        ORDER BY evidence_id
    """
    ev_rows = timed_query(cursor, ev_query, tuple(target_ids), label="get_oversight_evidence_files")
    evidence_breakdown = [{
        'evidence_id': ev['evidence_id'],
        'faculty_name': faculty_by_target.get(ev['target_id'], 'Unknown'),
        'file_path': ev['file_path'],
        'actual_qty_Q': ev['actual_qty_Q'],
        'verification_status': ev['verification_status'],
    } for ev in ev_rows]

    return {
        'total_actual_quantity': total_actual_quantity,
        'max_actual_duration_value': max_actual_duration_value,
        'avg_efficiency_rating': avg_efficiency_rating,
        'evidence_count': len(evidence_breakdown),
        'evidence_breakdown': evidence_breakdown,
    }


def apply_oversight_overrides(cursor, emp_id, term_id, rows):
    """
    Post-processes a list of committed-target rows (dicts with at least 'indicator_id',
    'is_admin_function', and the fields build_actual_accomplishment/compute_target_rating
    need) so that every genuine Departmental Oversight row reflects the scoped faculty's
    real work instead of its own (never-uploaded-to) actual_quantity/actual_duration_value.

    This is the one place the override happens, called from both
    get_designated_committed_targets (the Evidence Gathering dashboard/readiness gate) and
    get_faculty_committed_targets (the scoring engine via compute_ipcr_score, and the printed
    IPCR via build_ipcr_form) -- those two functions are a genuinely separate pair of queries
    against tbl_committed_targets, not layers on top of one another, so both need this call
    for the aggregation to reach the dashboard, the rating, and the print consistently.
    A no-op for anyone with no oversight role (get_oversight_indicator_ids returns an empty
    set immediately), which is every Regular Faculty member.
    """
    from app.models.scoring import build_actual_accomplishment, client_satisfaction_label, compute_target_rating

    oversight_ids = get_oversight_indicator_ids(cursor, emp_id, term_id)
    if not oversight_ids:
        for r in rows:
            r['is_oversight_cascade'] = False
        return rows

    for r in rows:
        r['is_oversight_cascade'] = bool(r.get('is_admin_function')) and r.get('indicator_id') in oversight_ids
        if not r['is_oversight_cascade']:
            continue
        agg = get_oversight_evidence(cursor, emp_id, term_id, r['indicator_id'])
        r['actual_quantity'] = agg['total_actual_quantity']
        r['actual_duration_value'] = agg['max_actual_duration_value']
        r['evidence_count'] = agg['evidence_count']
        # Only meaningful for a Client Satisfaction indicator (rate_efficiency ignores this
        # field for every other efficiency_type) -- see get_oversight_evidence's
        # avg_efficiency_rating for the aggregation rule (rounded average across contributors).
        r['efficiency_rating_E'] = agg['avg_efficiency_rating']
        r['actual_accomplishment'] = build_actual_accomplishment(
            r.get('indicator_description'),
            r.get('actual_quantity'),
            r.get('actual_duration_value'),
            r.get('target_duration_unit'),
            client_satisfaction_label(r.get('efficiency_rating_E')),
            raw_indicator_description=r.get('raw_indicator_description'),
            is_auto_description=r.get('is_auto_description'),
        )
        r['rating'] = compute_target_rating(r)
    return rows


def update_oversight_draft_deadline(conn, cursor, emp_id, draft_id, duration_value, duration_unit):
    """
    Lets a chair correct their own Departmental Oversight row's deadline before locking -- the
    one field on that row that's never had any source but the chair's own input (see
    get_oversight_targets: quantity is the department's fixed cascade, never editable; the
    deadline has no other source at all). This is deliberately its own narrow save, separate
    from the full submit/re-submit path: everything else about a Dean-formulated draft stays
    read-only (see routes/designated.py's can_edit, always False for Program Chair/RET Chair/
    Dean) right up to Lock & Commit.

    Ownership, oversight-row identity, and not-yet-locked are all re-verified here -- the UI
    only ever renders this control for a genuine, still-unlocked oversight row, but that's not
    enforcement on its own against a direct POST.
    """
    from app.models.scoring import DURATION_UNITS, format_duration
    from app.models.ipcr_description import format_ipcr_target_description

    if duration_unit not in DURATION_UNITS:
        return False, "Invalid duration unit."
    try:
        duration_value = int(duration_value)
        if duration_value <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return False, "Duration must be a positive number."

    try:
        cursor.execute("""
            SELECT dt.emp_id, dt.indicator_id, dt.is_admin_function, dt.proposed_quantity,
                   mi.indicator_description, mi.term_id
            FROM tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            WHERE dt.draft_id = %s
        """, (draft_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Target not found."
        if row[0] != emp_id:
            return False, "You can only update your own targets."
        if not row[2]:
            return False, "This is not a Departmental Oversight target."

        term_id = row[5]
        if row[1] not in get_oversight_indicator_ids(cursor, emp_id, term_id):
            return False, "This is not a Departmental Oversight target."

        # Scoped to this same term -- a plain "has this emp_id ever committed anything"
        # check would permanently lock out anyone with committed targets from a *past* term,
        # which is every returning employee after their first term.
        cursor.execute("""
            SELECT COUNT(*) FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
        """, (emp_id, term_id))
        if cursor.fetchone()[0] > 0:
            return False, "Your IPCR is already locked and can no longer be edited."

        new_description = format_ipcr_target_description(
            row[4], row[3], duration_value, duration_unit)
        new_deadline = format_duration(duration_value, duration_unit)

        cursor.execute("""
            UPDATE tbl_draft_targets
            SET target_duration_value = %s, target_duration_unit = %s,
                target_description = %s, target_deadline = %s
            WHERE draft_id = %s
        """, (duration_value, duration_unit, new_description, new_deadline, draft_id))
        conn.commit()
        return True, "Deadline updated."
    except Exception as e:
        conn.rollback()
        return False, str(e)


def submit_designated_ipcr(conn, cursor, emp_id, term_id, selected_targets, custom_targets, oversight_durations=None):
    """
    Transactionally processes standard baseline selections and inserts custom ad-hoc targets
    upstream before compiling all submissions securely inside tbl_draft_targets.
    Also resets any prior Dean review so the Dean can review again.

    selected_targets: [{'indicator_id': int, 'proposed_quantity': int, 'target_description': str, 'target_deadline': str}]
    custom_targets: [{'description': str, 'proposed_quantity': int, 'category_name': str, 'target_deadline': str}]
    oversight_durations: {indicator_id: {'target_duration_value', 'target_duration_unit', 'target_deadline'}} —
        the chair's deadline input for their departmental oversight targets (see get_oversight_targets).
        Quantity/description for those targets is never taken from the form, only the deadline.
    """
    oversight_durations = oversight_durations or {}
    try:
        # 0. Clear any prior Dean review so Dean can re-review fresh
        cursor.execute(
            "SELECT review_id FROM tbl_ipcr_dean_review WHERE emp_id = %s AND term_id = %s",
            (emp_id, term_id)
        )
        old_review = cursor.fetchone()
        if old_review:
            old_review_id = old_review[0]
            cursor.execute("DELETE FROM tbl_ipcr_dean_review_items WHERE review_id = %s", (old_review_id,))
            cursor.execute("DELETE FROM tbl_ipcr_dean_review WHERE review_id = %s", (old_review_id,))

        # Capture the chair's/RET chair's departmental oversight quota rows (see
        # get_oversight_targets) BEFORE clearing tbl_draft_targets below — this function
        # LEFT JOINs the existing draft row to pre-fill a previously-saved target_description/
        # target_duration_value/target_duration_unit, so calling it after the delete would
        # always see a fresh, empty join and silently drop whatever the chair had entered.
        oversight_rows = get_oversight_targets(cursor, emp_id, term_id)

        # 1. Clear any prior unverified submissions for this profile to prevent key errors
        cursor.execute("DELETE FROM tbl_draft_targets WHERE emp_id = %s", (emp_id,))

        # A designated faculty's Core Functions are only their personal teaching work: the
        # mandatory teaching load plus whatever instruction the Program Chair allocated to
        # them (departmental CHAIR instruction, not College-Wide Dean assignments). Everything
        # else they carry — College-Wide targets, targets picked from the pool, custom items, and
        # a chair's oversight cascades — is a Strategic Priorities/Support Function.
        #
        # Derived here rather than taken from the form so the category cannot be spoofed or
        # drift out of step with what the dashboard displayed.
        core_indicator_ids = {r['indicator_id'] for r in get_core_instruction_allocation(cursor, emp_id, term_id)}

        # A chair's/RET chair's departmental oversight quota (see get_oversight_targets) can
        # be the *same indicator* as their personal Core Function allocation above — e.g. the
        # Dean cascades "Instruction 1" to WST, the WST chair keeps a personal teaching share
        # of it (Core Function, in core_indicator_ids) and separately answers for the
        # department's full quota (Strategic Priorities, inserted below from oversight_rows,
        # never trusted from the form). An indicator with *no* personal allocation — Support/
        # Admin/Innovation quotas, or any RET/Extension quota — only ever appears here as a
        # stray, data-less submission (the template renders no qty/duration fields for a pure
        # oversight row), so it's dropped; one *with* a personal allocation is real Core
        # Function input and must still be processed normally below.
        # (oversight_rows was captured earlier, before the tbl_draft_targets delete.)
        oversight_indicator_ids = {r['indicator_id'] for r in oversight_rows}
        pure_oversight_ids = oversight_indicator_ids - core_indicator_ids

        from app.models.ipcr_description import (
            format_ipcr_target_description, get_indicator_description, has_placeholders)

        # 2. Process Standard Baseline Selected Targets
        for target in selected_targets:
            if target['indicator_id'] in pure_oversight_ids:
                # A stray submission for an oversight-only row (see above) — the real
                # oversight target is inserted separately below.
                continue
            desc = target.get('target_description') or None
            dead = target.get('target_deadline') or None
            dur_value = target.get('target_duration_value')
            dur_unit = target.get('target_duration_unit')
            is_teaching_load = 'Teaching Load' in str(target.get('target_description') or '')
            is_core = is_teaching_load or target['indicator_id'] in core_indicator_ids
            is_admin = 0 if is_core else 1
            # is_auto_description True (explicit, from the frontend) always regenerates,
            # even if non-blank text was submitted — protects against client-side drift
            # (Decision 1). A blank description always regenerates too, regardless.
            is_auto_description = 1 if (target.get('is_auto_description') is True or not desc) else 0
            if is_auto_description:
                desc = format_ipcr_target_description(
                    get_indicator_description(cursor, target['indicator_id']),
                    target['proposed_quantity'], dur_value, dur_unit)
            cursor.execute("""
                INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status, target_description, target_deadline,
                                               target_duration_value, target_duration_unit, is_admin_function, is_auto_description)
                VALUES (%s, %s, %s, 'Pending Review', %s, %s, %s, %s, %s, %s)
            """, (emp_id, target['indicator_id'], target['proposed_quantity'], desc, dead, dur_value, dur_unit,
                  is_admin, is_auto_description))

        from app.models.institution import resolve_teaching_load, teaching_load_description
        from app.models.scoring import format_duration

        # 2b. Insert the chair's/RET chair's departmental oversight targets. Quantity and
        # description come from get_oversight_targets (the cascade total — never the form, see
        # the note above); the deadline is real chair input, submitted separately in
        # oversight_durations (the `_adm`-suffixed fields) precisely because it can't be
        # derived from anywhere else and Timeliness scoring needs it.
        for r in oversight_rows:
            ov_input = oversight_durations.get(r['indicator_id'], {})
            ov_dur_value = (ov_input.get('target_duration_value') or r.get('target_duration_value') or 1)
            ov_dur_unit = (ov_input.get('target_duration_unit') or r.get('target_duration_unit') or 'semesters')
            ov_deadline = (ov_input.get('target_deadline') or r.get('target_deadline')
                           or format_duration(ov_dur_value, ov_dur_unit))
            # Always regenerated from the indicator + the department's full quota, using
            # whatever duration is actually being saved this submission — never the chair's
            # own text (there's no description input for this row) and never a stale duration
            # from an earlier load. See get_oversight_targets() for why the quantity always
            # comes from total_target_value, never from the row itself.
            ov_desc = format_ipcr_target_description(
                r['indicator_description'], r['total_target_value'], ov_dur_value, ov_dur_unit)
            cursor.execute("""
                INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status, target_description, target_deadline,
                                               target_duration_value, target_duration_unit, is_admin_function, is_auto_description)
                VALUES (%s, %s, %s, 'Pending Review', %s, %s, %s, %s, 1, 1)
            """, (emp_id, r['indicator_id'], r['total_target_value'], ov_desc, ov_deadline, ov_dur_value, ov_dur_unit))

        # Ensure the mandatory Teaching Load target is saved, using the Admin's configured
        # hours and duration for Designated faculty (previously hardcoded at 10 hours).
        cursor.execute("SELECT academic_rank FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
        tl_rank_row = cursor.fetchone()
        tl_hours, tl_dur_value, tl_dur_unit = resolve_teaching_load(
            cursor, term_id, 'Designated Faculty', tl_rank_row[0] if tl_rank_row else None)
        tl_desc = teaching_load_description(tl_hours)
        tl_deadline = format_duration(tl_dur_value, tl_dur_unit)

        cursor.execute("SELECT category_id FROM tbl_target_categories WHERE slug = 'instruction'")
        cat_row = cursor.fetchone()
        cat_id = cat_row[0] if cat_row else 1
        cursor.execute("SELECT indicator_id FROM tbl_master_indicators WHERE indicator_description = %s AND term_id = %s",
                       (tl_desc, term_id))
        tl_row = cursor.fetchone()
        if tl_row:
            tl_ind_id = tl_row[0]
        else:
            cursor.execute("INSERT INTO tbl_master_indicators (category_id, indicator_description, efficiency_type, term_id, is_custom) VALUES (%s, %s, 'Output-Based', %s, 0)",
                           (cat_id, tl_desc, term_id))
            tl_ind_id = cursor.lastrowid

        cursor.execute("SELECT draft_id FROM tbl_draft_targets WHERE emp_id = %s AND indicator_id = %s", (emp_id, tl_ind_id))
        tl_draft = cursor.fetchone()
        if not tl_draft:
            cursor.execute("""
                INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status,
                                               target_description, target_deadline,
                                               target_duration_value, target_duration_unit)
                VALUES (%s, %s, %s, 'Pending Review', %s, %s, %s, %s)
            """, (emp_id, tl_ind_id, tl_hours, tl_desc, tl_deadline, tl_dur_value, tl_dur_unit))

        # 3. Process Custom Ad-Hoc Target Items
        for custom in custom_targets:
            text_clean = custom['description'].strip()
            qty = custom['proposed_quantity']
            dead = custom.get('target_deadline') or None
            cust_dur_value = custom.get('target_duration_value')
            cust_dur_unit = custom.get('target_duration_unit')
            if not text_clean:
                continue

            # Reconcile the description the person typed with the quantity/duration they
            # entered in the separate fields beside it. Three branches, none of which ever
            # guesses which number in a free-typed sentence is "the quantity":
            #
            #  1. Tagged ({qty}/{duration} present, via the click-to-tag helper on the Add
            #     Custom Target modal) — substitute. The binding is exact because the person
            #     established it themselves by clicking the number, so this also works when
            #     the quantity sits mid-sentence, which is where the position-0 legacy rule
            #     can't reach.
            #  2. Untagged but the text already contains digits — store it verbatim. We can't
            #     tell whether a bare "3" in "Report 3 activities" is the tracked quantity, a
            #     year level, or a standard number, and prepending on top of it produces the
            #     confusing "1 Report 3 activities". Trusting exactly what was typed is the
            #     only non-guessing option; the quantity and duration still reach scoring
            #     through their own columns and still render in their own table columns.
            #  3. Untagged with no digits at all (a bare activity phrase, which is what the
            #     field's placeholder asks for) — unambiguous, so combine into the same
            #     "[Quantity] [Description] within [Duration]" convention every other target
            #     uses. Idempotent if re-run on its own output with the same values.
            #
            # The modal mirrors this exact rule in JS (composeCustomTargetDescription) so the
            # preview and the added row read the same as what lands here.
            raw_text = text_clean
            tagged = has_placeholders(text_clean)
            if tagged or not any(ch.isdigit() for ch in text_clean):
                text_clean = format_ipcr_target_description(text_clean, qty, cust_dur_value, cust_dur_unit)
            if not tagged:
                # Nothing to re-substitute later, so the master indicator holds the same
                # final text the draft row does — the pre-tagging behaviour, unchanged.
                raw_text = text_clean

            # Step A: Identify or provision the specific category block dynamically
            cat_name = custom.get('category_name', 'Support Functions')
            cursor.execute("SELECT category_id FROM tbl_target_categories WHERE category_name = %s", (cat_name,))
            cat_row = cursor.fetchone()
            if cat_row:
                category_id = cat_row[0]
            else:
                cursor.execute("INSERT INTO tbl_target_categories (category_name) VALUES (%s)", (cat_name,))
                category_id = cursor.lastrowid

            # Step B: Upstream runtime injection into master indicators (Explicitly flagged as is_custom = 1).
            # A tagged item stores its *raw* placeholder text here, exactly like an
            # Admin-authored indicator — that is what lets build_actual_accomplishment()
            # substitute the achieved quantity by placeholder position instead of falling
            # back to its regex anchored at character 0, which a mid-sentence quantity
            # ("Report {qty} activities...") would never match.
            cursor.execute("""
                SELECT indicator_id FROM tbl_master_indicators
                WHERE indicator_description = %s AND term_id = %s AND category_id = %s AND is_custom = 1
            """, (raw_text, term_id, category_id))
            existing_ind = cursor.fetchone()
            if existing_ind:
                new_indicator_id = existing_ind[0]
            else:
                cursor.execute("""
                    INSERT INTO tbl_master_indicators (category_id, indicator_description, efficiency_type, term_id, is_custom)
                    VALUES (%s, %s, 'Output-Based', %s, 1)
                """, (category_id, raw_text, term_id))
                new_indicator_id = cursor.lastrowid

            # Step C: Downstream projection into the unified draft staging table.
            # Custom ad-hoc items are never personal teaching work, so they always rate
            # under Strategic Priorities/Support Functions.
            #
            # is_auto_description is set explicitly rather than left to the schema default,
            # and it means different things for the two kinds of custom item:
            #
            #  Tagged (1): the stored master text still holds {qty}/{duration}, so this row
            #  genuinely does mirror it — regenerating reproduces target_description exactly,
            #  and the scoring engine needs the flag to take its placeholder fast path.
            #  Untagged (0): the text was combined (or kept verbatim) once, here, and there
            #  is nothing left to substitute — no placeholders, and no separate "current
            #  quantity" to regenerate against later, unlike a real cascaded indicator.
            #  Leaving it at the default 1 would let a read path re-run already-combined text
            #  through format_ipcr_target_description() a second time: harmless for identical
            #  values, wrong the moment anything about the row changes outside this function.
            cursor.execute("""
                INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status, target_description, target_deadline,
                                               target_duration_value, target_duration_unit, is_admin_function, is_auto_description)
                VALUES (%s, %s, %s, 'Pending Review', %s, %s, %s, %s, 1, %s)
            """, (emp_id, new_indicator_id, qty, text_clean, dead, cust_dur_value, cust_dur_unit, 1 if tagged else 0))

        conn.commit()
        return True, "Designated IPCR successfully compiled and submitted to Draft Targets for verification review."
    except Exception as e:
        conn.rollback()
        return False, str(e)


# ──────────────────────────────────────────────
# Process 6: Evidence Gathering Helpers
# ──────────────────────────────────────────────

def get_designated_committed_targets(cursor, emp_id, term_id):
    """
    Designated faculty's committed targets, including the fields the scoring engine
    needs (durations, reported accomplishment, efficiency type) so their IPCR rates
    the same way a regular faculty's does.
    """
    from app.models.connection import timed_query
    from app.models.scoring import build_actual_accomplishment, client_satisfaction_label, compute_target_rating
    query = """
        SELECT ct.target_id, ct.indicator_id, ct.assigned_quantity, ct.actual_quantity, ct.status,
               COALESCE(ct.target_description, dt.target_description, mi.indicator_description) as indicator_description,
               COALESCE(ct.target_description, dt.target_description) as target_description,
               mi.indicator_description as raw_indicator_description, ct.is_auto_description,
               COALESCE(ct.target_deadline, dt.target_deadline) as target_deadline,
               COALESCE(ct.target_duration_value, dt.target_duration_value) as target_duration_value,
               COALESCE(ct.target_duration_unit, dt.target_duration_unit) as target_duration_unit,
               ct.actual_duration_value, ct.completion_status, ct.efficiency_rating_E,
               ct.is_admin_function, ct.print_remarks,
               mi.efficiency_type,
               tc.category_name, tc.category_id, mi.is_custom,
               COALESCE(ev.evidence_count, 0) as evidence_count
        FROM tbl_committed_targets ct
        JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
        LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        LEFT JOIN tbl_draft_targets dt ON dt.emp_id = ct.emp_id AND dt.indicator_id = ct.indicator_id
              AND dt.is_admin_function = ct.is_admin_function
        LEFT JOIN (
            SELECT target_id, COUNT(*) as evidence_count FROM tbl_evidence_repo GROUP BY target_id
        ) ev ON ev.target_id = ct.target_id
        WHERE ct.emp_id = %s AND mi.term_id = %s
        ORDER BY tc.category_name, mi.indicator_id
    """
    rows = timed_query(cursor, query, (emp_id, term_id), label="get_designated_committed_targets")
    for r in rows:
        r['actual_accomplishment'] = build_actual_accomplishment(
            r.get('indicator_description'),
            r.get('actual_quantity'),
            r.get('actual_duration_value'),
            r.get('target_duration_unit'),
            client_satisfaction_label(r.get('efficiency_rating_E')),
            raw_indicator_description=r.get('raw_indicator_description'),
            is_auto_description=r.get('is_auto_description'),
        )
        r['rating'] = compute_target_rating(r)

    # Overrides any genuine Departmental Oversight row's qty/duration/evidence/rating with
    # the scoped faculty's aggregate -- see apply_oversight_overrides. A no-op for anyone
    # without an oversight role (every plain Designated Faculty member).
    apply_oversight_overrides(cursor, emp_id, term_id, rows)
    return rows



def check_designated_evidence_readiness(cursor, emp_id, term_id, dpcr_targets):
    if not dpcr_targets:
        return {
            'all_evidence_ready': False,
            'evidence_submitted': False,
            'has_missing_timeliness': False,
            'targets_missing_timeliness': [],
            'total_targets': 0,
            'targets_with_evidence': 0,
            'targets_met_qty': 0
        }

    from app.models.faculty import get_evidence_by_target

    total_targets = len(dpcr_targets)
    targets_with_evidence = 0
    targets_met_qty = 0
    submitted_count = 0
    targets_missing_timeliness = []

    for t in dpcr_targets:
        if t.get('is_oversight_cascade'):
            # Its evidence lives on scoped faculty's own committed targets, not this row's
            # own target_id -- get_designated_committed_targets already aggregated it into
            # actual_duration_value/evidence_count. Exempt from the raw per-file lookup and
            # from the missing-timeliness block below: a chair has no way to make a scoped
            # faculty member enter a duration themselves (same rationale as the
            # target-duration edge case documented in the evidence-verification plan).
            if t.get('evidence_count', 0) > 0:
                targets_with_evidence += 1
        else:
            ev_list = t.get('evidence_list')
            if ev_list is None:
                ev_list = get_evidence_by_target(cursor, t['target_id'])
                t['evidence_list'] = ev_list

            valid_evs = [e for e in ev_list if e.get('verification_status') not in ('Returned', 'Rejected')]
            if len(valid_evs) > 0:
                targets_with_evidence += 1
                # Evidence exists but there's nothing to compute Timeliness from -- would
                # otherwise resolve to a silently-dropped None instead of a real score. 0 is
                # a legitimate "completed instantly" value (rate_timeliness treats it as
                # valid too) -- only a genuinely blank duration counts as missing.
                if t.get('actual_duration_value') is None:
                    targets_missing_timeliness.append(t.get('indicator_description') or f"target #{t.get('target_id')}")

        actual_q = t.get('actual_quantity') or 0
        assigned_q = t.get('assigned_quantity') or t.get('total_target_value') or 0
        if actual_q >= assigned_q and assigned_q > 0:
            targets_met_qty += 1

        if t.get('status') in ('Submitted', 'Pending Verification', 'Verified', 'Submitted to Dean', 'Dean Approved'):
            submitted_count += 1

    has_missing_timeliness = len(targets_missing_timeliness) > 0

    # Neither quantity nor evidence needs to be present to submit -- a target a faculty
    # member never accomplished at all is still a valid target to report; scoring.py
    # already handles zero accomplishment gracefully (lowest band, not an error).
    # targets_with_evidence/targets_met_qty stay informational (progress badges) only.
    all_ready = (total_targets > 0) and not has_missing_timeliness
    evidence_submitted = (submitted_count == total_targets) and (total_targets > 0)

    return {
        'all_evidence_ready': all_ready,
        'evidence_submitted': evidence_submitted,
        'has_missing_timeliness': has_missing_timeliness,
        'targets_missing_timeliness': targets_missing_timeliness,
        'total_targets': total_targets,
        'targets_with_evidence': targets_with_evidence,
        'targets_met_qty': targets_met_qty
    }


def submit_designated_evidences(conn, cursor, emp_id, term_id):
    dpcr_targets = get_designated_committed_targets(cursor, emp_id, term_id)
    if not dpcr_targets:
        return False, "No committed targets found."

    readiness = check_designated_evidence_readiness(cursor, emp_id, term_id, dpcr_targets)
    if readiness['evidence_submitted']:
        return False, "Evidences have already been submitted for verification."

    if readiness.get('has_missing_timeliness'):
        names = ', '.join(readiness['targets_missing_timeliness'])
        return False, f"Provide a completion duration for evidence already uploaded on: {names}."

    # Every Designated Faculty member -- plain or a Program Chair/RET Chair/Dean's own
    # IPCR -- has their evidence reviewed by the Dean, not a Program Chair; only Regular
    # Faculty goes through RET/Program Chair review first.
    try:
        target_ids = [t['target_id'] for t in dpcr_targets if t.get('target_id')]
        if target_ids:
            placeholders = ','.join(['%s'] * len(target_ids))
            update_sql = f"UPDATE tbl_committed_targets SET status = 'Submitted to Dean' WHERE emp_id = %s AND target_id IN ({placeholders})"
            cursor.execute(update_sql, [emp_id] + target_ids)
            conn.commit()
            return True, "Evidences successfully submitted to the Dean for verification."
    except Exception as e:
        conn.rollback()
        return False, f"Error submitting evidences: {str(e)}"


def lock_and_commit_designated_ipcr(conn, cursor, emp_id, term_id):
    """
    Locks the designated faculty / chair IPCR after Dean approval.
    Commits approved draft targets into tbl_committed_targets and locks them for evidence gathering.
    """
    try:
        cursor.execute(
            "SELECT overall_status, review_id FROM tbl_ipcr_dean_review WHERE emp_id = %s AND term_id = %s",
            (emp_id, term_id)
        )
        review_row = cursor.fetchone()
        if not review_row or review_row[0] != 'Approved':
            return False, "Your IPCR must be approved by the Dean before locking."

        review_id = review_row[1]

        # A Dean-formulated draft (save_and_issue_designated_draft_ipcr, app/models/dean.py)
        # never inserts this person's own Core instruction share into tbl_draft_targets at
        # issue time -- it can't, since the Program Chair may distribute it to them before or
        # after the Dean issues the rest of the draft. Folding it in here, at commit time,
        # makes the two actions order-independent: whichever happens last, this still picks it
        # up. A no-op for the classic self-submitted flow, where the row already exists
        # (inserted by submit_designated_ipcr from the person's own checkbox selection).
        for r in get_core_instruction_allocation(cursor, emp_id, term_id):
            # is_admin_function = 0 specifically: the same indicator can also carry this
            # person's departmental oversight copy (is_admin_function = 1, inserted separately
            # from get_oversight_targets) — that row existing must never be mistaken for the
            # personal Core share already being present. fetchall() (not fetchone()) drains the
            # cursor fully even if duplicates ever exist, since this connection isn't buffered
            # and a left-over unread row would break the very next execute() on this cursor.
            cursor.execute(
                "SELECT draft_id FROM tbl_draft_targets WHERE emp_id = %s AND indicator_id = %s AND is_admin_function = 0",
                (emp_id, r['indicator_id'])
            )
            if cursor.fetchall():
                continue
            desc, deadline, is_auto = describe_core_instruction_allocation(r)
            dur_value = r.get('target_duration_value')
            dur_unit = r.get('target_duration_unit')
            cursor.execute("""
                INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status,
                                               target_description, target_deadline,
                                               target_duration_value, target_duration_unit, is_admin_function,
                                               is_auto_description)
                VALUES (%s, %s, %s, 'Approved', %s, %s, %s, %s, 0, %s)
            """, (emp_id, r['indicator_id'], r['assigned_quantity'], desc, deadline, dur_value, dur_unit, is_auto))

        # Fetch approved draft items
        cursor.execute("""
            SELECT dt.indicator_id,
                   COALESCE(dri.reviewed_quantity, dt.proposed_quantity),
                   dt.target_description,
                   dt.target_deadline,
                   dt.target_duration_value,
                   dt.target_duration_unit,
                   dt.is_admin_function,
                   dt.is_auto_description
            FROM tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            LEFT JOIN tbl_ipcr_dean_review_items dri ON dt.draft_id = dri.draft_id AND dri.review_id = %s
            WHERE dt.emp_id = %s AND mi.term_id = %s
        """, (review_id, emp_id, term_id))
        draft_items = cursor.fetchall()

        if not draft_items:
            return False, "No draft targets found to commit."

        # Delete any existing committed targets for this term
        cursor.execute("""
            DELETE ct FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
        """, (emp_id, term_id))

        # Insert approved items into tbl_committed_targets
        for indicator_id, qty, target_desc, target_dead, dur_value, dur_unit, is_admin, is_auto_description in draft_items:
            if qty > 0:
                cursor.execute("""
                    INSERT INTO tbl_committed_targets (emp_id, indicator_id, assigned_quantity, status, actual_quantity,
                                                       target_description, target_deadline,
                                                       target_duration_value, target_duration_unit, is_admin_function,
                                                       is_auto_description)
                    VALUES (%s, %s, %s, 'Approved', 0, %s, %s, %s, %s, %s, %s)
                """, (emp_id, indicator_id, qty, target_desc, target_dead, dur_value, dur_unit, is_admin or 0,
                      is_auto_description))

        conn.commit()
        return True, "IPCR locked successfully and committed to evaluation targets."
    except Exception as e:
        conn.rollback()
        return False, str(e)
