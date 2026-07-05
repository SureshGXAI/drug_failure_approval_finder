#!/usr/bin/env python3
"""
drug_failure_finder.py
=======================
Thin backward-compatible entry point. All real logic now lives in the
`drug_pipeline` package (sibling to this file). This script exists so the
original invocation still works unchanged:

    python drug_failure_finder.py --query "EGFR"

Equivalent to:
    python -m drug_pipeline --query "EGFR"

See drug_pipeline/README.md (or README.md next to this file) for full docs,
and see drug_pipeline/cli.py for the orchestration logic.
"""

from drug_pipeline.cli import main

if __name__ == "__main__":
    main()
