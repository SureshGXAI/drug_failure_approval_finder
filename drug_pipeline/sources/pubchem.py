"""
sources/pubchem.py
===================
PubChem PUG REST API - CID, molecular formula, SMILES, and molecular weight
for a drug, looked up by name. Used by Modules A, B, and D.

NOTE ON PUBCHEM'S SMILES FIELD NAMES
-------------------------------------
PubChem renamed its SMILES property fields at the API level: the old
"CanonicalSMILES" request tag now comes back in the JSON under the key
"ConnectivitySMILES" (no stereochemistry), and the old "IsomericSMILES" tag
is now just "SMILES" (includes stereochemistry). We request both current
tags and prefer the fuller "SMILES" (isomeric) value, falling back to
"ConnectivitySMILES", and also check the old key names in case PubChem
serves an older API version to some accounts/regions.
"""

import time
from typing import Optional
from urllib.parse import quote

import requests

from .. import config

# Checked in order of preference: isomeric (with stereochemistry) first,
# then connectivity-only, then the old pre-rename key names as a last resort.
SMILES_KEYS = ("SMILES", "ConnectivitySMILES", "IsomericSMILES", "CanonicalSMILES")


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
                smiles = next((p[k] for k in SMILES_KEYS if p.get(k)), None)
                props = {
                    "cid": p.get("CID"),
                    "formula": p.get("MolecularFormula"),
                    "smiles": smiles,
                    "weight": p.get("MolecularWeight"),
                }
    except requests.RequestException:
        pass

    cache[key] = props
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return props
