"""Constants and configuration for MAP Accelerator."""

from pathlib import Path

# Gemma model
MODEL = "gemma4:e4b"

# Data directory
DATA_DIR = Path(__file__).parent / "data"

# Season ordering for chronological sorting (calendar order, NOT school year)
SEASON_ORDER: dict[str, int] = {"spring": 0, "fall": 1, "winter": 2}

# ---------------------------------------------------------------------------
# NWEA 2025 MAP Growth Norms — Mathematics (Student-level)
# Source: 2025 MAP Growth Norms Technical Manual, Version 2025.1.0
#   Table A.1  — Achievement Norms (Mean & SD)
#   Table B.1  — Achievement Percentiles, Fall
#   Table B.3  — Achievement Percentiles, Winter
#   Table B.5  — Achievement Percentiles, Spring
# ---------------------------------------------------------------------------

# Mean and SD by grade and season (Table A.1)
NWEA_NORMS: dict[int, dict[str, dict[str, float]]] = {
    0: {
        "fall":   {"mean": 141.17, "sd": 12.29},
        "winter": {"mean": 150.65, "sd": 12.57},
        "spring": {"mean": 157.77, "sd": 13.04},
    },
    1: {
        "fall":   {"mean": 159.29, "sd": 13.40},
        "winter": {"mean": 168.26, "sd": 13.83},
        "spring": {"mean": 174.99, "sd": 14.32},
    },
    2: {
        "fall":   {"mean": 172.87, "sd": 15.44},
        "winter": {"mean": 181.20, "sd": 15.70},
        "spring": {"mean": 187.46, "sd": 16.07},
    },
    3: {
        "fall":   {"mean": 184.05, "sd": 15.54},
        "winter": {"mean": 192.65, "sd": 16.34},
        "spring": {"mean": 199.10, "sd": 17.03},
    },
    4: {
        "fall":   {"mean": 197.03, "sd": 15.91},
        "winter": {"mean": 204.48, "sd": 17.02},
        "spring": {"mean": 210.07, "sd": 18.04},
    },
    5: {
        "fall":   {"mean": 206.23, "sd": 16.23},
        "winter": {"mean": 211.82, "sd": 17.42},
        "spring": {"mean": 216.01, "sd": 18.44},
    },
}

# Mean RIT shortcut (used by prompts)
NWEA_MEAN_RIT: dict[int, dict[str, int]] = {
    grade: {season: round(data["mean"]) for season, data in seasons.items()}
    for grade, seasons in NWEA_NORMS.items()
}

# Expected annual RIT growth by grade (fall-to-spring mean difference)
EXPECTED_GROWTH: dict[int, int] = {
    grade: round(NWEA_NORMS[grade]["spring"]["mean"] - NWEA_NORMS[grade]["fall"]["mean"])
    for grade in NWEA_NORMS
}

# ---------------------------------------------------------------------------
# Official Achievement Percentiles (Tables B.1, B.3, B.5)
# Structure: grade -> season -> {percentile: RIT}
# ---------------------------------------------------------------------------
NWEA_PERCENTILES: dict[int, dict[str, dict[int, int]]] = {
    0: {
        "fall":   {5: 121, 10: 125, 15: 128, 20: 131, 25: 133, 30: 135, 35: 136, 40: 138, 45: 140, 50: 141, 55: 143, 60: 144, 65: 146, 70: 148, 75: 149, 80: 152, 85: 154, 90: 157, 95: 161},
        "winter": {5: 130, 10: 135, 15: 138, 20: 140, 25: 142, 30: 144, 35: 146, 40: 147, 45: 149, 50: 151, 55: 152, 60: 154, 65: 155, 70: 157, 75: 159, 80: 161, 85: 164, 90: 167, 95: 171},
        "spring": {5: 136, 10: 141, 15: 144, 20: 147, 25: 149, 30: 151, 35: 153, 40: 154, 45: 156, 50: 158, 55: 159, 60: 161, 65: 163, 70: 165, 75: 167, 80: 169, 85: 171, 90: 174, 95: 179},
    },
    1: {
        "fall":   {5: 137, 10: 142, 15: 145, 20: 148, 25: 150, 30: 152, 35: 154, 40: 156, 45: 158, 50: 159, 55: 161, 60: 163, 65: 164, 70: 166, 75: 168, 80: 171, 85: 173, 90: 176, 95: 181},
        "winter": {5: 146, 10: 151, 15: 154, 20: 157, 25: 159, 30: 161, 35: 163, 40: 165, 45: 167, 50: 168, 55: 170, 60: 172, 65: 174, 70: 176, 75: 178, 80: 180, 85: 183, 90: 186, 95: 191},
        "spring": {5: 151, 10: 157, 15: 160, 20: 163, 25: 165, 30: 167, 35: 169, 40: 171, 45: 173, 50: 175, 55: 177, 60: 179, 65: 181, 70: 183, 75: 185, 80: 187, 85: 190, 90: 193, 95: 199},
    },
    2: {
        "fall":   {5: 147, 10: 153, 15: 157, 20: 160, 25: 162, 30: 165, 35: 167, 40: 169, 45: 171, 50: 173, 55: 175, 60: 177, 65: 179, 70: 181, 75: 183, 80: 186, 85: 189, 90: 193, 95: 198},
        "winter": {5: 155, 10: 161, 15: 165, 20: 168, 25: 171, 30: 173, 35: 175, 40: 177, 45: 179, 50: 181, 55: 183, 60: 185, 65: 187, 70: 189, 75: 192, 80: 194, 85: 197, 90: 201, 95: 207},
        "spring": {5: 161, 10: 167, 15: 171, 20: 174, 25: 177, 30: 179, 35: 181, 40: 183, 45: 185, 50: 187, 55: 189, 60: 192, 65: 194, 70: 196, 75: 198, 80: 201, 85: 204, 90: 208, 95: 214},
    },
    3: {
        "fall":   {5: 158, 10: 164, 15: 168, 20: 171, 25: 174, 30: 176, 35: 178, 40: 180, 45: 182, 50: 184, 55: 186, 60: 188, 65: 190, 70: 192, 75: 195, 80: 197, 85: 200, 90: 204, 95: 210},
        "winter": {5: 166, 10: 172, 15: 176, 20: 179, 25: 182, 30: 184, 35: 186, 40: 189, 45: 191, 50: 193, 55: 195, 60: 197, 65: 199, 70: 201, 75: 204, 80: 206, 85: 210, 90: 214, 95: 220},
        "spring": {5: 171, 10: 177, 15: 181, 20: 185, 25: 188, 30: 190, 35: 193, 40: 195, 45: 197, 50: 199, 55: 201, 60: 203, 65: 206, 70: 208, 75: 211, 80: 213, 85: 217, 90: 221, 95: 227},
    },
    4: {
        "fall":   {5: 171, 10: 177, 15: 181, 20: 184, 25: 186, 30: 189, 35: 191, 40: 193, 45: 195, 50: 197, 55: 199, 60: 201, 65: 203, 70: 205, 75: 208, 80: 210, 85: 214, 90: 217, 95: 223},
        "winter": {5: 176, 10: 183, 15: 187, 20: 190, 25: 193, 30: 196, 35: 198, 40: 200, 45: 202, 50: 204, 55: 207, 60: 209, 65: 211, 70: 213, 75: 216, 80: 219, 85: 222, 90: 226, 95: 232},
        "spring": {5: 180, 10: 187, 15: 191, 20: 195, 25: 198, 30: 201, 35: 203, 40: 206, 45: 208, 50: 210, 55: 212, 60: 215, 65: 217, 70: 220, 75: 222, 80: 225, 85: 229, 90: 233, 95: 240},
    },
    5: {
        "fall":   {5: 180, 10: 185, 15: 189, 20: 193, 25: 195, 30: 198, 35: 200, 40: 202, 45: 204, 50: 206, 55: 208, 60: 210, 65: 212, 70: 215, 75: 217, 80: 220, 85: 223, 90: 227, 95: 233},
        "winter": {5: 183, 10: 189, 15: 194, 20: 197, 25: 200, 30: 203, 35: 205, 40: 207, 45: 210, 50: 212, 55: 214, 60: 216, 65: 219, 70: 221, 75: 224, 80: 226, 85: 230, 90: 234, 95: 240},
        "spring": {5: 186, 10: 192, 15: 197, 20: 200, 25: 204, 30: 206, 35: 209, 40: 211, 45: 214, 50: 216, 55: 218, 60: 221, 65: 223, 70: 226, 75: 228, 80: 232, 85: 235, 90: 240, 95: 246},
    },
}


def estimate_percentile(rit_score: int, grade: int, season: str = "fall") -> int:
    """Estimate the percentile for a given RIT score using the official tables.

    Interpolates between the 5-point percentile entries in NWEA_PERCENTILES.
    """
    grade = max(0, min(grade, 5))
    pcts = NWEA_PERCENTILES.get(grade, NWEA_PERCENTILES[3])
    season_pcts = pcts.get(season, pcts["fall"])

    # Walk through the percentile table to find where this score falls
    pct_keys = sorted(season_pcts.keys())
    if rit_score <= season_pcts[pct_keys[0]]:
        return pct_keys[0]
    if rit_score >= season_pcts[pct_keys[-1]]:
        return 99

    for i in range(len(pct_keys) - 1):
        low_pct = pct_keys[i]
        high_pct = pct_keys[i + 1]
        low_rit = season_pcts[low_pct]
        high_rit = season_pcts[high_pct]
        if low_rit <= rit_score <= high_rit:
            if high_rit == low_rit:
                return low_pct
            frac = (rit_score - low_rit) / (high_rit - low_rit)
            return round(low_pct + frac * (high_pct - low_pct))

    return 50


def get_percentile_cutoffs(grade: int, season: str) -> dict[int, int]:
    """Get standard percentile cutoffs (25, 50, 75, 90, 95) for a grade/season."""
    grade = max(0, min(grade, 5))
    pcts = NWEA_PERCENTILES.get(grade, NWEA_PERCENTILES[3])
    season_pcts = pcts.get(season, pcts["fall"])
    return {p: season_pcts[p] for p in (25, 50, 75, 90, 95)}


# Conditional growth norms: expected fall-to-spring growth by starting percentile
# Derived from NWEA 2025 percentile tables (spring - fall at same percentile)
NWEA_CONDITIONAL_GROWTH: dict[int, dict[int, int]] = {
    0: {10: 16, 25: 16, 50: 17, 75: 18, 90: 17, 95: 18},
    1: {10: 15, 25: 15, 50: 16, 75: 17, 90: 17, 95: 18},
    2: {10: 14, 25: 15, 50: 14, 75: 15, 90: 15, 95: 16},
    3: {10: 13, 25: 14, 50: 15, 75: 16, 90: 17, 95: 17},
    4: {10: 10, 25: 12, 50: 13, 75: 14, 90: 16, 95: 17},
    5: {10: 7, 25: 9, 50: 10, 75: 11, 90: 13, 95: 13},
}
