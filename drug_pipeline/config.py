"""
config.py
=========
Single source of truth for every external endpoint, timeout, and status
vocabulary used across the pipeline. Nothing in here talks to the network -
it's pure configuration so every `sources/*` module reads from one place.
"""

import os

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
OT_URL = "https://api.platform.opentargets.org/api/v4/graphql"
CHEMBL_MOLECULE_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule/{}.json"
CTGOV_STUDY_URL = "https://clinicaltrials.gov/api/v2/studies/{}"
OPENFDA_DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
EUTILS_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EUTILS_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBCHEM_PROPERTY_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
    "{}/property/MolecularFormula,CanonicalSMILES,MolecularWeight/JSON"
)
UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
REACTOME_PATHWAYS_URL = "https://reactome.org/ContentService/data/mapping/UniProt/{}/pathways"
DISGENET_GDA_URL = "https://api.disgenet.com/api/v1/gda/summary"

# ---------------------------------------------------------------------------
# Status vocabularies (matched case-insensitively against Open Targets /
# ClinicalTrials.gov trial status strings)
# ---------------------------------------------------------------------------
STOPPED_STATUSES = {
    "terminated", "suspended", "withdrawn", "discontinued",
    "no longer available", "failed",
}

ONGOING_STATUSES = {
    "recruiting", "not yet recruiting", "active, not recruiting",
    "enrolling by invitation", "ongoing",
}

# ---------------------------------------------------------------------------
# Networking behaviour
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_CALLS = 0.34  # ~3 req/sec, polite to public APIs

# ---------------------------------------------------------------------------
# DisGeNET auth
# ---------------------------------------------------------------------------
DISGENET_API_KEY_ENV = "DISGENET_API_KEY"


def default_disgenet_api_key():
    return os.environ.get(DISGENET_API_KEY_ENV)
