ANALYSIS SET (ROW-LIMITED FILES)
M.Y.A. Perera, S/20472 - PV-TEG-PCM hybrid energy harvester

What this folder is
The files here are the data that the thesis tables were calculated from. They are copies of the
original files with the rows outside the analysis window removed (thesis Appendix A.1, Table A.1).
The original, complete files stay untouched in Python_Analysis_of_Sweep_files and
Outdoor_Campain_Data.

Totals (checked against the thesis traceability workbook, difference 0)
  230 paired PV1/PV2 sweeps (172 hybrid, 58 baseline)
   82 TEG sweeps (12 Sep 27, 13 Sep 27, 14 Sep 1, 18 Sep 11, 19 Sep 16)
 3195 one-minute records (418, 405, 319, 304, 375, 361, 218, 400, 395)

Rule 1 - sweep summary files (sweep_summaries_limited)
  Rows up to and including the "last row used" of Table A.1 are kept. Row 1 is the header, so
  "last row 31" = the first 30 sweeps. The rows removed are the evening sweeps after the limit
  and the sweeps that failed to fit (they sit at the bottom of the original files).
  The Average / Minimum / Maximum rows are the author's own and move up under the data.
  Not created: TEG 16 and 17 Sep (TEG faulty), TEG 28 Sep and 1 Oct (not connected).

Rule 2 - one-minute files (one_minute_files_limited)
  From the last record at or before the start of the first used sweep, to one minute after the
  end of the last used sweep (inclusive). Calibrated columns are formulas: raw reading minus
  the ice-point offset in the small table at AD:AE. TC2 on 28 Sep and 1 Oct is the faulty
  channel (raw about 0 degrees C, calibrated about -3.5); it is kept, as in the thesis.

Other files
  row_limits_TableA1.csv   Table A.1 as a machine-readable table
  row_limit_log.csv        for every file: rows before and after, and which sweeps were removed
  tools/apply_row_limits.py   the script that made these files (run it again to repeat)
