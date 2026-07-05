"""
sources/openfda.py
===================
openFDA Drugs@FDA API - confirms US FDA approval and supplies application
number, sponsor, approval date, and marketing status. Used exclusively by
Module B.
"""

import time

import requests

from .. import config


def get_fda_approval_info(drug_name: str, cache: dict) -> list:
    """Query openFDA Drugs@FDA for approval details of a drug by name.
    Tries generic_name first, then brand_name. Returns a list of dicts (one
    per matching product), or [] if nothing matched."""
    key = (drug_name or "").strip().lower()
    if not key:
        return []
    if key in cache:
        return cache[key]

    results = []
    for field in ("generic_name", "brand_name"):
        try:
            params = {"search": f'openfda.{field}:"{drug_name}"', "limit": 5}
            resp = requests.get(config.OPENFDA_DRUGSFDA_URL, params=params,
                                 timeout=config.REQUEST_TIMEOUT)
            if resp.ok:
                data = resp.json()
                for entry in data.get("results", []):
                    sponsor = entry.get("sponsor_name")
                    app_no = entry.get("application_number")
                    approval_dates = [
                        s.get("submission_status_date")
                        for s in entry.get("submissions", [])
                        if s.get("submission_status") == "AP" and s.get("submission_status_date")
                    ]
                    approval_date = min(approval_dates) if approval_dates else None
                    for product in entry.get("products", []):
                        results.append({
                            "application_number": app_no,
                            "sponsor": sponsor,
                            "marketing_status": product.get("marketing_status"),
                            "approval_date": approval_date,
                        })
                if results:
                    break
        except requests.RequestException:
            pass
        time.sleep(config.SLEEP_BETWEEN_CALLS)

    cache[key] = results
    return results
