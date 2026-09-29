# Admin — Account Claims

When someone **claims** a pre-registered profile, their request lands here. A claim is
**not usable until you approve it** — this replaced the old automatic approval.

![Account Claims](/static/img/admin/07-account-claims.png)

## Review a claim

1. Go to **Account Claims** in the sidebar (the red badge shows how many are waiting).
2. Check the row: **Employee ID**, **Name**, **Designation**, **Corporate Email** and the
   **System Role** the claim will receive.
3. Choose:
   - **Approve** → the credential becomes `APPROVED` and the account becomes `Active`.
     The person can now sign in.
   - **Deny** → the request is **removed**, which frees the Employee ID and email so the
     person can claim again with corrected details.

Both actions are recorded in the **audit log** (`Account Claim Approved` /
`Account Claim Denied`), and the request itself was logged as `Account Claim Requested`.

## How the role is decided

The system role is derived from the person's **Designation** on their profile:

| Designation | System role |
| --- | --- |
| Admin | `Admin` |
| Dean | `DEAN` |
| Program Chair | `PROGRAM_CHAIR` |
| RET Chair | `RET_CHAIR` |
| Designated Faculty | `DESIGNATED_FACULTY` |
| anything else | `FACULTY` |

If the designation is wrong, fix it under **Faculty Configuration** *before* approving.

## What the person sees

Until approval, logging in shows *"Your account claim is pending administrator approval."*
If you deny it, they see a message telling them to contact the administrator.
