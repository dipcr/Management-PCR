USE ipcr_db;

SET FOREIGN_KEY_CHECKS=0;

CREATE TABLE `tbl_academic_terms` (
  `term_id` int NOT NULL AUTO_INCREMENT,
  `academic_year` varchar(20) NOT NULL,
  `semester` varchar(20) NOT NULL,
  `period_start` date DEFAULT NULL,
  `period_end` date DEFAULT NULL,
  `is_active` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`term_id`)
) ENGINE=InnoDB AUTO_INCREMENT=59 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_audit_logs` (
  `log_id` int NOT NULL AUTO_INCREMENT,
  `log_timestamp` datetime DEFAULT CURRENT_TIMESTAMP,
  `actor_id` int DEFAULT NULL,
  `action_type` varchar(100) NOT NULL,
  `action_details` text NOT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`log_id`),
  KEY `fk_audit_actor` (`actor_id`),
  CONSTRAINT `fk_audit_actor` FOREIGN KEY (`actor_id`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=165 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_auth_credentials` (
  `emp_id` int NOT NULL,
  `corporate_email` varchar(150) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `last_login` datetime DEFAULT NULL,
  `verification_status` enum('PENDING','APPROVED','REJECTED') DEFAULT 'PENDING',
  PRIMARY KEY (`emp_id`),
  UNIQUE KEY `corporate_email` (`corporate_email`),
  CONSTRAINT `fk_auth_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_cascaded_quotas` (
  `quota_id` int NOT NULL AUTO_INCREMENT,
  `indicator_id` int NOT NULL,
  `total_target_value` int NOT NULL,
  `assigned_to_role` varchar(50) NOT NULL,
  `allow_chair_allocation` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`quota_id`),
  KEY `fk_quota_ind` (`indicator_id`),
  CONSTRAINT `fk_quota_ind` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`)
) ENGINE=InnoDB AUTO_INCREMENT=554 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_committed_targets` (
  `target_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `indicator_id` int NOT NULL,
  `assigned_quantity` int NOT NULL,
  `target_description` text,
  `target_deadline` varchar(50) DEFAULT NULL,
  `target_duration_value` int DEFAULT NULL,
  `target_duration_unit` enum('days','weeks','months','semesters') DEFAULT NULL,
  `status` varchar(50) DEFAULT 'Draft',
  `is_admin_function` tinyint(1) NOT NULL DEFAULT '0',
  `actual_quantity` int NOT NULL DEFAULT '0',
  `actual_duration_value` int DEFAULT NULL,
  `completion_status` enum('COMPLETED','PARTIAL_AT_DEADLINE','NOT_BEGUN') DEFAULT NULL,
  `efficiency_rating_E` int DEFAULT NULL,
  `print_remarks` varchar(255) DEFAULT NULL,
  `is_auto_description` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`target_id`),
  KEY `fk_target_emp` (`emp_id`),
  KEY `fk_target_ind` (`indicator_id`),
  CONSTRAINT `fk_target_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`),
  CONSTRAINT `fk_target_ind` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`)
) ENGINE=InnoDB AUTO_INCREMENT=709 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_criteria_weights` (
  `weight_id` int NOT NULL AUTO_INCREMENT,
  `term_id` int NOT NULL,
  `designation_type` enum('Regular Faculty','Designated Faculty') NOT NULL DEFAULT 'Regular Faculty',
  `ipcr_category_id` int NOT NULL,
  `rank_band` varchar(50) NOT NULL,
  `weight_pct` decimal(5,2) NOT NULL,
  PRIMARY KEY (`weight_id`),
  UNIQUE KEY `uq_weight` (`term_id`,`ipcr_category_id`,`rank_band`),
  KEY `fk_w_ipcr_cat` (`ipcr_category_id`),
  CONSTRAINT `fk_w_ipcr_cat` FOREIGN KEY (`ipcr_category_id`) REFERENCES `tbl_ipcr_categories` (`ipcr_category_id`),
  CONSTRAINT `fk_w_term` FOREIGN KEY (`term_id`) REFERENCES `tbl_academic_terms` (`term_id`)
) ENGINE=InnoDB AUTO_INCREMENT=256 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_departments` (
  `department_id` int NOT NULL AUTO_INCREMENT,
  `department_name` varchar(100) NOT NULL,
  `department_code` varchar(20) DEFAULT NULL,
  `display_order` int NOT NULL DEFAULT '100',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`department_id`),
  UNIQUE KEY `uq_department` (`department_name`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_draft_allocation` (
  `allocation_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `indicator_id` int NOT NULL,
  `assigned_quantity` int NOT NULL,
  `custom_description` text,
  `target_deadline` varchar(50) DEFAULT NULL,
  `target_duration_value` int DEFAULT NULL,
  `target_duration_unit` enum('days','weeks','months','semesters') DEFAULT NULL,
  `is_auto_description` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`allocation_id`),
  KEY `fk_draftalloc_emp` (`emp_id`),
  KEY `fk_draftalloc_ind` (`indicator_id`),
  CONSTRAINT `fk_draftalloc_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_draftalloc_ind` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2158 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_draft_targets` (
  `draft_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `indicator_id` int NOT NULL,
  `proposed_quantity` int NOT NULL,
  `target_description` text,
  `target_deadline` varchar(50) DEFAULT NULL,
  `target_duration_value` int DEFAULT NULL,
  `target_duration_unit` enum('days','weeks','months','semesters') DEFAULT NULL,
  `review_status` varchar(50) DEFAULT 'Pending Review' COMMENT 'Pending Review, Returned, or Approved',
  `is_admin_function` tinyint(1) NOT NULL DEFAULT '0',
  `is_auto_description` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`draft_id`),
  KEY `fk_drafttarget_emp` (`emp_id`),
  KEY `fk_drafttarget_ind` (`indicator_id`),
  CONSTRAINT `fk_drafttarget_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_drafttarget_ind` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3292 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_employee_profiles` (
  `emp_id` int NOT NULL AUTO_INCREMENT,
  `employee_id_number` varchar(50) NOT NULL,
  `first_name` varchar(100) NOT NULL,
  `last_name` varchar(100) NOT NULL,
  `college` varchar(100) NOT NULL DEFAULT 'CICT',
  `assigned_program` varchar(100) NOT NULL,
  `academic_rank` varchar(100) NOT NULL,
  `employment_status` varchar(50) NOT NULL,
  `designation` varchar(50) DEFAULT 'None',
  `leave_status` varchar(50) DEFAULT 'Active',
  `specialization` varchar(250) DEFAULT NULL,
  PRIMARY KEY (`emp_id`),
  UNIQUE KEY `employee_id_number` (`employee_id_number`)
) ENGINE=InnoDB AUTO_INCREMENT=104 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_evidence_repo` (
  `evidence_id` int NOT NULL AUTO_INCREMENT,
  `target_id` int NOT NULL,
  `file_path` varchar(255) NOT NULL,
  `actual_qty_Q` int NOT NULL,
  `verification_status` varchar(50) DEFAULT 'Pending',
  `supervisor_comment` text,
  PRIMARY KEY (`evidence_id`),
  KEY `fk_evid_target` (`target_id`),
  CONSTRAINT `fk_evid_target` FOREIGN KEY (`target_id`) REFERENCES `tbl_committed_targets` (`target_id`)
) ENGINE=InnoDB AUTO_INCREMENT=377 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_final_score_breakdown` (
  `breakdown_id` int NOT NULL AUTO_INCREMENT,
  `score_id` int NOT NULL,
  `weight_group` varchar(40) NOT NULL,
  `raw_avg` decimal(6,3) DEFAULT NULL,
  `weight_pct` decimal(5,2) DEFAULT NULL,
  `weighted_value` decimal(6,3) DEFAULT NULL,
  PRIMARY KEY (`breakdown_id`),
  KEY `fk_b_score` (`score_id`),
  CONSTRAINT `fk_b_score` FOREIGN KEY (`score_id`) REFERENCES `tbl_final_scores` (`score_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=135 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_final_scores` (
  `score_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `term_id` int NOT NULL,
  `final_score` decimal(4,2) NOT NULL,
  `adjectival_rating` varchar(50) NOT NULL,
  `dean_approval_status` varchar(50) DEFAULT 'Pending',
  PRIMARY KEY (`score_id`),
  KEY `fk_score_emp` (`emp_id`),
  KEY `fk_score_term` (`term_id`),
  CONSTRAINT `fk_score_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`),
  CONSTRAINT `fk_score_term` FOREIGN KEY (`term_id`) REFERENCES `tbl_academic_terms` (`term_id`)
) ENGINE=InnoDB AUTO_INCREMENT=46 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_institution_settings` (
  `setting_key` varchar(60) NOT NULL,
  `setting_value` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_approval_notifications` (
  `notification_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `term_id` int NOT NULL,
  `tier` varchar(30) NOT NULL,
  `event_type` varchar(60) NOT NULL,
  `recipient_emails` text NOT NULL,
  `sent_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `status` enum('SENT','FAILED','DEV_LOGGED') NOT NULL DEFAULT 'SENT',
  `error_message` text,
  PRIMARY KEY (`notification_id`),
  UNIQUE KEY `uq_emp_term_tier` (`emp_id`,`term_id`,`tier`),
  KEY `idx_emp_term` (`emp_id`,`term_id`),
  KEY `fk_notif_term` (`term_id`),
  CONSTRAINT `fk_notif_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_notif_term` FOREIGN KEY (`term_id`) REFERENCES `tbl_academic_terms` (`term_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_categories` (
  `ipcr_category_id` int NOT NULL AUTO_INCREMENT,
  `designation_type` varchar(50) NOT NULL,
  `category_name` varchar(120) NOT NULL,
  `display_order` int NOT NULL DEFAULT '100',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`ipcr_category_id`),
  UNIQUE KEY `uq_ipcr_cat` (`designation_type`,`category_name`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_category_types` (
  `ipcr_category_id` int NOT NULL,
  `category_id` int NOT NULL,
  PRIMARY KEY (`ipcr_category_id`,`category_id`),
  KEY `fk_ict_type` (`category_id`),
  CONSTRAINT `fk_ict_cat` FOREIGN KEY (`ipcr_category_id`) REFERENCES `tbl_ipcr_categories` (`ipcr_category_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ict_type` FOREIGN KEY (`category_id`) REFERENCES `tbl_target_categories` (`category_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_chair_review` (
  `review_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `term_id` int NOT NULL,
  `chair_emp_id` int NOT NULL,
  `overall_status` enum('Pending','Approved','Rejected') DEFAULT 'Pending',
  `overall_remarks` text,
  `reviewed_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`review_id`),
  UNIQUE KEY `uq_review` (`emp_id`,`term_id`),
  KEY `fk_chair_review_term` (`term_id`),
  KEY `fk_chair_review_chair` (`chair_emp_id`),
  CONSTRAINT `fk_chair_review_chair` FOREIGN KEY (`chair_emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`),
  CONSTRAINT `fk_chair_review_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_chair_review_term` FOREIGN KEY (`term_id`) REFERENCES `tbl_academic_terms` (`term_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=100 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_chair_review_items` (
  `item_id` int NOT NULL AUTO_INCREMENT,
  `review_id` int NOT NULL,
  `draft_id` int DEFAULT NULL,
  `indicator_id` int NOT NULL,
  `original_quantity` int NOT NULL,
  `reviewed_quantity` int NOT NULL,
  `item_remarks` varchar(1000) DEFAULT NULL,
  PRIMARY KEY (`item_id`),
  UNIQUE KEY `uq_chair_review_item` (`review_id`,`draft_id`),
  KEY `fk_chair_item_draft` (`draft_id`),
  KEY `fk_chair_item_ind` (`indicator_id`),
  CONSTRAINT `fk_chair_item_draft` FOREIGN KEY (`draft_id`) REFERENCES `tbl_draft_targets` (`draft_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_chair_item_ind` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`) ON DELETE CASCADE,
  CONSTRAINT `tbl_ipcr_chair_review_items_ibfk_1` FOREIGN KEY (`review_id`) REFERENCES `tbl_ipcr_chair_review` (`review_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=725 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_dean_review` (
  `review_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `term_id` int NOT NULL,
  `dean_id` int NOT NULL,
  `overall_status` varchar(20) DEFAULT 'Pending',
  `overall_remarks` text,
  `reviewed_at` datetime DEFAULT NULL,
  PRIMARY KEY (`review_id`),
  UNIQUE KEY `uq_dean_review` (`emp_id`,`term_id`),
  KEY `fk_dean_review_term` (`term_id`),
  KEY `fk_dean_review_dean` (`dean_id`),
  CONSTRAINT `fk_dean_review_dean` FOREIGN KEY (`dean_id`) REFERENCES `tbl_employee_profiles` (`emp_id`),
  CONSTRAINT `fk_dean_review_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_dean_review_term` FOREIGN KEY (`term_id`) REFERENCES `tbl_academic_terms` (`term_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=73 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_dean_review_items` (
  `item_id` int NOT NULL AUTO_INCREMENT,
  `review_id` int NOT NULL,
  `draft_id` int DEFAULT NULL,
  `indicator_id` int NOT NULL,
  `original_quantity` int DEFAULT '0',
  `reviewed_quantity` int DEFAULT '0',
  `item_remarks` text,
  PRIMARY KEY (`item_id`),
  UNIQUE KEY `uq_dean_review_item` (`review_id`,`draft_id`),
  KEY `fk_dean_item_draft` (`draft_id`),
  KEY `fk_dean_item_ind` (`indicator_id`),
  CONSTRAINT `fk_dean_item_draft` FOREIGN KEY (`draft_id`) REFERENCES `tbl_draft_targets` (`draft_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_dean_item_ind` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_dean_item_review` FOREIGN KEY (`review_id`) REFERENCES `tbl_ipcr_dean_review` (`review_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=560 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_ret_review` (
  `review_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `term_id` int NOT NULL,
  `ret_chair_emp_id` int NOT NULL,
  `overall_status` enum('Pending','Approved','Rejected') DEFAULT 'Pending',
  `overall_remarks` text,
  `reviewed_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`review_id`),
  UNIQUE KEY `uq_ret_review` (`emp_id`,`term_id`),
  KEY `fk_ret_review_term` (`term_id`),
  KEY `fk_ret_review_chair` (`ret_chair_emp_id`),
  CONSTRAINT `fk_ret_review_chair` FOREIGN KEY (`ret_chair_emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`),
  CONSTRAINT `fk_ret_review_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ret_review_term` FOREIGN KEY (`term_id`) REFERENCES `tbl_academic_terms` (`term_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=75 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_ret_review_items` (
  `item_id` int NOT NULL AUTO_INCREMENT,
  `review_id` int NOT NULL,
  `draft_id` int DEFAULT NULL,
  `indicator_id` int NOT NULL,
  `original_quantity` int NOT NULL,
  `reviewed_quantity` int NOT NULL,
  `item_remarks` varchar(1000) DEFAULT NULL,
  PRIMARY KEY (`item_id`),
  UNIQUE KEY `uq_ret_review_item` (`review_id`,`draft_id`),
  KEY `review_id` (`review_id`),
  KEY `fk_ret_item_draft` (`draft_id`),
  KEY `fk_ret_item_ind` (`indicator_id`),
  CONSTRAINT `fk_ret_item_draft` FOREIGN KEY (`draft_id`) REFERENCES `tbl_draft_targets` (`draft_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_ret_item_ind` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`) ON DELETE CASCADE,
  CONSTRAINT `tbl_ipcr_ret_review_items_ibfk_1` FOREIGN KEY (`review_id`) REFERENCES `tbl_ipcr_ret_review` (`review_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=125 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ipcr_signatories` (
  `signatory_id` int NOT NULL AUTO_INCREMENT,
  `block_key` enum('REVIEWED_BY','APPROVED_BY','ASSESSED_BY','FINAL_RATING_BY') NOT NULL,
  `designation_type` enum('Regular Faculty','Designated Faculty') DEFAULT NULL,
  `source` enum('FIXED','PROGRAM_CHAIR','DEAN') NOT NULL DEFAULT 'FIXED',
  `full_name` varchar(150) DEFAULT NULL,
  `position_title` varchar(150) DEFAULT NULL,
  PRIMARY KEY (`signatory_id`),
  UNIQUE KEY `uq_block` (`block_key`,`designation_type`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_master_indicators` (
  `indicator_id` int NOT NULL AUTO_INCREMENT,
  `category_id` int NOT NULL,
  `indicator_description` text NOT NULL,
  `efficiency_type` varchar(50) NOT NULL,
  `term_id` int DEFAULT NULL,
  `is_custom` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`indicator_id`),
  KEY `fk_master_cat` (`category_id`),
  KEY `fk_master_ind_term` (`term_id`),
  CONSTRAINT `fk_master_cat` FOREIGN KEY (`category_id`) REFERENCES `tbl_target_categories` (`category_id`),
  CONSTRAINT `fk_master_ind_term` FOREIGN KEY (`term_id`) REFERENCES `tbl_academic_terms` (`term_id`)
) ENGINE=InnoDB AUTO_INCREMENT=529 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ret_assignments` (
  `assignment_id` int NOT NULL AUTO_INCREMENT,
  `emp_id` int NOT NULL,
  `indicator_id` int NOT NULL,
  `target_quantity` int NOT NULL DEFAULT '1',
  `target_description` text,
  `target_duration_value` int DEFAULT NULL,
  `target_duration_unit` enum('days','weeks','months','semesters') DEFAULT NULL,
  `assigned_by` int DEFAULT NULL,
  `is_auto_description` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`assignment_id`),
  UNIQUE KEY `uk_assign` (`emp_id`,`indicator_id`),
  KEY `fk_ra_ind` (`indicator_id`),
  KEY `fk_ra_assigned_by` (`assigned_by`),
  CONSTRAINT `fk_ra_assigned_by` FOREIGN KEY (`assigned_by`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_ra_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_ra_ind` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=23 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ret_rule_indicators` (
  `rule_indicator_id` int NOT NULL AUTO_INCREMENT,
  `rule_id` int NOT NULL,
  `indicator_id` int NOT NULL,
  `target_quantity` int DEFAULT '1',
  `target_description` text,
  `target_duration_value` int DEFAULT NULL,
  `target_duration_unit` enum('days','weeks','months','semesters') DEFAULT NULL,
  `is_auto_description` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`rule_indicator_id`),
  KEY `rule_id` (`rule_id`),
  KEY `indicator_id` (`indicator_id`),
  CONSTRAINT `tbl_ret_rule_indicators_ibfk_1` FOREIGN KEY (`rule_id`) REFERENCES `tbl_ret_rules` (`rule_id`) ON DELETE CASCADE,
  CONSTRAINT `tbl_ret_rule_indicators_ibfk_2` FOREIGN KEY (`indicator_id`) REFERENCES `tbl_master_indicators` (`indicator_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=115 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_ret_rules` (
  `rule_id` int NOT NULL AUTO_INCREMENT,
  `academic_rank` varchar(255) NOT NULL,
  `required_selections` int NOT NULL,
  `is_locked` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`rule_id`)
) ENGINE=InnoDB AUTO_INCREMENT=56 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_system_access` (
  `emp_id` int NOT NULL,
  `system_role` varchar(50) NOT NULL,
  `account_status` varchar(50) DEFAULT 'Pending',
  PRIMARY KEY (`emp_id`),
  CONSTRAINT `fk_access_emp` FOREIGN KEY (`emp_id`) REFERENCES `tbl_employee_profiles` (`emp_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_target_categories` (
  `category_id` int NOT NULL AUTO_INCREMENT,
  `category_name` varchar(100) NOT NULL,
  `slug` varchar(40) DEFAULT NULL,
  `review_lane` enum('CHAIR','RET') NOT NULL DEFAULT 'CHAIR',
  `is_core` tinyint(1) NOT NULL DEFAULT '1',
  `display_order` int NOT NULL DEFAULT '100',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`category_id`),
  UNIQUE KEY `category_name` (`category_name`),
  UNIQUE KEY `uq_cat_slug` (`slug`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `tbl_teaching_load_config` (
  `config_id` int NOT NULL AUTO_INCREMENT,
  `term_id` int NOT NULL,
  `designation_type` enum('Regular Faculty','Designated Faculty') NOT NULL,
  `rank_band` varchar(50) NOT NULL DEFAULT 'General',
  `hours` int NOT NULL,
  `duration_value` int NOT NULL DEFAULT '6',
  `duration_unit` enum('days','weeks','months','semesters') NOT NULL DEFAULT 'months',
  PRIMARY KEY (`config_id`),
  UNIQUE KEY `uq_teaching_load` (`term_id`,`designation_type`,`rank_band`),
  CONSTRAINT `fk_tl_term` FOREIGN KEY (`term_id`) REFERENCES `tbl_academic_terms` (`term_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=124 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
-- Procedures
DELIMITER $$
CREATE PROCEDURE `get_user_by_email`(IN p_email VARCHAR(255))
BEGIN
    SELECT 
        a.emp_id,
        a.password_hash,
        a.verification_status,
        s.system_role
    FROM tbl_auth_credentials a
    LEFT JOIN tbl_system_access s ON a.emp_id = s.emp_id
    WHERE a.corporate_email = p_email;
END $$

DELIMITER ;

DELIMITER $$
CREATE PROCEDURE `register_user`(
    IN p_employee_id_number VARCHAR(50),
    IN p_email VARCHAR(150),
    IN p_password_hash VARCHAR(255)
)
BEGIN
    DECLARE v_emp_id INT DEFAULT NULL;
    DECLARE v_designation VARCHAR(50) DEFAULT NULL;
    DECLARE v_role VARCHAR(50) DEFAULT 'FACULTY';
    DECLARE v_exists INT DEFAULT 0;

    SELECT emp_id, designation INTO v_emp_id, v_designation
    FROM tbl_employee_profiles
    WHERE employee_id_number = p_employee_id_number;

    IF v_emp_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Employee ID Number is not recognized by HR. Please contact the administrator.';
    END IF;

    SELECT COUNT(*) INTO v_exists
    FROM tbl_auth_credentials
    WHERE emp_id = v_emp_id;

    IF v_exists > 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'This employee account has already been claimed.';
    END IF;

    SELECT COUNT(*) INTO v_exists
    FROM tbl_auth_credentials
    WHERE corporate_email = p_email;

    IF v_exists > 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'This corporate email is already registered to another account.';
    END IF;

    IF v_designation = 'Admin' THEN
        SET v_role = 'Admin';
    ELSEIF v_designation = 'Dean' THEN
        SET v_role = 'DEAN';
    ELSEIF v_designation = 'Program Chair' THEN
        SET v_role = 'PROGRAM_CHAIR';
    ELSEIF v_designation = 'RET Chair' THEN
        SET v_role = 'RET_CHAIR';
    ELSEIF v_designation = 'Designated Faculty' THEN
        SET v_role = 'DESIGNATED_FACULTY';
    ELSE
        SET v_role = 'FACULTY';
    END IF;

    INSERT INTO tbl_auth_credentials (emp_id, corporate_email, password_hash, verification_status)
    VALUES (v_emp_id, p_email, p_password_hash, 'APPROVED');

    INSERT INTO tbl_system_access (emp_id, system_role, account_status)
    VALUES (v_emp_id, v_role, 'Active')
    ON DUPLICATE KEY UPDATE system_role = v_role, account_status = 'Active';

END $$

DELIMITER ;

DELIMITER $$
CREATE TRIGGER `trg_sync_faculty_role` AFTER UPDATE ON `tbl_employee_profiles` FOR EACH ROW BEGIN
    DECLARE v_new_role VARCHAR(50);

    -- Only execute synchronization if the designation column actually changed
    IF OLD.designation <> NEW.designation THEN
        IF NEW.designation = 'Dean' THEN
            SET v_new_role = 'DEAN';
        ELSEIF NEW.designation = 'RET Chair' THEN
            SET v_new_role = 'RET_CHAIR';
        ELSEIF NEW.designation = 'Program Chair' THEN
            SET v_new_role = 'PROGRAM_CHAIR';
        ELSEIF NEW.designation = 'Designated Faculty' THEN
            SET v_new_role = 'DESIGNATED_FACULTY';
        ELSE
            SET v_new_role = 'FACULTY';
        END IF;

        UPDATE `tbl_system_access`
        SET `system_role` = v_new_role
        WHERE `emp_id` = NEW.emp_id;
    END IF;
END $$

DELIMITER ;

SET FOREIGN_KEY_CHECKS=1;