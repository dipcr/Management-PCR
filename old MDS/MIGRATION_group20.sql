-- MIGRATION_group20.sql
-- Declare the last undeclared relationship: tbl_ret_assignments.assigned_by.
--
-- assigned_by holds the emp_id of the RET Chair who authored the assignment, but carried no
-- foreign key. After MIGRATION_group19 gave tbl_audit_logs.actor_id its constraint, this was
-- the only remaining column in the schema that names a person without declaring the
-- relationship -- it does not end in "_id", which is why it survived earlier sweeps.
--
-- Verified against the live ipcr_db before writing this file:
--   * column is already INT NULL, and tbl_employee_profiles.emp_id is INT -- types match
--   * 16 rows, 0 NULL, 0 orphans
--   * no constraint named fk_ra_assigned_by exists yet
--
-- ON DELETE SET NULL, matching fk_audit_actor and for the same reason: the assignment is a
-- record of work given to a faculty member and must outlive the chair who created it.
-- CASCADE would delete a faculty member's targets because a chair's profile was removed.
--
-- This table already has fk_ra_emp pointing at tbl_employee_profiles. Two foreign keys from
-- one table to the same parent is NOT a redundant relationship -- they are different roles
-- (the faculty member who receives the target vs the chair who assigned it), exactly like
-- tbl_ipcr_chair_review.emp_id vs .chair_emp_id. It adds no new path between the two tables,
-- so the number of closed shapes in the ERD is unchanged at 15.
--
-- No application code changes accompany this migration.
--
-- Run AFTER MIGRATION_group19.sql, with a DDL-privileged account -- run_migration.py
-- authenticates as app_user, which holds no DDL rights.

USE ipcr_db;

ALTER TABLE `tbl_ret_assignments`
  ADD CONSTRAINT `fk_ra_assigned_by` FOREIGN KEY (`assigned_by`)
    REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE SET NULL;
