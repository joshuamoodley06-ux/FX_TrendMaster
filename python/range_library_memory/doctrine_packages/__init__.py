"""Uploadable FXTM doctrine packages.

Each doctrine topic has one current package file. Approved source history lives
in the doctrine database, not as parallel runnable files in this directory.

Current structure chain:
Weekly BOS -> reclaim -> reclaim depth -> movement classification -> profile
classification -> extreme rejection destination -> Daily mapping coverage audit
-> Weekly Daily relationship builder.

Daily state-at-freeze, sequence summary, and relationship classification remain
held until the first two Daily bridge packages pass manual five-candidate review.
"""
