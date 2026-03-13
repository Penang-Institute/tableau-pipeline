"""Shared helpers for OpenDOSM population data transforms.

Consolidates ETHNICITY_MAP, STATE_RENAMES, and clean_opendosm() which were
duplicated across population_opendosm.py and population_ethnicity.py.

Canonical ethnicity mapping: The R scripts (prep_pop_opendosm.R, line 107)
map "other_noncitizen" to "Non-Malaysian Citizens" in the base mapping, then
recode to "Non-citizens" only for district-level outputs. This module follows
the same convention.
"""

import pandas as pd

# --- Ethnicity mapping (OpenDOSM codes -> display labels) ----------------
# Covers all ethnicity codes found in population_state/district parquets.
ETHNICITY_MAP: dict[str, str] = {
    "overall_ethnicity": "Total",
    "bumi": "Bumiputera",
    "bumi_malay": "Malay",
    "bumi_other": "Other Bumiputera",
    "chinese": "Chinese",
    "indian": "Indians",
    "other_citizen": "Others",
    "other_noncitizen": "Non-Malaysian Citizens",
}

# --- Nationality mapping (for population_ethnicity) ----------------------
NATIONALITY_MAP: dict[str, str] = {
    "overall_ethnicity": "Total",
    "other_noncitizen": "Non-Malaysian",
}

# --- Historical state name corrections -----------------------------------
STATE_RENAMES: dict[str, str] = {
    "Johore": "Johor",
    "Malacca": "Melaka",
    "Negri Sembilan": "Negeri Sembilan",
    "Penang": "Pulau Pinang",
    "Trengganu": "Terengganu",
}


def clean_opendosm(
    df: pd.DataFrame,
    *,
    include_nationality: bool = False,
) -> pd.DataFrame:
    """Apply standard OpenDOSM population cleanup.

    Equivalent to the R ``clean_opendosm()`` helper used across multiple
    population scripts. Maps ethnicity codes, sex codes, extracts year
    from date, and renames standard columns.

    Args:
        df: Raw OpenDOSM population DataFrame.
        include_nationality: If True, also create a ``Nationality`` column
            using NATIONALITY_MAP (used by population_ethnicity).

    Returns:
        Cleaned DataFrame with columns: Ethnic, Gender, Year, Age,
        Population ('000), Updated as of.
    """
    result = df.copy()

    # Map ethnicity codes
    if "ethnicity" in result.columns:
        result["Ethnic"] = result["ethnicity"].map(ETHNICITY_MAP).fillna(
            result["ethnicity"].str.title()
        )
        if include_nationality:
            result["Nationality"] = (
                result["ethnicity"].map(NATIONALITY_MAP).fillna("Malaysian")
            )

    # Map sex
    if "sex" in result.columns:
        result["Gender"] = result["sex"].apply(
            lambda x: "Total" if x in ("both", "overall_sex") else str(x).title()
        )

    # Extract year from date
    if "date" in result.columns:
        result["Year"] = pd.to_datetime(result["date"]).dt.year
        result = result.drop(columns=["date"])

    result["Updated as of"] = pd.Timestamp.today().year

    # Rename age and population
    rename_map = {}
    if "age" in result.columns:
        rename_map["age"] = "Age"
    if "population" in result.columns:
        rename_map["population"] = "Population ('000)"
    result = result.rename(columns=rename_map)

    # Drop original coded columns
    for col in ["sex", "ethnicity"]:
        if col in result.columns:
            result = result.drop(columns=[col])

    return result


def recode_ethnicity_for_district(ethnic_label: str) -> str:
    """Recode ethnicity labels for district-level outputs.

    In the R scripts, district data recodes:
      - "Others" -> "Other Malaysians"
      - "Non-Malaysian Citizens" -> "Non-citizens"

    This matches prep_pop_opendosm.R line 220 and
    prep_pop_state_ethnicity.R line 394.
    """
    if ethnic_label == "Others":
        return "Other Malaysians"
    if ethnic_label == "Non-Malaysian Citizens":
        return "Non-citizens"
    return ethnic_label
