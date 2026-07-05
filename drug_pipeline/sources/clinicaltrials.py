"""
sources/clinicaltrials.py
==========================
ClinicalTrials.gov API v2 - supplies the *live* status, sponsor, and dates
for a specific trial by NCT ID. Open Targets already provides a snapshot of
trial status and (for stopped trials) the stop reason, so this module is
used mainly by Module D to get up-to-the-minute detail on ongoing trials.
"""

import time

import requests

from .. import config


def get_ctgov_details(nct_id: str, cache: dict) -> dict:
    if nct_id in cache:
        return cache[nct_id]
    info = {"overall_status": None, "primary_completion_date": None,
            "start_date": None, "sponsor": None}
    try:
        resp = requests.get(config.CTGOV_STUDY_URL.format(nct_id),
                             timeout=config.REQUEST_TIMEOUT)
        if resp.ok:
            study = resp.json()
            protocol = study.get("protocolSection", {})
            status_module = protocol.get("statusModule", {})
            sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
            info["overall_status"] = status_module.get("overallStatus")
            info["primary_completion_date"] = (
                status_module.get("primaryCompletionDateStruct", {}).get("date")
            )
            info["start_date"] = status_module.get("startDateStruct", {}).get("date")
            info["sponsor"] = (sponsor_module.get("leadSponsor", {}) or {}).get("name")
    except requests.RequestException:
        pass
    cache[nct_id] = info
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return info
