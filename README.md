# PV-TEG-PCM hybrid energy harvester: data, code and calculations

Data repository of the B.Sc. thesis **Thermal Performance Analysis of a PV-TEG-PCM Hybrid Energy Harvester under Sri Lankan Tropical Outdoor Conditions**
(M.Y.A. Perera, S/20472, University of Peradeniya, 2026).

Outdoor campaign: 12, 13, 14, 16, 17, 18, 19 September 2026 (hybrid panel PV1 against bare panel PV2) and 28 September and 1 October 2026 (both panels bare, baseline).
Laboratory work: nine paraffin-coconut oil mixtures (PCM1 to PCM9), cooling curves and melting-point readings.

## Folder map

| Folder | Content |
|---|---|
| `1_raw_and_calibrated_data` | Sweep files `SMMDD.xlsx` (every I-V sweep as logged), one-minute temperature files `VMMDD_Callibrated.xlsx` (raw and calibrated thermocouple columns), the ice-point calibration file, and the PWM range files used for fitting |
| `2_analysis_set_row_limited` | The data the thesis tables were calculated from: the same files with the rows outside the analysis windows removed (Table A.1). Has its own README and a log of every removed sweep |
| `3_analysis_output_full` | Complete output of the Python analysis for every day: sweep summaries (PV1, PV2, TEG), fit figures of every sweep, captions, batch logs, and the one-minute temperature overview figures |
| `4_calculation_files` | One Excel file per table that shows calculated values: steps in words, the arithmetic and a check against the printed value. Has its own README |
| `5_figures` | Every figure of the thesis as an image, with its caption (`figure_captions.csv`) |
| `6_pcm_laboratory` | Cooling-curve data of the PCM mixtures (trials A and B), their graphs and the results sheet |
| `7_code` | Arduino sketch of the data acquisition system, the Python analysis scripts, the script that makes the row-limited set and the script that builds the calculation files |
| `8_documentation` | Data dictionary, table-to-file map, figure-to-source map, known data notes |

## How to follow a value from the data to the thesis

1. Find the table in `8_documentation/table_to_file_map.csv`.
2. Open its file in `4_calculation_files`. The sheet **Steps** explains the calculation in words. The sheet **Working** shows each step with its formula. The sheet **Result** compares the recalculated value with the printed one.
3. The input sheets of that file name the source file and row of every value, in `2_analysis_set_row_limited`.
4. The row-limited files are copies of the files in `1_raw_and_calibrated_data` and `3_analysis_output_full` (rule in Table A.1 of the thesis).

## Notes

- File names keep the spelling "Callibrated" used when the data were recorded.
- Calibrated temperature = raw reading minus the ice-point offset of each thermocouple (`Thermocouple_Callibration.xlsx`). No correction for the offset between the two panels was applied to the hybrid-day temperatures; it is disclosed in the thesis.
- Thermocouple TC2 (rear of the bare panel) read about 0 deg C raw on 28 September (16 records) and 1 October (13 records). These records are kept and handled in the analysis (see `8_documentation/data_notes.md`).
- The real-time clock (DS3231) was set from the computer time when the sketch was uploaded, the setting line was then commented out and the sketch uploaded again; a backup battery kept the time. No check against a reference clock was recorded.
- The sketch in `7_code/arduino` is the documentation version of the sketch that logged the data: only comments, some serial messages and one unused constant were corrected so that it agrees with the thesis (see its header).

## Licence and citation

Suggested: data under CC BY 4.0, code under the MIT licence (see `LICENSE.md`). Citation details are in `CITATION.cff`. Archive address / DOI: to be added.

`MANIFEST_sha256.csv` lists every file with its size and SHA-256 checksum.
