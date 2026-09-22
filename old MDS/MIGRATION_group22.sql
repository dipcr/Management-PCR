-- MIGRATION_group22.sql
-- Add tbl_academic_terms.faculty_config_reviewed, backing the Admin dashboard's
-- "recheck Faculty Configuration" banner shown after a new term opens.
--
-- Opening a term (app/models/term.py::open_new_term) never touches faculty
-- specialization/rank/designation -- those carry over unchanged from whatever
-- was last saved, which is often stale by the time a new term starts (e.g. a
-- newly promoted Program Chair whose designation was never updated in Faculty
-- Configuration). This column tracks, per term, whether the Admin has
-- confirmed the roster is current for that term. It defaults to un-reviewed
-- (0) so every newly opened term prompts a check, and is flipped to 1 via a
-- new "Mark as Reviewed" action (app/routes/admin.py::admin_mark_faculty_reviewed)
-- once the Admin has looked at Faculty Configuration.
--
-- Verified against the live ipcr_db before writing this file: tbl_academic_terms
-- has no column by this name yet.
--
-- Run AFTER MIGRATION_group21.sql, with a DDL-privileged account -- run_migration.py
-- authenticates as app_user, which holds no DDL rights.

USE ipcr_db;

ALTER TABLE `tbl_academic_terms`
  ADD COLUMN `faculty_config_reviewed` TINYINT(1) NOT NULL DEFAULT 0
    AFTER `is_active`;
