# Admin — Overview

The Admin sets up **everything the other roles depend on**: the academic term, the master
indicators, the roster, and the accounts.

![Admin dashboard — Overview](/static/img/admin/00-overview.png)

## The sidebar

| Group | Item | What it does |
| --- | --- | --- |
| Dashboard | **Overview** | Roster adoption and the active term |
| Management | **Term Configuration** | Open/close terms, set the rating period |
| Management | **Faculty Configuration** | Add, edit and deactivate employee profiles |
| Management | **Institution Setup** | Departments, signatories, teaching load, institution text |
| Management | **Criteria** | Target types, categories, review lanes and weights |
| Management | **Master Indicators** | The actual targets for the term |
| System | **Account Claims** | Approve/deny people who claimed their account |
| System | **System Security** | Emergency access controls + audit log |
| System | **Backup Database** | Download a `.sql` snapshot |

## The Overview cards

- **Roster Adoption Rate** — how many roster profiles have a claimed account
  (e.g. *100% — 10 / 10 Accounts Claimed*).
- **Active Academic Term** — the term currently open, e.g. *2028 - 2029 (1st Semester)*.

## Recommended setup order for a new term

1. **Institution Setup** — confirm departments, signatories and teaching-load rules.
2. **Criteria** — confirm the six target types, their review lanes and the weight
   allocation per rank band.
3. **Term Configuration** — open the new term and set the rating period.
4. **Master Indicators** — add the targets for the term.
5. **Faculty Configuration** — ensure every employee has a profile, then approve their
   **Account Claims** as they come in.

> Only **one** term can be active at a time. Opening a new term deactivates the previous one.
