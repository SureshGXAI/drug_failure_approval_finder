"""
drug_pipeline
=============

A modular pipeline that, for a given target or disease, reports:
  - failed / stopped / discontinued clinical-stage drugs   (Module A)
  - FDA-approved drugs                                      (Module B)
  - target biological annotation                            (Module C)
  - drugs currently in an ongoing clinical trial             (Module D)

See README.md for full usage. Run with:
    python -m drug_pipeline --query "EGFR"
"""

__version__ = "2.0.0"
