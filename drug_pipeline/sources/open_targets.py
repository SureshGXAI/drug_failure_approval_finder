"""
sources/open_targets.py
========================
Open Targets Platform (GraphQL) - the core data source. Everything else in
the pipeline enriches records that originate here.

Responsibilities:
  - resolve_input(): turn a gene symbol / disease name / stable ID into a
    concrete Open Targets target or disease ID.
  - fetch_known_drugs(): pull every drug + clinical-trial-report record for
    that target/disease via the current `drugAndClinicalCandidates` field.
    (Open Targets retired the older `knownDrugs` field; if you see a 400
    GraphQL error here in the future, check
    https://api.platform.opentargets.org/api/v4/graphql/schema again and
    update MOA_FRAGMENT / REPORT_FRAGMENT below.)
  - fetch_disease_associated_targets(): for Module C, map a disease to its
    top-N most strongly associated targets.
  - flatten_clinical_reports() / approved_drug_summaries(): reshape the
    nested Open Targets response into the flat row shapes Modules A/B/D need.
"""

import sys
from typing import Optional

import requests

from .. import config
from ..utils import extract_nct_id


def graphql_query(query: str, variables: dict) -> dict:
    """POST a query to the Open Targets GraphQL endpoint and return `data`.
    Raises RuntimeError with the server's own error message on failure,
    rather than a generic HTTPError, since Open Targets returns useful
    detail in the JSON body even on non-200 responses."""
    resp = requests.post(
        config.OT_URL,
        json={"query": query, "variables": variables},
        timeout=config.REQUEST_TIMEOUT,
    )
    try:
        payload = resp.json()
    except ValueError:
        resp.raise_for_status()
        raise RuntimeError(f"Open Targets returned a non-JSON response (HTTP {resp.status_code}).")

    if payload.get("errors"):
        messages = "; ".join(e.get("message", str(e)) for e in payload["errors"])
        raise RuntimeError(f"Open Targets GraphQL error: {messages}")
    if not resp.ok:
        resp.raise_for_status()
    return payload["data"]


def looks_like_id(text: str) -> Optional[str]:
    t = text.strip().upper()
    if t.startswith("ENSG"):
        return "target"
    if t.startswith(("EFO_", "MONDO_", "HP_", "ORPHA", "DOID_")):
        return "disease"
    return None


def resolve_input(query: str) -> dict:
    """Resolve free text or a stable ID to {'type', 'id', 'name'}."""
    id_guess = looks_like_id(query)
    if id_guess == "target":
        return {"type": "target", "id": query.strip().upper(), "name": query}
    if id_guess == "disease":
        return {"type": "disease", "id": query.strip().upper(), "name": query}

    search_gql = """
    query Search($q: String!) {
      search(queryString: $q, entityNames: ["target", "disease"], page: {index: 0, size: 5}) {
        hits { id entity name }
      }
    }
    """
    data = graphql_query(search_gql, {"q": query})
    hits = data["search"]["hits"]
    if not hits:
        raise ValueError(f"No target or disease found matching '{query}'.")

    top = hits[0]
    if len(hits) > 1:
        print(f"[info] Multiple matches for '{query}', using top hit: "
              f"{top['name']} ({top['entity']}, {top['id']})", file=sys.stderr)
        for h in hits[1:]:
            print(f"         - {h['name']} ({h['entity']}, {h['id']})", file=sys.stderr)

    return {"type": top["entity"], "id": top["id"], "name": top["name"]}


def fetch_target_symbol(ensembl_id: str) -> Optional[str]:
    """Look up a target's approved gene symbol from its Ensembl ID."""
    gql = "query T($id: String!) { target(ensemblId: $id) { approvedSymbol } }"
    try:
        data = graphql_query(gql, {"id": ensembl_id})
        return (data.get("target") or {}).get("approvedSymbol")
    except Exception:
        return None


MOA_FRAGMENT = """
    mechanismsOfAction {
      rows { mechanismOfAction actionType targets { approvedSymbol } }
    }
"""

REPORT_FRAGMENT = """
    clinicalReports {
      trialPhase
      clinicalStage
      trialOverallStatus
      trialWhyStopped
      trialStartDate
      url
      title
      source
      trialLiterature
      countries
      diseases { diseaseFromSource disease { id name } }
    }
"""


def fetch_known_drugs(entity_type: str, entity_id: str) -> list:
    """
    Fetch raw drug + clinical-report data for a target or disease using the
    current Open Targets schema field `drugAndClinicalCandidates`.
    Returns the raw list of drug-level rows (each with nested clinicalReports).
    """
    if entity_type == "target":
        gql = f"""
        query ClinicalCandidates($id: String!) {{
          target(ensemblId: $id) {{
            approvedSymbol
            drugAndClinicalCandidates {{
              count
              rows {{
                maxClinicalStage
                drug {{
                  id
                  name
                  {MOA_FRAGMENT}
                }}
                {REPORT_FRAGMENT}
              }}
            }}
          }}
        }}
        """
        data = graphql_query(gql, {"id": entity_id})
        node = data.get("target") or {}
    else:
        gql = f"""
        query ClinicalCandidates($id: String!) {{
          disease(efoId: $id) {{
            name
            drugAndClinicalCandidates {{
              count
              rows {{
                maxClinicalStage
                drug {{
                  id
                  name
                  {MOA_FRAGMENT}
                }}
                {REPORT_FRAGMENT}
              }}
            }}
          }}
        }}
        """
        data = graphql_query(gql, {"id": entity_id})
        node = data.get("disease") or {}

    return ((node.get("drugAndClinicalCandidates") or {}).get("rows")) or []


def fetch_disease_associated_targets(disease_id: str, top_n: int) -> list:
    """Return the top-N targets associated with a disease (for Module C)."""
    gql = """
    query AssocTargets($id: String!, $size: Int!) {
      disease(efoId: $id) {
        associatedTargets(page: {index: 0, size: $size}) {
          rows {
            score
            target { id approvedSymbol }
          }
        }
      }
    }
    """
    data = graphql_query(gql, {"id": disease_id, "size": top_n})
    node = data.get("disease")
    if not node or not node.get("associatedTargets"):
        return []
    return node["associatedTargets"]["rows"]


def _moa_and_targets(drug: dict):
    moa_rows = ((drug.get("mechanismsOfAction") or {}).get("rows")) or []
    moa_text = "; ".join(sorted({m.get("mechanismOfAction") for m in moa_rows if m.get("mechanismOfAction")}))
    target_symbols = sorted({
        t.get("approvedSymbol")
        for m in moa_rows for t in (m.get("targets") or []) if t.get("approvedSymbol")
    })
    return moa_text, target_symbols


def flatten_clinical_reports(raw_rows: list) -> list:
    """Turn nested drug -> clinicalReports rows into one row per
    (drug, report). Used by Modules A (failed) and D (ongoing)."""
    flat = []
    for row in raw_rows:
        drug = row.get("drug") or {}
        moa_text, target_symbols = _moa_and_targets(drug)
        for report in (row.get("clinicalReports") or []):
            nct_id = extract_nct_id(report.get("url"))
            disease_names = [
                (d.get("disease") or {}).get("name") or d.get("diseaseFromSource")
                for d in (report.get("diseases") or [])
            ]
            flat.append({
                "drugId": drug.get("id") or "",
                "prefName": drug.get("name") or "",
                "phase": report.get("clinicalStage") or report.get("trialPhase") or "Unknown",
                "status": report.get("trialOverallStatus") or "",
                "why_stopped": report.get("trialWhyStopped") or "",
                "mechanismOfAction": moa_text,
                "target_symbols": target_symbols,
                "ctIds": [nct_id] if nct_id else [],
                "urls": [{"url": report.get("url"), "niceName": report.get("source")}] if report.get("url") else [],
                "disease_names": [d for d in disease_names if d],
                "pmids": [p for p in (report.get("trialLiterature") or []) if p],
            })
    return flat


def approved_drug_summaries(raw_rows: list) -> list:
    """One row per drug whose maxClinicalStage indicates regulatory
    approval. Used by Module B."""
    summaries = []
    for row in raw_rows:
        stage = row.get("maxClinicalStage") or ""
        if "approved" not in stage.lower():
            continue
        drug = row.get("drug") or {}
        moa_text, target_symbols = _moa_and_targets(drug)
        disease_names, urls, pmids = set(), [], set()
        for report in (row.get("clinicalReports") or []):
            for d in (report.get("diseases") or []):
                name = (d.get("disease") or {}).get("name") or d.get("diseaseFromSource")
                if name:
                    disease_names.add(name)
            if report.get("url"):
                urls.append({"url": report.get("url"), "niceName": report.get("source")})
            for p in (report.get("trialLiterature") or []):
                if p:
                    pmids.add(p)
        summaries.append({
            "drugId": drug.get("id") or "",
            "prefName": drug.get("name") or "",
            "phase": stage,
            "mechanismOfAction": moa_text,
            "target_symbols": target_symbols,
            "disease_names": sorted(disease_names),
            "urls": urls,
            "pmids": sorted(pmids),
        })
    return summaries
