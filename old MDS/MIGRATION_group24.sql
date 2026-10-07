-- MIGRATION_group24: display-only job title for plain Designated Faculty.
-- `designation` keeps driving weights/routing/roles; this column only changes what is
-- printed on the IPCR and shown on dashboards. NULL/blank falls back to `designation`.
ALTER TABLE tbl_employee_profiles
  ADD COLUMN designation_title VARCHAR(150) NULL DEFAULT NULL AFTER designation;
