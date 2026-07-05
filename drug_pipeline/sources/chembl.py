"""
sources/chembl.py
==================
ChEMBL REST API - supplies the official market-withdrawal reason, year, and
country for a molecule. Used by Module A to explain *why* a failed drug's
program ended, when it was also withdrawn from a market at some point.
"""

import time

import requests

from .. import config


def get_chembl_withdrawal_info(chembl_id: str, cache: dict) -> dict:
    if chembl_id in cache:
        return cache[chembl_id]
    info = {"withdrawn_flag": None, "withdrawn_reason": None,
            "withdrawn_year": None, "withdrawn_country": None}
    try:
        resp = requests.get(config.CHEMBL_MOLECULE_URL.format(chembl_id),
                             timeout=config.REQUEST_TIMEOUT)
        if resp.ok:
            mol = resp.json()
            info["withdrawn_flag"] = mol.get("withdrawn_flag")
            info["withdrawn_reason"] = mol.get("withdrawn_reason")
            info["withdrawn_year"] = mol.get("withdrawn_year")
            info["withdrawn_country"] = mol.get("withdrawn_country")
    except requests.RequestException:
        pass
    cache[chembl_id] = info
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return info
