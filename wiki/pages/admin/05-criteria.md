# Admin — Criteria

**Criteria** (target types) are the six building blocks that every indicator belongs to.
Each one has a **review lane** that decides who reviews targets of that type.

![Criteria, category management and weights](/static/img/admin/05-criteria.png)

## Add a criterion

1. In **Add Criterion**, enter a **Name** (e.g. *Innovation*).
2. **Slug (optional)** — *leave this blank* unless you are rebuilding a built-in type.
   The application matches on the exact slugs:
   `instruction`, `research`, `extension`, `support`, `administrative`, `custom`.
   A generated slug such as `a_instructions` **will not route targets**.
3. Choose a **Review Lane**:
   - **Program Chair** reviews *Instruction*, *Support* and *Administrative*.
   - **RET Chair** reviews *Research* and *Extension*.
4. Click **Add Criterion**.

## The criteria table

Each row shows **Name**, **Slug**, **Lane**, **Core** (structured vs. free-form), **Order**
(▲▼ to reorder), and **Edit / Deactivate**.

## Category Management

Categories group target types differently for different purposes:

| Scope | Category | Includes |
| --- | --- | --- |
| Master Indicators | Strategic Priorities | Instruction |
| Master Indicators | Core Functions | Research, Extension |
| Master Indicators | Support Functions | Support |
| Regular Faculty | Strategic Priorities | Instruction |
| Regular Faculty | Core Functions | Research, Extension |
| Regular Faculty | Support Functions | Support |
| Designated Faculty | Strategic Priorities/Support Functions | Support, Administrative |
| Designated Faculty | Core Functions | Instruction |

The **grouping differs per scope** — the same target type can fall into a different category
depending on who is being rated. Category **display order matters** (the printed IPCR must
read Strategic Priorities → Core Functions → Support Functions).

## Weight Allocation by Rank

The percentage each category contributes to the final score, **per rank band**, for the
active term. Switch between **Regular Faculty** and **Designated Faculty**; each configured
row must total **100%**.

- **Regular Faculty:** 50 / 40 / 10 (Strategic / Core / Support)
- **Designated Faculty:** 75 / 25 (Strategic & Support / Core)

You can set one **General** allocation for all ranks, or **Specific per Academic Rank**, and
**Copy from Previous Term**.
