"""
modules/module_b_approved.py
==============================
Module B - FDA-approved drugs.

Pipeline for each qualifying drug:
  Open Targets (maxClinicalStage == Approved)
    -> openFDA (confirm approval, application/sponsor/date)
    -> PubMed (supporting reference)
    -> PubChem (chemical properties)
"""

from ..sources import openfda, pubmed, pubchem
from ..sources.open_targets import approved_drug_summaries
from ..utils import pubmed_str, pubchem_str

FIELDNAMES_TEMPLATE = [
    "Drug Name", "Drug ID (ChEMBL)", "{partner_col}", "Phase", "FDA Approval Status",
    "Application Number(s)", "Sponsor(s)", "Approval Date(s)", "Marketing Status",
    "Mechanism of Action", "PubMed Reference", "PubChem CID", "Molecular Formula",
    "Canonical SMILES", "Molecular Weight", "Source URLs",
]


def select_rows(raw_rows: list) -> list:
    """Return one summary row per drug that reached an approved stage."""
    return approved_drug_summaries(raw_rows)


def run(raw_rows: list, entity_type: str, partner_col: str, args, caches: dict) -> list:
    """
    Build Module B's output rows.

    raw_rows:    raw Open Targets drugAndClinicalCandidates rows (unflattened)
    entity_type: 'target' or 'disease' - decides which field feeds partner_col
    args:        parsed CLI namespace (uses skip_fda_lookup/skip_pubmed/skip_pubchem)
    caches:      dict of shared cache dicts, keyed 'fda', 'pubmed_id',
                 'pubmed_search', 'pubchem'
    """
    approved_rows = select_rows(raw_rows)
    output = []

    for r in approved_rows:
        chembl_id = r.get("drugId") or ""
        drug_name = r.get("prefName") or ""

        fda_matches = [] if args.skip_fda_lookup else \
            openfda.get_fda_approval_info(drug_name, caches["fda"])
        if fda_matches:
            app_numbers = "; ".join(sorted({m["application_number"] for m in fda_matches if m.get("application_number")}))
            sponsors = "; ".join(sorted({m["sponsor"] for m in fda_matches if m.get("sponsor")}))
            approval_dates = "; ".join(sorted({m["approval_date"] for m in fda_matches if m.get("approval_date")}))
            marketing_statuses = "; ".join(sorted({m["marketing_status"] for m in fda_matches if m.get("marketing_status")}))
            fda_flag = "Yes (openFDA match found)"
        else:
            app_numbers = sponsors = approval_dates = marketing_statuses = ""
            fda_flag = ("Unconfirmed (reached an approved stage per Open Targets; no openFDA "
                        "match - may be approved outside the US, or a name mismatch)")

        pubmed_ref = None
        if not args.skip_pubmed:
            pubmed_ref = pubmed.get_pubmed_reference(
                drug_name, r.get("pmids"), "FDA approval OR approved",
                caches["pubmed_id"], caches["pubmed_search"])

        pc = pubchem_str(None if args.skip_pubchem else
                          pubchem.get_pubchem_properties(drug_name, caches["pubchem"]))

        partner_val = ", ".join(r.get("disease_names") or []) if entity_type == "target" \
            else ", ".join(r.get("target_symbols") or [])

        output.append({
            "Drug Name": drug_name,
            "Drug ID (ChEMBL)": chembl_id,
            partner_col: partner_val,
            "Phase": r.get("phase") or "Approved",
            "FDA Approval Status": fda_flag,
            "Application Number(s)": app_numbers,
            "Sponsor(s)": sponsors,
            "Approval Date(s)": approval_dates,
            "Marketing Status": marketing_statuses,
            "Mechanism of Action": r.get("mechanismOfAction") or "",
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
