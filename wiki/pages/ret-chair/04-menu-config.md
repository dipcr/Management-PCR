# RET Chair — Menu Config

Configure the **rank-based rules** that decide what Research faculty may self-select and how
much Extension is distributed to each rank. This is the heart of the RET setup.

![Menu Config](/static/img/ret-chair/04-menu-config.png)

## The rank bands

For each academic rank band, configure:

| Setting | Meaning |
| --- | --- |
| **Research selections** | Which research indicators a person at this rank may pick from the pool, and the required quantity |
| **Extension quantity** | The mandatory Extension quantity distributed to this rank |
| **Lock** | Locking a rule freezes it so it cannot be changed later |

## Typical workflow

1. Pick a **rank band**.
2. Tick the **Research** indicators that rank may select.
3. Set the **Extension** quantity per faculty.
4. **Save** the rule. Repeat for each rank band.

## Important behaviour

- The **Extension** distribution is **mandatory / locked** on the faculty dashboard for that
  rank band — it is not self-selected.
- Saving **deletes and rewrites** the rule rows for the term (a deliberate design), so review
  before saving.
- Rules are scoped to the **active term**; a past term's locked row can no longer block a
  future term's save.
- **Unlock** an Extension rule only when you deliberately need to change it.

## After configuring

Return to **Target Assignment** to apply the rules, then monitor **Commitments** and
**Evidence Monitor**.
