# Data dictionary

## Sweep files `1_raw_and_calibrated_data/SMMDD.xlsx` (one sheet per day)
Columns: Date, Time, PWM (duty value 0 to 255 of the load MOSFET), V1_PV1(V), I1_PV1(mA), P1_PV1(mW), V2_PV2(V), I2_PV2(mA), P2_PV2(mW), V_TEG(V), I_TEG(mA), P_TEG(mW), V_BPW(V).
A row "Sweep N" starts each sweep. One sweep has 256 PWM steps (about 40 s) and one sweep was started every 15 minutes. TEG current and the BPW34 signal are clamped at 0 or above in the logger.
V_BPW (V) is the BPW34 photodiode signal, a relative irradiance indicator.

## One-minute files `VMMDD_Callibrated.xlsx`
Date, Time, PWM, V1 ... V_BPW (the last values of the one-minute record), TC1 to TC8 raw (deg C), TC1_Callibrated to TC8_Callibrated (deg C; formulas: raw minus offset). The offsets are in the small table in columns AD:AE.
Thermocouples: TC1 front of bare panel PV2; TC2 rear of PV2; TC3 front of hybrid panel PV1; TC4 not used; TC5 rear of PV1; TC6 PCM in the long block on PV1; TC7 PCM in the short block under the TEG; TC8 ambient air.

## Summary files `summary_PV1_MMDD.xlsx`, `summary_PV2_MMDD.xlsx`, `summary_TEG_MMDD.xlsx`
One row per sweep: sweep, source, date, start_time, end_time, PWM_lo, PWM_hi (range of PWM used for the fit), n_fit_points, bpw_avg_fit_V (mean BPW34 signal over the fitted range), Voc, Voc_err, Isc, Isc_err, Vmp, Vmp_err, Imp, Imp_err, Pmp, Pmp_err, FF, Rin_ohm, R2, RMSE_mA, v_unit, p_unit, pwm_source, status (ok or failed), figure.
PV1 and PV2 are fitted with the single-exponential diode model; the TEG with a linear (Thevenin) model, where Pmp is the maximum power Pmax and Rin the internal resistance. Units: V, mA, mW for PV; mV and uW for the TEG (see v_unit, p_unit). Statistics rows (Average, Minimum, Maximum) below the data cover the rows of the data block.

## `pwm_ranges_override_SMMDD.xlsx`
The PWM range used for the fit of each sweep and source (sweep, source, PWM_lo, PWM_hi).

## PCM laboratory files `6_pcm_laboratory`
`Cooling_curve_data_nX.xlsx` (n = mixture 1 to 9, X = trial A or B): Date, Time, Elapsed, New_Elapsed (elapsed time restarting at 00:00:00), Callibrated (calibrated temperature, deg C), TC2_C. `Results_of_PCM.xlsx`: composition, cooling-curve transition temperatures of both trials, melting start and complete melting.
