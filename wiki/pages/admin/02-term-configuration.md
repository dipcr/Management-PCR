# Admin — Term Configuration

The academic term is the container for everything: indicators, quotas, drafts, evidence and
scores all belong to a term. **Only one term is active at a time.**

![Term Configuration](/static/img/admin/02-term-configuration.png)

## Open a new term

1. Go to **Term Configuration**.
2. Fill in the **Open New Term** card:
   - **Academic Year** — must be two consecutive years in `YYYY - YYYY` format,
     e.g. `2028 - 2029` (the form validates this).
   - **Semester** — e.g. *1st Semester*.
   - **Rating Period From / To** — the period printed on the IPCR header
     (e.g. *January 2029* to *June 2029*).
3. Click **Open Term**.

Opening a term **deactivates the previous term** and copies the previous term's
**teaching-load configuration** forward, so you don't start from a blank slate.

## Term history

The **Term History** table lists every term with its academic year, semester, rating period
and active status. Use it to confirm which term is current before you add indicators.

## Notes

- The rating period comes from **Period From/To** (`period_start` / `period_end`); the
  academic year and semester alone cannot express it.
- There is **no submission deadline field** — it was removed deliberately. Nothing in the
  app blocks submissions by date.
- Changing the active term changes what every other role sees, so coordinate before
  switching.
