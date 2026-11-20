# Queensland emergency department performance

[![CI](https://github.com/nisha1324/qld-emergency-department-performance/actions/workflows/ci.yml/badge.svg)](https://github.com/nisha1324/qld-emergency-department-performance/actions/workflows/ci.yml)

**Status: work in progress.** Parts 1 and 2 of 5 are done: the source profile, and the split between patient mix and performance.

Where do patients wait in Queensland's public hospital emergency departments (EDs), and which hospitals miss the 4-hour mark? This project treats the state's published ED figures the way an operations analyst would treat a service-level report: check the data first, then find where the delays are, how much is down to the mix of patients, and which hospitals to look at.

## Why it matters

An ED is a queue with a service level attached. Two numbers are watched everywhere: the share of patients **seen within the clinically recommended time** for their triage category, and the share whose **whole ED stay is within 4 hours**. A hospital executive, a health-service planner or a consultant needs to know which of the two is slipping, where, and whether the cause is at the front door (waiting to be seen) or the back door (waiting to leave, usually for a bed).

## Data

| | |
| --- | --- |
| Source | Queensland Health, [Emergency departments - quarterly data](https://www.data.qld.gov.au/dataset/emergency-departments-quarterly-data) |
| Licence | Creative Commons Attribution 4.0 (© State of Queensland, Queensland Health) |
| Coverage | 14 quarters, Jan-Mar 2023 to Apr-Jun 2026; 104 reporting hospitals (105 from Apr-Jun 2026) and a Queensland total |
| Grain | One row per hospital, quarter and triage category (1 to 5, and all categories): 8,826 rows |
| Measures | Attendances, patients seen within the recommended time, median wait, did not wait, left after treatment started, admitted, admissions within 4 hours, ED stays within 4 hours |
| Access | The open data portal's public datastore API. No key or sign-up. |

Triage categories follow the Australasian Triage Scale: 1 is resuscitation (seen immediately) and 5 is non-urgent.

The raw files (1.0 MB) and the tidy snapshot (0.6 MB) are committed, so everything runs offline. `scripts/download_data.py` fetches the same files again and checks each against a pinned SHA-256, so a revision by Queensland Health stops the run instead of silently changing the results.

Not included: the nine earlier quarters (Oct-Dec 2020 to Oct-Dec 2022). The portal holds them only as XLS, XLSX and CSV files in older layouts, not in its datastore.

## Part 1: source, snapshot and profile

Full report: [`results/SOURCE_PROFILE.md`](results/SOURCE_PROFILE.md).

### What the data says so far

Same quarter, three years apart, all triage categories:

| | Apr-Jun 2023 | Apr-Jun 2026 |
| --- | ---: | ---: |
| Attendances | 584,431 | 593,177 |
| Seen within the recommended time | 71% | 74.6% |
| Median wait to treatment | 17 min | 14 min |
| ED stay within 4 hours | 61% | 56.1% |
| Admissions to hospital within 4 hours | 37% | 31.3% |

**1. The delay is at the back door, not the front door.** Patients are being seen a little sooner, yet fewer leave within 4 hours, and the same is true of patients who are admitted. Attendances are up only 1.5% on the same quarter three years earlier, so volume alone does not explain it.

![State trend](results/charts/01_state_trend.png)

**2. The mix is getting more urgent.** Triage category 2 rose from 16.8% to 20.0% of attendances, while categories 4 and 5 together fell from 40.4% to 36.2%. More urgent patients are admitted more often and stay longer, so part of the fall in the 4-hour figure is mix, not performance. Part 2 separates the two.

![Triage mix](results/charts/02_triage_mix.png)

**3. The state figure describes 22 hospitals.** In Apr-Jun 2026, 22 of 105 hospitals had 10,000 or more attendances and handled 70.2% of the total. At those hospitals 45.7% of stays were within 4 hours; at the other 83 it was 80.6%. The median hospital is at 86.9%, nowhere near the state's 56.1%.

![Size and 4-hour stays](results/charts/03_size_vs_4h.png)

**So what?** A statewide target tells most hospitals nothing about themselves. The 4-hour problem is concentrated in the large EDs, and across the state what has worsened is getting patients out of the ED, not getting them seen. That points towards beds and discharge flow in the rest of the hospital more than the ED's own front end. It is a hypothesis at this stage: Parts 2 to 4 test it hospital by hospital.

### Is the data trustworthy?

Mostly yes, with quirks the loader handles and the later parts must respect.

- Triage categories 1 to 5 add up to the all-categories row in 1,471 of 1,471 hospital-quarters, and hospitals add up to the Queensland row in 14 of 14 quarters.
- The published "did not wait" and "left after treatment" percentages equal their counts ÷ attendances, to rounding, in every row that has both.
- The published change in attendances matches a recomputed year-on-year change in 6,115 of 6,157 rows. The 42 that do not are in two quarters. The largest gaps are at Nambour in Oct-Dec 2025: for all categories the published change is +5.0%, but the two quarters' own attendance figures give +22.0%.
- Hospital names change between files for 105 of 106 facility codes, column names drift, and missing values are written four ways.
- Percentages are whole numbers in the first 5 quarters and have one decimal place after that.
- In 4 quarters a zero is published as `-`, the same symbol used for "no data".

The profile ends with eight rules for the rest of the project, for example: use facility codes, compare the same quarter a year apart, and never average hospitals to describe the state (the plain average of hospital 4-hour figures is 79.2%, against 56.1% for the state).

## Part 2: mix versus performance

Full report: [`results/MIX_VS_PERFORMANCE.md`](results/MIX_VS_PERFORMANCE.md).

An all-categories rate can fall for two reasons: more patients arrive in the triage categories where stays are longer (**mix**), or patients in the same category get a worse result (**within category**). The change between two quarters splits exactly into the two, with nothing left over. The main comparison is Apr-Jun 2024 to Apr-Jun 2026, the longest same-quarter span published to one decimal place.

| Queensland, Apr-Jun 2024 to Apr-Jun 2026 | Change (points) | Mix | Within category |
| --- | ---: | ---: | ---: |
| ED stay within 4 hours | −3.05 | −1.14 | −1.91 |
| Admitted patients: ED stay within 4 hours | −3.10 | −0.06 | −3.04 |
| Seen within the recommended time | +1.30 | −0.48 | +1.78 |

**1. A more urgent mix is 37% of the fall in 4-hour stays. The other 63% is within category.** The 4-hour rate fell in all five triage categories. Mix lowered the rate in 10 of 10 year-on-year comparisons, and its pull is growing. With the triage mix held at its Jan-Mar 2023 level, the Apr-Jun 2026 figure would be 57.8% instead of 56.1%.

![Actual against fixed mix](results/charts/04_fixed_mix.png)

**2. The front door improved by more than the headline shows.** Patients seen on time rose 1.30 points, but the mix pulled that down by 0.48: within categories the gain was 1.78 points. It is not a steady gain; the within-category effect was negative in 3 of 10 year-on-year comparisons.

![Mix and within-category effects](results/charts/05_mix_vs_within.png)

**3. Patients who are not admitted are leaving later too.** A second split, into admitted and not admitted, does not rely on triage. Admitted patients' 4-hour rate fell from 34.5% to 31.3%. The rate for everyone else is not published, but the published figures imply 68.7% falling to 66.2%, and because those patients are 71% of attendances they account for 1.78 of the 3.0 points, against 0.91 for admitted patients. That corrects Part 1's "back door" reading: the delay is not only among admitted patients.

**4. At the large hospitals the fall is mostly within category; at the other hospitals it is mostly mix.** At the 22 large hospitals the 4-hour rate fell 3.47 points and 83% of that is within category. At the other 82 it fell 1.43 points and 80% of that is mix. Among the 22, 18 fell (9 of them by 5 points or more, led by Sunshine Coast University, 49.8% to 41.4%) and 4 rose (Queensland Children's most, 63.2% to 70.8%).

![Large hospitals](results/charts/06_large_hospitals.png)

**A caution on the mix.** Category 2 grew from 17.9% to 20.0% of attendances while a smaller share of its patients were admitted (50.6% to 47.6%). That fits a change in how patients are triaged as well as it fits sicker patients, and quarterly totals cannot tell the two apart. The triage split puts mix at 37% of the fall and the admitted split puts it at 10%.

**So what?** "Patients are sicker" does not explain most of the fall in 4-hour stays, on either split. A health service should report within-category rates next to the headline, because the headline understates the gain in patients seen on time and overstates the loss in 4-hour stays. And it should look at its large hospitals one at a time: over the same two years two lost about 8 points and one gained more than 7, which a state average hides.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/profile_source.py     # Part 1 report, CSVs and charts from the committed snapshot
python scripts/mix_report.py         # Part 2 report, CSVs and charts
pytest                               # tests

# optional: rebuild from the source
python scripts/download_data.py      # verifies data/raw/ against pinned hashes; --force fetches again
python scripts/build_snapshot.py     # data/raw/*.json -> data/ed_quarterly.csv
```

## Repository layout

```
edperf/source.py          where the data comes from; pinned hashes; API fetch
edperf/load.py            raw quarterly files -> one tidy table
edperf/profile.py         measures behind the source profile
edperf/mix.py             mix versus within-category split
scripts/                  download, snapshot build, Part 1 and Part 2 reports
data/raw/                 14 raw quarterly files as returned by the API
data/ed_quarterly.csv     tidy snapshot: hospital x quarter x triage category
data/facility_names.csv   every spelling each facility code has had
results/                  SOURCE_PROFILE.md, MIX_VS_PERFORMANCE.md, CSVs, charts
tests/                    loader, measures, the split on hand-made numbers, report regeneration, README figures
```

## Roadmap

1. ~~Source, snapshot and profile~~
2. ~~Mix versus performance: how much of the fall in 4-hour stays is a more urgent mix, and how much is each triage category getting slower~~
3. Hospital scorecard: peer groups by size, which hospitals are improving or slipping within category, and by how much
4. Front door versus back door: waits, walk-outs and admitted-patient delays by hospital
5. Star-schema export for Power BI, CI and the final write-up with recommendations

## Limitations

- Aggregated data: quarterly percentages and medians per hospital, with no patient-level records, times of day or diagnoses.
- "Admissions to hospital within 4 hours" is the source's column name. It is read here as the share of admitted patients whose ED stay was within 4 hours; the portal's definitions file could not be downloaded from the machine this was built on.
- Triage category is the only measure of how sick patients are. A change in triage practice looks the same as a change in patients, so the mix effect in Part 2 is an estimate, not a fact about patients.
- The 4-hour rate of patients who were not admitted is implied by three published figures, not published itself.
- "Seen within the recommended time" does not rebuild exactly from its five categories (the rebuilt figure is about 0.3 points higher), so Part 2 uses its changes, not its levels.
- The 10,000-attendance line between "large" and other hospitals is a working threshold for Part 1, not an official peer group.
- No official targets are applied yet. Part 3 will add them once they are confirmed from a Queensland Health source.

## Attribution

Contains data from Queensland Health, "Emergency departments - quarterly data", licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The analysis and any errors are mine.
