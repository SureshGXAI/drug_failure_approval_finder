"""
utils.py
========
Small, dependency-free helpers shared by every module: NCT-ID extraction,
status/text normalization, and CSV writing. Nothing here calls the network.
"""

import csv
import re
from typing import Optional

NCT_REGEX = re.compile(r"(NCT\d{6,})")


def extract_nct_id(url: Optional[str]) -> Optional[str]:
    """Pull a ClinicalTrials.gov NCT ID out of a URL, if present."""
    if not url:
        return None
    m = NCT_REGEX.search(url)
    return m.group(1) if m else None


def normalize_status(status: Optional[str]) -> str:
    if not status:
        return "Unknown"
    return status.strip().title()


def pubmed_str(ref: Optional[dict]) -> str:
    """Render a PubMed reference dict ({pmid, title, journal, year}) as one
    display string for a CSV cell."""
    if not ref or not ref.get("pmid"):
        return ""
    bits = [f"PMID:{ref['pmid']}"]
    if ref.get("title"):
        bits.append(ref["title"])
    if ref.get("journal") or ref.get("year"):
        bits.append(f"({ref.get('journal', '')} {ref.get('year', '')})".strip())
    return " - ".join(bits)


def pubchem_str(props: Optional[dict]) -> dict:
    """Normalize a PubChem properties dict into flat CSV-ready strings."""
    if not props:
        return {"cid": "", "formula": "", "smiles": "", "weight": ""}
    return {
        "cid": props.get("cid") or "",
        "formula": props.get("formula") or "",
        "smiles": props.get("smiles") or "",
        "weight": props.get("weight") or "",
    }


def write_csv(path: str, rows: list, default_fields: list) -> None:
    """Write a list of dicts to CSV. Falls back to `default_fields` as the
    header when `rows` is empty, so an empty result still produces a
    correctly-headed file."""
    fieldnames = list(rows[0].keys()) if rows else default_fields
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
