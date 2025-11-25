import io

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm

# --------------------------------------------------------------------
# CONSTANTS (Emission Factors)
# --------------------------------------------------------------------
FERT_EF_N2O_N = 0.01                    # kg N2O-N per kg N
N2O_TO_N2O_RATIO = 44 / 28              # molecular weight conversion
N2O_GWP = 265                           # Global Warming Potential of N2O
ELECTRICITY_EF_KG_PER_KWH = 0.716       # Indian grid (kg CO2/kWh)
DIESEL_EF_KG_PER_L = 2.68               # kg CO2e/L
PETROL_EF_KG_PER_L = 2.27               # kg CO2e/L
RICE_AREA_EF_KG_PER_HA = 7870           # kg CO2e/ha/year
RICE_YIELD_EF_KG_PER_KG = 0.9           # kg CO2e/kg rice
STEEL_EF_T_PER_TONNE = 2.55             # t CO2/tonne crude steel
LIVESTOCK_EF_KG_PER_HEAD_PER_YEAR = 912.5  # simple per cow/year factor


# --------------------------------------------------------------------
# CORE CALCULATION FUNCTIONS
# --------------------------------------------------------------------
def compute_fertilizer_emissions(n_kg: float) -> float:
    """
    Fertilizer emissions (kg CO2e):

    1. N2O-N = N_applied × 0.01
    2. N2O   = N2O-N × (44/28)
    3. CO2e  = N2O × 265
    """
    n2o_n_emissions = n_kg * FERT_EF_N2O_N
    n2o_emissions = n2o_n_emissions * N2O_TO_N2O_RATIO
    co2e_emissions = n2o_emissions * N2O_GWP
    return co2e_emissions


def fertilizer_emission_factor_kg_per_kgN() -> float:
    """Effective kg CO2e per kg N applied."""
    return FERT_EF_N2O_N * N2O_TO_N2O_RATIO * N2O_GWP


def compute_electricity_emissions(kwh: float) -> float:
    """Electricity emissions (kg CO2e)."""
    return kwh * ELECTRICITY_EF_KG_PER_KWH


def compute_fuel_emissions(litres: float, fuel_type: str) -> float:
    """Fuel emissions (kg CO2e) for diesel or petrol."""
    if fuel_type.lower() == "diesel":
        factor = DIESEL_EF_KG_PER_L
    else:
        factor = PETROL_EF_KG_PER_L
    return litres * factor


def compute_rice_emissions(area_ha: float, yield_tonnes: float) -> float:
    """
    Rice paddy emissions (kg CO2e):

    Area-based:  Em_area  = area_ha × 7,870
    Yield-based: Em_yield = yield_kg × 0.9
    Final:       Emissions = (Em_area + Em_yield) / 2
    """
    area_emissions = area_ha * RICE_AREA_EF_KG_PER_HA
    yield_emissions = yield_tonnes * 1000 * RICE_YIELD_EF_KG_PER_KG
    return (area_emissions + yield_emissions) / 2


def compute_steel_emissions(tonnes: float) -> float:
    """Steel production direct emissions (kg CO2)."""
    emissions_tonnes = tonnes * STEEL_EF_T_PER_TONNE
    return emissions_tonnes * 1000  # to kg


def compute_livestock_emissions(headcount: int) -> float:
    """Simple livestock (enteric methane) emissions (kg CO2e/year)."""
    return headcount * LIVESTOCK_EF_KG_PER_HEAD_PER_YEAR


def kg_to_tonnes(kg: float) -> float:
    return kg / 1000.0


def nice_number(x: float, ndigits: int = 2) -> str:
    return f"{x:.{ndigits}f}"


# --------------------------------------------------------------------
# MRV PDF HELPERS
# --------------------------------------------------------------------
def _base_mrv_header(story, styles, title_text, org, loc, year):
    title_style = styles["Title"]
    h2 = styles["Heading2"]
    normal = styles["Normal"]

    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 0.4 * cm))

    info_lines = [
        f"<b>Organisation / Facility:</b> {org}",
        f"<b>Location:</b> {loc}",
        f"<b>Reporting year:</b> {year}",
    ]
    for line in info_lines:
        story.append(Paragraph(line, normal))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Purpose of this MRV Report", h2))
    story.append(
        Paragraph(
            "This document provides a structured Measurement, Reporting and "
            "Verification (MRV) summary of greenhouse gas (GHG) emissions "
            "for the specified activity boundary. It is suitable as an "
            "evidence document for carbon accounting, crediting, or internal ESG reporting.",
            normal,
        )
    )
    story.append(Spacer(1, 0.5 * cm))


def _mrv_section_A_measurement_agri(story, styles, inputs_dict):
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]
    normal = styles["Normal"]

    area_ha = inputs_dict["area_ha"]
    crop_type = inputs_dict["crop_type"]
    rice_yield_t = inputs_dict["rice_yield_t"]
    fert_n_kg = inputs_dict["fert_n_kg"]
    diesel_l = inputs_dict["diesel_l"]
    petrol_l = inputs_dict["petrol_l"]
    elec_kwh = inputs_dict["elec_kwh"]
    livestock_count = inputs_dict["livestock_count"]

    fert_factor = fertilizer_emission_factor_kg_per_kgN()

    story.append(Paragraph("Section A – Measurement", h2))
    story.append(Spacer(1, 0.2 * cm))

    # A.1 Activity data
    story.append(Paragraph("A.1 Activity data collected", h3))
    story.append(
        Paragraph(
            "The following primary activity data were provided by the farmer/producer "
            "for the defined reporting year:",
            normal,
        )
    )
    story.append(Spacer(1, 0.2 * cm))

    bullet_lines = [
        f"Cultivated area: {nice_number(area_ha)} ha",
        f"Main crop: {crop_type}" + (f" (rice yield: {nice_number(rice_yield_t)} tonnes/year)" if crop_type == "Rice" else ""),
        f"Synthetic nitrogen fertilizer applied: {nice_number(fert_n_kg)} kg N/year",
        f"Diesel consumption: {nice_number(diesel_l)} litres/year",
        f"Petrol consumption: {nice_number(petrol_l)} litres/year",
        f"Electricity consumption: {nice_number(elec_kwh)} kWh/year",
        f"Number of cattle (enteric methane): {livestock_count} head",
    ]
    for line in bullet_lines:
        story.append(Paragraph("• " + line, normal))
    story.append(Spacer(1, 0.3 * cm))

    # A.2 Emission factors
    story.append(Paragraph("A.2 Emission factors used", h3))
    ef_lines = [
        f"Synthetic N fertilizer: {nice_number(fert_factor)} kg CO₂e per kg N applied",
        f"Diesel fuel: {DIESEL_EF_KG_PER_L} kg CO₂e per litre",
        f"Petrol: {PETROL_EF_KG_PER_L} kg CO₂e per litre",
        f"Grid electricity: {ELECTRICITY_EF_KG_PER_KWH} kg CO₂ per kWh",
        f"Rice paddies (if applicable): 7,870 kg CO₂e/ha/year and 0.9 kg CO₂e/kg rice",
        f"Livestock (cattle, simple factor): {LIVESTOCK_EF_KG_PER_HEAD_PER_YEAR} kg CO₂e/head/year",
    ]
    for line in ef_lines:
        story.append(Paragraph("• " + line, normal))
    story.append(Spacer(1, 0.3 * cm))

    # A.3 Calculation formulas
    story.append(Paragraph("A.3 Calculation formulas", h3))
    story.append(
        Paragraph(
            "For each emission source, emissions in kg CO₂e are computed as "
            "Activity data × Emission factor. Key formulas are:",
            normal,
        )
    )
    story.append(Spacer(1, 0.2 * cm))

    formula_lines = [
        "Fertilizer (N): Emissions = N_applied × 0.01 × (44/28) × 265",
        f"Diesel: Emissions = Diesel_volume_L × {DIESEL_EF_KG_PER_L}",
        f"Petrol: Emissions = Petrol_volume_L × {PETROL_EF_KG_PER_L}",
        f"Electricity: Emissions = Electricity_kWh × {ELECTRICITY_EF_KG_PER_KWH}",
        "Rice paddies: Emissions = (Area_ha × 7,870 + Rice_yield_kg × 0.9) / 2",
        f"Livestock: Emissions = Headcount × {LIVESTOCK_EF_KG_PER_HEAD_PER_YEAR}",
    ]
    for line in formula_lines:
        story.append(Paragraph("• " + line, normal))
    story.append(Spacer(1, 0.5 * cm))


def _mrv_section_A_measurement_alloy(story, styles, inputs_dict):
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]
    normal = styles["Normal"]

    steel_prod_t = inputs_dict["steel_prod_t"]
    elec_kwh_alloy = inputs_dict["elec_kwh_alloy"]
    diesel_l_alloy = inputs_dict["diesel_l_alloy"]
    petrol_l_alloy = inputs_dict["petrol_l_alloy"]

    story.append(Paragraph("Section A – Measurement", h2))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("A.1 Activity data collected", h3))
    story.append(
        Paragraph(
            "The following annual activity data were provided by the alloy/steel facility:",
            normal,
        )
    )
    story.append(Spacer(1, 0.2 * cm))

    bullet_lines = [
        f"Crude steel/alloy production: {nice_number(steel_prod_t)} tonnes/year",
        f"Electricity consumption: {nice_number(elec_kwh_alloy)} kWh/year",
        f"Diesel consumption: {nice_number(diesel_l_alloy)} litres/year",
        f"Petrol consumption: {nice_number(petrol_l_alloy)} litres/year",
    ]
    for line in bullet_lines:
        story.append(Paragraph("• " + line, normal))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("A.2 Emission factors used", h3))
    ef_lines = [
        f"Steel production: {STEEL_EF_T_PER_TONNE} t CO₂ per tonne of crude steel (~{STEEL_EF_T_PER_TONNE*1000:.0f} kg CO₂/tonne)",
        f"Grid electricity: {ELECTRICITY_EF_KG_PER_KWH} kg CO₂ per kWh",
        f"Diesel fuel: {DIESEL_EF_KG_PER_L} kg CO₂e per litre",
        f"Petrol: {PETROL_EF_KG_PER_L} kg CO₂e per litre",
    ]
    for line in ef_lines:
        story.append(Paragraph("• " + line, normal))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("A.3 Calculation formulas", h3))
    formula_lines = [
        f"Steel: Emissions = Steel_tonnes × {STEEL_EF_T_PER_TONNE} × 1000 (to kg)",
        f"Electricity: Emissions = Electricity_kWh × {ELECTRICITY_EF_KG_PER_KWH}",
        f"Diesel: Emissions = Diesel_volume_L × {DIESEL_EF_KG_PER_L}",
        f"Petrol: Emissions = Petrol_volume_L × {PETROL_EF_KG_PER_L}",
    ]
    for line in formula_lines:
        story.append(Paragraph("• " + line, normal))
    story.append(Spacer(1, 0.5 * cm))


def _mrv_section_B_reporting(story, styles, total_em_t, total_em_kg, baseline_t, credits_t, df_breakdown):
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]
    normal = styles["Normal"]

    story.append(Paragraph("Section B – Reporting", h2))
    story.append(Spacer(1, 0.2 * cm))

    # B.1 Summary KPIs
    story.append(Paragraph("B.1 Summary of GHG emissions", h3))
    story.append(
        Paragraph(
            f"Total GHG emissions for the defined activity boundary are estimated at "
            f"<b>{nice_number(total_em_t)}</b> t CO₂e/year "
            f"({nice_number(total_em_kg)} kg CO₂e/year).",
            normal,
        )
    )
    story.append(Spacer(1, 0.2 * cm))

    if baseline_t > 0:
        story.append(
            Paragraph(
                f"A baseline scenario of <b>{nice_number(baseline_t)}</b> t CO₂e/year "
                "was provided by the user.",
                normal,
            )
        )
        story.append(
            Paragraph(
                f"The difference between baseline and project emissions is "
                f"<b>{nice_number(credits_t, 3)}</b> t CO₂e/year, which represents the "
                "maximum potential annual volume of carbon credits, subject to verification "
                "and eligibility under a recognised standard.",
                normal,
            )
        )
    else:
        story.append(
            Paragraph(
                "No baseline scenario was provided, so this report focuses on absolute "
                "emissions rather than emission reductions.",
                normal,
            )
        )
    story.append(Spacer(1, 0.4 * cm))

    # B.2 Breakdown table
    story.append(Paragraph("B.2 Emissions breakdown by source", h3))

    table_cols = [
        "Source",
        "Activity data",
        "Emission factor",
        "Emissions (kg CO₂e/year)",
    ]
    df_display = df_breakdown[table_cols].copy()
    df_display["Emissions (kg CO₂e/year)"] = df_display["Emissions (kg CO₂e/year)"].round(2)

    table_data = [table_cols] + df_display.values.tolist()
    table = Table(table_data, colWidths=[5 * cm, 4 * cm, 4 * cm, 4 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 0.3 * cm))

    # B.3 Interpretation
    story.append(Paragraph("B.3 Interpretation of results", h3))

    try:
        top_row = df_display.loc[df_display["Emissions (kg CO₂e/year)"].idxmax()]
        dominant_source = top_row["Source"]
        dominant_value = float(top_row["Emissions (kg CO₂e/year)"])
        share_pct = (dominant_value / total_em_kg * 100) if total_em_kg > 0 else 0.0
        interp_text = (
            f"The largest contributor to total emissions is "
            f"<b>{dominant_source}</b>, with approximately "
            f"{nice_number(dominant_value)} kg CO₂e/year "
            f"({nice_number(share_pct)}% of total emissions). "
            "Prioritising mitigation interventions for this source will usually "
            "yield the greatest impact."
        )
    except Exception:
        interp_text = (
            "The breakdown table above shows the relative contribution of each "
            "source to total emissions. Mitigation options should focus on the "
            "largest contributors."
        )

    story.append(Paragraph(interp_text, normal))
    story.append(Spacer(1, 0.6 * cm))


def _mrv_section_C_verification(story, styles):
    h2 = styles["Heading2"]
    h3 = styles["Heading3"]
    normal = styles["Normal"]

    story.append(Paragraph("Section C – Verification", h2))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("C.1 Evidence and documentation", h3))
    story.append(
        Paragraph(
            "For third-party verification, the following evidence is typically required "
            "to substantiate the activity data used in this report:",
            normal,
        )
    )
    evidence_lines = [
        "Fuel purchase records (diesel/petrol invoices, logbooks).",
        "Electricity bills or meter readings covering the reporting year.",
        "Fertilizer purchase records and application logs.",
        "Production records (for alloy/steel plants) or yield/harvest records (for farms).",
        "Livestock registers (for enteric methane estimates).",
        "Any previous MRV reports or baseline studies.",
    ]
    for line in evidence_lines:
        story.append(Paragraph("• " + line, normal))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("C.2 Assumptions and limitations", h3))
    story.append(
        Paragraph(
            "This report relies on default emission factors and simplified formulas. "
            "Actual emissions may differ depending on site-specific technology, "
            "management practices and local conditions. For formal carbon crediting, "
            "the applicable methodology of the chosen standard (e.g., Gold Standard, "
            "Verra, ISO 14064) must be followed.",
            normal,
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("C.3 Sign-off (for internal use or verification)", h3))
    story.append(Paragraph("Prepared by: ___________________________", normal))
    story.append(Paragraph("Designation: ____________________________", normal))
    story.append(Paragraph("Date: _________________________________", normal))
    story.append(Spacer(1, 0.4 * cm))


def create_mrv_pdf_agri(org, loc, year, baseline_t, total_em_t, total_em_kg,
                         credits_t, df_breakdown, inputs_dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    _base_mrv_header(
        story,
        styles,
        "MRV Carbon Footprint & Carbon Credit Report – Agriculture",
        org,
        loc,
        year,
    )
    _mrv_section_A_measurement_agri(story, styles, inputs_dict)
    _mrv_section_B_reporting(story, styles, total_em_t, total_em_kg, baseline_t, credits_t, df_breakdown)
    _mrv_section_C_verification(story, styles)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def create_mrv_pdf_alloy(org, loc, year, baseline_t, total_em_t, total_em_kg,
                         credits_t, df_breakdown, inputs_dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    _base_mrv_header(
        story,
        styles,
        "MRV Carbon Footprint & Carbon Credit Report – Alloy / Steel",
        org,
        loc,
        year,
    )
    _mrv_section_A_measurement_alloy(story, styles, inputs_dict)
    _mrv_section_B_reporting(story, styles, total_em_t, total_em_kg, baseline_t, credits_t, df_breakdown)
    _mrv_section_C_verification(story, styles)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# --------------------------------------------------------------------
# STREAMLIT APP
# --------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="MRV Carbon Footprint & Carbon Credit Report",
        page_icon="🌱",
        layout="wide",
    )

    st.title("🌱 MRV Carbon Footprint & Carbon Credit Report")
    st.caption("Measurement, Reporting & Verification (MRV) prototype for agriculture and alloy/steel sectors.")

    st.markdown(
        """
This tool collects activity data, calculates greenhouse gas emissions in **CO₂e**,
and generates a structured **MRV PDF report** with:

- Section A – Measurement (data, factors, formulas)  
- Section B – Reporting (results, breakdown, interpretation)  
- Section C – Verification (evidence, assumptions, sign-off)  
        """
    )

    # Sidebar
    st.sidebar.header("Scenario details")
    sector = st.sidebar.selectbox(
        "Select sector / user type",
        ["Agriculture / Farmer", "Alloy / Steel Producer"],
    )
    organisation = st.sidebar.text_input("Organisation / Farm / Plant name", "")
    location = st.sidebar.text_input("Location (village/city, state)", "")
    reporting_year = st.sidebar.text_input("Reporting year (e.g., 2024–25)", "")

    st.sidebar.markdown("---")
    st.sidebar.info("Fill the form below and click **Generate Carbon Footprint & Credit Report**.")

    # Main form
    st.subheader("1. Input Data Form")

    with st.form("mrv_input_form"):
        baseline_tco2e = st.number_input(
            "Baseline emissions for this activity (t CO₂e/year, optional)",
            min_value=0.0,
            step=0.1,
            value=0.0,
            help="Business-as-usual or historical level, used to estimate potential carbon credits.",
        )

        st.markdown("---")

        if sector == "Agriculture / Farmer":
            st.markdown("#### Agriculture / Farming Inputs")

            col1, col2 = st.columns(2)
            with col1:
                area_ha = st.number_input(
                    "Cultivated area (hectares)",
                    min_value=0.0,
                    step=0.01,
                    value=0.0,
                )
                crop_type = st.selectbox("Main crop", ["General", "Rice"])
                if crop_type == "Rice":
                    rice_yield_t = st.number_input(
                        "Annual rice yield (tonnes/year)",
                        min_value=0.0,
                        step=0.1,
                        value=0.0,
                    )
                else:
                    rice_yield_t = 0.0

                livestock_count = st.number_input(
                    "Number of cattle (for enteric methane)",
                    min_value=0,
                    step=1,
                    value=0,
                )

            with col2:
                fert_n_kg = st.number_input(
                    "Synthetic nitrogen fertilizer applied (kg N/year)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                )
                diesel_l = st.number_input(
                    "Diesel consumption (L/year)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                )
                petrol_l = st.number_input(
                    "Petrol consumption (L/year)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                )
                elec_kwh = st.number_input(
                    "Electricity consumption (kWh/year)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                )

        else:
            st.markdown("#### Alloy / Steel Industry Inputs")

            col1, col2 = st.columns(2)
            with col1:
                steel_prod_t = st.number_input(
                    "Annual crude steel/alloy production (tonnes/year)",
                    min_value=0.0,
                    step=0.1,
                    value=0.0,
                )
                elec_kwh_alloy = st.number_input(
                    "Electricity consumption (kWh/year)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                )
            with col2:
                diesel_l_alloy = st.number_input(
                    "Diesel consumption (L/year)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                )
                petrol_l_alloy = st.number_input(
                    "Petrol consumption (L/year)",
                    min_value=0.0,
                    step=1.0,
                    value=0.0,
                )

        submitted = st.form_submit_button("✅ Generate Carbon Footprint & Credit Report")

    if not submitted:
        st.info("Fill in the form above and click **Generate Carbon Footprint & Credit Report**.")
        return

    org_display = organisation or "Unnamed facility / organisation"
    loc_display = location or "Location not specified"
    year_display = reporting_year or "Reporting year not specified"

    # After submit: calculations
    if sector == "Agriculture / Farmer":
        fert_em = compute_fertilizer_emissions(fert_n_kg)
        diesel_em = compute_fuel_emissions(diesel_l, "Diesel")
        petrol_em = compute_fuel_emissions(petrol_l, "Petrol")
        elec_em = compute_electricity_emissions(elec_kwh)
        rice_em = compute_rice_emissions(area_ha, rice_yield_t) if crop_type == "Rice" else 0.0
        livestock_em = compute_livestock_emissions(livestock_count)

        sources = [
            "Synthetic nitrogen fertilizer",
            "Diesel",
            "Petrol",
            "Electricity (grid)",
            "Rice paddies",
            "Livestock (enteric methane)",
        ]
        em_values_kg = [fert_em, diesel_em, petrol_em, elec_em, rice_em, livestock_em]

        total_em_kg = float(sum(em_values_kg))
        total_em_t = kg_to_tonnes(total_em_kg)
        potential_credits_t = max(0.0, baseline_tco2e - total_em_t) if baseline_tco2e > 0 else 0.0

        # Snapshot
        st.subheader("2. Emissions Snapshot")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total emissions", f"{nice_number(total_em_t)} t CO₂e/year")
        c2.metric("Baseline emissions", f"{nice_number(baseline_tco2e)} t CO₂e/year")
        c3.metric("Indicative carbon credits", f"{nice_number(potential_credits_t, 3)} t CO₂e/year")

        # Breakdown table on screen
        st.subheader("3. Emissions Breakdown by Source")
        ef_fert = fertilizer_emission_factor_kg_per_kgN()
        data_rows = [
            {
                "Source": "Synthetic nitrogen fertilizer",
                "Activity data": f"{nice_number(fert_n_kg)} kg N/year",
                "Emission factor": f"{nice_number(ef_fert)} kg CO₂e/kg N",
                "Formula": "Emissions = N × 0.01 × 44/28 × 265",
                "Emissions (kg CO₂e/year)": fert_em,
            },
            {
                "Source": "Diesel",
                "Activity data": f"{nice_number(diesel_l)} L/year",
                "Emission factor": f"{DIESEL_EF_KG_PER_L} kg CO₂e/L",
                "Formula": "Emissions = Diesel_L × 2.68",
                "Emissions (kg CO₂e/year)": diesel_em,
            },
            {
                "Source": "Petrol",
                "Activity data": f"{nice_number(petrol_l)} L/year",
                "Emission factor": f"{PETROL_EF_KG_PER_L} kg CO₂e/L",
                "Formula": "Emissions = Petrol_L × 2.27",
                "Emissions (kg CO₂e/year)": petrol_em,
            },
            {
                "Source": "Electricity (grid)",
                "Activity data": f"{nice_number(elec_kwh)} kWh/year",
                "Emission factor": f"{ELECTRICITY_EF_KG_PER_KWH} kg CO₂/kWh",
                "Formula": "Emissions = kWh × 0.716",
                "Emissions (kg CO₂e/year)": elec_em,
            },
            {
                "Source": "Rice paddies",
                "Activity data": f"{nice_number(area_ha)} ha & {nice_number(rice_yield_t)} t/year" if crop_type == "Rice" else "Not applicable",
                "Emission factor": "7,870 kg CO₂e/ha/year & 0.9 kg CO₂e/kg rice" if crop_type == "Rice" else "-",
                "Formula": "Emissions = (Area × 7,870 + Yield_kg × 0.9) / 2" if crop_type == "Rice" else "-",
                "Emissions (kg CO₂e/year)": rice_em,
            },
            {
                "Source": "Livestock (enteric methane)",
                "Activity data": f"{livestock_count} head of cattle",
                "Emission factor": f"{LIVESTOCK_EF_KG_PER_HEAD_PER_YEAR} kg CO₂e/head/year",
                "Formula": "Emissions = headcount × 912.5",
                "Emissions (kg CO₂e/year)": livestock_em,
            },
        ]
        df_breakdown = pd.DataFrame(data_rows)
        df_breakdown["Emissions (kg CO₂e/year)"] = df_breakdown["Emissions (kg CO₂e/year)"].round(2)
        st.dataframe(df_breakdown, use_container_width=True)

        # Chart
        chart_df = df_breakdown[["Source", "Emissions (kg CO₂e/year)"]]
        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X("Source", sort="-y"),
                y=alt.Y("Emissions (kg CO₂e/year)", title="Emissions (kg CO₂e/year)"),
                tooltip=["Source", "Emissions (kg CO₂e/year)"],
            )
            .properties(title="Emissions breakdown by source")
        )
        st.altair_chart(chart, use_container_width=True)

        # PDF creation
        inputs_dict = {
            "area_ha": area_ha,
            "crop_type": crop_type,
            "rice_yield_t": rice_yield_t,
            "fert_n_kg": fert_n_kg,
            "diesel_l": diesel_l,
            "petrol_l": petrol_l,
            "elec_kwh": elec_kwh,
            "livestock_count": livestock_count,
        }
        pdf_bytes = create_mrv_pdf_agri(
            org_display,
            loc_display,
            year_display,
            baseline_tco2e,
            total_em_t,
            total_em_kg,
            potential_credits_t,
            df_breakdown,
            inputs_dict,
        )

    else:
        # Alloy / Steel
        steel_em_kg = compute_steel_emissions(steel_prod_t)
        elec_em_kg = compute_electricity_emissions(elec_kwh_alloy)
        diesel_em_kg = compute_fuel_emissions(diesel_l_alloy, "Diesel")
        petrol_em_kg = compute_fuel_emissions(petrol_l_alloy, "Petrol")

        sources = ["Steel production", "Electricity (grid)", "Diesel", "Petrol"]
        em_values_kg = [steel_em_kg, elec_em_kg, diesel_em_kg, petrol_em_kg]

        total_em_kg = float(sum(em_values_kg))
        total_em_t = kg_to_tonnes(total_em_kg)
        potential_credits_t = max(0.0, baseline_tco2e - total_em_t) if baseline_tco2e > 0 else 0.0

        st.subheader("2. Emissions Snapshot")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total emissions", f"{nice_number(total_em_t)} t CO₂e/year")
        c2.metric("Baseline emissions", f"{nice_number(baseline_tco2e)} t CO₂e/year")
        c3.metric("Indicative carbon credits", f"{nice_number(potential_credits_t, 3)} t CO₂e/year")

        st.subheader("3. Emissions Breakdown by Source")
        data_rows = [
            {
                "Source": "Steel production",
                "Activity data": f"{nice_number(steel_prod_t)} tonnes/year",
                "Emission factor": f"{STEEL_EF_T_PER_TONNE} t CO₂/tonne (~{STEEL_EF_T_PER_TONNE*1000:.0f} kg CO₂/tonne)",
                "Formula": "Emissions = production_t × 2.55 × 1000",
                "Emissions (kg CO₂e/year)": steel_em_kg,
            },
            {
                "Source": "Electricity (grid)",
                "Activity data": f"{nice_number(elec_kwh_alloy)} kWh/year",
                "Emission factor": f"{ELECTRICITY_EF_KG_PER_KWH} kg CO₂/kWh",
                "Formula": "Emissions = kWh × 0.716",
                "Emissions (kg CO₂e/year)": elec_em_kg,
            },
            {
                "Source": "Diesel",
                "Activity data": f"{nice_number(diesel_l_alloy)} L/year",
                "Emission factor": f"{DIESEL_EF_KG_PER_L} kg CO₂e/L",
                "Formula": "Emissions = Diesel_L × 2.68",
                "Emissions (kg CO₂e/year)": diesel_em_kg,
            },
            {
                "Source": "Petrol",
                "Activity data": f"{nice_number(petrol_l_alloy)} L/year",
                "Emission factor": f"{PETROL_EF_KG_PER_L} kg CO₂e/L",
                "Formula": "Emissions = Petrol_L × 2.27",
                "Emissions (kg CO₂e/year)": petrol_em_kg,
            },
        ]
        df_breakdown = pd.DataFrame(data_rows)
        df_breakdown["Emissions (kg CO₂e/year)"] = df_breakdown["Emissions (kg CO₂e/year)"].round(2)
        st.dataframe(df_breakdown, use_container_width=True)

        chart_df = df_breakdown[["Source", "Emissions (kg CO₂e/year)"]]
        chart = (
            alt.Chart(chart_df)
            .mark_bar()
            .encode(
                x=alt.X("Source", sort="-y"),
                y=alt.Y("Emissions (kg CO₂e/year)", title="Emissions (kg CO₂e/year)"),
                tooltip=["Source", "Emissions (kg CO₂e/year)"],
            )
            .properties(title="Emissions breakdown by source")
        )
        st.altair_chart(chart, use_container_width=True)

        inputs_dict = {
            "steel_prod_t": steel_prod_t,
            "elec_kwh_alloy": elec_kwh_alloy,
            "diesel_l_alloy": diesel_l_alloy,
            "petrol_l_alloy": petrol_l_alloy,
        }

        pdf_bytes = create_mrv_pdf_alloy(
            org_display,
            loc_display,
            year_display,
            baseline_tco2e,
            total_em_t,
            total_em_kg,
            potential_credits_t,
            df_breakdown,
            inputs_dict,
        )

    # Download PDF
    st.subheader("4. Download MRV Report (PDF)")
    st.download_button(
        label="📄 Download MRV report (PDF)",
        data=pdf_bytes,
        file_name="mrv_carbon_footprint_report.pdf",
        mime="application/pdf",
    )


if __name__ == "__main__":
    main()
