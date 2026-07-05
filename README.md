# Drug Failure & Approval Finder

Given a **target** (gene symbol or Ensembl ID) or a **disease** (free-text
name or EFO/MONDO/Orphanet ID), this tool produces three CSV reports:

| File | Contents |
|---|---|
| `failed_drugs.csv` | Drugs that were **failed / stopped / terminated / suspended / withdrawn / discontinued** at Phase I, II, or III |
| `approved_drugs.csv` | Drugs that reached **FDA approval** |
| `target_annotation.csv` | Biological context on the target(s) involved (protein function, pathways, other disease associations) |
| `ongoing_trials.csv` | Drugs currently in an **active clinical trial** (Recruiting, Not yet recruiting, Active not recruiting, Enrolling by invitation) |

## Project layout

The pipeline is a proper Python package now, not a single script. Each
external API and each output module lives in its own file:

```
drug_failure_finder.py        thin backward-compatible entry point
streamlit_app.py               interactive web UI (tabs + downloads)
README.md
drug_pipeline/
├── __init__.py
├── __main__.py                lets you run `python -m drug_pipeline`
├── cli.py                     argparse + orchestration (the only file that
│                              wires modules and sources together)
├── config.py                  endpoints, timeouts, status vocab, env vars
├── utils.py                   shared helpers (CSV writer, string formatting)
├── report.py                  builds the combined PDF report
├── sources/                   one file per external API - no CSV/CLI logic
│   ├── open_targets.py        core data source: resolve + fetch + reshape
│   ├── chembl.py
│   ├── clinicaltrials.py
│   ├── openfda.py
│   ├── pubmed.py
│   ├── pubchem.py
│   ├── uniprot.py
│   ├── reactome.py
│   └── disgenet.py
└── modules/                   one file per output CSV - orchestrates sources
    ├── module_a_failed.py
    ├── module_b_approved.py
    ├── module_c_annotation.py
    └── module_d_ongoing.py
```

Each `sources/*.py` file does exactly one thing: call one external API and
return plain dicts/lists. Each `modules/*.py` file takes already-fetched
Open Targets data plus shared cache dicts, calls whichever sources it
needs, and returns rows ready to write to CSV. `cli.py` is the only file
that knows about argparse, file paths, or the order things run in - so you
can import and reuse any `sources` or `modules` function independently
(e.g. in a notebook, a test, or a different pipeline) without pulling in
the CLI at all.

Run it either way - both are equivalent:

```bash
python3 drug_failure_finder.py --query "EGFR"
python3 -m drug_pipeline --query "EGFR"          # run from the directory containing drug_pipeline/
```

## PDF report

Every CLI run also builds a combined PDF (`drug_pipeline_report.pdf` by
default) with a title/summary page followed by one table per module. It's a
curated summary - a handful of the most useful columns per module, not a
full CSV dump - meant for sharing or printing. The full column set is
always in the matching CSV.

```bash
python3 drug_failure_finder.py --query "EGFR" --pdf-output egfr_report.pdf
python3 drug_failure_finder.py --query "EGFR" --skip-pdf   # skip building it
```

`drug_pipeline/report.py` exposes `build_pdf(entity, module_rows, output_path)`
directly if you want to generate a PDF from data you've already fetched
(this is exactly how `streamlit_app.py` uses it).

## Streamlit web app

`streamlit_app.py` gives you an interactive UI: enter a target or disease,
click **Run pipeline**, and browse each module's results in its own tab -
Failed / stopped, Approved, Ongoing trials, Target annotation, and PDF
report - each with a CSV download button, plus a PDF download and inline
preview in the last tab.

```bash
pip install streamlit requests reportlab pandas
streamlit run streamlit_app.py
```

The app calls the exact same `drug_pipeline.sources` / `drug_pipeline.modules`
functions the CLI does - it just renders the results interactively instead
of writing files directly, and lets you download each one (or the combined
PDF) on demand. All the sidebar options mirror the CLI's `--skip-*` flags
and `--top-targets` / `--disgenet-api-key`.

## Data sources

| # | Source | Used for |
|---|---|---|
| 1 | [Open Targets Platform](https://platform.opentargets.org/) (GraphQL) | Resolves your input to a target/disease ID; lists every drug tested against it with clinical phase and trial status; maps a disease to its top associated targets |
| 2 | [ChEMBL](https://www.ebi.ac.uk/chembl/) (REST) | Official market-withdrawal reason, year, and country |
| 3 | [ClinicalTrials.gov](https://clinicaltrials.gov/) (API v2) | The "why stopped" free-text reason for a specific terminated/suspended/withdrawn trial |
| 4 | [openFDA Drugs@FDA](https://open.fda.gov/apis/drug/drugsfda/) | Confirms US FDA approval; application number, sponsor, approval date, marketing status |
| 5 | [PubMed](https://pubmed.ncbi.nlm.nih.gov/) (NCBI E-utilities) | A representative supporting literature reference (PMID + title) for each drug's failure or approval |
| 6 | [PubChem](https://pubchem.ncbi.nlm.nih.gov/) (PUG REST) | Chemical identifiers: CID, molecular formula, canonical SMILES, molecular weight |
| 7 | [UniProt](https://www.uniprot.org/) (REST) | Target protein name, functional summary, keywords |
| 8 | [Reactome](https://reactome.org/) (ContentService REST) | Biological pathways the target participates in |
| 9 | [DisGeNET](https://www.disgenet.com/) (REST, **requires a free API key**) | Other diseases genetically/curation-associated with the target, with evidence scores |

All sources are free to use. Only DisGeNET requires registering for an API
key; if you don't provide one, that column is simply left blank and every
other module still runs normally.

## Installation

Requires Python 3.8+.

```bash
pip install requests reportlab
pip install streamlit pandas   # only needed for the web app (streamlit_app.py)
```

## Usage

```bash
# Basic: target by gene symbol
python3 drug_failure_finder.py --query "EGFR"

# Basic: disease by name
python3 drug_failure_finder.py --query "Alzheimer's disease"

# Using stable IDs directly (skips the name-resolution search step)
python3 drug_failure_finder.py --query ENSG00000146648   # target
python3 drug_failure_finder.py --query EFO_0000270        # disease

# Custom output filenames
python3 drug_failure_finder.py --query "EGFR" \
    --output egfr_failed.csv \
    --approved-output egfr_approved.csv \
    --annotation-output egfr_annotation.csv \
    --ongoing-output egfr_ongoing.csv

# Disease query, annotate top 10 associated targets instead of the default 5
python3 drug_failure_finder.py --query "asthma" --top-targets 10

# Provide a DisGeNET API key (or set the DISGENET_API_KEY env var instead)
python3 drug_failure_finder.py --query "EGFR" --disgenet-api-key YOUR_KEY_HERE
```

### Speed / scope flags

Each enrichment step calls a public API and is rate-limited (~3 requests/
second) to be a good citizen. For targets/diseases with many known drugs,
a full run can take a while. Skip any step you don't need:

| Flag | Effect |
|---|---|
| `--skip-enrichment` | Skip ChEMBL / ClinicalTrials.gov lookups (Module A) |
| `--skip-fda-lookup` | Skip openFDA lookups (Module B) |
| `--skip-pubmed` | Skip PubMed reference lookups (Modules A & B) |
| `--skip-pubchem` | Skip PubChem chemical-property lookups (Modules A & B) |
| `--skip-annotation` | Skip Module C entirely (UniProt/Reactome/DisGeNET) |
| `--skip-ongoing` | Skip Module D entirely (ongoing clinical trials) |

## Output columns

### `failed_drugs.csv`
`Drug Name, Drug ID (ChEMBL), Queried Disease/Target (per drug), Phase, Status, Reason, Mechanism of Action, Trial IDs (NCT), PubMed Reference, PubChem CID, Molecular Formula, Canonical SMILES, Molecular Weight, Source URLs`

### `approved_drugs.csv`
`Drug Name, Drug ID (ChEMBL), Queried Disease/Target (per drug), Phase, FDA Approval Status, Application Number(s), Sponsor(s), Approval Date(s), Marketing Status, Mechanism of Action, PubMed Reference, PubChem CID, Molecular Formula, Canonical SMILES, Molecular Weight, Source URLs`

### `target_annotation.csv`
`Gene Symbol, Ensembl Target ID, Association Score (to queried disease), UniProt Accession, Protein Name, Function Summary, UniProt Keywords, Reactome Pathways, DisGeNET Associated Diseases`

### `ongoing_trials.csv`
`Drug Name, Drug ID (ChEMBL), Queried Disease/Target (per drug), Phase, Trial Status, Sponsor, Estimated Primary Completion Date, Trial Start Date, Mechanism of Action, Trial IDs (NCT), PubMed Reference, PubChem CID, Molecular Formula, Canonical SMILES, Molecular Weight, Source URLs`

(The "Association Score" column is only populated when you queried by
disease; for a direct target query it is left blank since there's no
disease to score against.)

## Notes & limitations

- **Internet access is required at run time** — the script makes live calls
  to eight public APIs.
- **Open Targets schema**: Open Targets retired the old `knownDrugs` field.
  This script uses the current `drugAndClinicalCandidates` field (one row
  per drug, each carrying a list of `clinicalReports` for individual trial
  records), which it flattens internally. If you see a `400 Bad Request` /
  GraphQL error again in the future, Open Targets has likely changed its
  schema again — check `https://api.platform.opentargets.org/api/v4/graphql/schema`
  (or the interactive browser at `.../graphql/browser`) and compare against
  the `MOA_FRAGMENT` / `REPORT_FRAGMENT` query fragments near the top of
  `fetch_known_drugs()`.
- **Name matching** for PubChem/openFDA/PubMed is done by drug name string
  match; uncommon synonyms, salts, or brand-vs-generic naming can
  occasionally cause a miss. When that happens, the relevant columns are
  left blank rather than guessed.
- **DisGeNET's API has changed shape across versions.** The request/response
  handling is written defensively, but if DisGeNET updates their API again,
  you may need to adjust `get_disgenet_associations()` — the failure mode is
  simply an empty column, not a crash.
- Trial "Status" values are as reported by Open Targets (sourced from ChEMBL
  and ClinicalTrials.gov) at the time of your query; historical trial
  statuses can occasionally be revised by trial sponsors.
- This tool is for research/informational purposes and does not constitute
  regulatory, medical, or investment advice.
