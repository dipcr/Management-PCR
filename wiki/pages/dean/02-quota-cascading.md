# Dean — Quota Cascading

This is where you set, per indicator, how many units each **program**, **College-Wide**, and
**RET / Extension** should carry. Those quotas become the pools the Program Chair and RET
Chair distribute to faculty.

![Quota Cascading](/static/img/dean/02-quota-cascading.png)

## Set quotas

1. Go to **Quota Cascading** for the active term.
2. For each master indicator, type a quota under the column for each role:
   - a **program** column (e.g. *WST Program*, *DST Program*)
   - **RET / Extension**
   - **College-Wide**
3. Click **Save** to cascade.

Saving **replaces** the existing quota rows for the active term, so review the whole screen
before saving.

## College-Wide: "Silent" vs "To Chairs"

Each College-Wide quota has a toggle that defaults to **Silent (Dean Only)**:

| Setting | Meaning |
| --- | --- |
| **Silent** | Kept off the regular faculty's IPCR — an institutional/administrative duty |
| **To Chairs** | Falls to the Program Chair for distribution — **only for Support-type** indicators |

> **College-Wide Instruction / Strategic targets are never offered to Program Chairs.**
> They are institution-level rollup metrics that no individual faculty member commits to.
> Only **College-Wide Support** flows to the chair, and only when you flip it to **To Chairs**.

## What the chairs see afterwards

- **Program Chair** sees quotas where `assigned_to_role` equals **their specialization**, plus
  any **College-Wide Support** quota you marked **To Chairs**.
- **RET Chair** sees the **RET / Extension** quotas.

If a chair reports "I don't see the cascaded targets", check: (a) the quota was saved against
the department name that matches their **Specialization**, and (b) if it was College-Wide,
that it is set to **To Chairs** and is a Support indicator.
