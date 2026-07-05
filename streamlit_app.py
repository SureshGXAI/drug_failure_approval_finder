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

import pandas as pd
import streamlit as st

from drug_pipeline import config, report
from drug_pipeline.sources import open_targets
from drug_pipeline.modules import (
    module_a_failed, module_b_approved, module_c_annotation, module_d_ongoing,
)
from drug_pipeline.cli import build_caches, make_partner_helpers

st.set_page_config(page_title="Drug pipeline explorer", layout="wide")


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
        st.dataframe(failed_df, use_container_width=True)
        download_csv_button(failed_df, "Download CSV", "failed_drugs.csv", "dl_failed")

    with tab_approved:
        st.subheader("FDA-approved drugs")
        st.dataframe(approved_df, use_container_width=True)
        download_csv_button(approved_df, "Download CSV", "approved_drugs.csv", "dl_approved")

    with tab_ongoing:
        st.subheader("Ongoing clinical trials")
        st.dataframe(ongoing_df, use_container_width=True)
        download_csv_button(ongoing_df, "Download CSV", "ongoing_trials.csv", "dl_ongoing")

    with tab_annotation:
        st.subheader("Target biological annotation")
        st.dataframe(annotation_df, use_container_width=True)
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
