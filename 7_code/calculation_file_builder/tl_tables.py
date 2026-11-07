"""tl_tables.py - one builder per thesis table (calculation, working steps, explanation)."""
from tl_lib import *

IN_SW = ('Sweep results: summary_PV1_MMDD.xlsx and summary_PV2_MMDD.xlsx of each day (row-limited copies in the folder '
         'sweep_summaries_limited). The two files hold the same sweeps; they are copied side by side to the sheet Sweeps, one row per sweep (230 rows).')
IN_TM = ('Temperatures: V0912_Callibrated.xlsx ... V1001_Callibrated.xlsx (row-limited copies in the folder one_minute_files_limited), '
         'columns TC1_Callibrated ... TC8_Callibrated. They are copied to the sheet Temps, one row per one-minute record (3195 rows). '
         'Each Temps row names its source file and the row in that file. Calibrated value = raw reading minus the ice-point offset (sheet Calibration).')
IN_TEG = 'TEG results: summary_TEG_MMDD.xlsx of the five days with a working TEG (row-limited copies), copied to the sheet TEG (82 rows).'
SH_RES = 'Result: the table as printed, the recalculated table, and the check (OK / DIFF) for every number.'
SH_WK = 'Working: every step of the calculation in order, with the formula in the Value cell.'
SH_SW = 'Sweeps: the sweep data copied from the summary files (blue), with the ratios and class columns calculated by formulas (black).'
SH_TM = 'Temps: the calibrated one-minute records (blue).'
SH_TG = 'TEG: the TEG sweeps (blue) with the interpolated temperatures and differences by formula.'
SH_CA = 'Calibration: how the thermocouple offsets were obtained from the ice-point readings.'
SH_SWF = ('Sweeps: as above, plus the thermocouple temperatures at the middle of each sweep (linear interpolation between the last record before '
          'and the first record after the sweep, Section 3.7.1) and the temperature differences PV1 - PV2.')


def cdS(S, c): return f'({S.r("code")}="{c}")'
def CHs(S): return f'({S.r("typ")}="H")'
def CBs(S): return f'({S.r("typ")}="B")'
def pbs(S, lo): return f'({S.r("pbin")}={lo})'
def P(*cs): return '*'.join(cs)
def lo_of(label): return int(label.split('–')[0])


def mean_block(L, name, sumf, nf, fmt='0.00', unit=''):
    s = L.add(f'{name}: sum of the values', sumf, fmt if fmt != '0' else '0.00', unit)
    n = L.add(f'{name}: number of values', nf, '0')
    m = L.add(f'{name}: mean = sum / number', f'={s.loc}/{n.loc}', fmt, unit)
    return s, n, m


# ================================================================== Table 3.5
def t3_5(c):
    L = c['L']; rows = c['rows']
    L.sec('Constants from the data sheets (blue = input)')
    ina_v = L.input('INA219 bus-voltage register: one step', 4, '0', 'mV')
    cal = L.input('INA219 calibration register used by the default calibration (Adafruit library, 32 V / 2 A)', 4096, '0')
    rsh = L.input('INA219 shunt resistor on the module', 0.1, '0.0', 'ohm')
    fs = L.input('ADS1115 full-scale range used (gain 2/3), plus and minus', 6.144, '0.000', 'V')
    bits = L.input('ADS1115: bits of the signed result, so the number of steps from 0 to full scale is 2^15', 15, '0')
    r13 = L.input('Shunt resistor of the TEG channel (measured with a multimeter)', 1.3, '0.0', 'ohm')
    tmax = L.input('MAX6675: highest temperature of the 12-bit range', 1023.75, '0.00', 'deg C')
    tst = L.input('MAX6675: number of steps of the 12-bit range (2^12 - 1)', 4095, '0')
    L.sec('Calculations')
    ic = L.add('INA219 current step = 0.04096 / (calibration register x shunt resistance), in ampere, then x 1000 for mA',
               f'=0.04096/({cal.loc}*{rsh.loc})*1000', '0.0', 'mA')
    ads = L.add('ADS1115 voltage step = full scale / 2^15, in mV', f'={fs.loc}/2^{bits.loc}*1000', '0.0000', 'mV')
    adsi = L.add('ADS1115 current step on the 1.3 ohm shunt = voltage step / resistance (mV / ohm = mA)', f'={ads.loc}/{r13.loc}', '0.0000', 'mA')
    mx = L.add('MAX6675 temperature step = range / number of steps', f'={tmax.loc}/{tst.loc}', '0.00', 'deg C')
    ex = [[None, None, f'={ina_v.ref}'], [None, None, f'={ic.ref}'],
          [None, None, f'=TEXT({ads.ref},"0.00")&" mV ("&TEXT({ads.ref},"0.0000")&" mV)"'],
          [None, None, f'=TEXT({ads.ref},"0.00")&" mV, and "&TEXT({adsi.ref},"0.00")&" mA"'],
          [None, None, f'={ads.ref}'], [None, None, f'={mx.ref}']]
    return dict(exprs=ex, what=('The smallest change of the reading (the resolution) of each measurement channel. It is not measured; it follows from '
                                'the number of steps of each converter and from its range.'),
                inputs=['Data-sheet values of the INA219, ADS1115 and MAX6675 and the library calibration (blue cells on the Working sheet).',
                        'Shunt of the TEG channel: 1.3 ohm, measured (Section 3.3).'],
                steps=['INA219 bus voltage: one step of the register is 4 mV (data sheet).',
                       'INA219 current: with the default calibration of the Adafruit library the calibration register is 4096 and the shunt is 0.1 ohm, so one step of the current register is 0.04096 / (4096 x 0.1) = 0.0001 A = 0.1 mA.',
                       'ADS1115: the range of +/-6.144 V is divided into 2^15 = 32768 steps on the positive side, so one step is 6.144 V / 32768 = 0.1875 mV. This holds for channels A0, A1 and A2.',
                       'TEG current: the step of A1 divided by the shunt, 0.1875 mV / 1.3 ohm = 0.144 mA.',
                       'MAX6675: the 12-bit result covers 0 to 1023.75 deg C in 4095 steps, so one step is 0.25 deg C.'],
                example=[tx('ADS1115: 6.144 V / 2^15 = ', (ads, '0.0000'), ' mV; on the 1.3 ohm shunt this is ', (adsi, '0.000'), ' mA per step.')],
                notes=['These are the smallest steps of the converters. They are not the accuracy of the measurements.'],
                sheets=[SH_RES, SH_WK])


# ================================================================== Table 4.1
def t4_1(c):
    L = c['L']; S = c['S']; T = c['T']; G = c['G']; rows = c['rows']
    ex = []; refs = []
    for r in rows[:-1]:
        d = code(r[0]); dd = d[1:]
        L.sec(f'{r[0]} 2026')
        lr = L.input(f'Last row of the summary file used (Table I.1; row 1 is the header, so {LASTROW[dd][0]-1} sweep rows)', LASTROW[dd][0], '0')
        n = L.add('Sweeps analysed = number of rows of this day in the sheet Sweeps', f'=COUNTIFS({S.r("code")},"{d}")', '0')
        fl = L.add('Failed sweeps removed = rows within the limit (last row - 1) minus sweeps analysed', f'=({lr.loc}-1)-{n.loc}', '0')
        a = L.add('Start of the first sweep', f'=_xlfn.MINIFS({S.r("t0")},{S.r("code")},"{d}")', 'hh:mm:ss')
        b = L.add('End of the last sweep', f'=_xlfn.MAXIFS({S.r("t1")},{S.r("code")},"{d}")', 'hh:mm:ss')
        w = L.add('Analysis window as printed = start and end to the minute (seconds dropped)',
                  f'=TEXT(INT({a.loc}*1440)/1440,"hh:mm")&"–"&TEXT(INT({b.loc}*1440)/1440,"hh:mm")', '@')
        nt = L.add('Thermocouple records = number of rows of this day in the sheet Temps', f'=COUNTIFS({T.r("code")},"{d}")', '0')
        ng = None
        if r[7].isdigit():
            ng = L.add('TEG sweeps = number of rows of this day in the sheet TEG', f'=COUNTIFS({G.r("code")},"{d}")', '0')
        ex.append([None, None, f'={lr.ref}', f'={n.ref}', f'={fl.ref}', f'={w.ref}', f'={nt.ref}', (f'={ng.ref}' if ng else None)])
        refs.append((lr, n, fl, nt, ng))
    L.sec('Totals')
    tn = L.add('Total sweeps analysed', '=' + '+'.join(x[1].loc for x in refs), '0')
    tf = L.add('Total failed sweeps removed', '=' + '+'.join(x[2].loc for x in refs), '0')
    tt = L.add('Total thermocouple records', '=' + '+'.join(x[3].loc for x in refs), '0')
    tg = L.add('Total TEG sweeps', '=' + '+'.join(x[4].loc for x in refs if x[4]), '0')
    ex.append([None, None, None, f'={tn.ref}', f'={tf.ref}', None, f'={tt.ref}', f'={tg.ref}'])
    return dict(exprs=ex, what=('An inventory of the data set: for each day the rows kept, the sweeps analysed, the analysis window, the number of '
                                'one-minute temperature records and the number of TEG sweeps.'),
                inputs=[IN_SW, IN_TM, IN_TEG, 'Last row used: Table I.1 (a rule chosen by the author, entered as an input on the Working sheet).'],
                steps=['Take the last row used of each summary file from Table I.1. Row 1 is the header, so the sweep rows are 2 to that row.',
                       'Count the sweeps of the day in the sheet Sweeps. This is "Sweeps analysed".',
                       'Failed sweeps removed = (rows inside the limit) - (sweeps analysed). A sweep that failed to fit (status not ok) would be missing from the sheet; none fell inside the limit.',
                       'Analysis window = start of the first sweep of the day to the end of the last sweep, written as hours and minutes (seconds dropped).',
                       'Thermocouple records = number of one-minute records of the day kept in the sheet Temps (rule: from the last record at or before the first sweep to one minute after the last sweep).',
                       'TEG sweeps = number of rows of the day in the sheet TEG (only on the five days with a working TEG).',
                       'Add the columns to get the totals 230 sweeps, 3195 records and 82 TEG sweeps.'],
                example=[tx('12 Sep: ', (refs[0][1], '0'), ' sweeps, ', (refs[0][3], '0'), ' temperature records.')],
                notes=['The row limits themselves (Table I.1) are decisions of the author and are not calculated.'],
                sheets=[SH_RES, SH_WK, SH_SW, SH_TM, SH_TG])


# ================================================================== Table 4.2
def t4_2(c):
    L = c['L']; S = c['S']; T = c['T']; rows = c['rows']; ex = []; first = None
    for r in rows:
        d = code(r[0]); L.sec(f'{r[0]} 2026')
        sT, nT, mT = mean_block(L, 'Ambient temperature (calibrated TC8, one-minute records)',
                                f'=SUMIFS({T.r("TC8")},{T.r("code")},"{d}")', f'=COUNTIFS({T.r("code")},"{d}",{T.r("TC8")},"<>")', '0.00', 'deg C')
        mn = L.add('Ambient minimum = smallest TC8 value of the day', f'=_xlfn.MINIFS({T.r("TC8")},{T.r("code")},"{d}")', '0.00', 'deg C')
        mx = L.add('Ambient maximum = largest TC8 value of the day', f'=_xlfn.MAXIFS({T.r("TC8")},{T.r("code")},"{d}")', '0.00', 'deg C')
        sB, nB, mB = mean_block(L, 'BPW34 signal (sweeps of the day)', f'=SUMIFS({S.r("bpw")},{S.r("code")},"{d}")', f'=COUNTIFS({S.r("code")},"{d}")', '0.000', 'V')
        xB = L.add('BPW34 maximum', f'=_xlfn.MAXIFS({S.r("bpw")},{S.r("code")},"{d}")', '0.000', 'V')
        sP, nP, mP = mean_block(L, 'PV2 maximum power Pmp (sweeps of the day)', f'=SUMIFS({S.r("P2")},{S.r("code")},"{d}")', f'=COUNTIFS({S.r("code")},"{d}")', '0.0', 'mW')
        xP = L.add('PV2 maximum power, largest value', f'=_xlfn.MAXIFS({S.r("P2")},{S.r("code")},"{d}")', '0.0', 'mW')
        k9 = L.add('Number of sweeps with PV2 Pmp of 900 mW or more', f'=COUNTIFS({S.r("code")},"{d}",{S.r("P2")},">=900")', '0')
        sh = L.add('Share of sweeps with PV2 >= 900 mW = number / number of sweeps x 100', f'={k9.loc}/{nP.loc}*100', '0.0', '%')
        ex.append([None, f'={mT.ref}', f'={mn.ref}', f'={mx.ref}', f'={mB.ref}', f'={xB.ref}', f'={mP.ref}', f'={xP.ref}', f'={sh.ref}'])
        if first is None: first = (sT, nT, mT, mn, mx)
    sT, nT, mT, mn, mx = first
    return dict(exprs=ex, what=('The weather on each day, taken from the ambient thermocouple (TC8) and the light sensor (BPW34), and the output of the '
                                'bare panel PV2 as a measure of how bright the day was.'),
                inputs=[IN_TM, IN_SW, 'Thermocouple offsets: Thermocouple_Callibration.xlsx (sheet Calibration).'],
                steps=['Calibrate: each raw TC8 reading is reduced by the ice-point offset of TC8 (3.74 deg C). The V...Callibrated files already hold the calibrated column TC8_Callibrated.',
                       'Keep the one-minute records inside the analysis window of the day (Table 4.1). They are the rows of the day in the sheet Temps.',
                       'Ambient mean = (sum of the TC8 values) / (number of records). Ambient minimum and maximum are the smallest and largest TC8 values of the day.',
                       'BPW34 mean = (sum of the BPW34 value of each sweep, column bpw_avg_fit_V) / (number of sweeps); BPW34 maximum is the largest of them.',
                       'PV2 Pmp mean and maximum: the same for the maximum power point of PV2 of each sweep.',
                       'Share of sweeps with PV2 >= 900 mW = (number of sweeps with Pmp >= 900 mW) / (number of sweeps) x 100.'],
                example=[tx('12 Sep ambient: sum of TC8 = ', (sT, '0.00'), ' deg C over ', (nT, '0'), ' records, so mean = ', (sT, '0.00'), ' / ', (nT, '0'),
                            ' = ', (mT, '0.00'), ' deg C (printed 34.1). Minimum ', (mn, '0.00'), ', maximum ', (mx, '0.00'), '.')],
                notes=['Ambient = calibrated TC8 within the analysis window, as in the table title.'],
                sheets=[SH_RES, SH_WK, SH_TM, SH_SW, SH_CA])


# ================================================================== Table 4.3
def t4_3(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []
    mp = {('PV1', 'Voc'): ('V1', 'V1e', 'rV1'), ('PV1', 'Isc'): ('I1', 'I1e', 'rI1'), ('PV1', 'Pmp'): ('P1', 'P1e', 'rP1'),
          ('PV2', 'Voc'): ('V2', 'V2e', 'rV2'), ('PV2', 'Isc'): ('I2', 'I2e', 'rI2'), ('PV2', 'Pmp'): ('P2', 'P2e', 'rP2')}
    first = None
    for r in rows:
        k = r[1].split(' ')[0]; v, e, rl = mp[(r[0], k)]
        L.sec(f'{r[0]} {r[1]}')
        n = L.add('Number of sweeps', f'=COUNT({S.r(v)})', '0')
        mv = L.add('Median value over the sweeps', f'=MEDIAN({S.r(v)})', '0.000')
        me = L.add('Median uncertainty (the fit uncertainty of each sweep, median over the sweeps)', f'=MEDIAN({S.r(e)})', '0.0000')
        mr = L.add('Median relative uncertainty = median of (uncertainty / value) of each sweep, x 100', f'=MEDIAN({S.r(rl)})*100', '0.00', '%')
        xr = L.add('Maximum relative uncertainty = largest of (uncertainty / value), x 100', f'=MAX({S.r(rl)})*100', '0.00', '%')
        ex.append([None, None, f'={mv.ref}', f'={me.ref}', f'={mr.ref}', f'={xr.ref}'])
        if first is None: first = (n, mv, me, mr)
    n, mv, me, mr = first
    return dict(exprs=ex, what='How well the I-V fit of each sweep determined Voc, Isc and Pmp: the size of the fit uncertainty, over all 230 sweeps.',
                inputs=[IN_SW + ' The uncertainty of each parameter is the column Voc_err, Isc_err or Pmp_err of the summary files (from the fit, Section 3.4.4).'],
                steps=['For each sweep and parameter, relative uncertainty = uncertainty / value (columns "Rel. unc." of the sheet Sweeps).',
                       'Median value and median uncertainty = the middle value of the 230 sweeps (sorted, the 115th and 116th values averaged).',
                       'Median and maximum relative uncertainty = median and largest of the 230 relative uncertainties, times 100.'],
                example=[tx('PV1 Voc: median value ', (mv, '0.00'), ' V, median uncertainty ', (me, '0.000'), ' V, so the median relative uncertainty is ', (mr, '0.0'), ' %.')],
                notes=['A median is used so that a few poor fits do not decide the result (Section 3.7.5).'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.5
def t4_5(c):
    L = c['L']; T = c['T']; rows = c['rows']; ex = []; first = None
    for r in rows:
        d = code(r[0]); cd_ = f'{T.r("code")},"{d}"'; L.sec(f'{r[0]} 2026')
        n = L.add('Records = number of one-minute records of the day', f'=COUNTIFS({cd_},{T.r("TC6")},"<>")', '0')
        mn = L.add('TC6 minimum', f'=_xlfn.MINIFS({T.r("TC6")},{cd_})', '0.0', 'deg C')
        s6 = L.add('TC6: sum of the values', f'=SUMIFS({T.r("TC6")},{cd_})', '0.00', 'deg C')
        m6 = L.add('TC6 mean = sum / records', f'={s6.loc}/{n.loc}', '0.0', 'deg C')
        mx = L.add('TC6 maximum', f'=_xlfn.MAXIFS({T.r("TC6")},{cd_})', '0.0', 'deg C')
        sd = L.add('Sum of (TC6 - TC5) over the records (column "TC6 - TC5" of the sheet Temps)', f'=SUMIFS({T.r("d65")},{cd_})', '0.00', 'deg C')
        md = L.add('Mean TC6 - TC5 = sum / records', f'={sd.loc}/{n.loc}', '0.00', 'deg C')
        k45 = L.add('Number of records with TC6 of 45 deg C or more', f'=COUNTIFS({cd_},{T.r("TC6")},">=45")', '0')
        h45 = L.add('Time TC6 >= 45 deg C = number of records x 1 min / 60', f'={k45.loc}/60', '0.00', 'h')
        k50 = L.add('Number of records with TC6 from 50 to 55 deg C', f'=COUNTIFS({cd_},{T.r("TC6")},">=50",{T.r("TC6")},"<=55")', '0')
        h50 = L.add('Time TC6 50-55 deg C = number of records / 60', f'={k50.loc}/60', '0.00', 'h')
        ex.append([None, f'={n.ref}', f'={mn.ref}', f'={m6.ref}', f'={mx.ref}', f'={md.ref}', f'={h45.ref}', f'={h50.ref}'])
        if first is None: first = (n, s6, m6, k45, h45)
    n, s6, m6, k45, h45 = first
    return dict(exprs=ex, what='How hot the PCM (thermocouple TC6, inside the enclosure) became on each hybrid day, and for how long it was above its melting onset.',
                inputs=[IN_TM],
                steps=['Take the calibrated one-minute records of the day (analysis window of Table 4.1).',
                       'Records = number of rows. TC6 minimum and maximum = smallest and largest TC6 value.',
                       'TC6 mean = (sum of the TC6 values) / (number of records).',
                       'Mean TC6 - TC5 = (sum of TC6 - TC5 over the records) / (number of records), where TC5 is the rear surface of the hybrid panel.',
                       'Time above a temperature = (number of records above it) x 1 min / 60. Each record stands for the minute that it was taken in.'],
                example=[tx('12 Sep: TC6 mean = ', (s6, '0.0'), ' / ', (n, '0'), ' = ', (m6, '0.0'), ' deg C; ', (k45, '0'), ' records at 45 deg C or more = ', (h45, '0.00'), ' h.')],
                notes=['Only the seven hybrid days are in the table; PCM was not fitted on the baseline days.'],
                sheets=[SH_RES, SH_WK, SH_TM, SH_CA])


# ================================================================== Table 4.6
def t4_6(c):
    L = c['L']; T = c['T']; S = c['S']; rows = c['rows']; ex = []; first = None
    for r in rows:
        d = code(r[0]); cd_ = f'{T.r("code")},"{d}"'; L.sec(f'{r[0]} 2026')
        mx = L.add('TC6 maximum of the day', f'=_xlfn.MAXIFS({T.r("TC6")},{cd_})', '0.0', 'deg C')
        k1 = L.add('Records with TC6 below 45 deg C', f'=COUNTIFS({cd_},{T.r("TC6")},"<45")', '0')
        k2 = L.add('Records with TC6 from 45 deg C up to (not including) 53 deg C', f'=COUNTIFS({cd_},{T.r("TC6")},">=45",{T.r("TC6")},"<53")', '0')
        k3 = L.add('Records with TC6 of 53 deg C or more', f'=COUNTIFS({cd_},{T.r("TC6")},">=53")', '0')
        h1 = L.add('Time below 45 deg C = records / 60', f'={k1.loc}/60', '0.00', 'h')
        h2 = L.add('Time 45-53 deg C = records / 60', f'={k2.loc}/60', '0.00', 'h')
        h3 = L.add('Time at or above 53 deg C = records / 60', f'={k3.loc}/60', '0.00', 'h')
        st = L.add('PCM state: "Melted through" if TC6 maximum >= 53; otherwise "Partly melted" if the time in 45-53 is 0.25 h or more; otherwise "At or below onset"',
                   f'=IF({mx.loc}>=53,"Melted through",IF({h2.loc}>=0.25,"Partly melted","At or below onset"))', '@')
        nS = L.add('Number of sweeps of the day', f'=COUNTIFS({S.r("code")},"{d}")', '0')
        md = L.add('Front temperature difference PV1 - PV2 = median over the sweeps of (TC3 - TC1)', f'=MEDIAN(IF({cdS(S, d)},{S.r("dF")}))', '0.00', 'deg C', arr=True)
        ex.append([None, f'={mx.ref}', f'={h1.ref}', f'={h2.ref}', f'={h3.ref}', f'={st.ref}', f'={md.ref}'])
        if first is None: first = (mx, k2, h2, st)
    mx, k2, h2, st = first
    return dict(exprs=ex, what='How long the PCM stayed in each part of its melting range (45 to 53 deg C) on each hybrid day, and the cooling of the front surface on the same day.',
                inputs=[IN_TM, 'Sweeps: PV1 and PV2 sweep results, as in Table 4.8.', 'The interpolated temperatures at the sweeps are explained in Section 3.7.1.'],
                steps=['Count the one-minute records of the day with TC6 below 45 deg C, from 45 to below 53 deg C, and 53 deg C or more.',
                       'Divide each count by 60 to get hours.',
                       'PCM state: melted through if TC6 reached 53 deg C; partly melted if it spent at least 0.25 h between 45 and 53 deg C; otherwise at or below onset.',
                       'Front difference = median over the sweeps of the day of (TC3 - TC1) = hybrid front minus bare front, each temperature interpolated to the middle of the sweep.'],
                example=[tx('12 Sep: TC6 maximum ', (mx, '0.0'), ' deg C; ', (k2, '0'), ' records between 45 and 53 deg C = ', (h2, '0.00'), ' h.')],
                notes=['The melting range 45 to 53 deg C comes from the melting-point and cooling-curve measurements of Section 4.2.'],
                sheets=[SH_RES, SH_WK, SH_TM, SH_SWF, SH_CA], need={'sweeps_full', 'temps'})


# ================================================================== Table 4.7
def t4_7(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    for r in rows:
        both = r[0].startswith('Both')
        cond = CBs(S) if both else cdS(S, code(r[0]))
        cs = f'{S.r("typ")},"B"' if both else f'{S.r("code")},"{code(r[0])}"'
        L.sec(r[0])
        n = L.add('Number of sweeps', f'=COUNTIFS({cs})', '0')
        med = L.add('Median of the power ratio PV1/PV2', f'=MEDIAN(IF({cond},{S.r("rP")}))', '0.0000', arr=True)
        q1 = L.add('First quartile Q1 (a quarter of the ratios lie below)', f'=QUARTILE(IF({cond},{S.r("rP")}),1)', '0.0000', arr=True)
        q3 = L.add('Third quartile Q3 (three quarters lie below)', f'=QUARTILE(IF({cond},{S.r("rP")}),3)', '0.0000', arr=True)
        sr = L.add('Sum of the ratios', f'=SUMIFS({S.r("rP")},{cs})', '0.000')
        mean = L.add('Mean ratio = sum / number of sweeps', f'={sr.loc}/{n.loc}', '0.000')
        mn = L.add('Smallest ratio', f'=MIN(IF({cond},{S.r("rP")}))', '0.000', arr=True)
        mx = L.add('Largest ratio', f'=MAX(IF({cond},{S.r("rP")}))', '0.000', arr=True)
        s1 = L.add('Total PV1 power of all sweeps', f'=SUMIFS({S.r("P1")},{cs})', '0.0', 'mW')
        s2 = L.add('Total PV2 power of all sweeps', f'=SUMIFS({S.r("P2")},{cs})', '0.0', 'mW')
        rt = L.add('Ratio of total power = total PV1 / total PV2', f'={s1.loc}/{s2.loc}', '0.000')
        txt = L.add('Median (Q1-Q3) as printed', f'=TEXT({med.loc},"0.000")&" ("&TEXT({q1.loc},"0.000")&"–"&TEXT({q3.loc},"0.000")&")"', '@')
        ex.append([None, f'={n.ref}', f'={txt.ref}', f'={mean.ref}', f'={mn.ref}', f'={mx.ref}', f'={rt.ref}'])
        if first is None: first = (n, med, q1, q3, mean)
    n, med, q1, q3, mean = first
    return dict(exprs=ex, what='The starting point of the comparison: how the power of PV1 compares with PV2 when both panels are bare (the two baseline days).',
                inputs=[IN_SW],
                steps=['For each sweep, power ratio R = PV1 Pmp / PV2 Pmp (Equation 3.2); column "Ratio Pmp PV1/PV2" of the sheet Sweeps.',
                       'Median = the middle value of the ratios; Q1 and Q3 = the values below which a quarter and three quarters of the ratios lie (Excel QUARTILE).',
                       'Mean ratio = (sum of the ratios) / (number of sweeps).',
                       'Minimum and maximum = smallest and largest ratio.',
                       'Ratio of total power = (sum of all PV1 powers) / (sum of all PV2 powers).'],
                example=[tx('28 Sep: ', (n, '0'), ' sweeps, median ', (med, '0.000'), ' (Q1 ', (q1, '0.000'), ' to Q3 ', (q3, '0.000'), '), mean ', (mean, '0.000'), '.')],
                notes=['The median is the quantity used for the gain (Equation 3.3); the mean is shown for comparison.'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.8
def t4_8(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    for r in rows[:-1]:
        d = code(r[0]); cond = cdS(S, d); L.sec(f'{r[0]} 2026')
        n = L.add('Number of sweeps of the day', f'=COUNTIFS({S.r("code")},"{d}")', '0')
        md = {}
        for key, desc in (('TC8', 'Ambient (TC8)'), ('TC1', 'PV2 front (TC1)'), ('TC3', 'PV1 front (TC3)'), ('dF', 'PV1 - PV2 front difference (TC3 - TC1)'),
                          ('TC2', 'PV2 rear (TC2)'), ('TC5', 'PV1 rear (TC5)'), ('dR', 'PV1 - PV2 rear difference (TC5 - TC2)')):
            md[key] = L.add(f'Median over the sweeps: {desc}', f'=MEDIAN(IF({cond},{S.r(key)}))', '0.00', 'deg C', arr=True)
        ex.append([None] + [f'={md[k].ref}' for k in ('TC8', 'TC1', 'TC3', 'dF', 'TC2', 'TC5', 'dR')])
        if first is None: first = (n, md)
    L.sec('All hybrid sweeps')
    nH = L.add('Number of hybrid sweeps', f'=COUNTIFS({S.r("typ")},"H")', '0')
    aF = L.add('Median front difference over all hybrid sweeps', f'=MEDIAN(IF({CHs(S)},{S.r("dF")}))', '0.00', 'deg C', arr=True)
    aR = L.add('Median rear difference over all hybrid sweeps', f'=MEDIAN(IF({CHs(S)},{S.r("dR")}))', '0.00', 'deg C', arr=True)
    ex.append([None, None, None, None, f'={aF.ref}', None, None, f'={aR.ref}'])
    n, md = first
    return dict(exprs=ex, what='The temperatures of the panels on each hybrid day and how much cooler the hybrid panel PV1 was than the bare panel PV2.',
                inputs=[IN_SW, IN_TM],
                steps=['For every sweep, find the temperature of each thermocouple at the middle of the sweep: draw a straight line between the last one-minute record before the sweep and the first one after it, and read it at the midpoint (Section 3.7.1). This is done by formula in the sheet Sweeps.',
                       'Front difference = TC3 - TC1 and rear difference = TC5 - TC2, both PV1 minus PV2 (Equation 3.4), for each sweep.',
                       'For each day, the table gives the median of each quantity over the sweeps of the day (the middle value).',
                       'The last row is the median of the front and rear differences over all 172 hybrid sweeps.'],
                example=[tx('12 Sep: ', (n, '0'), ' sweeps; median PV2 front ', (md['TC1'], '0.0'), ' deg C, median PV1 front ', (md['TC3'], '0.0'), ' deg C; median difference ', (md['dF'], '0.0'), ' deg C.')],
                notes=['A difference of the medians need not equal the median of the differences; the table gives the median of the differences.',
                       'Only hybrid days are used. The baseline temperature differences are discussed separately in Section 4.4.'],
                sheets=[SH_RES, SH_WK, SH_SWF, SH_TM, SH_CA], need={'sweeps_full', 'temps'})


# ================================================================== Table 4.9
def t4_9(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    for r in rows[:-1]:
        lo = lo_of(r[0]); cond = P(CHs(S), pbs(S, lo)); L.sec(f'PV2 power class {r[0]} mW')
        n = L.add('Number of hybrid sweeps in this class', f'=COUNTIFS({S.r("typ")},"H",{S.r("pbin")},{lo})', '0')
        f = L.add('Median front difference (TC3 - TC1)', f'=MEDIAN(IF({cond},{S.r("dF")}))', '0.00', 'deg C', arr=True)
        rr = L.add('Median rear difference (TC5 - TC2)', f'=MEDIAN(IF({cond},{S.r("dR")}))', '0.00', 'deg C', arr=True)
        ex.append([None, f'={n.ref}', f'={f.ref}', f'={rr.ref}'])
        if first is None: first = (n, f, rr)
    L.sec('All sweeps')
    n = L.add('Number of hybrid sweeps', f'=COUNTIFS({S.r("typ")},"H")', '0')
    f = L.add('Median front difference over all hybrid sweeps', f'=MEDIAN(IF({CHs(S)},{S.r("dF")}))', '0.00', 'deg C', arr=True)
    rr = L.add('Median rear difference over all hybrid sweeps', f'=MEDIAN(IF({CHs(S)},{S.r("dR")}))', '0.00', 'deg C', arr=True)
    ex.append([None, f'={n.ref}', f'={f.ref}', f'={rr.ref}'])
    n0, f0, r0 = first
    return dict(exprs=ex, what='How the cooling of the hybrid panel depends on the light level (the power of the bare panel PV2).',
                inputs=[IN_SW, IN_TM],
                steps=['Give each sweep a light class from the power of PV2: 0-300, 300-600, 600-900, 900-1200 or 1200-2000 mW (column "PV2 power class" of the sheet Sweeps).',
                       'Keep the hybrid sweeps of the class and count them.',
                       'Front and rear differences (PV1 - PV2) of each sweep are as in Table 4.8. The table gives their median in each class and for all hybrid sweeps.'],
                example=[tx('Class 0-300 mW: ', (n0, '0'), ' hybrid sweeps; median front difference ', (f0, '0.00'), ' deg C.')],
                notes=['Few sweeps fall in the lowest class (9), so its median is less reliable than the others.'],
                sheets=[SH_RES, SH_WK, SH_SWF, SH_TM, SH_CA], need={'sweeps_full', 'temps'})


# ================================================================== Table 4.10
def t4_10(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    for r in rows:
        d = code(r[0]); cs = f'{S.r("code")},"{d}"'; L.sec(f'{r[0]} 2026 ({r[1]})')
        n = L.add('Number of sweeps', f'=COUNTIFS({cs})', '0')
        s1, _, m1 = mean_block(L, 'PV1 Pmp', f'=SUMIFS({S.r("P1")},{cs})', f'=COUNTIFS({cs})', '0.0', 'mW')
        a1 = L.add('PV1 Pmp smallest', f'=_xlfn.MINIFS({S.r("P1")},{cs})', '0.0', 'mW'); b1 = L.add('PV1 Pmp largest', f'=_xlfn.MAXIFS({S.r("P1")},{cs})', '0.0', 'mW')
        s2, _, m2 = mean_block(L, 'PV2 Pmp', f'=SUMIFS({S.r("P2")},{cs})', f'=COUNTIFS({cs})', '0.0', 'mW')
        a2 = L.add('PV2 Pmp smallest', f'=_xlfn.MINIFS({S.r("P2")},{cs})', '0.0', 'mW'); b2 = L.add('PV2 Pmp largest', f'=_xlfn.MAXIFS({S.r("P2")},{cs})', '0.0', 'mW')
        rt = L.add('Ratio of the means = PV1 mean / PV2 mean', f'={m1.loc}/{m2.loc}', '0.000')
        ex.append([None, None, f'={n.ref}', f'={m1.ref}', f'={a1.ref}', f'={b1.ref}', f'={m2.ref}', f'={a2.ref}', f'={b2.ref}', f'={rt.ref}'])
        if first is None: first = (s1, n, m1, s2, m2, rt)
    s1, n, m1, s2, m2, rt = first
    return dict(exprs=ex, what='The maximum power point of each panel on each day: mean, smallest and largest value, and the ratio of the means.',
                inputs=[IN_SW],
                steps=['Take the Pmp of PV1 and PV2 of each sweep (from the I-V fit of the sweep, Section 3.4.4).',
                       'Mean = (sum of the Pmp values of the day) / (number of sweeps). Smallest and largest = minimum and maximum of the day.',
                       'Ratio of the means = PV1 mean / PV2 mean.'],
                example=[tx('12 Sep: PV1 mean = ', (s1, '0.0'), ' / ', (n, '0'), ' = ', (m1, '0.0'), ' mW; PV2 mean ', (m2, '0.0'), ' mW; ratio = ', (rt, '0.000'), '.')],
                notes=['The ratio of the means is a daily value; the per-sweep median ratios used for the gain are in Tables 4.13 and 4.14.'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.11
def t4_11(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    for r in rows:
        d = code(r[0]); cs = f'{S.r("code")},"{d}"'; L.sec(f'{r[0]} 2026')
        m = {}
        for key, desc, fmt in (('V1', 'PV1 Voc', '0.000'), ('V2', 'PV2 Voc', '0.000'), ('I1', 'PV1 Isc', '0.00'), ('I2', 'PV2 Isc', '0.00'),
                               ('F1', 'PV1 FF', '0.0000'), ('F2', 'PV2 FF', '0.0000')):
            _, _, m[key] = mean_block(L, desc, f'=SUMIFS({S.r(key)},{cs})', f'=COUNTIFS({cs})', fmt)
        rv = L.add('Voc ratio = PV1 mean / PV2 mean', f'={m["V1"].loc}/{m["V2"].loc}', '0.000')
        ri = L.add('Isc ratio = PV1 mean / PV2 mean', f'={m["I1"].loc}/{m["I2"].loc}', '0.000')
        rf = L.add('FF ratio = PV1 mean / PV2 mean', f'={m["F1"].loc}/{m["F2"].loc}', '0.000')
        ex.append([None] + [f'={m[k].ref}' for k in ('V1', 'V2', 'I1', 'I2', 'F1', 'F2')] + [f'={rv.ref}', f'={ri.ref}', f'={rf.ref}'])
        if first is None: first = (m, rv)
    m, rv = first
    return dict(exprs=ex, what='The daily means of the open-circuit voltage, short-circuit current and fill factor of each panel, and their ratios.',
                inputs=[IN_SW],
                steps=['For each day, mean = (sum of the values over the sweeps) / (number of sweeps), for Voc, Isc and FF of each panel.',
                       'Each ratio = PV1 mean / PV2 mean.'],
                example=[tx('12 Sep Voc: PV1 ', (m['V1'], '0.000'), ' V, PV2 ', (m['V2'], '0.000'), ' V, ratio ', (rv, '0.000'), '.')],
                notes=['These are ratios of daily means. The median of the per-sweep ratios (Table 4.13) is used for the gain.'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.12
def t4_12(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    fm = {'V': ('V1', 'V2', '0.00'), 'I': ('I1', 'I2', '0.0'), 'P': ('P1', 'P2', '0'), 'F': ('F1', 'F2', '0.000')}
    for r in rows:
        k = r[0][0] if r[0][0] in 'VIP' else 'F'; a, b, f = fm[k]
        L.sec(r[0]); cells = []
        for grp, cond, key, nm in ((CBs(S), 'B', a, 'baseline PV1'), (CBs(S), 'B', b, 'baseline PV2'), (CHs(S), 'H', a, 'hybrid-day PV1'), (CHs(S), 'H', b, 'hybrid-day PV2')):
            n = L.add(f'{nm}: number of sweeps', f'=COUNTIFS({S.r("typ")},"{cond}")', '0')
            md = L.add(f'{nm}: median', f'=MEDIAN(IF({grp},{S.r(key)}))', f, arr=True)
            q1 = L.add(f'{nm}: Q1', f'=QUARTILE(IF({grp},{S.r(key)}),1)', f, arr=True)
            q3 = L.add(f'{nm}: Q3', f'=QUARTILE(IF({grp},{S.r(key)}),3)', f, arr=True)
            t = L.add(f'{nm}: median (Q1-Q3) as printed', f'=TEXT({md.loc},"{f}")&" ("&TEXT({q1.loc},"{f}")&"–"&TEXT({q3.loc},"{f}")&")"', '@')
            cells.append((t, md, q1, q3, n))
        ex.append([None] + [f'={x[0].ref}' for x in cells])
        if first is None: first = (r[0], cells[0], f)
    nm, cell, f = first
    return dict(exprs=ex, what='The spread of Voc, Isc, Pmp and FF of both panels over all sweeps, separately for the baseline days and the hybrid days.',
                inputs=[IN_SW],
                steps=['Group the sweeps: 58 baseline sweeps (28 Sep, 1 Oct) and 172 hybrid-day sweeps.',
                       'For each parameter and panel, find the median (middle value) and the quartiles Q1 and Q3 (Excel QUARTILE) of the group.',
                       'Write them as median (Q1-Q3).'],
                example=[tx('Baseline PV1, first parameter: median ', (cell[1], '0.000'), ', Q1 ', (cell[2], '0.000'), ', Q3 ', (cell[3], '0.000'), ' over ', (cell[4], '0'), ' sweeps.')],
                notes=['Isc of PV1 is lower than that of PV2 on the baseline days, while on hybrid days they are equal; this is the main finding behind Table 4.13.'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.13
def t4_13(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    qm = {'V': 'rV', 'I': 'rI', 'P': 'rP', 'F': 'rF'}
    for r in rows:
        k = r[0][0]; col = qm[k]; L.sec(r[0])
        b = L.add('Median of the PV1/PV2 ratio over the 58 baseline sweeps', f'=MEDIAN(IF({CBs(S)},{S.r(col)}))', '0.0000', arr=True)
        h = L.add('Median of the PV1/PV2 ratio over the 172 hybrid sweeps', f'=MEDIAN(IF({CHs(S)},{S.r(col)}))', '0.0000', arr=True)
        g = L.add('Change = (hybrid median / baseline median - 1) x 100', f'=({h.loc}/{b.loc}-1)*100', '0.00', '%')
        ex.append([None, f'={b.ref}', f'={h.ref}', f'={g.ref}'])
        if first is None: first = (b, h, g)
    b, h, g = first
    return dict(exprs=ex, what='How each part of the power ratio (Voc, Isc, FF and Pmp) changed between the baseline days and the hybrid days.',
                inputs=[IN_SW],
                steps=['For each sweep, ratio = PV1 value / PV2 value, for Voc, Isc, FF and Pmp.',
                       'Median ratio of the baseline sweeps and of the hybrid sweeps.',
                       'Change (%) = (hybrid median / baseline median - 1) x 100 (Equation 3.3 applied to each quantity). For Pmp this is the gain G.'],
                example=[tx('First row: baseline median ', (b, '0.000'), ', hybrid median ', (h, '0.000'), ', so the change is (', (h, '0.000'), ' / ', (b, '0.000'), ' - 1) x 100 = ', (g, '0.0'), ' %.')],
                notes=['Pmp = Voc x Isc x FF for each sweep, so the three ratio changes combine to the change of the power ratio (Section 4.5).'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.14
def t4_14(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    for r in rows:
        lo = None if r[0].startswith('All') else lo_of(r[0]); L.sec(f'PV2 power class {r[0]}' + ('' if lo is None else ' mW'))
        cB = P(CBs(S), pbs(S, lo)) if lo is not None else CBs(S); cH = P(CHs(S), pbs(S, lo)) if lo is not None else CHs(S)
        extra = f',{S.r("pbin")},{lo}' if lo is not None else ''
        nb = L.add('Number of baseline sweeps', f'=COUNTIFS({S.r("typ")},"B"{extra})', '0')
        nh = L.add('Number of hybrid sweeps', f'=COUNTIFS({S.r("typ")},"H"{extra})', '0')
        v = {}
        for key, nm in (('rP', 'Pmp'), ('rI', 'Isc'), ('rF', 'FF'), ('rV', 'Voc')):
            v[key + 'B'] = L.add(f'Baseline median {nm} ratio', f'=MEDIAN(IF({cB},{S.r(key)}))', '0.0000', arr=True)
            v[key + 'H'] = L.add(f'Hybrid median {nm} ratio', f'=MEDIAN(IF({cH},{S.r(key)}))', '0.0000', arr=True)
            if key == 'rP':
                gn = L.add('Gain G = (hybrid Pmp ratio / baseline Pmp ratio - 1) x 100', f'=({v["rPH"].loc}/{v["rPB"].loc}-1)*100', '0.00', '%')
        ex.append([None, f'={nb.ref}', f'={nh.ref}', f'={v["rPB"].ref}', f'={v["rPH"].ref}', f'={gn.ref}', f'={v["rIB"].ref}', f'={v["rIH"].ref}',
                   f'={v["rFB"].ref}', f'={v["rFH"].ref}', f'={v["rVB"].ref}', f'={v["rVH"].ref}'])
        last = (v, gn)
    v, gn = last
    return dict(exprs=ex, what='The relative gain of the hybrid assembly, in each light class and for all sweeps, with the parts Isc, FF and Voc. The last row is the headline result (gain 38.3%).',
                inputs=[IN_SW],
                steps=['Give each sweep a light class from the power of PV2 (column "PV2 power class").',
                       'For each class and for all sweeps: median of the PV1/PV2 ratio of Pmp, Isc, FF and Voc, for the baseline sweeps and for the hybrid sweeps.',
                       'Gain G (%) = (median hybrid Pmp ratio / median baseline Pmp ratio - 1) x 100 (Equation 3.3). In the last row: 1.008 / 0.729 - 1 = 0.383, that is +38.3%.'],
                example=[tx('All sweeps: baseline Pmp ratio ', (v['rPB'], '0.0000'), ', hybrid ', (v['rPH'], '0.0000'), ', gain G = ', (gn, '0.0'), ' %.')],
                notes=['Because the gain is a ratio of ratios, it is not affected by the light level of a day, which both panels share.'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.15
def t4_15(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    for r in rows:
        lo = lo_of(r[0]); b = P(CBs(S), pbs(S, lo)); h = P(CHs(S), pbs(S, lo)); L.sec(f'PV2 power class {r[0]} mW')
        vals = []
        for cond, key, nm in ((b, 'F2', 'PV2 FF, baseline days'), (h, 'F2', 'PV2 FF, hybrid days'), (b, 'F1', 'PV1 FF, baseline days'), (h, 'F1', 'PV1 FF, hybrid days')):
            vals.append(L.add(f'Median {nm}', f'=MEDIAN(IF({cond},{S.r(key)}))', '0.0000', arr=True))
        ex.append([None] + [f'={x.ref}' for x in vals])
        if first is None: first = vals
    return dict(exprs=ex, what='A stability check: the fill factor of each panel at matched light on the baseline and the hybrid days, to see whether the change in the power ratio comes from a change of the panels themselves.',
                inputs=[IN_SW],
                steps=['Group the sweeps by day type (baseline, hybrid) and light class (power of PV2).',
                       'Median fill factor of PV2 and of PV1 in each group.'],
                example=[tx('Class 0-300 mW: PV2 FF ', (first[0], '0.000'), ' (baseline) and ', (first[1], '0.000'), ' (hybrid).')],
                notes=['PV2 is the same bare panel on all days, so a stable FF of PV2 shows that the conditions were comparable.'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.16
def t4_16(c):
    L = c['L']; S = c['S']; rows = c['rows']
    L.sec('Constants (blue = input; literature values of Section 3.7.7)')
    b1 = L.input('Power coefficient, lower value: relative power change per kelvin', 0.35, '0.00', '% per K')
    b2 = L.input('Power coefficient, upper value', 0.45, '0.00', '% per K')
    v1 = L.input('Voc coefficient, lower value: relative Voc change per kelvin', 0.3, '0.00', '% per K')
    v2 = L.input('Voc coefficient, upper value', 0.4, '0.00', '% per K')
    L.sec('Observed gain (as in Table 4.14, all sweeps)')
    mB = L.add('Median power ratio, 58 baseline sweeps', f'=MEDIAN(IF({CBs(S)},{S.r("rP")}))', '0.0000', arr=True)
    mH = L.add('Median power ratio, 172 hybrid sweeps', f'=MEDIAN(IF({CHs(S)},{S.r("rP")}))', '0.0000', arr=True)
    G = L.add('Gain G = (hybrid / baseline - 1) x 100', f'=({mH.loc}/{mB.loc}-1)*100', '0.000', '%')
    L.sec('Gain from the daily ratios (ratio of the means of each day, Table 4.10)')
    dly = {}
    for d in DAYS:
        dly[d] = L.add(f'{LABEL[d]}: daily ratio = mean PV1 / mean PV2 (sum of PV1 / sum of PV2)',
                       f'=SUMIFS({S.r("P1")},{S.r("code")},"D{d}")/SUMIFS({S.r("P2")},{S.r("code")},"D{d}")', '0.0000')
    mhd = L.add('Mean of the 7 hybrid daily ratios', '=(' + '+'.join(dly[d].loc for d in HYB) + ')/7', '0.0000')
    mbd = L.add('Mean of the 2 baseline daily ratios', '=(' + '+'.join(dly[d].loc for d in BASE) + ')/2', '0.0000')
    Gd = L.add('Gain from daily ratios = (mean hybrid / mean baseline - 1) x 100', f'=({mhd.loc}/{mbd.loc}-1)*100', '0.000', '%')
    lo = L.add('Lowest gain: lowest hybrid day / highest baseline day - 1, x 100', f'=(MIN({",".join(dly[d].loc for d in HYB)})/MAX({",".join(dly[d].loc for d in BASE)})-1)*100', '0.00', '%')
    hi = L.add('Highest gain: highest hybrid day / lowest baseline day - 1, x 100', f'=(MAX({",".join(dly[d].loc for d in HYB)})/MIN({",".join(dly[d].loc for d in BASE)})-1)*100', '0.00', '%')
    L.sec('Voc route')
    vB = L.add('Median Voc ratio, baseline', f'=MEDIAN(IF({CBs(S)},{S.r("rV")}))', '0.0000', arr=True)
    vH = L.add('Median Voc ratio, hybrid', f'=MEDIAN(IF({CHs(S)},{S.r("rV")}))', '0.0000', arr=True)
    vc = L.add('Change of the Voc ratio = (hybrid / baseline - 1) x 100', f'=({vH.loc}/{vB.loc}-1)*100', '0.000', '%')
    cl = L.add('Cooling implied, lower = change / upper Voc coefficient', f'={vc.loc}/{v2.loc}', '0.00', 'K')
    ch = L.add('Cooling implied, upper = change / lower Voc coefficient', f'={vc.loc}/{v1.loc}', '0.00', 'K')
    gl = L.add('Expected power gain from that cooling, lower = lower power coefficient x lower cooling', f'={b1.loc}*{cl.loc}', '0.00', '%')
    gh = L.add('Expected power gain from that cooling, upper = upper power coefficient x upper cooling', f'={b2.loc}*{ch.loc}', '0.00', '%')
    L.sec('Surface-temperature route')
    dF = L.add('Median front difference over all hybrid sweeps (TC3 - TC1)', f'=MEDIAN(IF({CHs(S)},{S.r("dF")}))', '0.0000', 'deg C', arr=True)
    el = L.add('Expected gain, lower = lower power coefficient x |difference|', f'={b1.loc}*ABS({dF.loc})', '0.00', '%')
    eh = L.add('Expected gain, upper = upper power coefficient x |difference|', f'={b2.loc}*ABS({dF.loc})', '0.00', '%')
    f9 = L.add('Median front difference, class 900-1200 mW (hybrid sweeps)', f'=MEDIAN(IF({P(CHs(S), pbs(S, 900))},{S.r("dF")}))', '0.0000', 'deg C', arr=True)
    f12 = L.add('Median front difference, class 1200-2000 mW (hybrid sweeps)', f'=MEDIAN(IF({P(CHs(S), pbs(S, 1200))},{S.r("dF")}))', '0.0000', 'deg C', arr=True)
    bl = L.add('Expected gain, brightest classes, lower = lower coefficient x |difference of the 900-1200 class|', f'={b1.loc}*ABS({f9.loc})', '0.00', '%')
    bh = L.add('Expected gain, brightest classes, upper = upper coefficient x |difference of the 1200-2000 class|', f'={b2.loc}*ABS({f12.loc})', '0.00', '%')
    L.sec('Part of the gain not explained by cooling')
    un = L.add('Observed gain minus the largest expected thermal gain (the upper value of the Voc route), in percentage points', f'={G.loc}-MAX({gh.loc},{eh.loc},{bh.loc})', '0.00', 'points')
    f1 = lambda x: f'TEXT({x.ref},"0.0")'
    ex = [None] * 9
    ex = [[None, f'="+"&{f1(G)}&"% (daily ratios: +"&{f1(Gd)}&"%, range "&TEXT({lo.ref},"0")&"–"&TEXT({hi.ref},"0")&"%)"'],
          [None, f'="+"&{f1(vc)}&"%"'],
          [None, f'={dF.ref}'],
          [None, f'="+"&{f1(el)}&" to +"&{f1(eh)}&"%"'],
          [None, f'={f1(f9)}&" to "&{f1(f12)}&" °C"'],
          [None, f'="+"&{f1(bl)}&" to +"&{f1(bh)}&"%"'],
          [None, f'={f1(cl)}&" to "&{f1(ch)}&" K"'],
          [None, f'="+"&{f1(gl)}&" to +"&{f1(gh)}&"%"'],
          [None, f'="about "&TEXT(ROUND({un.ref},0),"0")&" of the "&TEXT(ROUND({G.ref},0),"0")&" percentage points"']]
    return dict(exprs=ex, what='How much of the 38% gain the cooling of the hybrid panel can explain, estimated in three ways with literature coefficients (Section 3.7.7).',
                inputs=[IN_SW, IN_TM, 'Coefficients 0.35-0.45% per K (power) and 0.3-0.4% per K (Voc) from the literature, Section 3.7.7 (blue inputs).'],
                steps=['Observed gain G = median hybrid power ratio / median baseline power ratio - 1 (Table 4.14, all sweeps); also from the daily ratios (Table 4.10).',
                       'Observed change of the Voc ratio = median hybrid Voc ratio / median baseline Voc ratio - 1.',
                       'Surface route: expected gain = power coefficient x |front temperature difference|, with the median front difference of all hybrid sweeps (Table 4.8).',
                       'Brightest-class route: the same with the median front difference of the 900-1200 mW class (lower value) and of the 1200-2000 mW class (upper value) (Table 4.9).',
                       'Voc route: cooling = Voc change / Voc coefficient (0.4 to 0.3 % per K), then expected gain = power coefficient x cooling.',
                       'Not explained = observed gain - the largest expected thermal gain, in percentage points.'],
                example=[tx('Observed gain ', (G, '0.0'), ' %. Front difference ', (dF, '0.00'), ' deg C gives ', (el, '0.00'), ' to ', (eh, '0.00'), ' %. Voc change ', (vc, '0.00'), ' % implies ', (cl, '0.0'), ' to ', (ch, '0.0'), ' K of cooling, and ', (gl, '0.0'), ' to ', (gh, '0.0'), ' % gain.')],
                notes=['The expected gains are calculated from literature coefficients and measured values; they are not fitted values.',
                       'The Voc route is an upper estimate, since not all of a Voc change need be thermal.'],
                sheets=[SH_RES, SH_WK, SH_SWF, SH_TM, SH_CA], need={'sweeps_full', 'temps'})


# ================================================================== Table 4.17
def t4_17(c):
    L = c['L']; S = c['S']; rows = c['rows']; ex = []; first = None
    wins = {'H': [], 'B': []}; sums = {'H': ([], []), 'B': ([], [])}
    for r in rows[:-2]:
        d = code(r[0]); cs = f'{S.r("code")},"{d}"'; ty = 'H' if d[1:] in HYB else 'B'; L.sec(f'{r[0]} 2026')
        n = L.add('Number of sweeps', f'=COUNTIFS({cs})', '0')
        w = L.add('Window = (end of the last sweep - start of the first sweep) x 24', f'=(_xlfn.MAXIFS({S.r("t1")},{cs})-_xlfn.MINIFS({S.r("t0")},{cs}))*24', '0.00', 'h')
        s1 = L.add('Sum of PV1 Pmp', f'=SUMIFS({S.r("P1")},{cs})', '0.0', 'mW')
        e1 = L.add('PV1 energy = sum of Pmp x 0.25 h / 1000 (Equation 3.5)', f'={s1.loc}*0.25/1000', '0.000', 'Wh')
        s2 = L.add('Sum of PV2 Pmp', f'=SUMIFS({S.r("P2")},{cs})', '0.0', 'mW')
        e2 = L.add('PV2 energy = sum of Pmp x 0.25 h / 1000', f'={s2.loc}*0.25/1000', '0.000', 'Wh')
        rt = L.add('PV1/PV2 = PV1 energy / PV2 energy', f'={e1.loc}/{e2.loc}', '0.000')
        ex.append([None, None, f'={n.ref}', f'={w.ref}', f'={e1.ref}', f'={e2.ref}', f'={rt.ref}'])
        wins[ty].append(w); sums[ty][0].append(e1); sums[ty][1].append(e2)
        if first is None: first = (s1, n, e1, e2, rt)
    for ty, lab in (('H', 'Hybrid days, total'), ('B', 'Baseline days, total')):
        L.sec(lab)
        n = L.add('Number of sweeps', f'=COUNTIFS({S.r("typ")},"{ty}")', '0')
        w = L.add('Window = sum of the daily windows', '=' + '+'.join(x.loc for x in wins[ty]), '0.00', 'h')
        e1 = L.add('PV1 energy = sum of the daily energies', '=' + '+'.join(x.loc for x in sums[ty][0]), '0.000', 'Wh')
        e2 = L.add('PV2 energy = sum of the daily energies', '=' + '+'.join(x.loc for x in sums[ty][1]), '0.000', 'Wh')
        rt = L.add('PV1/PV2', f'={e1.loc}/{e2.loc}', '0.000')
        ex.append([None, None, f'={n.ref}', f'={w.ref}', f'={e1.ref}', f'={e2.ref}', f'={rt.ref}'])
    s1, n, e1, e2, rt = first
    return dict(exprs=ex, what='The energy that each panel would have produced if it had always worked at its maximum power point, estimated from the sweeps.',
                inputs=[IN_SW],
                steps=['One sweep was taken every 15 minutes, so the maximum power Pmp of a sweep is taken to represent the 0.25 h around it.',
                       'Energy of a day = (sum of the Pmp values of the day) x 0.25 h / 1000, in Wh (Equation 3.5).',
                       'Window = end of the last sweep minus start of the first sweep of the day, in hours.',
                       'PV1/PV2 = energy of PV1 / energy of PV2. Totals add the days (hybrid days, baseline days).'],
                example=[tx('12 Sep: sum of PV1 Pmp = ', (s1, '0.0'), ' mW over ', (n, '0'), ' sweeps; E = ', (s1, '0.0'), ' x 0.25 / 1000 = ', (e1, '0.00'), ' Wh (PV2 ', (e2, '0.00'), ' Wh, ratio ', (rt, '0.000'), ').')],
                notes=['This overstates the energy of a real installation (it assumes perfect maximum power point tracking); it is used to compare PV1 with PV2 only.'],
                sheets=[SH_RES, SH_WK, SH_SW])


# ================================================================== Table 4.18
def t4_18(c):
    L = c['L']; G = c['G']; rows = c['rows']; ex = []; first = None
    for r in rows:
        if r[0].startswith('All'):
            def sel(fn, col): return f'={fn}({G.r(col)})'
            cond = None; ncell = L.add('Number of TEG sweeps', f'=COUNTA({G.r("sweep")})', '0'); L.sec('All TEG sweeps')
        else:
            d = code(r[0]); L.sec(f'{r[0]} 2026'); cond = f'({G.r("code")}="{d}")'
            ncell = L.add('Number of TEG sweeps', f'=COUNTIFS({G.r("code")},"{d}")', '0')
        def stat(fn, col, desc, fmt, unit):
            if cond is None: return L.add(desc, f'={fn}({G.r(col)})', fmt, unit)
            return L.add(desc, f'={fn}(IF({cond},{G.r(col)}))', fmt, unit, arr=True)
        if cond is None:
            sv = L.add('Voc: sum', f'=SUM({G.r("Voc")})', '0.0', 'mV'); vm = L.add('Voc mean = sum / number', f'={sv.loc}/{ncell.loc}', '0.0', 'mV')
            sp = L.add('Pmax: sum', f'=SUM({G.r("Pmax")})', '0.0', 'uW'); pm = L.add('Pmax mean = sum / number', f'={sp.loc}/{ncell.loc}', '0.0', 'uW')
            sr = L.add('Rin: sum', f'=SUM({G.r("Rin")})', '0.0', 'ohm'); rm = L.add('Rin mean = sum / number', f'={sr.loc}/{ncell.loc}', '0.0', 'ohm')
        else:
            sv = L.add('Voc: sum', f'=SUMIFS({G.r("Voc")},{G.r("code")},"{d}")', '0.0', 'mV'); vm = L.add('Voc mean = sum / number', f'={sv.loc}/{ncell.loc}', '0.0', 'mV')
            sp = L.add('Pmax: sum', f'=SUMIFS({G.r("Pmax")},{G.r("code")},"{d}")', '0.0', 'uW'); pm = L.add('Pmax mean = sum / number', f'={sp.loc}/{ncell.loc}', '0.0', 'uW')
            sr = L.add('Rin: sum', f'=SUMIFS({G.r("Rin")},{G.r("code")},"{d}")', '0.0', 'ohm'); rm = L.add('Rin mean = sum / number', f'={sr.loc}/{ncell.loc}', '0.0', 'ohm')
        vmin = stat('MIN', 'Voc', 'Voc smallest', '0.0', 'mV'); vmax = stat('MAX', 'Voc', 'Voc largest', '0.0', 'mV')
        pmin = stat('MIN', 'Pmax', 'Pmax smallest', '0.0', 'uW'); pmax = stat('MAX', 'Pmax', 'Pmax largest', '0.0', 'uW')
        pmed = stat('MEDIAN', 'Pmax', 'Pmax median', '0.0', 'uW')
        shm = stat('MEDIAN', 'share', 'Median of (Pmax / 1000 / PV1 Pmp x 100) = TEG share of the PV1 power', '0.0000', '%')
        ex.append([None, f'={ncell.ref}', f'={vm.ref}', f'={vmin.ref}', f'={vmax.ref}', f'={pm.ref}', f'={pmin.ref}', f'={pmax.ref}', f'={pmed.ref}', f'={rm.ref}', f'={shm.ref}'])
        if first is None: first = (ncell, sv, vm, sp, pm)
    n, sv, vm, sp, pm = first
    return dict(exprs=ex, what='The results of the TEG sweeps on the five days with a working TEG: open-circuit voltage, maximum power, internal resistance and the share of the power of PV1.',
                inputs=[IN_TEG, IN_SW.split(' The two')[0], 'PV1 power of the same sweep is read from the sheet Sweeps.'],
                steps=['The TEG is fitted by the same sweep method (Section 3.4.4). Voc (mV), maximum power Pmax (uW) and internal resistance Rin (ohm) of each sweep are copied from summary_TEG_MMDD.xlsx.',
                       'Mean = (sum of the values) / (number of sweeps). Smallest, largest and median as in the table.',
                       'Share of the PV1 power of one sweep = (Pmax in uW / 1000) / (Pmp of PV1 in mW of the same sweep) x 100; the table gives the median of these shares.'],
                example=[tx('12 Sep: ', (n, '0'), ' sweeps; mean Voc = ', (sv, '0.0'), ' / ', (n, '0'), ' = ', (vm, '0.0'), ' mV; mean Pmax = ', (sp, '0.0'), ' / ', (n, '0'), ' = ', (pm, '0.0'), ' uW.')],
                notes=['Pmax is in microwatt and the PV power in milliwatt, hence the division by 1000.'],
                sheets=[SH_RES, SH_WK, SH_TG, SH_SW, SH_TM, SH_CA], need={'teg', 'sweeps'})


# ================================================================== Table 4.19
def t4_19(c):
    L = c['L']; G = c['G']; rows = c['rows']; ex = []
    cm = ['d38', 'd58', 'd68', 'd78', 'd57', 'd37', 'd67']; first = None
    for r, col in zip(rows, cm):
        L.sec(r[0])
        n = L.add('Number of sweeps n', f'=COUNT({G.r(col)})', '0')
        rng = L.add('Range of the difference: smallest to largest (°C)', f'=TEXT(MIN({G.r(col)}),"0.0")&" to "&TEXT(MAX({G.r(col)}),"0.0")', '@')
        mx = L.add('Mean of x (the temperature difference)', f'=SUM({G.r(col)})/{n.loc}', '0.0000', 'deg C')
        my = L.add('Mean of y (TEG Voc)', f'=SUM({G.r("Voc")})/{n.loc}', '0.0000', 'mV')
        sxx = L.add('Sxx = sum of (x - mean x)^2', f'=SUMPRODUCT(({G.r(col)}-{mx.loc})^2)', '0.0000')
        syy = L.add('Syy = sum of (y - mean y)^2', f'=SUMPRODUCT(({G.r("Voc")}-{my.loc})^2)', '0.0000')
        sxy = L.add('Sxy = sum of (x - mean x)(y - mean y)', f'=SUMPRODUCT(({G.r(col)}-{mx.loc})*({G.r("Voc")}-{my.loc}))', '0.0000')
        sl = L.add('Slope = Sxy / Sxx (least-squares line)', f'={sxy.loc}/{sxx.loc}', '0.000', 'mV per K')
        rr = L.add('Correlation coefficient r = Sxy / square root of (Sxx x Syy)', f'={sxy.loc}/SQRT({sxx.loc}*{syy.loc})', '0.000')
        ex.append([None, f'={rng.ref}', f'={sl.ref}', f'={rr.ref}'])
        if first is None: first = (n, mx, my, sxx, sxy, sl, rr)
    n, mx, my, sxx, sxy, sl, rr = first
    return dict(exprs=ex, what='Whether the open-circuit voltage of the TEG follows the temperature differences measured by the thermocouples: the range of each difference, the slope of a straight line fitted through the 82 sweeps, and the correlation coefficient r.',
                inputs=[IN_TEG, IN_TM],
                steps=['For each TEG sweep, the thermocouple temperatures at the middle of the sweep are found by linear interpolation (Section 3.7.1); the differences (for example TC3 - TC8) are formed in the sheet TEG.',
                       'x = the temperature difference, y = the TEG Voc (mV). Find the means of x and y.',
                       'Sxx = sum of (x - mean x)^2, Syy = sum of (y - mean y)^2, Sxy = sum of (x - mean x)(y - mean y).',
                       'Slope = Sxy / Sxx (mV per kelvin); correlation coefficient r = Sxy / square root of (Sxx x Syy). These agree with the Excel functions SLOPE and CORREL.'],
                example=[tx('First row: ', (n, '0'), ' sweeps; slope = Sxy / Sxx = ', (sxy, '0.0'), ' / ', (sxx, '0.0'), ' = ', (sl, '0.00'), ' mV per K; r = ', (rr, '0.00'), '.')],
                notes=['The TEG face temperatures were not measured, so the differences are those of the surrounding thermocouples (Section 4.8).'],
                sheets=[SH_RES, SH_WK, SH_TG, SH_TM, SH_CA], need={'teg', 'sweeps'})


# ================================================================== Table 4.4 (arithmetic only; the readings are inputs)
def t4_4(c):
    L = c['L']; rows = c['rows']; ex = []; first = None
    def num(x):
        try: return float(x)
        except ValueError: return x
    for r in rows:
        L.sec(r[0])
        p = L.input('Paraffin (g), weighed', num(r[1]), '0', 'g'); co = L.input('Coconut oil (g), weighed', num(r[2]), '0', 'g')
        a = L.input('Cooling curve, trial A: transition temperature read from the curve (NL = not located)', num(r[4]), '0.0', 'deg C')
        b = L.input('Cooling curve, trial B: transition temperature read from the curve (NL = not located)', num(r[5]), '0.0', 'deg C')
        m0 = L.input('Melting starts, read on the melting-point apparatus', num(r[7]), '0', 'deg C')
        m1 = L.input('Complete melting, read on the melting-point apparatus', num(r[8]), '0', 'deg C')
        ratio = L.add('Paraffin : coconut oil = paraffin share and coconut-oil share of the total mass, in per cent',
                      f'=TEXT({p.loc}/({p.loc}+{co.loc})*100,"0")&":"&TEXT({co.loc}/({p.loc}+{co.loc})*100,"0")', '@')
        mean = L.add('Cooling curve mean = (A + B) / 2; if only one trial was located, that trial alone; if none, NL',
                     f'=IF(AND(ISNUMBER({a.loc}),ISNUMBER({b.loc})),({a.loc}+{b.loc})/2,IF(ISNUMBER({a.loc}),{a.loc},IF(ISNUMBER({b.loc}),{b.loc},"NL")))', '0.0', 'deg C')
        rng = L.add('Melting range = complete melting - melting start', f'={m1.loc}-{m0.loc}', '0', 'deg C')
        ex.append([None, None, None, f'={ratio.ref}', None, None, f'={mean.ref}', None, None, f'={rng.ref}'])
        if first is None: first = (a, b, mean)
        if r[0] == 'PCM7 (hybrid panel)': pcm7 = (a, b, mean, m0, m1, rng)
    a, b, mean, m0, m1, rng = pcm7
    return dict(exprs=ex, what=('The nine paraffin-coconut oil mixtures. The mass ratio, the mean of the two cooling-curve trials and the melting range are calculated; '
                                'the weighed masses, the transition temperatures read from the cooling curves and the melting start and end read on the melting-point apparatus are measured inputs.'),
                inputs=['Weighed masses (Section 3.2) and the two temperatures read on the melting-point apparatus: entered by hand (blue cells on Working).',
                        'Transition temperature of each trial: read from the cooling-curve graph (see "How the cooling curves are plotted" below). Files: PCM Preparation / Cooling_curve_data_1A ... 9B.xlsx.'],
                steps=['Ratio = paraffin / (paraffin + coconut oil) x 100 : coconut oil / (paraffin + coconut oil) x 100. Each sample is 20 g, so 8 g : 12 g is 40:60.',
                       'Cooling-curve mean = (trial A + trial B) / 2. Where no transition could be located in one trial (NL), the other trial is used alone (PCM5); where neither could be located the result is NL (PCM9).',
                       'Melting range = complete melting - melting start.'],
                example=[tx('PCM7: (', (a, '0.0'), ' + ', (b, '0.0'), ') / 2 = ', (mean, '0.00'), ' deg C (printed 52.7); melting range ', (m1, '0'), ' - ', (m0, '0'), ' = ', (rng, '0'), ' deg C.')],
                notes=['How the cooling curves are plotted (no calculation file): each file Cooling_curve_data_nX.xlsx has one row per reading, about every 2 s. '
                       'The x axis is the elapsed time (column New_Elapsed restarts at 00:00:00 on the first row used; Elapsed is the logger clock) and the y axis is the calibrated '
                       'thermocouple temperature (column Callibrated, the raw reading minus the ice-point offset). Trials A and B of one mixture are drawn on the same axes. '
                       'The transition temperature is then read by eye as the short plateau or deflection point on the falling curve.',
                       'The transition temperatures and the melting start and end are readings, not calculated values.'],
                sheets=[SH_RES, SH_WK])


TABLES = {
    '3.5': ('Resolution_of_measurement_channels', t3_5, set()),
    '4.1': ('Data_set_inventory', t4_1, {'sweeps', 'temps', 'teg'}),
    '4.2': ('Ambient_and_light_conditions', t4_2, {'sweeps', 'temps', 'calib'}),
    '4.3': ('Quality_and_uncertainty', t4_3, {'sweeps'}),
    '4.4': ('PCM_mixtures_and_transition_temperatures', t4_4, set()),
    '4.5': ('PCM_temperature', t4_5, {'temps', 'calib'}),
    '4.6': ('PCM_melting_range_time', t4_6, {'sweeps_full', 'temps', 'calib'}),
    '4.7': ('Baseline_power_ratio', t4_7, {'sweeps'}),
    '4.8': ('Daily_panel_temperatures', t4_8, {'sweeps_full', 'temps', 'calib'}),
    '4.9': ('Temperature_difference_by_light_level', t4_9, {'sweeps_full', 'temps', 'calib'}),
    '4.10': ('Maximum_power_point_by_day', t4_10, {'sweeps'}),
    '4.11': ('Voc_Isc_FF_by_day', t4_11, {'sweeps'}),
    '4.12': ('Parameters_of_all_sweeps', t4_12, {'sweeps'}),
    '4.13': ('Paired_ratios_baseline_vs_hybrid', t4_13, {'sweeps'}),
    '4.14': ('Gain_by_irradiance_level', t4_14, {'sweeps'}),
    '4.15': ('Fill_factor_stability_check', t4_15, {'sweeps'}),
    '4.16': ('Thermal_contribution_to_gain', t4_16, {'sweeps_full', 'temps', 'calib'}),
    '4.17': ('Sampled_energy', t4_17, {'sweeps'}),
    '4.18': ('TEG_results_by_day', t4_18, {'teg', 'sweeps', 'temps', 'calib'}),
    '4.19': ('TEG_Voc_vs_temperature', t4_19, {'teg', 'sweeps', 'temps', 'calib'}),
}
