# Data notes

## Row limits
Table A.1 of the thesis fixes the last row used of every summary file. Row 1 is the header, so "last row 31" means the first 30 sweeps. The row-limited copies are in `2_analysis_set_row_limited`; the removed sweeps are listed in `row_limit_log.csv`. Totals: 230 paired sweeps (172 hybrid, 58 baseline), 82 TEG sweeps, 3195 one-minute records.

## Failed TEG days
The TEG sweeps of 16 and 17 September are not used (TEG faulty). The TEG was not connected on 28 September and 1 October.

## Thermocouple TC2 on the baseline days
On 28 September (16 records) and 1 October (13 records) TC2 reads about 0 deg C raw (about -3.5 deg C calibrated). Records are kept in the files. In the analysis the rear temperature difference (TC5 - TC2) is calculated only when TC2 is above 15 deg C at both records around a sweep; four baseline sweeps therefore have no rear difference.

## TC4
Not used in the analysis; no calibration offset.

## Calibration
Offset = average of the ice-point readings minus the 0.5 deg C reference reading. Calibrated temperature = raw reading minus the offset. Offsets (deg C): TC1 3.86, TC2 3.51, TC3 3.59, TC5 2.99, TC6 2.24, TC7 2.40, TC8 3.74. The calculation is shown in the sheet Calibration of the calculation files.

## Missing items
Original SD-card CSV files, photographs as separate files and editable diagram sources are not part of this version.
