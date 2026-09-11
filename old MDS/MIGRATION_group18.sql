-- MIGRATION_group18.sql
-- Remove the redundant relationships to tbl_academic_terms.
--
-- The Database Panel rejected the ERD for "circular connections" on tbl_academic_terms.
-- Three tables held a DIRECT foreign key to tbl_academic_terms while ALSO reaching it
-- through tbl_master_indicators:
--
--     X.term_id ---------------------------------------> tbl_academic_terms
--     X.indicator_id -> tbl_master_indicators.term_id --^
--
-- That is a redundant relationship in ER terms, and a transitive dependency in
-- normalisation terms (3NF): term_id is functionally determined by indicator_id, not by
-- the table's own key. Verified against live ipcr_db before writing this file:
--
--   * 0 rows where X.term_id <> its indicator's term_id, across all 519 rows of the
--     three tables
--   * 0 indicators belong to more than one term; 0 NULL term_id on tbl_master_indicators
--   * term_id is never SELECTed out of these tables -- only filtered, joined and inserted
--   * two queries already asserted the dependency by hand
--     (routes/designated.py "AND cq.term_id = mi.term_id"), which is the redundancy
--     written out in query form
--
-- After this migration no table reaches tbl_academic_terms both directly and indirectly,
-- and its incoming relationships drop from 11 to 8.
--
-- Run AFTER MIGRATION_group17.sql, with a DDL-privileged account -- run_migration.py
-- authenticates as app_user, which holds no DDL rights.

USE ipcr_db;

-- 1. tbl_ret_extension_distribution is dead. The RET/Extension refactor
--    (MIGRATION_group13.sql + "REVISION MDs/ret_menu_and_extension_distribution_refactor.md")
--    moved Extension configuration into tbl_ret_rules / tbl_ret_rule_indicators. The table
--    retains 37 legacy rows but no code in app/ reads or writes it. Dropping it removes one
--    redundant relationship and one box from the ERD outright.
DROP TABLE IF EXISTS `tbl_ret_extension_distribution`;

-- 2. tbl_cascaded_quotas: the term comes from the indicator.
--    Dropping the FK also drops its backing KEY of the same name.
ALTER TABLE `tbl_cascaded_quotas`
  DROP FOREIGN KEY `fk_quota_term`;
ALTER TABLE `tbl_cascaded_quotas`
  DROP COLUMN `term_id`;

-- 3. tbl_ret_assignments: same, plus the unique key loses its now-redundant leading column.
--    (emp_id, indicator_id) stays exactly as strict as (term_id, emp_id, indicator_id) was,
--    because the indicator already determines the term.
ALTER TABLE `tbl_ret_assignments`
  DROP FOREIGN KEY `fk_ra_term`;
ALTER TABLE `tbl_ret_assignments`
  DROP INDEX `uk_assign`,
  DROP COLUMN `term_id`,
  ADD UNIQUE KEY `uk_assign` (`emp_id`, `indicator_id`);
