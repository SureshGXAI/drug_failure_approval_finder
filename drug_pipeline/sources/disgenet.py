"""
sources/disgenet.py
====================
DisGeNET REST API - other diseases genetically/curation-associated with a
target gene, with evidence scores. Used exclusively by Module C.

Requires a free API key from https://www.disgenet.com (see README.md for
signup steps). Without a key, get_disgenet_associations() simply returns an
empty list rather than raising - the pipeline degrades gracefully.
"""

import time
from typing import Optional

import requests

from .. import config


def get_disgenet_associations(gene_symbol: str, api_key: Optional[str], cache: dict,
                               limit: int = 5) -> list:
    if not gene_symbol or not api_key:
        return []
    key = gene_symbol.strip().upper()
    if key in cache:
        return cache[key]

    associations = []
    try:
        headers = {"Authorization": api_key}
        params = {"gene_symbol": gene_symbol}
        resp = requests.get(config.DISGENET_GDA_URL, headers=headers, params=params,
                             timeout=config.REQUEST_TIMEOUT)
        if resp.ok:
            data = resp.json()
            # DisGeNET's response shape has varied across API versions; handle
            # a couple of plausible shapes defensively.
            records = data.get("payload") if isinstance(data, dict) else data
            if isinstance(records, list):
                for rec in records[:limit]:
                    associations.append({
                        "disease": rec.get("disease_name") or rec.get("diseaseName"),
                        "score": rec.get("score") or rec.get("gda_score"),
                    })
    except (requests.RequestException, ValueError):
        pass

    cache[key] = associations
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return associations
