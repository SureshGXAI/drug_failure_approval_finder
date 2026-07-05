"""
cli.py
======
The only place that knows about argparse, file paths, and the order the
four modules run in. Everything else in this package is a pure function
that this file calls and writes the results of.

Run via:
    python -m drug_pipeline --query "EGFR"
or via the top-level convenience script:
    python drug_failure_finder.py --query "EGFR"
"""

import argparse
import os
import sys

from . import config
from . import report
from .sources import open_targets
from .modules import module_a_failed, module_b_approved, module_c_annotation, module_d_ongoing
from .utils import write_csv


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List failed/stopped/discontinued, ongoing, and FDA-approved drugs "
                    "for a target or disease, plus target biological annotation."
    )
    parser.add_argument("--query", required=True,
                         help="Gene symbol, Ensembl target ID, disease name, or EFO/MONDO ID.")
    parser.add_argument("--output", default="failed_drugs.csv",
                         help="Failed/stopped drugs CSV path (default: failed_drugs.csv).")
    parser.add_argument("--approved-output", default="approved_drugs.csv",
                         help="FDA-approved drugs CSV path (default: approved_drugs.csv).")
    parser.add_argument("--annotation-output", default="target_annotation.csv",
                         help="Target annotation CSV path (default: target_annotation.csv).")
    parser.add_argument("--ongoing-output", default="ongoing_trials.csv",
                         help="Ongoing clinical trials CSV path (default: ongoing_trials.csv).")
    parser.add_argument("--pdf-output", default="drug_pipeline_report.pdf",
                         help="Combined PDF report path (default: drug_pipeline_report.pdf).")
    parser.add_argument("--skip-pdf", action="store_true",
                         help="Skip building the combined PDF report.")
    parser.add_argument("--top-targets", type=int, default=5,
                         help="When --query is a disease, number of top associated "
                              "targets to annotate in Module C (default: 5).")
    parser.add_argument("--disgenet-api-key", default=config.default_disgenet_api_key(),
                         help="Free API key from https://www.disgenet.com "
                              "(or set the DISGENET_API_KEY environment variable).")
    parser.add_argument("--skip-enrichment", action="store_true",
                         help="Skip ChEMBL/ClinicalTrials.gov lookups (Modules A & D).")
    parser.add_argument("--skip-fda-lookup", action="store_true",
                         help="Skip openFDA lookups (Module B).")
    parser.add_argument("--skip-pubmed", action="store_true",
                         help="Skip PubMed reference lookups (Modules A, B & D).")
    parser.add_argument("--skip-pubchem", action="store_true",
                         help="Skip PubChem chemical-property lookups (Modules A, B & D).")
    parser.add_argument("--skip-annotation", action="store_true",
                         help="Skip Module C entirely (UniProt/Reactome/DisGeNET).")
    parser.add_argument("--skip-ongoing", action="store_true",
                         help="Skip Module D entirely (ongoing clinical trials).")
    return parser


def build_caches() -> dict:
    """One fresh cache dict per external source, shared across all modules
    that call it, so a drug looked up in both Module A and Module D (for
    example) only hits PubChem/PubMed once."""
    return {
        "chembl": {}, "ctgov": {}, "fda": {},
        "pubmed_id": {}, "pubmed_search": {}, "pubchem": {},
        "uniprot": {}, "reactome": {}, "disgenet": {},
    }


def make_partner_helpers(entity_type: str):
    """Return (partner_col, queried_partner) - the column header and a
    per-row accessor for 'the other side' of a drug's association (the
    disease name if you queried by target, or the target symbol if you
    queried by disease)."""
    partner_col = "Queried " + ("Disease (per drug)" if entity_type == "target"
                                 else "Target (per drug)")

    def queried_partner(row):
        if entity_type == "target":
            return ", ".join(row.get("disease_names") or [])
        return ", ".join(row.get("target_symbols") or [])

    return partner_col, queried_partner


def main():
    args = build_arg_parser().parse_args()

    print(f"[info] Resolving '{args.query}' ...", file=sys.stderr)
    entity = open_targets.resolve_input(args.query)
    print(f"[info] Using {entity['type']} '{entity['name']}' ({entity['id']})", file=sys.stderr)

    print("[info] Fetching drug & clinical trial data from Open Targets ...", file=sys.stderr)
    raw_rows = open_targets.fetch_known_drugs(entity["type"], entity["id"])
    print(f"[info] Retrieved {len(raw_rows)} drug records.", file=sys.stderr)

    flat_reports = open_targets.flatten_clinical_reports(raw_rows)
    print(f"[info] Flattened to {len(flat_reports)} drug/trial-report records.", file=sys.stderr)

    caches = build_caches()
    partner_col, queried_partner = make_partner_helpers(entity["type"])
    module_rows = {}  # collected for the combined PDF report

    # ----------------------- Module A: failed / stopped ---------------------
    failed_output = module_a_failed.run(flat_reports, partner_col, queried_partner, args, caches)
    write_csv(args.output, failed_output, module_a_failed.fieldnames(partner_col))
    print(f"[done] Module A: wrote {len(failed_output)} rows to {args.output}", file=sys.stderr)
    module_rows["failed"] = failed_output

    # ----------------------- Module B: FDA approved --------------------------
    approved_output = module_b_approved.run(raw_rows, entity["type"], partner_col, args, caches)
    write_csv(args.approved_output, approved_output, module_b_approved.fieldnames(partner_col))
    print(f"[done] Module B: wrote {len(approved_output)} rows to {args.approved_output}", file=sys.stderr)
    module_rows["approved"] = approved_output

    # ----------------------- Module D: ongoing clinical trials ---------------
    if not args.skip_ongoing:
        ongoing_output = module_d_ongoing.run(flat_reports, partner_col, queried_partner, args, caches)
        write_csv(args.ongoing_output, ongoing_output, module_d_ongoing.fieldnames(partner_col))
        print(f"[done] Module D: wrote {len(ongoing_output)} rows to {args.ongoing_output}", file=sys.stderr)
        module_rows["ongoing"] = ongoing_output
    else:
        print("[info] Module D skipped (--skip-ongoing).", file=sys.stderr)
        module_rows["ongoing"] = []

    # ----------------------- Module C: target annotation ---------------------
    if not args.skip_annotation:
        annotation_output = module_c_annotation.run(entity, args, caches)
        write_csv(args.annotation_output, annotation_output, module_c_annotation.FIELDNAMES)
        print(f"[done] Module C: wrote {len(annotation_output)} rows to {args.annotation_output}",
              file=sys.stderr)
        module_rows["annotation"] = annotation_output
    else:
        print("[info] Module C skipped (--skip-annotation).", file=sys.stderr)
        module_rows["annotation"] = []

    # ----------------------- Combined PDF report ------------------------------
    if not args.skip_pdf:
        report.build_pdf(entity, module_rows, args.pdf_output)
        print(f"[done] PDF report: wrote combined summary to {args.pdf_output}", file=sys.stderr)
    else:
        print("[info] PDF report skipped (--skip-pdf).", file=sys.stderr)


if __name__ == "__main__":
    main()
