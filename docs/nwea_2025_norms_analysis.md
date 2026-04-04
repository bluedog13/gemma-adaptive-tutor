# NWEA 2025 MAP Growth Norms — Data Analysis & Integration

**Date:** April 3, 2026
**Purpose:** Document how the NWEA 2025 norms data was sourced, validated, and integrated into MAP Accelerator.

---

## 1. Problem Statement

MAP Accelerator's growth trajectory chart was showing incorrect percentile positions for students. A student with RIT 196 at Spring Grade 1 was displayed below the 90th percentile line, but the actual NWEA student report showed the 93rd percentile. The root cause was that the percentile data in `src/constants.py` was approximated from AI training data, not sourced from official NWEA publications.

---

## 2. Data Source

### Official Document

- **Title:** 2025 MAP Growth Norms Technical Manual
- **Version:** 2025.1.0
- **Publisher:** HMH Education Company (NWEA)
- **URL:** https://www.nwea.org/resource-center/white-paper/88182/MAP-Growth-Norms_NWEA_Technical-Manual.pdf/

### Tables Used

| Table | Page | Description |
|-------|------|-------------|
| A.1   | 36   | Achievement Norms — Mathematics, Student (Mean & SD) |
| B.1   | 41   | Achievement Percentiles — Mathematics, Fall, Student |
| B.3   | 43   | Achievement Percentiles — Mathematics, Winter, Student |
| B.5   | 45   | Achievement Percentiles — Mathematics, Spring, Student |

### Key Methodology Notes (from the manual)

- **Fall norms:** Based on assessments administered during the **4th week** of instruction
- **Winter norms:** Based on assessments administered during the **20th week** of instruction
- **Spring norms:** Based on assessments administered during the **32nd week** of instruction
- The manual provides **student-level** and **school-level** tables — we use **student-level**
- Growth models use a **3-piece piecewise linear** model (chosen over compound polynomial for better fit)

---

## 3. Previous Data (Incorrect)

The original `constants.py` contained approximated data labeled as "NWEA 2020 norms":

```python
# OLD — approximated from AI training data
NWEA_MEAN_RIT = {
    1: {"fall": 162, "winter": 171, "spring": 180},
    2: {"fall": 177, "winter": 183, "spring": 190},
    3: {"fall": 188, "winter": 194, "spring": 201},
    4: {"fall": 200, "winter": 205, "spring": 210},
    5: {"fall": 211, "winter": 216, "spring": 220},
}
```

### Comparison: Old vs Official 2025 Data (Fall Means)

| Grade | Old (approx) | Official 2025 | Difference |
|-------|-------------|---------------|------------|
| 1     | 162         | **159.29**    | +2.71      |
| 2     | 177         | **172.87**    | +4.13      |
| 3     | 188         | **184.05**    | +3.95      |
| 4     | 200         | **197.03**    | +2.97      |
| 5     | 211         | **206.23**    | +4.77      |

The old data was consistently **inflated by 3-5 RIT points**, causing percentile lines on the chart to be too high. This made advanced students appear lower in percentile ranking than they actually were.

---

## 4. Official 2025 Data — Achievement Norms (Table A.1)

### Mathematics, Student-Level

| Grade | Fall Mean | Fall SD | Winter Mean | Winter SD | Spring Mean | Spring SD |
|-------|----------|---------|-------------|-----------|-------------|-----------|
| 1     | 159.29   | 13.40   | 168.26      | 13.83     | 174.99      | 14.32     |
| 2     | 172.87   | 15.44   | 181.20      | 15.70     | 187.46      | 16.07     |
| 3     | 184.05   | 15.54   | 192.65      | 16.34     | 199.10      | 17.03     |
| 4     | 197.03   | 15.91   | 204.48      | 17.02     | 210.07      | 18.04     |
| 5     | 206.23   | 16.23   | 211.82      | 17.42     | 216.01      | 18.44     |

---

## 5. Official 2025 Data — Achievement Percentiles

### Mathematics, Fall, Student (Table B.1, Grades 1-5)

| Pct | G1  | G2  | G3  | G4  | G5  |
|-----|-----|-----|-----|-----|-----|
| 5   | 137 | 147 | 158 | 171 | 180 |
| 10  | 142 | 153 | 164 | 177 | 185 |
| 25  | 150 | 162 | 174 | 186 | 195 |
| 50  | 159 | 173 | 184 | 197 | 206 |
| 75  | 168 | 183 | 195 | 208 | 217 |
| 90  | 176 | 193 | 204 | 217 | 227 |
| 95  | 181 | 198 | 210 | 223 | 233 |

### Mathematics, Winter, Student (Table B.3, Grades 1-5)

| Pct | G1  | G2  | G3  | G4  | G5  |
|-----|-----|-----|-----|-----|-----|
| 5   | 146 | 155 | 166 | 176 | 183 |
| 10  | 151 | 161 | 172 | 183 | 189 |
| 25  | 159 | 171 | 182 | 193 | 200 |
| 50  | 168 | 181 | 193 | 204 | 212 |
| 75  | 178 | 192 | 204 | 216 | 224 |
| 90  | 186 | 201 | 214 | 226 | 234 |
| 95  | 191 | 207 | 220 | 232 | 240 |

### Mathematics, Spring, Student (Table B.5, Grades 1-5)

| Pct | G1  | G2  | G3  | G4  | G5  |
|-----|-----|-----|-----|-----|-----|
| 5   | 151 | 161 | 171 | 180 | 186 |
| 10  | 157 | 167 | 177 | 187 | 192 |
| 25  | 165 | 177 | 188 | 198 | 204 |
| 50  | 175 | 187 | 199 | 210 | 216 |
| 75  | 185 | 198 | 211 | 222 | 228 |
| 90  | 193 | 208 | 221 | 233 | 240 |
| 95  | 199 | 214 | 227 | 240 | 246 |

---

## 6. Validation Against Real Student Report

A real NWEA student report was used to validate the integrated data:

### Student Test Data (from NWEA report)

| Term  | Grade | RIT Score | Percentile (Report) |
|-------|-------|-----------|---------------------|
| SP25  | 01    | 193-196-199 (±Std Err) | 89-93-95   |
| FA25  | 02    | 190-193-196 | 86-90-93           |
| WI26  | 02    | 193-196-199 | 77-83-88           |

### Validation Results (using middle RIT value)

| Score Point    | RIT | Our Estimate | Real Report | Delta |
|---------------|-----|-------------|-------------|-------|
| SP25 G1       | 196 | **92nd**    | 93rd        | -1    |
| FA25 G2       | 193 | **90th**    | 90th        | 0     |
| WI26 G2       | 196 | **83rd**    | 83rd        | 0     |

The 1-percentile difference for SP25 is due to interpolation between the 5-point table entries (90th=193, 95th=199). The actual NWEA system uses continuous distributions for exact percentile calculation.

---

## 7. Percentile Estimation Method

### Approach: Table Interpolation

Since the official tables provide percentile cutoffs at 5-point intervals (5th, 10th, 15th, ..., 95th), we interpolate between entries:

```python
def estimate_percentile(rit_score, grade, season):
    # Find the two adjacent percentile entries that bracket the RIT score
    # Linear interpolation between them
    # Example: RIT 196 at Spring G1
    #   90th = 193, 95th = 199
    #   frac = (196 - 193) / (199 - 193) = 3/6 = 0.50
    #   percentile = 90 + 0.50 * (95 - 90) = 92.5 → 92
```

### Why Not Z-Score Method?

An earlier iteration used `Mean + (z × SD)` to compute percentiles. While NWEA's documentation mentions this as valid, the official percentile tables don't follow a perfect normal distribution (they use a piecewise linear growth model). Direct table lookup with interpolation is more accurate — our validation shows 0-1 percentile point accuracy vs 1-3 points with z-score approximation.

---

## 8. Chart Integration

### Percentile Band Lines

The growth trajectory chart shows 4 percentile reference lines (50th, 75th, 90th, 95th) using the official tables. Each score point uses the correct grade's percentile data:

```
Spring 2025 (G1) → uses Grade 1 Spring percentiles
Fall 2025 (G2)   → uses Grade 2 Fall percentiles
Winter 2026 (G2) → uses Grade 2 Winter percentiles
```

### Expected Growth Line

A green dotted line shows where the student would be if maintaining their initial percentile rank. This is computed by:
1. Finding the student's percentile at their first measurement (interpolating from the official table)
2. At each subsequent point, looking up what RIT that same percentile maps to for the new grade/season

### Trend Analysis

Gemma 4 receives the NWEA norms data in its prompt and provides qualitative analysis (trend classification, pattern identification, recommendations). The chart's quantitative elements (percentile lines, expected growth) are computed deterministically from the official tables.

---

## 9. Conditional Growth Norms

Derived from the percentile tables by computing `Spring RIT - Fall RIT` at each percentile level:

| Grade | 10th pct | 25th pct | 50th pct | 75th pct | 90th pct | 95th pct |
|-------|---------|---------|---------|---------|---------|---------|
| 1     | +15     | +15     | +16     | +17     | +17     | +18     |
| 2     | +14     | +15     | +14     | +15     | +15     | +16     |
| 3     | +13     | +14     | +15     | +16     | +17     | +17     |
| 4     | +10     | +12     | +13     | +14     | +16     | +17     |
| 5     | +7      | +9      | +10     | +11     | +13     | +13     |

**Key insight:** Unlike what many assume, higher-percentile students show **similar or slightly higher** growth than lower-percentile students in the 2025 norms. This differs from the 2020 norms where higher-percentile students showed lower growth (the "excellence gap"). The 2025 data reflects post-pandemic recovery patterns.

---

## 10. Files Modified

| File | Changes |
|------|---------|
| `src/constants.py` | Replaced all norms data with official 2025 tables. Added `estimate_percentile()`, `get_percentile_cutoffs()`. Full percentile tables at 5-point intervals (5th-95th). |
| `src/prompts.py` | Updated to use `estimate_percentile()` from constants. Changed "NWEA 2020" references to "NWEA 2025". |
| `frontend/app.py` | Chart title updated to "NWEA 2025". Added 90th-95th percentile band. Expected growth line uses percentile-based projection. |

---

## 11. Future Considerations

1. **Reading norms:** The manual also contains Reading percentile tables (Tables B.7-B.11). These can be added if MAP Accelerator expands beyond Math.
2. **Norms updates:** NWEA updates norms periodically. The next update should follow the same process: download the Technical Manual PDF, extract Tables A.x and B.x, update `constants.py`.
3. **Granularity:** The official tables provide percentiles at 5-point intervals. For exact percentile matching, NWEA uses continuous distributions internally — our interpolation introduces up to 1-2 percentile points of rounding.
4. **School vs Student norms:** We use student-level norms (Table B.1/B.3/B.5). School-level norms (B.2/B.4/B.6) have tighter distributions (smaller SD) and are used for school-level comparisons.
