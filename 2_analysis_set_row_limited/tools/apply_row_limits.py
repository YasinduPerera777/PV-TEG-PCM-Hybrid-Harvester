#!/usr/bin/env python3
"""
apply_row_limits.py
Creates the row-limited ("analysis set") copy of the sweep summary files and of the
calibrated one-minute files, following Table I.1 of the thesis.

Usage:  python3 -I apply_row_limits.py <Data Repository folder> <output folder>

Rules (thesis Appendix I.1)
  * Summary files: rows of the spreadsheet up to and including the "last row used"
    (Table I.1). Row 1 is the header, so "last row 31" means the first 30 sweeps.
    The block of Average / Minimum / Maximum rows below the data is kept and moves up.
  * One-minute files: the analysis window runs from the last one-minute record at or
    before the start of the first selected sweep to one minute after the end of the
    last selected sweep (inclusive). Selected sweeps are those inside the row limit
    that were fitted successfully (status ok) for both PV1 and PV2.
  * Original files are never modified.
"""
import sys, os, re, csv, glob, copy
import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter

# Table I.1: day code -> (configuration, last row PV1/PV2, last row TEG or note)
LIMITS = {
    "0912": ("Hybrid against bare", 31, 28),
    "0913": ("Hybrid against bare", 30, 28),
    "0914": ("Hybrid against bare", 24, 2),
    "0916": ("Hybrid against bare", 23, "TEG faulty"),
    "0917": ("Hybrid against bare", 28, "TEG faulty"),
    "0918": ("Hybrid against bare", 26, 12),
    "0919": ("Hybrid against bare", 17, 17),
    "0928": ("Bare against bare", 30, "Not connected"),
    "1001": ("Bare against bare", 30, "Not connected"),
}
MONTH = {"09": "September", "10": "October"}


def as_time_str(x):
    return str(x)


def trim_summary(src, dst, last_row, day, source):
    """Keep sheet rows 1..last_row of the data block; keep the statistics block."""
    wb = openpyxl.load_workbook(src)
    ws = wb.active
    # last data row = last row whose column A is a number
    data_end = 1
    for r in range(2, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if isinstance(v, (int, float)):
            data_end = r
    removed = []
    if last_row < data_end:
        for r in range(last_row + 1, data_end + 1):
            removed.append((int(ws.cell(r, 1).value), str(ws.cell(r, 3).value)[:10],
                            as_time_str(ws.cell(r, 4).value), as_time_str(ws.cell(r, 5).value),
                            str(ws.cell(r, 27).value)))
        ws.delete_rows(last_row + 1, data_end - last_row)
    # statistics formulas already point to 2:last_row in the original files; check it
    bad = []
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.startswith("="):
                for a, b in re.findall(r"[A-Z]+(\d+):[A-Z]+(\d+)", c.value):
                    if int(a) != 2 or int(b) != last_row:
                        bad.append((c.coordinate, c.value))
    note = wb.create_sheet("row_limit_note")
    note["A1"] = f"Row-limited copy of {os.path.basename(src)}"
    note["A2"] = (f"Rows after sheet row {last_row} were removed (Table I.1 of the thesis, "
                  f"{source} sweeps, day {day}). Row 1 is the header, so {last_row-1} sweep rows remain at most.")
    note["A3"] = "The Average / Minimum / Maximum rows are the author's own and cover rows 2 to %d." % last_row
    note["A4"] = "The original, unlimited file is kept in the folder Python_Analysis_of_Sweep_files."
    note.column_dimensions["A"].width = 110
    wb.save(dst)
    return data_end, removed, bad


def read_selected_sweeps(base, day, last_row):
    """Return (first_start, last_end, n_paired, set of paired sweep numbers)."""
    p1 = pd.read_excel(os.path.join(base, f"Day{day}_Outout", f"summary_PV1_{day}.xlsx"))
    p2 = pd.read_excel(os.path.join(base, f"Day{day}_Outout", f"summary_PV2_{day}.xlsx"))
    a = p1.iloc[:last_row - 1]
    c = p2.iloc[:last_row - 1]
    a = a[pd.to_numeric(a["sweep"], errors="coerce").notna()]
    c = c[pd.to_numeric(c["sweep"], errors="coerce").notna()]
    ok = set(a[a.status == "ok"].sweep) & set(c[c.status == "ok"].sweep)
    sel = a[a.sweep.isin(ok)]
    ds = sel.date.astype(str).str[:10]
    first = pd.to_datetime(ds + " " + sel.start_time.astype(str)).min()
    last = pd.to_datetime(ds + " " + sel.end_time.astype(str)).max()
    return first, last, len(ok), ok


def trim_voltage(src, dst, first, last):
    wb = openpyxl.load_workbook(src)
    ws = wb.active
    times = []
    for r in range(2, ws.max_row + 1):
        v = ws.cell(r, 2).value
        times.append((r, pd.to_datetime(v)))
    times = [(r, t) for r, t in times if not pd.isna(t)]
    end_lim = last + pd.Timedelta(minutes=1)
    before = [r for r, t in times if t <= first]
    start_row = max(before) if before else times[0][0]
    keep = [r for r, t in times if start_row <= r and t <= end_lim]
    # new workbook, same column widths, regenerate calibration formulas per row
    nwb = openpyxl.Workbook()
    nws = nwb.active
    nws.title = ws.title
    for c in range(1, ws.max_column + 1):
        nws.cell(1, c, ws.cell(1, c).value)
    for i, r in enumerate(keep, start=2):
        for c in range(1, ws.max_column + 1):
            if 30 <= c:                       # AD, AE: offset table, handled below
                continue
            v = ws.cell(r, c).value
            if isinstance(v, str) and v.startswith("="):
                v = re.sub(r"([A-Z]+)%d\b" % r, lambda m: f"{m.group(1)}{i}", v)
            cell = nws.cell(i, c, v)
            cell.number_format = ws.cell(r, c).number_format
    # offset table (AD/AE rows 1-10) copied to the same addresses
    for r in range(1, 11):
        for c in (30, 31):
            v = ws.cell(r, c).value
            if v is not None:
                nws.cell(r, c, v)
    for col, dim in ws.column_dimensions.items():
        nws.column_dimensions[col].width = dim.width
    note = nwb.create_sheet("row_limit_note")
    note["A1"] = f"Row-limited copy of {os.path.basename(src)}"
    note["A2"] = (f"Kept: records from {ws.cell(start_row,2).value} to {ws.cell(keep[-1],2).value} "
                  f"({len(keep)} records). Window = from the last record at or before the start of the first "
                  f"selected sweep to one minute after the end of the last selected sweep (Table I.1).")
    note["A3"] = "Calibrated columns are formulas: raw reading minus the offset in the table at AD:AE."
    note["A4"] = "The original, unlimited file is kept in the folder Outdoor_Campain_Data."
    note.column_dimensions["A"].width = 120
    nwb.save(dst)
    return len(times), len(keep), ws.cell(start_row, 2).value, ws.cell(keep[-1], 2).value


def main(root, out):
    base = os.path.join(root, "Python_Analysis_of_Sweep_files")
    outd = os.path.join(root, "Outdoor_Campain_Data")
    os.makedirs(os.path.join(out, "sweep_summaries_limited"), exist_ok=True)
    os.makedirs(os.path.join(out, "one_minute_files_limited"), exist_ok=True)
    log = []
    tot = dict(pv=0, teg=0, v=0)
    for day, (cfg, lp, lt) in LIMITS.items():
        first, last, npair, ok = read_selected_sweeps(base, day, lp)
        tot["pv"] += npair
        for source in ("PV1", "PV2", "TEG"):
            src = os.path.join(base, f"Day{day}_Outout", f"summary_{source}_{day}.xlsx")
            if not os.path.exists(src):
                log.append([day, source, "", "", "", "", "no file (%s)" % lt, ""])
                continue
            L = lp if source != "TEG" else lt
            if not isinstance(L, int):
                log.append([day, source, "", "", "", "", "not used (%s); original file only" % L, ""])
                continue
            dst = os.path.join(out, "sweep_summaries_limited", f"summary_{source}_{day}.xlsx")
            data_end, removed, bad = trim_summary(src, dst, L, day, source)
            nsweeps = L - 1 if L - 1 <= data_end - 1 else data_end - 1
            if source == "TEG":
                t = pd.read_excel(src).iloc[:L - 1]
                n_ok = int((t[pd.to_numeric(t["sweep"], errors="coerce").notna()].status == "ok").sum())
                tot["teg"] += n_ok
            else:
                n_ok = npair
            log.append([day, source, L, data_end - 1, nsweeps, n_ok,
                        "formula range check: " + ("OK" if not bad else "MISMATCH %s" % bad[:2]),
                        "; ".join(f"sweep {a} {b} {c}-{d} [{e}]" for a, b, c, d, e in removed)])
        # one-minute file
        cand = glob.glob(os.path.join(outd, f"V{day}_[Cc]allibrated.xlsx"))
        src = cand[0]
        dst = os.path.join(out, "one_minute_files_limited", f"V{day}_Callibrated.xlsx")
        n_all, n_keep, t0, t1 = trim_voltage(src, dst, first, last)
        tot["v"] += n_keep
        log.append([day, "V (one-minute)", "", n_all, n_keep, "", f"{t0} to {t1}", f"original name {os.path.basename(src)}"])
    with open(os.path.join(out, "row_limit_log.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "file", "last_row_used", "rows_in_original", "rows_kept", "paired_or_ok_sweeps", "check / window", "removed sweeps (number, date, start-end, status)"])
        w.writerows(log)
    with open(os.path.join(out, "row_limits_TableI1.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date_2026", "day_code", "configuration", "last_row_used_PV1_PV2", "last_row_used_TEG"])
        for day, (cfg, lp, lt) in LIMITS.items():
            w.writerow([f"{int(day[2:])} {MONTH[day[:2]]}", day, cfg, lp, lt])
    print(tot)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
