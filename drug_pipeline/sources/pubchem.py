"""
sources/pubchem.py
===================
PubChem PUG REST API - CID, molecular formula, canonical SMILES, and
molecular weight for a drug, looked up by name. Used by Modules A, B, and D.
"""

import time
from typing import Optional
from urllib.parse import quote

import requests

from .. import config


def get_pubchem_properties(drug_name: str, cache: dict) -> Optional[dict]:
    if not drug_name:
        return None
    key = drug_name.strip().lower()
    if key in cache:
        return cache[key]

    props = None
    try:
        url = config.PUBCHEM_PROPERTY_URL.format(quote(drug_name))
        resp = requests.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.ok:
            rows = resp.json().get("PropertyTable", {}).get("Properties", [])
            if rows:
                p = rows[0]
                props = {
                    "cid": p.get("CID"),
                    "formula": p.get("MolecularFormula"),
                    "smiles": p.get("CanonicalSMILES"),
                    "weight": p.get("MolecularWeight"),
                }
    except requests.RequestException:
        pass

    cache[key] = props
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return props
