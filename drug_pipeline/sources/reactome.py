"""
sources/reactome.py
====================
Reactome ContentService REST API - biological pathways a target participates
in, looked up by UniProt accession. Used exclusively by Module C, downstream
of sources/uniprot.py.
"""

import time

import requests

from .. import config


def get_reactome_pathways(uniprot_accession: str, cache: dict, limit: int = 5) -> list:
    if not uniprot_accession:
        return []
    if uniprot_accession in cache:
        return cache[uniprot_accession]

    pathways = []
    try:
        resp = requests.get(
            config.REACTOME_PATHWAYS_URL.format(uniprot_accession),
            params={"species": "9606"}, timeout=config.REQUEST_TIMEOUT,
        )
        if resp.ok:
            data = resp.json()
            for entry in data[:limit]:
                name = entry.get("displayName")
                if name:
                    pathways.append(name)
    except (requests.RequestException, ValueError):
        pass

    cache[uniprot_accession] = pathways
    time.sleep(config.SLEEP_BETWEEN_CALLS)
    return pathways
