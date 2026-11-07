"""tl_run.py - build, recalculate and verify the per-table calculation workbooks.
usage: python3 -I tl_run.py <out folder> [table numbers ...]"""
import sys, os, subprocess, shutil, glob, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/tmp/claude-0/-home-claude/011f708a-f9df-520a-b7d5-07acd55b36e2/scratchpad/v5')
import tl_lib as T
SC = '/tmp/claude-0/-home-claude/011f708a-f9df-520a-b7d5-07acd55b36e2/scratchpad'
T.FINAL = f'{SC}/repo_out/final'
T.REPO = f'{SC}/repo_in/x/Data Repository'
from tl_lib import *
import tl_tables as TB
from tabs import load_tables
import openpyxl

OUT = sys.argv[1]
ONLY = sys.argv[2:]
os.makedirs(OUT, exist_ok=True)
RAW = os.path.join(OUT, '_raw'); os.makedirs(RAW, exist_ok=True)
TABS = load_tables(f'{SC}/Perera_S20472_Final_Report_v7.docx')
Wd, Td, Gd = load_data()
print('data', len(Wd), len(Td), len(Gd))


def build(num):
    stem, fn, need0 = TB.TABLES[num]
    title, rows = TABS[num][0], TABS[num][1]
    head, body = rows[0], rows[1:]
    wb = Workbook(); wb.remove(wb.active)
    wsW = wb.create_sheet('Working')
    L = Ledger(wsW)
    # need is known only after the builder runs, but the layout only depends on the sizes
    full = 'sweeps_full' in need0
    S = sweeps_def(len(Wd), full); Tm = temps_def(len(Td)); G = teg_def(len(Gd))
    ctx = dict(L=L, S=S, T=Tm, G=G, rows=body, head=head)
    ret = fn(ctx)
    need = set(need0) | set(ret.get('need', set()))
    checks = []
    result_sheet(wb, num, title, head, body, ret['exprs'], checks)
    add_inputs(wb, Wd, Td, Gd, need)
    if 'calib' in need:
        row = add_calibration(wb); checks.append(('Calibration', f'B{row}:I{row}'))
    steps_sheet(wb, num, title, ret['what'], ret['inputs'], ret['steps'], ret.get('example'), ret.get('notes'), ret.get('sheets'))
    order = ['Steps', 'Result', 'Working']
    wb._sheets = [wb[n] for n in order] + [s for s in wb._sheets if s.title not in order]
    wb.active = 0
    fname = f'Table_{num}_{stem}.xlsx'
    path = os.path.join(RAW, fname); wb.save(path)
    return fname, checks


def recalc(fname):
    subprocess.run(['soffice', '--headless', '--calc', '--convert-to', 'xlsx', '--outdir', OUT, os.path.join(RAW, fname)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)


def verify(fname, checks):
    wb = openpyxl.load_workbook(os.path.join(OUT, fname), data_only=True)
    bad = []; nok = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith('#'):
                    bad.append((ws.title, c.coordinate, c.value))
    for sh, rng in checks:
        for row in wb[sh][rng]:
            for c in row:
                if c.value is None: bad.append((sh, c.coordinate, 'EMPTY')); continue
                if c.value == 'OK': nok += 1
                elif c.value == 'DIFF' or (isinstance(c.value, str) and c.value.startswith('#')): bad.append((sh, c.coordinate, c.value))
    return nok, bad


t0 = time.time()
summary = []
for num in TB.TABLES:
    if ONLY and num not in ONLY: continue
    try:
        fname, checks = build(num)
        recalc(fname)
        nok, bad = verify(fname, checks)
    except Exception as e:
        import traceback; traceback.print_exc()
        print(num, 'BUILD ERROR', e); summary.append((num, 'ERR', 0, [str(e)])); continue
    print(f'Table {num}: {nok} checks OK, {len(bad)} problems  ({time.time()-t0:.0f}s)')
    for b in bad[:8]: print('    ', b)
    summary.append((num, fname, nok, bad))
print('TOTAL OK', sum(s[2] for s in summary), 'problems', sum(len(s[3]) for s in summary))
