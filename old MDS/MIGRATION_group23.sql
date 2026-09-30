-- MIGRATION_group23.sql
-- Add tbl_committed_targets.reopen_request, backing the "Request to Add Evidence" flow.
--
-- After the Dean gives final approval, every target sits at status 'Dean Approved' and the
-- upload route refuses new evidence. A faculty member who still has time before the
-- deadline can now ask the Dean to reopen their IPCR. The request is recorded here rather
-- than as a new target status: 'Dean Approved' is matched by ~14 queries/checks (locked
-- lists, "is final" gates, the Dean's Completed list), and a request that is still waiting
-- must keep behaving exactly like an approved IPCR everywhere. A nullable column leaves all
-- of those untouched.
--
--   NULL          no request pending (the default for every existing row)
--   non-empty     the faculty member's reason; a request is pending
--
-- The reason is written to every target row of the requester for the term, so the Dean-side
-- code reads it with MAX() and clears it from all rows together. Approve sets the targets
-- back to status 'Approved' (the same pre-submission state a Returned evidence file uses)
-- and clears this column; Deny only clears it.
--
-- Both INSERT INTO tbl_committed_targets statements in the app list their columns
-- explicitly and nothing SELECTs * from this table, so a nullable column is safe.
--
-- Run AFTER MIGRATION_group22.sql, with a DDL-privileged account -- run_migration.py
-- authenticates as app_user, which holds no DDL rights.

USE ipcr_db;

ALTER TABLE `tbl_committed_targets`
  ADD COLUMN `reopen_request` VARCHAR(255) DEFAULT NULL
    AFTER `print_remarks`;
