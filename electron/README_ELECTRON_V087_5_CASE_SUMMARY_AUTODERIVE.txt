# v087.5 Case Summary Auto-Derive

Case Manager now derives missing High / Low / Window summary values from the linked Event Ledger rows.

- If a case did not persist Case High/Low, preview uses explicit SET_* range anchors where available.
- If no explicit anchors exist, preview falls back to highest/lowest linked event price.
- If a case has no saved date window, preview derives first/last linked event dates.
- This is read-only summary logic. Event Ledger remains the source of truth.
- Backend untouched.
