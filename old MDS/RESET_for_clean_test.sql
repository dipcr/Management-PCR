-- Clean slate for a full test run.
--
-- Clears every piece of *transactional* data — terms, targets, evidence, reviews, scores —
-- while keeping the configuration and accounts the system cannot rebuild by itself.
--
-- Read the "DO NOT TRUNCATE" section at the bottom before changing anything here.

USE ipcr_db;

SET FOREIGN_KEY_CHECKS = 0;

-- ── Evidence and scores ──────────────────────────────────────────────────────
TRUNCATE TABLE tbl_evidence_repo;
TRUNCATE TABLE tbl_final_score_breakdown;
TRUNCATE TABLE tbl_final_scores;

-- ── Reviews ──────────────────────────────────────────────────────────────────
TRUNCATE TABLE tbl_ipcr_chair_review_items;
TRUNCATE TABLE tbl_ipcr_chair_review;
TRUNCATE TABLE tbl_ipcr_ret_review_items;
TRUNCATE TABLE tbl_ipcr_ret_review;
TRUNCATE TABLE tbl_ipcr_dean_review_items;
TRUNCATE TABLE tbl_ipcr_dean_review;

-- ── Targets ──────────────────────────────────────────────────────────────────
TRUNCATE TABLE tbl_committed_targets;
TRUNCATE TABLE tbl_draft_targets;
TRUNCATE TABLE tbl_draft_allocation;

-- ── RET configuration (rules are term-specific by design) ────────────────────
TRUNCATE TABLE tbl_ret_rule_indicators;
TRUNCATE TABLE tbl_ret_rules;
TRUNCATE TABLE tbl_ret_assignments;

-- ── Term-scoped setup, rebuilt in Phase A ────────────────────────────────────
TRUNCATE TABLE tbl_cascaded_quotas;
TRUNCATE TABLE tbl_master_indicators;
TRUNCATE TABLE tbl_criteria_weights;
TRUNCATE TABLE tbl_teaching_load_config;
TRUNCATE TABLE tbl_academic_terms;

-- ── Audit trail ──────────────────────────────────────────────────────────────
TRUNCATE TABLE tbl_audit_logs;

SET FOREIGN_KEY_CHECKS = 1;


-- ═════════════════════════════════════════════════════════════════════════════
-- DO NOT TRUNCATE THESE
-- ═════════════════════════════════════════════════════════════════════════════
--
-- ACCOUNTS — safe to truncate ONLY if you then run bootstrap_admin.py.
--   tbl_employee_profiles
--   tbl_auth_credentials
--   tbl_system_access
--
--   Registration runs through the register_user stored procedure, which *claims* an
--   existing profile by employee_id_number. With no profiles there is nothing to claim,
--   and with no Admin nobody can create profiles — so clearing these locks everyone out
--   until an Admin is written directly:
--
--       python bootstrap_admin.py
--
--   To also wipe accounts, add these to the truncate block above:
--       TRUNCATE TABLE tbl_auth_credentials;
--       TRUNCATE TABLE tbl_system_access;
--       TRUNCATE TABLE tbl_employee_profiles;
--   then bootstrap an Admin, log in, and rebuild the roster (Phase L).
--
-- TARGET TYPES — rebuildable, but only if you set the slug by hand.
--   tbl_target_categories
--
--   23 places in the application match exact slugs: 'instruction', 'research',
--   'extension', 'support', 'administrative', 'custom'. Admin -> Criteria now has a
--   Slug field for exactly this — leave it blank for a new type, and type the exact
--   value when rebuilding a built-in one. A generated slug such as 'a_instructions'
--   matches nothing, and targets stop routing silently.
--
-- IPCR CATEGORIES — rebuildable, but only if you also redo the type mappings.
--   tbl_ipcr_categories
--   tbl_ipcr_category_types
--
-- PRINTED-IPCR CONFIG — one of these cannot be recreated at all.
--   tbl_institution_settings   (recoverable: the Admin panel upserts it)
--   tbl_ipcr_signatories       (self-healing: opening Admin -> Institution Setup
--                               recreates the five standard blocks if they are missing,
--                               leaving any already configured exactly as they were.
--                               Names still have to be re-entered.)
--
-- DEPARTMENTS — rebuildable through Institution Setup, but faculty specialization
-- values must keep matching department_name or targets stop routing.
--   tbl_departments


-- ═════════════════════════════════════════════════════════════════════════════
-- AFTER RUNNING
-- ═════════════════════════════════════════════════════════════════════════════
--
-- 1. Uploaded evidence files are still on disk in app/uploads/evidence/ but no longer
--    referenced. Delete them if you want a genuinely clean state:
--       rm app/uploads/evidence/*.pdf
--
-- 2. Confirm the configuration survived — each of these should return rows:
--       SELECT COUNT(*) FROM tbl_target_categories;    -- expect the seeded types
--       SELECT COUNT(*) FROM tbl_ipcr_categories;      -- expect 5
--       SELECT COUNT(*) FROM tbl_ipcr_signatories;     -- expect 5 (or open the Admin panel once)
--       SELECT COUNT(*) FROM tbl_departments;          -- expect your programs
--       SELECT COUNT(*) FROM tbl_employee_profiles;    -- expect your people
--
-- 3. Start the test script at Phase A1 (open a term). Phase 0 still works because
--    accounts were preserved.
