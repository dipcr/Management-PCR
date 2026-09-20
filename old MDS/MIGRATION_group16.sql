-- MIGRATION_group16.sql
-- Column cleanup and one silently-failing enum.
--
-- Run AFTER MIGRATION_group15.sql.

-- =============================================================================
-- 1. Drop a dead column
-- =============================================================================
--
-- tbl_draft_targets.manager_feedback: zero references anywhere in app/, and zero
-- non-empty values across all 1157 rows. Reviewer remarks live in
-- tbl_ipcr_chair_review_items.item_remarks (and the RET/dean equivalents) instead.

ALTER TABLE tbl_draft_targets DROP COLUMN manager_feedback;

-- =============================================================================
-- 2. Widen tbl_ipcr_approval_notifications.tier
-- =============================================================================
--
-- The column is enum('TIER_1','TIER_2'), but app/services/notification_service.py
-- inserts the literal 'TIER1_EVIDENCE' (twice). Both inserts sit inside a
-- try/except that only logs a warning, so every Tier-1 evidence notification has
-- been failing to record silently -- the table has 0 rows despite AUTO_INCREMENT=8.
--
-- Widening rather than editing the literals keeps both existing tier vocabularies
-- valid, and matches the VARCHAR(30) the (now-removed) in-code CREATE TABLE used.

ALTER TABLE tbl_ipcr_approval_notifications MODIFY COLUMN tier varchar(30) NOT NULL;

-- =============================================================================
-- NOT dropped here, deliberately -- do not "finish the job" without checking first
-- =============================================================================
--
-- is_auto_description (on tbl_committed_targets, tbl_draft_allocation,
-- tbl_draft_targets, tbl_ret_assignments, tbl_ret_extension_distribution and
-- tbl_ret_rule_indicators) is referenced NOWHERE in this repository -- not in code,
-- not in any migration, not in any doc -- yet all six columns exist on the shared
-- database with 646 rows populated. Someone applied it by hand. Nothing reads it,
-- but dropping it destroys data whose meaning is recorded nowhere. Ask the team
-- first. It is added to db/schema.sql so a fresh Docker build at least matches.
--
-- Correction (2026-09-20): the "referenced NOWHERE" claim above is no longer
-- accurate -- the auto-generated-vs-customized description feature built after
-- this migration (see MIGRATION_group11.sql) made heavy use of this column across
-- dean.py, designated.py, faculty.py, prog_chair.py, ret_chair.py and scoring.py.
-- Left as-is below as a historical record of what was true when this file was
-- written; do not treat this file as current documentation of the column's usage.
--
-- tbl_ret_rules.is_locked is also unread by code, but its values map exactly onto
-- the research (0) / extension (1) split -- it is the category discriminator that
-- tbl_ret_rules is otherwise missing, and the deferred RET normalization needs it.
