"""
sources/uniprot.py
===================
UniProt REST API - protein name, function summary, and keywords for a gene
symbol. Used exclusively by Module C, and feeds the accession number that
Module C then hands to sources/reactome.py.
"""

import time
from typing import Optional

import requests

from .. import config


def get_uniprot_annotation(gene_symbol: str, cache: dict) -> Optional[dict]:
    if not gene_symbol:
        return None
    key = gene_symbol.strip().upper()
    if key in cache:
        return cache[key]

    info = None
    try:
        params = {
            "query": f"gene:{gene_symbol} AND organism_id:9606 AND reviewed:true",
            "fields": "accession,protein_name,cc_function,keyword",
            "format": "json",
            "size": 1,
        }
        resp = requests.get(config.UNIPROT_SEARCH_URL, params=params,
                             timeout=config.REQUEST_TIMEOUT)
        if resp.ok:
            results = resp.json().get("results", [])
            if results:
                entry = results[0]
                accession = entry.get("primaryAccession")
                protein_name = (
                    entry.get("proteinDescription", {})
                    .get("recommendedName", {})
                    .get("fullName", {})
                    .get("value")
                )
                function_text = None
                for comment in entry.get("comments", []):
                    if comment.get("commentType") == "FUNCTION":
                        texts = comment.get("texts", [])
                        if texts:
                            function_text = texts[0].get("value")
                        break
                keywords = [kw.get("name") for kw in entry.get("keywords", [])][:8]
                info = {
                    "accession": accession,
                    "protein_name": protein_name,
                    "function": function_text,
                    "keywords": keywords,
                }
    except requests.RequestException:
        pass

    cache[key] = info
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return info
