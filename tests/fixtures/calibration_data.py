"""
Calibration fixture data for CRIA indicator tests.

Generates synthetic but realistic datasets for calibration/regression testing
of the full indicator -> aggregation -> binning pipeline. Uses fixed seed
for reproducibility.
"""

import numpy as np
import pandas as pd


# Fixed seed for reproducibility
RNG = np.random.default_rng(42)


def _clamp(arr: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Clamp array values to [lo, hi]."""
    return np.clip(arr, lo, hi)


def get_calibration_county_data(n_rows: int = 200) -> pd.DataFrame:
    """
    Generate synthetic county dataset with all source columns needed
    for the 22 CRIA indicators.

    Uses realistic distributions — not uniform random — based on typical
    county-level data ranges across the US.

    Args:
        n_rows: Number of synthetic counties to generate.

    Returns:
        DataFrame indexed by GEO_ID with all source columns required
        by the 22 indicators defined in config/indicators.yaml.
    """
    rng = np.random.default_rng(42)

    # Deterministic unique GEO_IDs: state cycles 01-55, county increments
    geo_ids = [f"0500000US{(i % 55) + 1:02d}{(i // 55) + 1:03d}"
               for i in range(n_rows)]

    # --- Population base ---
    total_pop = rng.lognormal(mean=10.5, sigma=1.2, size=n_rows).astype(int)
    total_pop = _clamp(total_pop, 5000, 500000)

    # --- Housing (DP04) ---
    housing_units = (total_pop * rng.uniform(0.35, 0.50, n_rows)).astype(int)
    mobile_homes = (housing_units * rng.uniform(0.02, 0.25, n_rows)).astype(int)
    owner_occupied = (housing_units * rng.uniform(0.50, 0.80, n_rows)).astype(int)

    # --- Education (S1501) ---
    pop_25_plus = (total_pop * rng.uniform(0.55, 0.70, n_rows)).astype(int)
    no_hs_9th = (pop_25_plus * rng.uniform(0.02, 0.10, n_rows)).astype(int)
    no_hs_12th = (pop_25_plus * rng.uniform(0.02, 0.08, n_rows)).astype(int)

    # --- No Vehicle (B08201) ---
    total_hh = (total_pop * rng.uniform(0.30, 0.45, n_rows)).astype(int)
    no_vehicle_hh = (total_hh * rng.uniform(0.02, 0.15, n_rows)).astype(int)

    # --- Age (S0101) ---
    pop_65_plus = (total_pop * rng.uniform(0.10, 0.25, n_rows)).astype(int)

    # --- Disability (S1810) ---
    civilian_pop = (total_pop * rng.uniform(0.95, 0.99, n_rows)).astype(int)
    disabled_pop = (civilian_pop * rng.uniform(0.08, 0.22, n_rows)).astype(int)

    # --- Limited English (S1602) ---
    hh_total_lang = (total_hh * rng.uniform(0.90, 1.0, n_rows)).astype(int)
    hh_limited_eng = (hh_total_lang * rng.uniform(0.01, 0.12, n_rows)).astype(int)

    # --- Single Parent (B09005) ---
    children_total = (total_pop * rng.uniform(0.15, 0.30, n_rows)).astype(int)
    single_father = (children_total * rng.uniform(0.02, 0.06, n_rows)).astype(int)
    single_mother = (children_total * rng.uniform(0.05, 0.15, n_rows)).astype(int)

    # --- Communications (S2801) ---
    hh_with_computer = (total_hh * rng.uniform(0.70, 0.95, n_rows)).astype(int)

    # --- Inactive Voter (EAVS) ---
    reg_voters = (total_pop * rng.uniform(0.45, 0.75, n_rows)).astype(int)
    inactive_voters = (reg_voters * rng.uniform(0.05, 0.25, n_rows)).astype(int)

    # --- CBP: Civil Org (NAICS 813410) ---
    civil_orgs = rng.integers(0, 20, size=n_rows)

    # --- CBP: Hospitals (NAICS 622110) ---
    hospitals = rng.integers(0, 8, size=n_rows)

    # --- Population Change (POP: NETMIG) ---
    net_mig_base = rng.normal(loc=50, scale=300, size=n_rows)
    netmig_2020 = (net_mig_base + rng.normal(0, 50, n_rows)).astype(int)
    netmig_2019 = (net_mig_base + rng.normal(0, 50, n_rows)).astype(int)
    netmig_2018 = (net_mig_base + rng.normal(0, 50, n_rows)).astype(int)
    netmig_2017 = (net_mig_base + rng.normal(0, 50, n_rows)).astype(int)
    netmig_2016 = (net_mig_base + rng.normal(0, 50, n_rows)).astype(int)

    # --- Religion (ARDA) ---
    religious_adherents = (total_pop * rng.uniform(0.20, 0.80, n_rows)).astype(int)
    arda_pop = total_pop.copy()

    # --- Unemployment (DP03) ---
    labor_force = (total_pop * rng.uniform(0.45, 0.65, n_rows)).astype(int)
    civilian_lf = (labor_force * rng.uniform(0.97, 0.995, n_rows)).astype(int)
    unemployed = (civilian_lf * rng.uniform(0.02, 0.15, n_rows)).astype(int)

    # --- Unemployed Women (DP03) ---
    women_16_plus = (total_pop * rng.uniform(0.35, 0.45, n_rows)).astype(int)
    women_employed = (women_16_plus * rng.uniform(0.45, 0.70, n_rows)).astype(int)

    # --- Median Income (S1903) ---
    median_income = rng.normal(loc=55000, scale=15000, size=n_rows)
    median_income = _clamp(median_income, 20000, 120000).astype(int)

    # --- GINI (B19083) ---
    gini = rng.normal(loc=0.44, scale=0.04, size=n_rows)
    gini = _clamp(gini, 0.35, 0.55)

    # --- Lack of Economic Diversity (DP03: 13 industry sectors) ---
    # Generate 13 industry sector employment counts
    industry_cols = {}
    for i, code in enumerate(range(33, 46)):  # DP03_0033E through DP03_0045E
        col = f"DP03_{code:04d}E"
        share = rng.uniform(0.02, 0.25, n_rows)
        industry_cols[col] = (civilian_lf * share).astype(int)
    total_employed = (civilian_lf * rng.uniform(0.85, 0.98, n_rows)).astype(int)

    # --- Poverty (S1701) ---
    poverty_pop_det = (total_pop * rng.uniform(0.90, 0.99, n_rows)).astype(int)
    poverty_count = (poverty_pop_det * rng.uniform(0.05, 0.30, n_rows)).astype(int)

    # --- Medical (S2401) ---
    medical_workers = (total_pop * rng.uniform(0.005, 0.03, n_rows)).astype(int)

    # --- Uninsured (S2701) ---
    civ_noninst = (total_pop * rng.uniform(0.92, 0.98, n_rows)).astype(int)
    uninsured = (civ_noninst * rng.uniform(0.04, 0.20, n_rows)).astype(int)

    # --- Assemble the DataFrame ---
    data = {
        # Population
        "S0101_C01_001E": total_pop,

        # Housing (Mobile Homes, Owner Occupied)
        "DP04_0001E": housing_units,
        "DP04_0014E": mobile_homes,
        "DP04_0046E": owner_occupied,

        # Education
        "S1501_C01_006E": pop_25_plus,
        "S1501_C01_007E": no_hs_9th,
        "S1501_C01_008E": no_hs_12th,

        # No Vehicle
        "B08201_001E": total_hh,
        "B08201_002E": no_vehicle_hh,

        # Age
        "S0101_C01_030E": pop_65_plus,

        # Disability
        "S1810_C01_001E": civilian_pop,
        "S1810_C02_001E": disabled_pop,

        # Limited English
        "S1602_C01_001E": hh_total_lang,
        "S1602_C03_001E": hh_limited_eng,

        # Single Parent
        "B09005_001E": children_total,
        "B09005_004E": single_father,
        "B09005_005E": single_mother,

        # Communications
        "S2801_C01_001E": total_hh,
        "S2801_C01_005E": hh_with_computer,

        # Inactive Voter (EAVS)
        "A1a": reg_voters,
        "A1c": inactive_voters,

        # Civil Org (CBP NAICS 813410)
        "813410": civil_orgs,

        # Population Change (POP net migration)
        "NETMIG2020": netmig_2020,
        "NETMIG2019": netmig_2019,
        "NETMIG2018": netmig_2018,
        "NETMIG2017": netmig_2017,
        "NETMIG2016": netmig_2016,

        # Religion (ARDA)
        "TOTADH": religious_adherents,
        "POP": arda_pop,

        # Unemployment
        "DP03_0003E": civilian_lf,
        "DP03_0005E": unemployed,

        # Unemployed Women
        "DP03_0012E": women_16_plus,
        "DP03_0013E": women_employed,

        # Median Income
        "S1903_C03_001E": median_income,

        # GINI
        "B19083_001E": gini,

        # Lack of Economic Diversity (13 industry sectors + total)
        "DP03_0032E": total_employed,
        **industry_cols,

        # Poverty
        "S1701_C01_001E": poverty_pop_det,
        "S1701_C02_001E": poverty_count,

        # Hospitals (CBP NAICS 622110)
        "622110": hospitals,

        # Medical
        "S2401_C01_016E": medical_workers,

        # Uninsured
        "S2701_C01_001E": civ_noninst,
        "S2701_C04_001E": uninsured,
    }

    df = pd.DataFrame(data, index=geo_ids)
    df.index.name = "GEO_ID"

    # Ensure all numeric
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def get_calibration_reference() -> pd.DataFrame:
    """
    Return reference DataFrame matching all 22 indicators from
    config/indicators.yaml.

    Columns: Indicator, Source, Function, numerator, denominator, rate,
             Units, Augment, Order_2023

    The Units and Augment columns control rescaling (fraction/index -> *100)
    and reorientation (reverse -> higher = more resilient) in the aggregator.
    """
    indicators = [
        # order, name, source, function, numerator, denominator, rate, units, augment
        (1, "Mobile Homes", "ACS", "divide", "DP04_0014E", "DP04_0001E", None, "fraction", "reverse"),
        (2, "Owner Occupied", "ACS", "divide", "DP04_0046E", "DP04_0001E", None, "fraction", None),
        (3, "Education", "ACS", "divide", "S1501_C01_007E, S1501_C01_008E", "S1501_C01_006E", None, "fraction", "reverse"),
        (4, "No Vehicle", "ACS", "divide", "B08201_002E", "B08201_001E", None, "fraction", "reverse"),
        (5, "Age", "ACS", "divide", "S0101_C01_030E", "S0101_C01_001E", None, "fraction", "reverse"),
        (6, "Disability", "ACS", "divide", "S1810_C02_001E", "S1810_C01_001E", None, "fraction", "reverse"),
        (7, "Limited English", "ACS", "divide", "S1602_C03_001E", "S1602_C01_001E", None, "fraction", "reverse"),
        (8, "Single Parent", "ACS", "divide", "B09005_004E, B09005_005E", "B09005_001E", None, "fraction", "reverse"),
        (9, "Low Access to Communications", "ACS", "reverse_divide", "S2801_C01_005E", "S2801_C01_001E", None, "fraction", "reverse"),
        (10, "Inactive Voter", "EAVS", "divide", "A1c", "A1a", None, "fraction", "reverse"),
        (11, "Civil Org", "CBP", "divide_scalar", "813410", "S0101_C01_001E", 10.0, "rate", None),
        (12, "Population Change", "POP", "mean", "NETMIG", "S0101_C01_001E", None, "fraction", None),
        (13, "Religion", "ARDA", "reverse_divide", "TOTADH", "POP", None, "fraction", "reverse"),
        (14, "Unemployment", "ACS", "divide", "DP03_0005E", "DP03_0003E", None, "fraction", "reverse"),
        (15, "Unemployed Women", "ACS", "reverse_divide", "DP03_0013E", "DP03_0012E", None, "fraction", "reverse"),
        (16, "Median Income", "ACS", "divide", "S1903_C03_001E", 1, None, "index", None),
        (17, "GINI", "ACS", "divide", "B19083_001E", 1, None, "index", "reverse"),
        (18, "Lack of Economic Diversity", "ACS", "max",
         "DP03_0033E, DP03_0034E, DP03_0035E, DP03_0036E, DP03_0037E, DP03_0038E, DP03_0039E, DP03_0040E, DP03_0041E, DP03_0042E, DP03_0043E, DP03_0044E, DP03_0045E",
         "DP03_0032E", None, "fraction", "reverse"),
        (19, "Poverty", "ACS", "divide", "S1701_C02_001E", "S1701_C01_001E", None, "fraction", "reverse"),
        (20, "Hospitals", "CBP", "divide_scalar", "622110", "S0101_C01_001E", 10.0, "rate", None),
        (21, "Medical", "ACS", "divide_scalar", "S2401_C01_016E", "S0101_C01_001E", 1.0, "rate", None),
        (22, "Uninsured Population", "ACS", "divide", "S2701_C04_001E", "S2701_C01_001E", None, "fraction", "reverse"),
    ]

    df = pd.DataFrame(indicators, columns=[
        "Order_2023", "Indicator", "Source", "Function",
        "numerator", "denominator", "rate", "Units", "Augment",
    ])

    return df


def get_calibration_years() -> dict:
    """Return standard years dict for calibration tests."""
    return {
        "acs": 2021,
        "cbp": 2020,
        "naics": 2017,
        "pop": 2020,
        "asarb": 2020,
        "acs_labels": 2020,
    }


def get_calibration_geo_reference(source_data: pd.DataFrame) -> pd.DataFrame:
    """
    Build a minimal geography reference DataFrame from source_data index.

    Extracts state FIPS from GEO_ID strings and creates the columns
    needed by the aggregator for CT CBP and PR Limited English handling.

    Args:
        source_data: DataFrame with GEO_ID index.

    Returns:
        DataFrame indexed by GEO_ID with state, state_name columns.
    """
    geo_ids = source_data.index.tolist()
    states = []
    for gid in geo_ids:
        # GEO_ID format: 0500000US{SS}{CCC}
        try:
            fips_part = gid.split("US")[1]
            state_fips = int(fips_part[:2])
        except (IndexError, ValueError):
            state_fips = 0
        states.append(state_fips)

    state_name_map = {
        9: "Connecticut",
        72: "Puerto Rico",
    }

    geo_ref = pd.DataFrame({
        "state": states,
        "state_name": [state_name_map.get(s, f"State_{s}") for s in states],
    }, index=geo_ids)
    geo_ref.index.name = "GEO_ID"

    return geo_ref


def get_ct_cbp_data(n_rows: int = 10) -> pd.DataFrame:
    """
    Generate data with Connecticut counties that have zero CBP values.

    Used to test the CT CBP special case: zero CBP values should propagate
    as NaN through the pipeline.

    Args:
        n_rows: Number of CT counties.

    Returns:
        DataFrame with CT county GEO_IDs and zero-valued CBP columns.
    """
    rng = np.random.default_rng(42)
    base = get_calibration_county_data(n_rows + 50)

    # Overwrite first n_rows GEO_IDs to be Connecticut (FIPS 09)
    # Use county codes 901+ to avoid collisions with deterministic base IDs
    new_index = list(base.index)
    for i in range(n_rows):
        new_index[i] = f"0500000US09{i+901:03d}"
    base.index = new_index
    base.index.name = "GEO_ID"

    # Set CBP values to 0 for CT counties (Civil Org and Hospitals)
    ct_mask = [idx.startswith("0500000US09") for idx in base.index]
    base.loc[ct_mask, "813410"] = 0
    base.loc[ct_mask, "622110"] = 0

    return base


def get_pr_limited_english_data(n_rows: int = 10) -> pd.DataFrame:
    """
    Generate data with Puerto Rico counties (state FIPS 72).

    Used to test the PR Limited English special case: Spanish speakers
    are not "limited English" in PR, so those values should be NaN.

    Args:
        n_rows: Number of PR counties.

    Returns:
        DataFrame with PR county GEO_IDs.
    """
    rng = np.random.default_rng(42)
    base = get_calibration_county_data(n_rows + 50)

    # Overwrite first n_rows GEO_IDs to be Puerto Rico (FIPS 72)
    # Use county codes 901+ to avoid collisions with deterministic base IDs
    new_index = list(base.index)
    for i in range(n_rows):
        new_index[i] = f"0500000US72{i+901:03d}"
    base.index = new_index
    base.index.name = "GEO_ID"

    return base
