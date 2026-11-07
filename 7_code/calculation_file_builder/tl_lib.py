"""
tl_lib.py - shared parts for the table calculation files.
Reads the ROW-LIMITED files (analysis set) and writes input sheets, the Working ledger,
the Result/Check sheet and the Steps sheet of each calculation workbook.
"""
import re, os, glob
import pandas as pd, numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter as CL
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.formatting.rule import CellIsRule

FINAL = None      # folder with the row-limited files (set by the runner)
REPO = None       # folder "Data Repository"

DAYS = ['0912', '0913', '0914', '0916', '0917', '0918', '0919', '0928', '1001']
LABEL = {'0912': '12 Sep', '0913': '13 Sep', '0914': '14 Sep', '0916': '16 Sep', '0917': '17 Sep',
         '0918': '18 Sep', '0919': '19 Sep', '0928': '28 Sep', '1001': '1 Oct'}
TEGDAYS = ['0912', '0913', '0914', '0918', '0919']
HYB, BASE = DAYS[:7], DAYS[7:]
LASTROW = {'0912': (31, 28), '0913': (30, 28), '0914': (24, 2), '0916': (23, 'TEG faulty'), '0917': (28, 'TEG faulty'),
           '0918': (26, 12), '0919': (17, 17), '0928': (30, 'Not connected'), '1001': (30, 'Not connected')}
TCS = ['TC1', 'TC2', 'TC3', 'TC5', 'TC6', 'TC7', 'TC8']

BLUE = Font(name='Arial', size=10, color='0000FF'); BLK = Font(name='Arial', size=10)
BOLD = Font(name='Arial', size=10, bold=True)
HDRF = PatternFill('solid', fgColor='E7E6E6'); HF = Font(name='Arial', size=10, bold=True)
YEL = PatternFill(fill_type=None); GREY = PatternFill(fill_type=None)
SECF = PatternFill(fill_type=None)


def code(label):
    """'12 Sep' -> 'D0912'"""
    l = str(label).strip()
    for k, v in LABEL.items():
        if v == l or (v == '1 Oct' and l == '01 Oct'):
            return 'D' + k
    raise KeyError(label)


class A:  # array formula marker
    def __init__(self, f): self.f = f


def setf(ws, addr, f):
    if isinstance(f, A):
        ws[addr] = ArrayFormula(addr, '=' + f.f)
    else:
        ws[addr] = f


# ------------------------------------------------------------------ data
def load_data():
    sw, tm, tg = [], [], []
    for d in DAYS:
        p1 = pd.read_excel(f"{FINAL}/sweep_summaries_limited/summary_PV1_{d}.xlsx")
        p2 = pd.read_excel(f"{FINAL}/sweep_summaries_limited/summary_PV2_{d}.xlsx")
        p1['row'] = np.arange(len(p1)) + 2; p2['row'] = np.arange(len(p2)) + 2
        p1 = p1[pd.to_numeric(p1.sweep, errors='coerce').notna()]; p2 = p2[pd.to_numeric(p2.sweep, errors='coerce').notna()]
        p1 = p1[p1.status == 'ok']; p2 = p2[p2.status == 'ok']
        m = p1.merge(p2, on='sweep', suffixes=('1', '2'))
        assert len(m) == len(p1) == len(p2), d
        m['day'] = d
        sw.append(m)
        v = pd.read_excel(f"{FINAL}/one_minute_files_limited/V{d}_Callibrated.xlsx")
        v = v[pd.to_datetime(v['Time'], errors='coerce').notna()].copy()
        v['row'] = np.arange(len(v)) + 2; v['day'] = d
        tm.append(v)
        if d in TEGDAYS:
            g = pd.read_excel(f"{FINAL}/sweep_summaries_limited/summary_TEG_{d}.xlsx")
            g['row'] = np.arange(len(g)) + 2
            g = g[pd.to_numeric(g.sweep, errors='coerce').notna()]; g = g[g.status == 'ok']; g['day'] = d
            tg.append(g)
    return pd.concat(sw, ignore_index=True), pd.concat(tm, ignore_index=True), pd.concat(tg, ignore_index=True)


def ts(date, t):
    return pd.Timestamp(str(date)[:10] + ' ' + str(t))


# ------------------------------------------------------------------ sheet descriptions
class Sh:
    def __init__(self, name, cols, n):
        self.name = name; self.cols = [c for c, _ in cols]; self.hdr = [h for _, h in cols]; self.n = n
        self.L = {c: CL(i + 1) for i, c in enumerate(self.cols)}

    def r(self, c): return f"{self.name}!${self.L[c]}$2:${self.L[c]}${self.n + 1}"
    def a(self, c, i): return f"{self.L[c]}{i}"


def sweeps_def(n, full):
    cols = [('day', 'Day'), ('code', 'Day code'), ('typ', 'Type (H hybrid, B bare)'), ('sweep', 'Sweep no.'),
            ('t0', 'Sweep start'), ('t1', 'Sweep end'), ('mid', 'Sweep midpoint (start + (end - start)/2)'),
            ('P1', 'PV1 Pmp (mW)'), ('P2', 'PV2 Pmp (mW)'), ('I1', 'PV1 Isc (mA)'), ('I2', 'PV2 Isc (mA)'),
            ('V1', 'PV1 Voc (V)'), ('V2', 'PV2 Voc (V)'), ('F1', 'PV1 FF'), ('F2', 'PV2 FF'), ('bpw', 'BPW34 (V)'),
            ('P1e', 'PV1 Pmp uncertainty (mW)'), ('P2e', 'PV2 Pmp uncertainty (mW)'), ('V1e', 'PV1 Voc uncertainty (V)'),
            ('V2e', 'PV2 Voc uncertainty (V)'), ('I1e', 'PV1 Isc uncertainty (mA)'), ('I2e', 'PV2 Isc uncertainty (mA)'),
            ('src1', 'Row in summary_PV1 file'), ('src2', 'Row in summary_PV2 file'),
            ('rP', 'Ratio Pmp PV1/PV2'), ('rI', 'Ratio Isc PV1/PV2'), ('rV', 'Ratio Voc PV1/PV2'), ('rF', 'Ratio FF PV1/PV2'),
            ('pbin', 'PV2 power class (lower bound, mW)'),
            ('rV1', 'Rel. unc. Voc PV1'), ('rI1', 'Rel. unc. Isc PV1'), ('rP1', 'Rel. unc. Pmp PV1'),
            ('rV2', 'Rel. unc. Voc PV2'), ('rI2', 'Rel. unc. Isc PV2'), ('rP2', 'Rel. unc. Pmp PV2')]
    if full:
        cols += [('idx', 'Row of the last one-minute record before the sweep (Temps sheet)'),
                 ('TC1', 'TC1 PV2 front (C)'), ('TC2', 'TC2 PV2 rear (C)'), ('TC3', 'TC3 PV1 front (C)'), ('TC5', 'TC5 PV1 rear (C)'),
                 ('TC6', 'TC6 PCM (C)'), ('TC7', 'TC7 under TEG (C)'), ('TC8', 'TC8 ambient (C)'),
                 ('dF', 'Front difference PV1 - PV2 = TC3 - TC1 (C)'), ('dR', 'Rear difference PV1 - PV2 = TC5 - TC2 (C)')]
    return Sh('Sweeps', cols, n)


def temps_def(n):
    return Sh('Temps', [('day', 'Day'), ('code', 'Day code'), ('time', 'Date and time'), ('TC1', 'TC1 PV2 front (C)'),
                        ('TC2', 'TC2 PV2 rear (C)'), ('TC3', 'TC3 PV1 front (C)'), ('TC5', 'TC5 PV1 rear (C)'),
                        ('TC6', 'TC6 PCM (C)'), ('TC7', 'TC7 under TEG (C)'), ('TC8', 'TC8 ambient (C)'),
                        ('d65', 'TC6 - TC5 (C)'), ('file', 'Source file (row-limited copy)'), ('row', 'Row in source file')], n)


def teg_def(n):
    return Sh('TEG', [('day', 'Day'), ('code', 'Day code'), ('sweep', 'Sweep no.'), ('t0', 'Sweep start'), ('t1', 'Sweep end'),
                      ('mid', 'Sweep midpoint'), ('Voc', 'TEG Voc (mV)'), ('Isc', 'TEG Isc (mA)'), ('Pmax', 'TEG Pmax (uW)'),
                      ('Rin', 'TEG Rin (ohm)'), ('R2', 'Fit R2'), ('src', 'Row in summary_TEG file'),
                      ('P1', 'PV1 Pmp of the same sweep (mW)'), ('share', 'TEG share of PV1 power (%) = Pmax/1000/PV1 Pmp x 100'),
                      ('idx', 'Row of the last one-minute record before the sweep (Temps sheet)'),
                      ('TC3', 'TC3 (C)'), ('TC5', 'TC5 (C)'), ('TC6', 'TC6 (C)'), ('TC7', 'TC7 (C)'), ('TC8', 'TC8 (C)'),
                      ('d38', 'TC3 - TC8'), ('d58', 'TC5 - TC8'), ('d68', 'TC6 - TC8'), ('d78', 'TC7 - TC8'),
                      ('d67', 'TC6 - TC7'), ('d57', 'TC5 - TC7'), ('d37', 'TC3 - TC7')], n)


def hdr_row(ws, names, row=1, h=54):
    for j, n in enumerate(names, 1):
        c = ws.cell(row=row, column=j, value=n); c.font = HF; c.fill = HDRF
        c.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')
    ws.row_dimensions[row].height = h


def interp(Tm, col, idxcell, midcell):
    """linear interpolation of Temps column `col` to time midcell, between record idx and idx+1"""
    tc = Tm.r(col); tt = Tm.r('time')
    return (f"=INDEX({tc},{idxcell})+(INDEX({tc},{idxcell}+1)-INDEX({tc},{idxcell}))"
            f"*MIN(1,MAX(0,({midcell}-INDEX({tt},{idxcell}))/(INDEX({tt},{idxcell}+1)-INDEX({tt},{idxcell}))))")


def idx_formula(Tm, midcell, codecell):
    m0 = f"IFERROR(MATCH({midcell},{Tm.r('time')},1),1)"
    return f"={m0}+IF(INDEX({Tm.r('code')},{m0})<>{codecell},1,0)"


def add_inputs(wb, Wd, Td, Gd, need):
    """need: set of {'sweeps','sweeps_full','temps','teg','calib','rowlimits'}"""
    out = {}
    nS, nT, nG = len(Wd), len(Td), len(Gd)
    Tm = temps_def(nT)
    full = 'sweeps_full' in need
    S = sweeps_def(nS, full)
    Gs = teg_def(nG)
    if 'sweeps' in need or full:
        ws = wb.create_sheet('Sweeps'); hdr_row(ws, S.hdr)
        for i, (_, r) in enumerate(Wd.iterrows(), 2):
            t0 = ts(r.date1, r.start_time1); t1 = ts(r.date1, r.end_time1)
            vals = {'day': LABEL[r.day], 'code': 'D' + r.day, 'typ': 'H' if r.day in HYB else 'B', 'sweep': int(r.sweep),
                    't0': t0.to_pydatetime(), 't1': t1.to_pydatetime(),
                    'P1': r.Pmp1, 'P2': r.Pmp2, 'I1': r.Isc1, 'I2': r.Isc2, 'V1': r.Voc1, 'V2': r.Voc2, 'F1': r.FF1, 'F2': r.FF2,
                    'bpw': r.bpw_avg_fit_V1, 'P1e': r.Pmp_err1, 'P2e': r.Pmp_err2, 'V1e': r.Voc_err1, 'V2e': r.Voc_err2,
                    'I1e': r.Isc_err1, 'I2e': r.Isc_err2, 'src1': int(r.row1), 'src2': int(r.row2)}
            for k, v in vals.items():
                c = ws[S.a(k, i)]; c.value = v; c.font = BLUE
            g = lambda n: S.a(n, i)
            ws[g('mid')] = f"={g('t0')}+({g('t1')}-{g('t0')})/2"
            ws[g('rP')] = f"={g('P1')}/{g('P2')}"; ws[g('rI')] = f"={g('I1')}/{g('I2')}"
            ws[g('rV')] = f"={g('V1')}/{g('V2')}"; ws[g('rF')] = f"={g('F1')}/{g('F2')}"
            ws[g('pbin')] = f"=IF({g('P2')}<300,0,IF({g('P2')}<600,300,IF({g('P2')}<900,600,IF({g('P2')}<1200,900,1200))))"
            ws[g('rV1')] = f"={g('V1e')}/{g('V1')}"; ws[g('rI1')] = f"={g('I1e')}/{g('I1')}"; ws[g('rP1')] = f"={g('P1e')}/{g('P1')}"
            ws[g('rV2')] = f"={g('V2e')}/{g('V2')}"; ws[g('rI2')] = f"={g('I2e')}/{g('I2')}"; ws[g('rP2')] = f"={g('P2e')}/{g('P2')}"
            for n in ('t0', 't1', 'mid'): ws[g(n)].number_format = 'dd mmm hh:mm:ss'
            if full:
                ws[g('idx')] = idx_formula(Tm, g('mid'), g('code'))
                for k in TCS:
                    ws[g(k)] = interp(Tm, k, g('idx'), g('mid'))
                ws[g('dF')] = f"={g('TC3')}-{g('TC1')}"
                ws[g('dR')] = (f'=IF(AND(INDEX({Tm.r("TC2")},{g("idx")})>15,INDEX({Tm.r("TC2")},{g("idx")}+1)>15),'
                               f'{g("TC5")}-{g("TC2")},"n/a (TC2 fault)")')
        ws.freeze_panes = 'E2'
        for j in range(1, len(S.hdr) + 1): ws.column_dimensions[CL(j)].width = 13
    if 'temps' in need or full or 'teg' in need:
        ws = wb.create_sheet('Temps'); hdr_row(ws, Tm.hdr)
        for i, (_, r) in enumerate(Td.iterrows(), 2):
            ws[Tm.a('day', i)] = LABEL[r.day]; ws[Tm.a('code', i)] = 'D' + r.day
            ws[Tm.a('time', i)] = pd.to_datetime(r['Time']).to_pydatetime(); ws[Tm.a('time', i)].number_format = 'dd mmm hh:mm:ss'
            for k in TCS:
                v = r[f'{k}_Callibrated']
                ws[Tm.a(k, i)] = None if pd.isna(v) else float(v)
            for k in ['day', 'code', 'time'] + TCS: ws[Tm.a(k, i)].font = BLUE
            ws[Tm.a('d65', i)] = f"={Tm.a('TC6', i)}-{Tm.a('TC5', i)}"
            ws[Tm.a('file', i)] = f"V{r.day}_Callibrated.xlsx (one_minute_files_limited)"; ws[Tm.a('row', i)] = int(r.row)
        ws.freeze_panes = 'D2'
        for j in range(1, len(Tm.hdr) + 1): ws.column_dimensions[CL(j)].width = 15
        ws.column_dimensions[Tm.L['file']].width = 44
    if 'teg' in need:
        ws = wb.create_sheet('TEG'); hdr_row(ws, Gs.hdr)
        Sx = sweeps_def(nS, False)
        for i, (_, r) in enumerate(Gd.iterrows(), 2):
            t0 = ts(r.date, r.start_time); t1 = ts(r.date, r.end_time)
            vals = {'day': LABEL[r.day], 'code': 'D' + r.day, 'sweep': int(r.sweep), 't0': t0.to_pydatetime(), 't1': t1.to_pydatetime(),
                    'Voc': r.Voc, 'Isc': r.Isc, 'Pmax': r.Pmp, 'Rin': r.Rin_ohm, 'R2': r.R2, 'src': int(r.row)}
            for k, v in vals.items():
                c = ws[Gs.a(k, i)]; c.value = v; c.font = BLUE
            g = lambda n: Gs.a(n, i)
            ws[g('mid')] = f"={g('t0')}+({g('t1')}-{g('t0')})/2"
            for n in ('t0', 't1', 'mid'): ws[g(n)].number_format = 'dd mmm hh:mm:ss'
            ws[g('P1')] = f"=SUMIFS({Sx.r('P1')},{Sx.r('code')},{g('code')},{Sx.r('sweep')},{g('sweep')})"
            ws[g('share')] = f"={g('Pmax')}/1000/{g('P1')}*100"
            ws[g('idx')] = idx_formula(Tm, g('mid'), g('code'))
            for k in ('TC3', 'TC5', 'TC6', 'TC7', 'TC8'):
                ws[g(k)] = interp(Tm, k, g('idx'), g('mid'))
            for nm, (a, b) in {'d38': ('TC3', 'TC8'), 'd58': ('TC5', 'TC8'), 'd68': ('TC6', 'TC8'), 'd78': ('TC7', 'TC8'),
                               'd67': ('TC6', 'TC7'), 'd57': ('TC5', 'TC7'), 'd37': ('TC3', 'TC7')}.items():
                ws[g(nm)] = f"={g(a)}-{g(b)}"
        ws.freeze_panes = 'G2'
        for j in range(1, len(Gs.hdr) + 1): ws.column_dimensions[CL(j)].width = 13
    return S, Tm, Gs


def add_calibration(wb):
    c = pd.read_excel(f"{REPO}/Outdoor_Campain_Data/Thermocouple_Callibration.xlsx", header=None)
    ws = wb.create_sheet('Calibration')
    ws['A1'] = 'Ice-point calibration of the eight thermocouples (file Thermocouple_Callibration.xlsx)'; ws['A1'].font = Font(name='Arial', size=12, bold=True)
    ws['A2'] = ('All eight tips were held in melting ice. offset = (average of the readings) - (reference thermometer reading). '
                'The calibrated temperature is the raw reading minus this offset (done in the columns TCn_Callibrated of the V files).')
    ws['A2'].font = Font(name='Arial', size=9, italic=True)
    hdr_row(ws, ['Time'] + [f'TC{i}(C)' for i in range(1, 9)], row=4, h=24)
    reads = c.iloc[1:100, :9]
    r0 = 5
    for k, (_, r) in enumerate(reads.iterrows()):
        ws.cell(row=r0 + k, column=1, value=str(r[0])).font = BLUE
        for j in range(1, 9):
            ws.cell(row=r0 + k, column=1 + j, value=float(r[j])).font = BLUE
    last = r0 + len(reads) - 1
    ra = last + 2
    labels = ['Number of readings n', 'Average of the readings (sum / n)', 'Reference thermometer in ice (deg C)', 'Offset = average - reference',
              'Offset printed in the calibration file', 'Check']
    for i, lb in enumerate(labels): ws.cell(row=ra + i, column=1, value=lb).font = BOLD
    ws.cell(row=ra + 2, column=2, value=float(c.iloc[0, 11])).font = BLUE
    for j in range(1, 9):
        col = CL(1 + j)
        ws[f'{col}{ra}'] = f'=COUNT({col}{r0}:{col}{last})'
        ws[f'{col}{ra + 1}'] = f'=SUM({col}{r0}:{col}{last})/{col}{ra}'
        if j > 1: ws[f'{col}{ra + 2}'] = f'=$B${ra + 2}'
        ws[f'{col}{ra + 3}'] = f'={col}{ra + 1}-{col}{ra + 2}' if j != 4 else 'not used'
        pv = c.iloc[101, j]
        ws[f'{col}{ra + 4}'] = None if pd.isna(pv) else float(pv); ws[f'{col}{ra + 4}'].font = BLUE
        ws[f'{col}{ra + 5}'] = (f'=IF(ABS(ROUND({col}{ra + 3},2)-{col}{ra + 4})<0.0000001,"OK","DIFF")' if not pd.isna(pv) else 'TC4 not calibrated')
        ws[f'{col}{ra + 3}'].fill = YEL
    ws.column_dimensions['A'].width = 40
    for j in range(2, 10): ws.column_dimensions[CL(j)].width = 11
    return ra + 5


# ------------------------------------------------------------------ Working ledger
class Ref:
    def __init__(self, sheet, row): self.loc = f"$C${row}"; self.ref = f"{sheet}!$C${row}"; self.row = row


class Ledger:
    def __init__(self, ws):
        self.ws = ws; self.r = 5; self.k = 0
        ws['A1'] = 'Working: every step of the calculation, in order'; ws['A1'].font = Font(name='Arial', size=12, bold=True)
        ws['A2'] = ('Values in black are formulas and values in blue are typed inputs. Each line says in words what is calculated; the formula is in the cell. '
                    'The Result sheet takes its values from here.')
        ws['A2'].font = Font(name='Arial', size=9, italic=True)
        for j, h in enumerate(['No.', 'What is calculated', 'Value', 'Unit'], 1):
            c = ws.cell(row=4, column=j, value=h); c.font = HF; c.fill = HDRF
        ws.column_dimensions['A'].width = 7; ws.column_dimensions['B'].width = 98
        ws.column_dimensions['C'].width = 16; ws.column_dimensions['D'].width = 10
        ws.freeze_panes = 'A5'

    def sec(self, text):
        for j in range(1, 5): self.ws.cell(row=self.r, column=j).fill = SECF
        self.ws.cell(row=self.r, column=1, value=text).font = BOLD
        self.r += 1

    def add(self, desc, formula, fmt='0.00', unit='', arr=False):
        self.k += 1
        self.ws.cell(row=self.r, column=1, value=self.k).font = BLK
        c = self.ws.cell(row=self.r, column=2, value=desc); c.font = BLK; c.alignment = Alignment(wrap_text=True, vertical='top')
        setf(self.ws, f'C{self.r}', A(formula[1:]) if arr and isinstance(formula, str) and formula.startswith('=') else formula)
        v = self.ws[f'C{self.r}']; v.font = BLK; v.fill = YEL; v.number_format = fmt
        self.ws.cell(row=self.r, column=4, value=unit).font = BLK
        ref = Ref('Working', self.r); self.r += 1
        return ref

    def input(self, desc, value, fmt='0.00', unit=''):
        self.k += 1
        self.ws.cell(row=self.r, column=1, value=self.k).font = BLK
        c = self.ws.cell(row=self.r, column=2, value=desc); c.font = BLK; c.alignment = Alignment(wrap_text=True, vertical='top')
        v = self.ws.cell(row=self.r, column=3, value=value); v.font = BLUE; v.number_format = fmt
        self.ws.cell(row=self.r, column=4, value=unit).font = BLK
        ref = Ref('Working', self.r); self.r += 1
        return ref


# ------------------------------------------------------------------ Result sheet
def isnum(s): return re.match(r'^[+\-−]?\d+(\.\d+)?(\s+[A-Za-zµΩ%°/]+)?$', s) is not None


def parse_num(s):
    m = re.match(r'^([+\-−]?)(\d+)(\.(\d+))?', s); d = len(m.group(4)) if m.group(4) else 0
    v = float(m.group(2) + (m.group(3) or ''))
    if m.group(1) in ('-', '−'): v = -v
    return v, d


def result_sheet(wb, num, title, head, rows, exprs, checks, note=None):
    ws = wb.create_sheet('Result')
    ws['A1'] = f'Table {num}: {title}'; ws['A1'].font = Font(name='Arial', size=12, bold=True)
    ws['A2'] = note or ('Block 1 = the value printed in the thesis. Block 2 = the value recalculated by the formulas of the Working sheet. '
                        'Block 3 = check: OK when the recalculated value, rounded as printed, equals the printed value.')
    ws['A2'].font = Font(name='Arial', size=9, italic=True)
    nc = len(head); nr = len(rows)
    r_p, r_c, r_k = 4, 4 + nr + 4, 4 + 2 * (nr + 4)
    for name, st in (('1. As printed in the thesis', r_p), ('2. Recalculated (formulas)', r_c), ('3. Check', r_k)):
        ws.cell(row=st, column=1, value=name).font = BOLD
        for j, h in enumerate(head, 1):
            c = ws.cell(row=st + 1, column=j, value=h); c.font = HF; c.fill = HDRF
            c.alignment = Alignment(wrap_text=True, vertical='center')
        ws.row_dimensions[st + 1].height = 32
    for i, row in enumerate(rows):
        for j, s in enumerate(row):
            ws.cell(row=r_p + 2 + i, column=j + 1, value=s).font = BLK
            f = exprs[i][j] if i < len(exprs) and j < len(exprs[i]) else None
            cc = ws.cell(row=r_c + 2 + i, column=j + 1); ck = ws.cell(row=r_k + 2 + i, column=j + 1)
            if f is None:
                cc.value = s; cc.font = BLK
                ck.value = s if j == 0 else 'n/a (not calculated)'; ck.font = BLK
                continue
            setf(ws, cc.coordinate, f); cc.font = BLK; cc.fill = YEL
            ref = cc.coordinate
            if isnum(s):
                v, d = parse_num(s)
                ck.value = f'=IF(ABS(ROUND({ref},{d})-({v}))<0.0000001,"OK","DIFF")'
                cc.number_format = '0.' + '0' * d if d > 0 else '0'
            else:
                s2 = s.replace('"', '""').replace('−', '-')
                ck.value = f'=IF(SUBSTITUTE({ref},"−","-")="{s2}","OK","DIFF")'
            ck.font = BLK
    rng = f"A{r_k + 2}:{CL(nc)}{r_k + 1 + nr}"
    ws.conditional_formatting.add(rng, CellIsRule(operator='equal', formula=['"OK"'], font=Font(color='006100')))
    ws.conditional_formatting.add(rng, CellIsRule(operator='equal', formula=['"DIFF"'], font=Font(color='9C0006', bold=True)))
    for j in range(1, nc + 1): ws.column_dimensions[CL(j)].width = 18
    ws.column_dimensions['A'].width = 30
    checks.append(("Result", rng))
    return ws


# ------------------------------------------------------------------ Steps sheet
def steps_sheet(wb, num, title, what, inputs, steps, example=None, notes=None, sheets=None):
    ws = wb.create_sheet('Steps', 0)
    ws.column_dimensions['A'].width = 150
    r = 1

    def put(text, bold=False, size=10, fill=None, formula=False):
        nonlocal r
        c = ws.cell(row=r, column=1, value=text)
        c.font = Font(name='Arial', size=size, bold=bold); c.alignment = Alignment(wrap_text=True, vertical='top')
        if fill: c.fill = fill
        r += 1

    put(f'Table {num}: {title}', True, 13)
    put('How the values of this table were obtained, step by step', False, 10)
    r += 1
    put('What the table shows', True, fill=SECF); put(what); r += 1
    put('Where the data come from', True, fill=SECF)
    for t in inputs: put('•  ' + t)
    r += 1
    put('Steps', True, fill=SECF)
    for i, t in enumerate(steps, 1): put(f'{i}.  {t}')
    r += 1
    if example:
        put('Worked example (live: these lines are formulas that read the Working sheet)', True, fill=SECF)
        for e in example:
            c = ws.cell(row=r, column=1, value=e); c.font = BLK; c.alignment = Alignment(wrap_text=True, vertical='top'); r += 1
        r += 1
    if notes:
        put('Notes', True, fill=SECF)
        for t in notes: put('•  ' + t)
        r += 1
    put('Sheets in this file', True, fill=SECF)
    for t in (sheets or []): put('•  ' + t)
    ws.sheet_view.showGridLines = False
    return ws


def tx(*parts):
    """worked-example formula: strings are literal text, (ref, fmt) pairs are numbers"""
    out = []
    for p in parts:
        if isinstance(p, str): out.append('"' + p.replace('"', '""') + '"')
        else:
            ref, fmt = p
            out.append(f'TEXT({ref.ref if hasattr(ref, "ref") else ref},"{fmt}")')
    return '=' + '&'.join(out)
