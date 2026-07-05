"""
modules/module_a_failed.py
============================
Module A - failed / stopped / discontinued clinical-stage drugs.

Pipeline for each qualifying record:
  Open Targets (core status + why_stopped)
    -> ChEMBL (market-withdrawal reason, if any)
    -> PubMed (supporting reference)
    -> PubChem (chemical properties)
"""

from .. import config
from ..sources import chembl, pubmed, pubchem
from ..utils import normalize_status, pubmed_str, pubchem_str

FIELDNAMES_TEMPLATE = [
    "Drug Name", "Drug ID (ChEMBL)", "{partner_col}", "Phase", "Status", "Reason",
    "Mechanism of Action", "Trial IDs (NCT)", "PubMed Reference", "PubChem CID",
    "Molecular Formula", "Canonical SMILES", "Molecular Weight", "Source URLs",
]


def select_rows(flat_reports: list) -> list:
    """Filter flattened (drug, trial-report) rows down to failed/stopped ones."""
    return [r for r in flat_reports
            if (r.get("status") or "").strip().lower() in config.STOPPED_STATUSES]


def run(flat_reports: list, partner_col: str, queried_partner, args, caches: dict) -> list:
    """
    Build Module A's output rows.

    flat_reports:   output of sources.open_targets.flatten_clinical_reports()
    partner_col:    the disease/target column header (varies by query type)
    queried_partner: callable(row) -> str, resolves the per-row partner name
    args:           parsed CLI namespace (uses skip_enrichment/skip_pubmed/skip_pubchem)
    caches:         dict of shared cache dicts, keyed 'chembl', 'pubmed_id',
                    'pubmed_search', 'pubchem'
    """
    stopped_rows = select_rows(flat_reports)
    output = []

    for r in stopped_rows:
        chembl_id = r.get("drugId") or ""
        drug_name = r.get("prefName") or ""
        reason_parts = []

        if r.get("why_stopped"):
            reason_parts.append(r["why_stopped"])

        if not args.skip_enrichment and chembl_id:
            wd = chembl.get_chembl_withdrawal_info(chembl_id, caches["chembl"])
            if wd["withdrawn_flag"]:
                pieces = ["Market withdrawal"]
                if wd["withdrawn_reason"]:
                    pieces.append(wd["withdrawn_reason"])
                if wd["withdrawn_year"]:
                    pieces.append(f"({wd['withdrawn_year']})")
                if wd["withdrawn_country"]:
                    pieces.append(f"in {wd['withdrawn_country']}")
                reason_parts.append(" ".join(str(p) for p in pieces))

        if not reason_parts:
            reason_parts.append(f"Trial status reported as '{r.get('status')}' (no further reason available)")

        pubmed_ref = None
        if not args.skip_pubmed:
            pubmed_ref = pubmed.get_pubmed_reference(
                drug_name, r.get("pmids"), "discontinued OR terminated OR withdrawn OR failed",
                caches["pubmed_id"], caches["pubmed_search"])

        pc = pubchem_str(None if args.skip_pubchem else
                          pubchem.get_pubchem_properties(drug_name, caches["pubchem"]))

        output.append({
            "Drug Name": drug_name,
            "Drug ID (ChEMBL)": chembl_id,
            partner_col: queried_partner(r),
            "Phase": r.get("phase") or "Unknown",
            "Status": normalize_status(r.get("status")),
            "Reason": " | ".join(reason_parts),
            "Mechanism of Action": r.get("mechanismOfAction") or "",
            "Trial IDs (NCT)": ", ".join(r.get("ctIds") or []),
            "PubMed Reference": pubmed_str(pubmed_ref),
            "PubChem CID": pc["cid"],
            "Molecular Formula": pc["formula"],
            "Canonical SMILES": pc["smiles"],
            "Molecular Weight": pc["weight"],
            "Source URLs": ", ".join(u.get("url", "") for u in (r.get("urls") or [])),
        })

    return output


def fieldnames(partner_col: str) -> list:
    return [partner_col if f == "{partner_col}" else f for f in FIELDNAMES_TEMPLATE]
