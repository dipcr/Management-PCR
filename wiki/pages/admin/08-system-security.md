# Admin — System Security

Emergency access controls and the read-only activity audit log.

![System Security](/static/img/admin/08-system-security.png)

## Emergency access controls

Search or filter the user list (by name, role or status), then use:

- **Issue Temp Password** — generates a temporary password for an account. You must relay it
  to the user directly.
- **Lock Account** — forces the account to `Locked`; the user can no longer sign in.

> These are emergency actions. Every one is permanently recorded in the audit log.

## Activity audit log

The **Activity Audit Log** shows the last 50 actions, newest first, with
**Timestamp**, **Actor**, **Action**, **Details** and **IP Address**. Use the search box to
filter.

Events you will see include:

| Action | Raised by |
| --- | --- |
| `Profile Created` / `Profile Updated` | Admin saving a roster entry |
| `CSV Roster Import` | Admin importing a roster |
| `Account Claim Requested` | A person claiming their account |
| `Account Claim Approved` / `Account Claim Denied` | Admin acting on a claim |
| `Term Opened` | Admin opening a term |

## Recommended practice

- Review the audit log after any bulk change (CSV import, term switch).
- Use **Backup Database** in the sidebar before opening a new term.
