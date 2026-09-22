-- MIGRATION_group21.sql
-- Composite uniqueness on tbl_academic_terms(academic_year, semester).
--
-- The Admin "Open New Term" form now checks for an existing row with the same Academic Year
-- + Semester before inserting (see app/models/term.py::open_new_term), but that is an
-- application-level guard only -- it does not stop a duplicate being written by any other
-- path (a race between two concurrent requests, a direct DB write, a future script). This
-- constraint is the database-level backstop for the same rule.
--
-- NOT auto-applied by this file as written -- verified against the live ipcr_db before
-- writing this, and it already has pre-existing duplicate rows that a UNIQUE constraint
-- would reject outright:
--   ('2030-2031',  '2nd Semester', 2 rows)
--   ('2038-2039',  '1st Semester', 4 rows)
--   ('2049-2050',  '2nd Semester', 2 rows)
--   ('2051 - 2052','2nd Semester', 2 rows)
--   ('2052 - 2053','1st Semester', 3 rows)
-- Which term_id in each group is the one to keep (and what happens to cascading/weighting
-- rows and committed IPCRs already keyed to the term_ids being retired) is a data decision
-- for whoever runs this, not something to decide silently in a migration script. Resolve
-- those groups first -- e.g. re-point child rows at the term_id to keep, then delete the
-- others -- and only then run the ALTER TABLE below.
--
-- Run AFTER MIGRATION_group20.sql, with a DDL-privileged account -- run_migration.py
-- authenticates as app_user, which holds no DDL rights.

USE ipcr_db;

ALTER TABLE `tbl_academic_terms`
  ADD CONSTRAINT `uq_academic_terms_year_semester` UNIQUE (`academic_year`, `semester`);
