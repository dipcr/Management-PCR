"""
Service layer modules for Management-PCR.
"""
from app.services.mail_service import send_async_email
from app.services.notification_service import (
    send_target_submission_notification,
    send_ret_approval_notifications,
    send_chair_approval_notification,
    send_return_notification,
    send_designated_target_submission_notification,
    send_designated_target_decision_notification,
    send_evidence_submission_notification,
    send_evidence_package_to_dean_notification,
    check_and_trigger_evidence_approved_notification,
    check_and_trigger_tier2_notification,
    send_evidence_return_notification,
)

__all__ = [
    'send_async_email',
    'send_target_submission_notification',
    'send_ret_approval_notifications',
    'send_chair_approval_notification',
    'send_return_notification',
    'send_designated_target_submission_notification',
    'send_designated_target_decision_notification',
    'send_evidence_submission_notification',
    'send_evidence_package_to_dean_notification',
    'check_and_trigger_evidence_approved_notification',
    'check_and_trigger_tier2_notification',
    'send_evidence_return_notification',
]
