"""
modules/module_c_annotation.py
=================================
Module C - target biological annotation. Unlike A/B/D, this module isn't
about individual drugs; it's about the target(s) behind them.

Pipeline for each target to annotate:
  UniProt (protein name, function, keywords)
    -> Reactome (pathways, keyed off the UniProt accession)
  UniProt (gene symbol)
    -> DisGeNET (other associated diseases, needs a free API key)

If the original query was a disease, Open Targets is used first to find the
top-N targets most strongly associated with it (fetch_disease_associated_targets);
one annotation row is produced per target either way.
"""

import sys

from ..sources import uniprot, reactome, disgenet
from ..sources.open_targets import fetch_disease_associated_targets, fetch_target_symbol

FIELDNAMES = [
    "Gene Symbol", "Ensembl Target ID", "Association Score (to queried disease)",
    "UniProt Accession", "Protein Name", "Function Summary", "UniProt Keywords",
    "Reactome Pathways", "DisGeNET Associated Diseases",
]


def select_targets(entity: dict, args) -> list:
    """Return the list of {'id', 'approvedSymbol', 'score'} targets to annotate."""
    if entity["type"] == "target":
        return [{"id": entity["id"], "approvedSymbol": None, "score": None}]

    print(f"[info] Module C: fetching top {args.top_targets} targets associated "
          f"with disease from Open Targets ...", file=sys.stderr)
    assoc = fetch_disease_associated_targets(entity["id"], args.top_targets)
    return [
        {"id": a["target"]["id"], "approvedSymbol": a["target"]["approvedSymbol"], "score": a["score"]}
        for a in assoc
    ]


def run(entity: dict, args, caches: dict) -> list:
    """
    Build Module C's output rows.

    entity:  {'type', 'id', 'name'} from open_targets.resolve_input()
    args:    parsed CLI namespace (uses top_targets, disgenet_api_key)
    caches:  dict of shared cache dicts, keyed 'uniprot', 'reactome', 'disgenet'
    """
    targets_to_annotate = select_targets(entity, args)

    if not args.disgenet_api_key:
        print("[info] No DisGeNET API key provided (--disgenet-api-key or "
              "DISGENET_API_KEY env var) - DisGeNET columns will be left blank. "
              "Get a free key at https://www.disgenet.com", file=sys.stderr)

    output = []
    for t in targets_to_annotate:
        symbol = t["approvedSymbol"] or fetch_target_symbol(t["id"])
        ensembl_id = t["id"]

        uniprot_info = uniprot.get_uniprot_annotation(symbol, caches["uniprot"]) if symbol else None
        accession = uniprot_info.get("accession") if uniprot_info else None
        pathways = reactome.get_reactome_pathways(accession, caches["reactome"]) if accession else []
        disgenet_assoc = disgenet.get_disgenet_associations(
            symbol, args.disgenet_api_key, caches["disgenet"]) if symbol else []

        output.append({
            "Gene Symbol": symbol or "",
            "Ensembl Target ID": ensembl_id,
            "Association Score (to queried disease)": t["score"] if t["score"] is not None else "",
            "UniProt Accession": accession or "",
            "Protein Name": (uniprot_info or {}).get("protein_name") or "",
            "Function Summary": (uniprot_info or {}).get("function") or "",
            "UniProt Keywords": ", ".join((uniprot_info or {}).get("keywords") or []),
            "Reactome Pathways": "; ".join(pathways),
            "DisGeNET Associated Diseases": "; ".join(
                f"{d['disease']} (score={d['score']})" for d in disgenet_assoc if d.get("disease")
            ),
        })

    return output
