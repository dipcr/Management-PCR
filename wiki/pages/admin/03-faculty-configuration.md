# Admin — Faculty Configuration

The roster is the list of employees. A person **cannot register by themselves** — the Admin
creates their profile here first, and the person later **claims** it (see
[Claiming your account](/p/getting-started/02-claim-account)).

![Faculty Configuration](/static/img/admin/03-faculty-configuration.png)

## Add or edit one person

1. Click **Add Faculty** (or **Edit** on an existing row).
2. Fill in the profile:
   - **Employee ID Number** — the official ID the person will type when claiming
   - **First / Last Name**
   - **College** and **Assigned Program**
   - **Specialization** — this is what the Dean cascades to and what a Program Chair
     distributes for; it must match a department name
   - **Academic Rank** — used for RET rules and weighting
   - **Employment Status**, **Leave Status**
   - **Designation** — the job title: `Regular Faculty`, `Designated Faculty`,
     `Program Chair`, `RET Chair`, `Dean`, or `Admin`
3. Click **Save**.

> The **Designation** drives two things: whether the person has an IPCR of their own, and
> which weight table scores it. A Program Chair, RET Chair or Dean is a *designated faculty
> member* and keeps a personal IPCR.

## Bulk import (CSV)

1. Click **Import CSV** and choose a `.csv` file with the roster columns.
2. The importer reports how many rows were **added, updated, and unchanged**.
3. The import is recorded in the audit log as *CSV Roster Import*.

## Activate / deactivate

Use **Toggle Status** on a row to move a person between **Active** and **Inactive**.
Inactive people stop appearing where recipients are listed.
