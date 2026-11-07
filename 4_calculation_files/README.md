# Calculation files for the thesis tables

Thesis: Thermal Performance Analysis of a PV-TEG-PCM Hybrid Energy Harvester under Sri Lankan Tropical Outdoor Conditions (M.Y.A. Perera, S/20472, University of Peradeniya, 2026).

There is one Excel file for every table that shows calculated values. Each file starts from the row-limited data (the analysis set), so the numbers can be followed from the calibrated thermocouple files and the sweep summary files to the printed table.

## How to read a file

| Sheet | Content |
|---|---|
| Steps | What the table shows, where the data come from, numbered steps in plain words, a worked example that updates with the data |
| Result | Block 1 the table as printed, block 2 recalculated by formulas, block 3 check (OK / DIFF for every calculated number; "n/a" where the printed cell is a label or is not calculated) |
| Working | Every calculation in order: sums, counts, means (sum / number), medians, ratios. The formula is in the Value cell |
| Sweeps, Temps, TEG, Calibration | The input data copied from the row-limited files (blue text = values taken from the data files, black text = formulas). Each row names its source file and row |

Means are shown as sum divided by number. Medians, quartiles, minima and maxima use the Excel functions MEDIAN, QUARTILE, MIN and MAX (the middle value, the values a quarter and three quarters of the way up the sorted list, the smallest and the largest).

## Files

| Table | Title | File |
|---|---|---|
| 3.5 | Smallest reading (resolution) of the measurement channels | Table_3.5_Resolution_of_measurement_channels.xlsx |
| 4.1 | Data set inventory and analysis windows | Table_4.1_Data_set_inventory.xlsx |
| 4.2 | Ambient and light conditions per day (ambient = calibrated TC8, within the analysis window) | Table_4.2_Ambient_and_light_conditions.xlsx |
| 4.3 | Quality and uncertainty of the extracted parameters (all 230 sweeps) | Table_4.3_Quality_and_uncertainty.xlsx |
| 4.4 | Composition and transition temperatures of the paraffin–coconut oil mixtures | Table_4.4_PCM_mixtures_and_transition_temperatures.xlsx |
| 4.5 | Temperature of the PCM inside the enclosure during operation on the hybrid days (TC6 = inside the PCM; TC5 = rear surface of the hybrid panel; analysis windows of Table 4.1) | Table_4.5_PCM_temperature.xlsx |
| 4.6 | Time the 40:60 PCM spent in each part of its melting range (TC6), and the front-surface temperature difference on the same day | Table_4.6_PCM_melting_range_time.xlsx |
| 4.7 | Baseline PV1/PV2 power ratio, both panels bare | Table_4.7_Baseline_power_ratio.xlsx |
| 4.8 | Daily panel temperatures on the hybrid days (medians at sweep midpoints) | Table_4.8_Daily_panel_temperatures.xlsx |
| 4.9 | Temperature difference between the panels (PV1 − PV2) by light level, hybrid days | Table_4.9_Temperature_difference_by_light_level.xlsx |
| 4.10 | Maximum power point by day | Table_4.10_Maximum_power_point_by_day.xlsx |
| 4.11 | Open-circuit voltage, short-circuit current and fill factor by day (daily means) | Table_4.11_Voc_Isc_FF_by_day.xlsx |
| 4.12 | Parameters of all sweeps, median (Q1–Q3) | Table_4.12_Parameters_of_all_sweeps.xlsx |
| 4.13 | Paired PV1/PV2 ratios: baseline against hybrid | Table_4.13_Paired_ratios_baseline_vs_hybrid.xlsx |
| 4.14 | Gain by irradiance level (PV2 power bin), median ratios PV1/PV2 | Table_4.14_Gain_by_irradiance_level.xlsx |
| 4.15 | Stability check: fill factor of each panel at matched light (median) | Table_4.15_Fill_factor_stability_check.xlsx |
| 4.16 | Thermal contribution to the 38% gain | Table_4.16_Thermal_contribution_to_gain.xlsx |
| 4.17 | Sampled energy at the maximum power point, by day | Table_4.17_Sampled_energy.xlsx |
| 4.18 | TEG sweep results by day | Table_4.18_TEG_results_by_day.xlsx |
| 4.19 | TEG open-circuit voltage against temperature differences from the thermocouples | Table_4.19_TEG_Voc_vs_temperature.xlsx |

## Tables without a calculation file

| Table | Why |
|---|---|
| 1.1, 3.1, 3.2, 3.3, 3.4, 3.6 | Descriptive tables (configuration, components, pins, addresses, thermocouple positions, experimental days). They contain no calculated values. |
| 4.4 | The mean of the two trials and the melting range are calculated (file included). The transition temperatures are read from the cooling-curve graphs, which are plotted with elapsed time on the x axis and the calibrated thermocouple temperature on the y axis (see the notes in the Table 4.4 file). |
| 4.20 | Summary of findings. Every number is taken from another table: 73% and 72-75% from Table 4.7; 1.7 and 2.5-2.9 deg C from Tables 4.8 and 4.9; 1.008 and 0.729, 38% and 36-42% from Tables 4.14 and 4.16; 0.6-1.3% and about 37 of 38 points from Table 4.16; 37.85 and 37.71 Wh from Table 4.17; TEG figures from Table 4.18; PCM entered its melting range on five days and reached 53 deg C on three from Table 4.6. |
| I.1 | Row limits are a decision of the author, not a calculation. The rule and the removed sweeps are listed in row_limits_TableI1.csv and row_limit_log.csv of the row-limited data set. |

## Notes

- Calibrated temperature = raw reading minus the ice-point offset of the thermocouple (sheet Calibration in the files that use temperatures). The offsets are not applied again; the calibrated columns of the V files are used as they are.
- Baseline-day temperatures are not corrected for the offset between the two panels; the offset is disclosed in the thesis, not corrected.
- File names keep the spelling "Callibrated" of the original data files.
