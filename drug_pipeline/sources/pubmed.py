"""
sources/pubmed.py
==================
PubMed / NCBI E-utilities - a supporting literature reference per drug.
Used by Modules A, B, and D.

Two lookup strategies, tried in order by get_pubmed_reference():
  1. get_pubmed_title_by_id() - when Open Targets already supplied a PMID
     (via clinicalReports.trialLiterature), just fetch its title/journal/year.
  2. get_pubmed_reference_by_search() - fallback keyword search when no PMID
     is available.
"""

import time
from typing import Optional

import requests

from .. import config


def get_pubmed_title_by_id(pmid: str, cache: dict) -> Optional[dict]:
    """Fetch title/journal/year for a known PMID."""
    if not pmid:
        return None
    if pmid in cache:
        return cache[pmid]
    result = None
    try:
        params = {"db": "pubmed", "id": pmid, "retmode": "json"}
        resp = requests.get(config.EUTILS_ESUMMARY_URL, params=params,
                             timeout=config.REQUEST_TIMEOUT)
        if resp.ok:
            r = resp.json().get("result", {}).get(pmid, {})
            if r:
                result = {
                    "pmid": pmid,
                    "title": r.get("title"),
                    "journal": r.get("fulljournalname") or r.get("source"),
                    "year": (r.get("pubdate") or "").split(" ")[0],
                }
    except requests.RequestException:
        pass
    cache[pmid] = result
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return result


def get_pubmed_reference_by_search(drug_name: str, context_terms: str, cache: dict) -> Optional[dict]:
    """Fallback: find a representative PubMed reference by keyword search
    when no PMID was supplied directly by Open Targets."""
    if not drug_name:
        return None
    cache_key = (drug_name.lower(), context_terms)
    if cache_key in cache:
        return cache[cache_key]

    reference = None
    try:
        term = f'"{drug_name}"[Title/Abstract] AND ({context_terms})'
        params = {"db": "pubmed", "term": term, "retmode": "json",
                  "retmax": 1, "sort": "relevance"}
        resp = requests.get(config.EUTILS_ESEARCH_URL, params=params,
                             timeout=config.REQUEST_TIMEOUT)
        if resp.ok:
            ids = resp.json().get("esearchresult", {}).get("idlist", [])
            if ids:
                time.sleep(config.SLEEP_BETWEEN_CALLS)
                reference = get_pubmed_title_by_id(ids[0], {})
    except requests.RequestException:
        pass

    cache[cache_key] = reference
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return reference


def get_pubmed_reference(drug_name: str, pmids: list, context_terms: str,
                          pmid_cache: dict, search_cache: dict) -> Optional[dict]:
    """Prefer a PMID supplied directly by Open Targets; fall back to a
    keyword search on PubMed if none is available."""
    for pmid in pmids or []:
        ref = get_pubmed_title_by_id(pmid, pmid_cache)
        if ref:
            return ref
    return get_pubmed_reference_by_search(drug_name, context_terms, search_cache)
