-- MIGRATION_group19.sql
-- Give tbl_audit_logs a real relationship to the person who acted.
--
-- tbl_audit_logs.actor_id was the only *_id column in the whole schema that is neither a
-- primary key nor a foreign key. It is declared varchar(50) but holds what is really an
-- emp_id, so the audit trail had no relationship to tbl_employee_profiles and the table
-- floated unconnected in the ERD.
--
-- Verified against the live ipcr_db before writing this file:
--   * 163 rows, all 163 numeric, 0 NULL
--   * 0 orphans -- every actor_id already matches an existing tbl_employee_profiles.emp_id
--
-- ON DELETE SET NULL, not CASCADE: an audit trail has to survive the deletion of the person
-- it refers to. Cascading would erase the log entry along with the employee, which defeats
-- the point of keeping one. That is also why the column stays nullable.
--
-- Note this does NOT affect the "circular connections" finding -- it adds a relationship
-- rather than removing one. It addresses the separate criticism of isolated tables, taking
-- them from 4 to 3 (tbl_departments, tbl_institution_settings and tbl_ipcr_signatories
-- remain; see the plan for why tbl_departments is deferred).
--
-- Run AFTER MIGRATION_group18.sql, with a DDL-privileged account -- run_migration.py
-- authenticates as app_user, which holds no DDL rights.

USE ipcr_db;

ALTER TABLE `tbl_audit_logs`
  MODIFY COLUMN `actor_id` INT NULL;

ALTER TABLE `tbl_audit_logs`
  ADD CONSTRAINT `fk_audit_actor` FOREIGN KEY (`actor_id`)
    REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE SET NULL;
