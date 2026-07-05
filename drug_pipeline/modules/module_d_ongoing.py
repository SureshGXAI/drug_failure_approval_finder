"""
modules/module_d_ongoing.py
==============================
Module D - drugs currently in an active clinical trial.

Pipeline for each qualifying record:
  Open Targets (core status = Recruiting / Active / etc.)
    -> ClinicalTrials.gov (live status, sponsor, start/completion dates)
    -> PubMed (supporting reference)
    -> PubChem (chemical properties)
"""

from .. import config
from ..sources import clinicaltrials, pubmed, pubchem
from ..utils import normalize_status, pubmed_str, pubchem_str

FIELDNAMES_TEMPLATE = [
    "Drug Name", "Drug ID (ChEMBL)", "{partner_col}", "Phase", "Trial Status", "Sponsor",
    "Estimated Primary Completion Date", "Trial Start Date", "Mechanism of Action",
    "Trial IDs (NCT)", "PubMed Reference", "PubChem CID", "Molecular Formula",
    "Canonical SMILES", "Molecular Weight", "Source URLs",
]


def select_rows(flat_reports: list) -> list:
    """Filter flattened (drug, trial-report) rows down to ongoing ones."""
    return [r for r in flat_reports
            if (r.get("status") or "").strip().lower() in config.ONGOING_STATUSES]


def run(flat_reports: list, partner_col: str, queried_partner, args, caches: dict) -> list:
    """
    Build Module D's output rows.

    flat_reports:    output of sources.open_targets.flatten_clinical_reports()
    partner_col:     the disease/target column header (varies by query type)
    queried_partner: callable(row) -> str, resolves the per-row partner name
    args:            parsed CLI namespace (uses skip_enrichment/skip_pubmed/skip_pubchem)
    caches:          dict of shared cache dicts, keyed 'ctgov', 'pubmed_id',
                     'pubmed_search', 'pubchem'
    """
    ongoing_rows = select_rows(flat_reports)
    output = []

    for r in ongoing_rows:
        chembl_id = r.get("drugId") or ""
        drug_name = r.get("prefName") or ""
        nct_ids = r.get("ctIds") or []

        live_status, completion_date, start_date, sponsor = "", "", "", ""
        if not args.skip_enrichment:
            for nct in nct_ids[:1]:
                details = clinicaltrials.get_ctgov_details(nct, caches["ctgov"])
                live_status = details.get("overall_status") or ""
                completion_date = details.get("primary_completion_date") or ""
                start_date = details.get("start_date") or ""
                sponsor = details.get("sponsor") or ""

        pubmed_ref = None
        if not args.skip_pubmed:
            pubmed_ref = pubmed.get_pubmed_reference(
                drug_name, r.get("pmids"), "clinical trial OR efficacy OR safety",
                caches["pubmed_id"], caches["pubmed_search"])

        pc = pubchem_str(None if args.skip_pubchem else
                          pubchem.get_pubchem_properties(drug_name, caches["pubchem"]))

        output.append({
            "Drug Name": drug_name,
            "Drug ID (ChEMBL)": chembl_id,
            partner_col: queried_partner(r),
            "Phase": r.get("phase") or "Unknown",
            "Trial Status": live_status or normalize_status(r.get("status")),
            "Sponsor": sponsor,
            "Estimated Primary Completion Date": completion_date,
            "Trial Start Date": start_date,
            "Mechanism of Action": r.get("mechanismOfAction") or "",
            "Trial IDs (NCT)": ", ".join(nct_ids),
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
