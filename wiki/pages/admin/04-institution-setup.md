# Admin — Institution Setup

Institution-level configuration: the departments used to route targets, the teaching-load
rules, the text printed on the IPCR, and the signatories.

![Institution Setup](/static/img/admin/04-institution-setup.png)

## Departments / programs

Departments are the **routing keys** for the whole cascade. A department's name is stored on
each employee's **Specialization** and on the Dean's cascaded quotas (`assigned_to_role`),
so:

- The Dean cascades a quota **to a department name**.
- The Program Chair sees quotas where `assigned_to_role` equals **their specialization**.

Add a department, give it a **code**, and set its **display order**. Renaming a department
also updates the rows that reference it.

## Teaching load

Configure the mandatory teaching-load hours per designation and rank band, plus the duration
value/unit. New terms inherit these settings automatically.

## Institution text

Free-text values printed on the IPCR (e.g. the college's full name, the form title).

## Signatories

The signatory blocks printed at the bottom of the IPCR. Each block has a label and a source,
so the printed form shows the correct names for the term.

> **Slug safety:** target *types* (not departments) are matched on their exact
> `slug` — see [Criteria](/p/admin/05-criteria). Never let a department name collide with a
> criterion slug.
