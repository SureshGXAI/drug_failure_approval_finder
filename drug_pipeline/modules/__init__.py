"""
modules
=======
One module per output file (A: failed, B: approved, C: annotation,
D: ongoing). Each exposes:
  - FIELDNAMES: the CSV column order for that module's default (empty) case
  - run(...): pure function that takes already-fetched Open Targets data
    plus shared caches, calls whichever `sources/*` functions it needs, and
    returns a list of row dicts ready for utils.write_csv().

None of these modules know about argparse, file paths, or each other -
drug_pipeline/cli.py is the only place that wires everything together.
"""
