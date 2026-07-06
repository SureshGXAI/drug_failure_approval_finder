"""
streamlit_app.py
=================
Interactive web front-end for the drug_pipeline package. Lets you run a
query, browse each module's results in its own tab, and download every
result as CSV plus one combined PDF report.

Run with:
    streamlit run streamlit_app.py

(Run this from the same directory that contains the drug_pipeline/ folder,
or `pip install -e .` / add it to PYTHONPATH first.)
"""

import base64
import io
import re

import pandas as pd
import streamlit as st

from drug_pipeline import config, report
from drug_pipeline.sources import open_targets
from drug_pipeline.modules import (
    module_a_failed, module_b_approved, module_c_annotation, module_d_ongoing,
)
from drug_pipeline.cli import build_caches, make_partner_helpers

st.set_page_config(page_title="Drug pipeline explorer", layout="wide")

NCT_URL_TEMPLATE = "https://clinicaltrials.gov/study/{}"
PUBMED_URL_TEMPLATE = "https://pubmed.ncbi.nlm.nih.gov/{}/"
UNIPROT_URL_TEMPLATE = "https://www.uniprot.org/uniprotkb/{}/entry"
PMID_REGEX = re.compile(r"PMID:(\d+)")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
class Args:
    """A plain object mimicking argparse.Namespace, since the module `run()`
    functions expect one. Built from the sidebar's widget values."""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def df_from_rows(rows: list, fieldnames: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=fieldnames)
    return pd.DataFrame(rows)


def download_csv_button(df: pd.DataFrame, label: str, file_name: str, key: str):
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, data=csv_bytes, file_name=file_name, mime="text/csv", key=key)


def embed_pdf_preview(pdf_bytes: bytes, height: int = 600):
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" width="100%" '
        f'height="{height}" style="border:none;"></iframe>',
        unsafe_allow_html=True,
    )


def _first_url(cell) -> str:
    """First URL out of a comma-joined 'Source URLs' cell, or ''."""
    if not cell or not isinstance(cell, str):
        return ""
    parts = [p.strip() for p in cell.split(",") if p.strip()]
    return parts[0] if parts else ""


def _nct_ids_to_url(cell) -> str:
    """Turn a 'Trial IDs (NCT)' cell into a clickable ClinicalTrials.gov URL
    when it holds exactly one ID. Multiple IDs are left as-is (can't cram
    more than one link into a single table cell)."""
    if not cell or not isinstance(cell, str):
        return cell or ""
    ids = [i.strip() for i in cell.split(",") if i.strip()]
    if len(ids) == 1:
        return NCT_URL_TEMPLATE.format(ids[0])
    return cell


def _pubmed_url_from_reference(cell) -> str:
    """Pull the PMID out of a 'PubMed Reference' cell (e.g. 'PMID:12345678 -
    Some title (Journal 2024)') and turn it into a clickable PubMed URL."""
    if not cell or not isinstance(cell, str):
        return ""
    m = PMID_REGEX.search(cell)
    return PUBMED_URL_TEMPLATE.format(m.group(1)) if m else ""


def clickable_view(df: pd.DataFrame):
    """
    Return (display_df, column_config) for st.dataframe(): a copy of `df`
    where URL-bearing columns are turned into single clickable links, so
    clicking a cell opens the original ClinicalTrials.gov trial or PubMed
    article. The CSV download always uses the original, unmodified `df`.
    """
    display_df = df.copy()
    column_config = {}

    if "Source URLs" in display_df.columns:
        display_df["Source URLs"] = display_df["Source URLs"].apply(_first_url)
        column_config["Source URLs"] = st.column_config.LinkColumn(
            "Source URLs", display_text="View study \u2197", width="small",
        )

    if "Trial IDs (NCT)" in display_df.columns:
        display_df["Trial IDs (NCT)"] = display_df["Trial IDs (NCT)"].apply(_nct_ids_to_url)
        column_config["Trial IDs (NCT)"] = st.column_config.LinkColumn(
            "Trial IDs (NCT)", display_text=r"study/(NCT\d+)", width="small",
        )

    if "PubMed Reference" in display_df.columns:
        pubmed_links = df["PubMed Reference"].apply(_pubmed_url_from_reference)
        if pubmed_links.any():
            insert_at = display_df.columns.get_loc("PubMed Reference") + 1
            display_df.insert(insert_at, "PubMed Link", pubmed_links)
            column_config["PubMed Link"] = st.column_config.LinkColumn(
                "PubMed Link", display_text="View on PubMed \u2197", width="small",
            )

    return display_df, column_config


def annotation_clickable_view(df: pd.DataFrame):
    """Same idea as clickable_view(), but for the annotation table: turns
    the UniProt Accession column into a clickable link to the UniProt entry."""
    display_df = df.copy()
    column_config = {}

    if "UniProt Accession" in display_df.columns:
        accessions = df["UniProt Accession"]
        insert_at = display_df.columns.get_loc("UniProt Accession") + 1
        display_df.insert(
            insert_at, "UniProt Link",
            accessions.apply(lambda a: UNIPROT_URL_TEMPLATE.format(a.strip()) if a else ""),
        )
        column_config["UniProt Link"] = st.column_config.LinkColumn(
            "UniProt Link", display_text="View on UniProt \u2197", width="small",
        )

    return display_df, column_config


# ---------------------------------------------------------------------------
# Sidebar - query + options
# ---------------------------------------------------------------------------
st.sidebar.title("Drug pipeline explorer")
st.sidebar.caption(
    "Open Targets, ChEMBL, ClinicalTrials.gov, openFDA, PubMed, PubChem, "
    "UniProt, Reactome, and DisGeNET, combined into one report."
)

query = st.sidebar.text_input(
    "Target or disease",
    placeholder="e.g. EGFR, Alzheimer's disease, ENSG00000146648, EFO_0000270",
)

with st.sidebar.expander("Options", expanded=False):
    top_targets = st.number_input(
        "Top associated targets to annotate (disease queries only)",
        min_value=1, max_value=25, value=5,
    )
    disgenet_api_key = st.text_input(
        "DisGeNET API key (optional)",
        value=config.default_disgenet_api_key() or "",
        type="password",
        help="Free key from https://www.disgenet.com. Leave blank to skip DisGeNET.",
    )
    skip_enrichment = st.checkbox("Skip ChEMBL / ClinicalTrials.gov lookups", value=False)
    skip_fda_lookup = st.checkbox("Skip openFDA lookups", value=False)
    skip_pubmed = st.checkbox("Skip PubMed reference lookups", value=False)
    skip_pubchem = st.checkbox("Skip PubChem chemical-property lookups", value=False)
    skip_annotation = st.checkbox("Skip target annotation (Module C)", value=False)
    skip_ongoing = st.checkbox("Skip ongoing trials (Module D)", value=False)

run_clicked = st.sidebar.button("Run pipeline", type="primary", use_container_width=True)


# ---------------------------------------------------------------------------
# Run the pipeline (mirrors drug_pipeline/cli.py, minus argparse/file writes)
# ---------------------------------------------------------------------------
def run_pipeline(query: str, args: Args):
    status = st.status("Running pipeline...", expanded=True)

    status.write(f"Resolving '{query}' via Open Targets ...")
    entity = open_targets.resolve_input(query)
    status.write(f"Using {entity['type']} **{entity['name']}** (`{entity['id']}`)")

    status.write("Fetching drug and clinical trial data from Open Targets ...")
    raw_rows = open_targets.fetch_known_drugs(entity["type"], entity["id"])
    flat_reports = open_targets.flatten_clinical_reports(raw_rows)
    status.write(f"Retrieved {len(raw_rows)} drug records "
                 f"({len(flat_reports)} drug/trial-report rows).")

    caches = build_caches()
    partner_col, queried_partner = make_partner_helpers(entity["type"])

    status.write("Running Module A (failed / stopped / discontinued) ...")
    failed_rows = module_a_failed.run(flat_reports, partner_col, queried_partner, args, caches)

    status.write("Running Module B (FDA-approved) ...")
    approved_rows = module_b_approved.run(raw_rows, entity["type"], partner_col, args, caches)

    ongoing_rows = []
    if not args.skip_ongoing:
        status.write("Running Module D (ongoing clinical trials) ...")
        ongoing_rows = module_d_ongoing.run(flat_reports, partner_col, queried_partner, args, caches)

    annotation_rows = []
    if not args.skip_annotation:
        status.write("Running Module C (target biological annotation) ...")
        annotation_rows = module_c_annotation.run(entity, args, caches)

    status.update(label="Pipeline complete.", state="complete", expanded=False)

    return {
        "entity": entity,
        "partner_col": partner_col,
        "failed": failed_rows,
        "approved": approved_rows,
        "ongoing": ongoing_rows,
        "annotation": annotation_rows,
    }


if run_clicked:
    if not query.strip():
        st.sidebar.error("Enter a target or disease first.")
    else:
        args = Args(
            top_targets=int(top_targets),
            disgenet_api_key=disgenet_api_key or None,
            skip_enrichment=skip_enrichment,
            skip_fda_lookup=skip_fda_lookup,
            skip_pubmed=skip_pubmed,
            skip_pubchem=skip_pubchem,
            skip_annotation=skip_annotation,
            skip_ongoing=skip_ongoing,
        )
        try:
            st.session_state["results"] = run_pipeline(query.strip(), args)
        except Exception as exc:
            st.error(f"Pipeline failed: {exc}")


# ---------------------------------------------------------------------------
# Main area - tabs
# ---------------------------------------------------------------------------
results = st.session_state.get("results")

if not results:
    st.title("Drug pipeline explorer")
    st.write(
        "Enter a target (gene symbol or Ensembl ID) or a disease (name or "
        "EFO/MONDO ID) in the sidebar and click **Run pipeline** to get started."
    )
else:
    entity = results["entity"]
    partner_col = results["partner_col"]
    st.title(f"Results for {entity['name']}")
    st.caption(f"Resolved as {entity['type']} `{entity['id']}`")

    failed_df = df_from_rows(results["failed"], module_a_failed.fieldnames(partner_col))
    approved_df = df_from_rows(results["approved"], module_b_approved.fieldnames(partner_col))
    ongoing_df = df_from_rows(results["ongoing"], module_d_ongoing.fieldnames(partner_col))
    annotation_df = df_from_rows(results["annotation"], module_c_annotation.FIELDNAMES)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Failed / stopped", len(failed_df))
    col2.metric("Approved", len(approved_df))
    col3.metric("Ongoing trials", len(ongoing_df))
    col4.metric("Targets annotated", len(annotation_df))

    tab_failed, tab_approved, tab_ongoing, tab_annotation, tab_report = st.tabs([
        "Failed / stopped", "Approved", "Ongoing trials", "Target annotation", "PDF report",
    ])

    with tab_failed:
        st.subheader("Failed, stopped, or discontinued drugs")
        display_df, col_cfg = clickable_view(failed_df)
        st.dataframe(display_df, use_container_width=True, column_config=col_cfg)
        download_csv_button(failed_df, "Download CSV", "failed_drugs.csv", "dl_failed")

    with tab_approved:
        st.subheader("FDA-approved drugs")
        display_df, col_cfg = clickable_view(approved_df)
        st.dataframe(display_df, use_container_width=True, column_config=col_cfg)
        download_csv_button(approved_df, "Download CSV", "approved_drugs.csv", "dl_approved")

    with tab_ongoing:
        st.subheader("Ongoing clinical trials")
        display_df, col_cfg = clickable_view(ongoing_df)
        st.dataframe(display_df, use_container_width=True, column_config=col_cfg)
        download_csv_button(ongoing_df, "Download CSV", "ongoing_trials.csv", "dl_ongoing")

    with tab_annotation:
        st.subheader("Target biological annotation")
        display_df, col_cfg = annotation_clickable_view(annotation_df)
        st.dataframe(display_df, use_container_width=True, column_config=col_cfg)
        download_csv_button(annotation_df, "Download CSV", "target_annotation.csv", "dl_annotation")

    with tab_report:
        st.subheader("Combined PDF report")
        st.write("A single PDF summarizing all four tables above, for sharing or printing.")
        if st.button("Generate PDF report"):
            with st.spinner("Building PDF ..."):
                buffer_path = "/tmp/drug_pipeline_report.pdf"
                report.build_pdf(entity, {
                    "failed": results["failed"],
                    "approved": results["approved"],
                    "ongoing": results["ongoing"],
                    "annotation": results["annotation"],
                }, buffer_path)
                with open(buffer_path, "rb") as f:
                    st.session_state["pdf_bytes"] = f.read()

        pdf_bytes = st.session_state.get("pdf_bytes")
        if pdf_bytes:
            st.download_button(
                "Download PDF report", data=pdf_bytes,
                file_name=f"{entity['name'].replace(' ', '_')}_drug_pipeline_report.pdf",
                mime="application/pdf",
            )
            embed_pdf_preview(pdf_bytes)
