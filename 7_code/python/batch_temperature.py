"""
Batch pipeline for the ONE-MINUTE records (V0912.CSV / V0912.xlsx, ...), the
companion of batch_process.py (which handles the sweep files).  For every day
it draws the variation through the day of

  * the eight thermocouple temperatures (panel fronts and rears, PCM,
    point under the TEG, ambient),
  * the BPW34 relative-irradiance signal,
  * the open-circuit voltages of PV1 and PV2 and of the TEG (the MOSFET loads
    are off between sweeps, so the one-minute records are open-circuit values),

in the same style as batch_process.py (Times New Roman, boxed axes, inward
ticks, dark major / light minor grid, 300 dpi, same colour palette).  Panels
that share the time axis are STACKED instead of using a second y axis.

Which file(s) to process
  - No arguments: every V*.csv / V*.xlsx in the folder of this script.
  - Explicit arguments: python3 batch_temperature.py V0912.CSV V0913.CSV

Outputs (under temperature_output/)
  daily/<stem>_overview.png     -- temperatures + BPW34 + open-circuit voltages (no BPW34 panel on
                                   the baseline days)
  daily/<stem>_difference.png   -- (hybrid days) how much cooler the front and the rear surface of PV1
                                   (hybrid) are than those of PV2 (bare), through that day
  daily/<stem>_teg.png          -- (hybrid days with a working TEG) rear/PCM/under-TEG/
                                   ambient temperatures + TEG open-circuit voltage + BPW34
  all_days_front_ambient.png    -- 3 x 3 small multiples, front temperatures and ambient
  all_days_rear_ambient.png     -- the same for the rear surfaces (TC2 PV2 rear, TC5 PV1 rear) and ambient
                                   (both figures are drawn at the width of the report text, see
                                   ALL_DAYS_FIGSIZE, in the report font, so they can be inserted without scaling)
  pcm_hybrid_days.png           -- PCM (TC6) against the 45-53 C melting range, hybrid days
  hybrid_difference_summary.csv -- per hybrid day: mean and largest PV1 - PV2 front / rear difference
  temperature_summary.csv       -- per-day min / mean / max of every channel
  batch_log.txt                 -- despiked points and warnings

Edit the CONFIG block below (thermocouple calibration, which days are hybrid,
analysis windows).  Nothing else needs touching.
"""

import os
import sys
import glob
import traceback
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, AutoMinorLocator, FixedLocator, FormatStrFormatter, FuncFormatter

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ===========================================================================
# CONFIG
# ===========================================================================
LOCATION = "6.767360° N, 79.884191° E (Moratuwa, Sri Lanka)"

# THERMOCOUPLE CALIBRATION
# If the file has calibrated columns (TC1_Callibrated ... TC8_Callibrated, as in
# V0912_Callibrated.xlsx) those are used and everything below is ignored.
# For a file WITHOUT calibrated columns the raw readings are corrected with
#     T_corrected = m * T_raw + b
# The defaults below are the shifts that were subtracted in V0912_Callibrated.xlsx
# (calibrated = raw - shift).  TC4 is not connected to anything.
SHIFT = {"TC1": 3.86, "TC2": 3.51, "TC3": 3.59, "TC5": 2.99, "TC6": 2.24, "TC7": 2.40, "TC8": 3.74}
CAL = {f"TC{i}": (1.0, -SHIFT.get(f"TC{i}", 0.0)) for i in range(1, 9)}
TC_USED = [1, 2, 3, 5, 6, 7, 8]        # TC4 unused

# Channel roles (from Table 3.4 of the thesis).
ROLE = {
    "TC1": "PV2 front (bare)",
    "TC2": "PV2 rear (bare)",
    "TC3": "PV1 front",
    "TC5": "PV1 rear",
    "TC6": "PCM (inside enclosure)",
    "TC7": "under the TEG",
    "TC8": "ambient",
}

# Day configuration (dates as YYYY-MM-DD).
HYBRID_DAYS = ["2026-09-12", "2026-09-13", "2026-09-14", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19"]
BASELINE_DAYS = ["2026-09-28", "2026-10-01"]
TEG_DAYS = ["2026-09-12", "2026-09-13", "2026-09-14", "2026-09-18", "2026-09-19"]   # TEG faulty on 16, 17 Sep

# Analysis windows of Table 4.1 (shaded in the daily figures).  Remove an entry to hide it.
WINDOWS = {
    "2026-09-12": ("08:47", "16:05"), "2026-09-13": ("09:08", "16:11"), "2026-09-14": ("10:37", "16:09"),
    "2026-09-16": ("10:43", "16:00"), "2026-09-17": ("09:40", "16:13"), "2026-09-18": ("08:12", "14:30"),
    "2026-09-19": ("10:28", "14:15"), "2026-09-28": ("09:07", "16:09"), "2026-10-01": ("08:09", "15:08"),
}

# Use only the records inside WINDOWS (everything else is dropped from the figures and from
# the numbers).  The window runs from the START minute to the END minute plus
# WINDOW_END_PAD_MIN, because the last record is the first one logged after the last sweep
# ends (V0912: window 08:47-16:05 keeps the records up to 16:06:00 = 418 rows).
CROP_TO_WINDOWS = True
WINDOW_END_PAD_MIN = 1
# Rows kept per day, from your table; the script compares its own count with these and says so
# in batch_log.txt (a mismatch means the window or the file differs from the one you used).
EXPECTED_ROWS = {"2026-09-12": (478, 418), "2026-09-13": (549, 405), "2026-09-14": (321, 319),
                 "2026-09-16": (428, 304), "2026-09-17": (402, 375), "2026-09-18": (560, 361),
                 "2026-09-19": (232, 218), "2026-09-28": (467, 400), "2026-10-01": (472, 395)}

PCM_MELT_LO, PCM_MELT_HI = 45.0, 53.0     # melting range of the 40:60 mixture (Table 4.4)

# Read failures: a surface thermocouple that reads below READ_FAIL_BELOW degrees C (after
# calibration) in daytime is a failed reading, not a temperature.  This happens on TC2 (PV2 rear)
# on the two baseline days, where the channel reads about 0 C (-3.5 C after calibration), in
# runs of up to ten minutes -- longer than the spike filter below can remove.  Such records are
# left out of the plots and of the numbers and are listed in batch_log.txt.  Set to None to keep them.
READ_FAIL_BELOW = 15.0

# Spike rejection: a temperature that differs from the rolling median of 7 records by
# more than DESPIKE_C is treated as a reading error (e.g. the TC2 glitches of Section 4.4)
# and left out of the plot (it is listed in batch_log.txt).  Set to None to plot raw data.
DESPIKE_C = 8.0

# Smoothing of the plotted curves: centred rolling median over SMOOTH_MIN minutes, then a
# short rolling mean (SMOOTH_MIN / 3 minutes).  Removes the one-minute scatter and leaves the
# slow daily variation.  Set to None to plot the raw one-minute values.
# (temperature_summary.csv always uses the un-smoothed temperatures.)
SMOOTH_MIN = 15

# ===========================================================================
# Style -- identical to batch_process.py
# ===========================================================================
INK, INK_MUTED, AXIS = "#0b0b0b", "#3a3a38", "#c3c2b7"
BORDER, GRID_MAJOR, GRID_MINOR = "black", "#595959", "#d9d9d9"
COL_PV1, COL_PV2 = "#2a78d6", "#d62728"        # PV1 blue (as the model curve), PV2 red
COL_PCM, COL_TEG, COL_AMB = "#eda100", "#1baf7a", "#0b0b0b"
COL_BPW = "#7b3fa0"
GREY = "#8c8c8c"

plt.rcParams.update({
    "font.family": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],   # report font first
    # mathtext ($...$) in real Times New Roman too (roman and italic), as in batch_process.py
    "mathtext.fontset": "custom",
    "mathtext.rm": "Times New Roman",
    "mathtext.it": "Times New Roman:italic",
    "mathtext.bf": "Times New Roman:bold",
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "axes.grid": True,
    "grid.color": "#e1e0d9",
    "grid.linewidth": 0.8,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "font.size": 10.5,
    "xtick.labelsize": 11.5,
    "ytick.labelsize": 11.5,
})

LW = 1.2   # thin marks

# Size of the two all-days figures (front, rear).  The width is that of the report text
# (A4, 2.54 cm margins -> 6.27 in; the figures of the report are inserted at 5.9 in), so the
# figure can be inserted at 100 % and the text keeps the size set here.  The font is the one
# of the report (Times New Roman).  For the old, large version use (11.69, 8.27) and 11.
ALL_DAYS_FIGSIZE = (5.9, 6.4)
ALL_DAYS_FONT = 8.0
ALL_DAYS_LW = 1.0


def hour_fmt(h, _pos=None):
    return f"{int(h):02d}:{int(round((h % 1) * 60)) % 60:02d}"


def style_time_axes(ax, xlim, ydata, nbins=7, show_xlabels=True, xstep=1, box_aspect=None):
    """Same axes and grid format as style_axes() of batch_process.py: black box, inward ticks
    (major 5 pt, minor 3 pt), dark major grid (0.8 pt) and light minor grid (0.5 pt) with 10 minor
    divisions per major step, y tick values from MaxNLocator and written without trailing zeros (20, 30, ... ; 0.5, 1 ...).
    The x axis is time of day in decimal hours with a major tick every xstep hours.
    box_aspect=1 makes the plot area square (used for the small multiples)."""
    steps = [1, 2, 2.5, 5, 10]      # round tick steps (10, 5, 2 ... degrees); batch_process.py also allows 4, 6.25, 8
    y_ticks = MaxNLocator(nbins=nbins, steps=steps).tick_values(*ydata)
    ax.set_ylim(y_ticks[0], y_ticks[-1])
    ax.yaxis.set_major_locator(FixedLocator(y_ticks))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%g"))
    x0, x1 = int(np.floor(xlim[0])), int(np.ceil(xlim[1]))
    ax.set_xlim(x0, x1)
    ax.xaxis.set_major_locator(FixedLocator(list(range(x0, x1 + 1, xstep))))
    ax.xaxis.set_major_formatter(FuncFormatter(hour_fmt))
    for spine in ("top", "right", "left", "bottom"):
        ax.spines[spine].set_visible(True)
        ax.spines[spine].set_color(BORDER)
    if box_aspect:
        ax.set_box_aspect(box_aspect)
    ax.xaxis.set_minor_locator(AutoMinorLocator(10))
    ax.yaxis.set_minor_locator(AutoMinorLocator(10))
    ax.tick_params(which="both", direction="in", color=BORDER, top=False, right=False, bottom=True, left=True)
    ax.tick_params(which="major", length=5)
    ax.tick_params(which="minor", length=3)
    ax.xaxis.grid(which="minor", color=GRID_MINOR, linewidth=0.5, linestyle="-", zorder=0.3)
    ax.yaxis.grid(which="minor", color=GRID_MINOR, linewidth=0.5, linestyle="-", zorder=0.3)
    ax.yaxis.grid(which="major", color=GRID_MAJOR, linewidth=0.8, linestyle="-", zorder=0.5)
    ax.xaxis.grid(which="major", color=GRID_MAJOR, linewidth=0.8, linestyle="-", zorder=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(labelbottom=bool(show_xlabels), labelleft=True)


def legend_right(ax, **kw):
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False, fontsize=10.5, **kw)


# ===========================================================================
# Data loading
# ===========================================================================
TC_COLS = [f"TC{i}(C)" for i in range(1, 9)]


def smooth_series(s, ts):
    """Centred, time-based smoothing (SMOOTH_MIN minutes): a rolling median removes
    the one-minute scatter, a short rolling mean then rounds off the steps.
    Gaps (sweep periods) are not bridged: windows only use records that exist."""
    x = pd.Series(s.to_numpy(dtype=float), index=pd.DatetimeIndex(ts))
    x = x.rolling(f"{int(SMOOTH_MIN)}min", center=True, min_periods=3).median()
    x = x.rolling(f"{max(int(SMOOTH_MIN // 3), 1)}min", center=True, min_periods=1).mean()
    return pd.Series(x.to_numpy(), index=s.index)


def find_col(df, names):
    """First column whose name matches one of names (case-insensitive), else None."""
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def load_day(path, log):
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path, sheet_name=0, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    tcol = find_col(df, ["Timestamp", "Time", "Date"])           # the time stamp column
    df["Timestamp"] = pd.to_datetime(df[tcol], errors="coerce")
    df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)
    for c in df.columns:
        if c not in ("Timestamp", "Date", "Time"):
            df[c] = pd.to_numeric(df[c], errors="coerce")        # "nan" text / notes -> NaN
    if "PWM" in df.columns:
        df = df[df["PWM"].fillna(0) == 0].reset_index(drop=True)  # open-circuit records only
    day = df["Timestamp"].iloc[0].strftime("%Y-%m-%d")

    src = []
    for i in TC_USED:
        ccol = find_col(df, [f"TC{i}_Callibrated", f"TC{i}_Calibrated", f"TC{i}_cal"])
        if ccol is not None and df[ccol].notna().any():
            cor = df[ccol].copy()
            src.append("calibrated column")
        else:
            m, b = CAL[f"TC{i}"]
            cor = m * df[f"TC{i}(C)"] + b
            src.append("raw + CAL")
        if READ_FAIL_BELOW is not None:
            fail = cor < READ_FAIL_BELOW
            if fail.any():
                log.append(f"{day} TC{i}: {int(fail.sum())} failed reading(s) (< {READ_FAIL_BELOW:g} C) removed at "
                           + ", ".join(df.loc[fail, "Timestamp"].dt.strftime("%H:%M").tolist()))
            cor = cor.mask(fail)
        if DESPIKE_C is not None:
            med = cor.rolling(7, center=True, min_periods=3).median()
            bad = (cor - med).abs() > DESPIKE_C
            if bad.any():
                log.append(f"{day} TC{i}: {int(bad.sum())} spike(s) removed "
                           f"(> {DESPIKE_C} C from the rolling median) at "
                           + ", ".join(df.loc[bad, "Timestamp"].dt.strftime("%H:%M").tolist()))
            cor = cor.mask(bad)
        df[f"TC{i}"] = cor
    log.append(f"{day}: temperatures taken from " + ("the calibrated columns" if set(src) == {"calibrated column"}
               else "raw readings corrected with CAL (no calibrated columns in this file)" if set(src) == {"raw + CAL"}
               else "calibrated columns for some channels and raw + CAL for the rest -- check the file"))
    df["hour"] = df["Timestamp"].dt.hour + df["Timestamp"].dt.minute / 60 + df["Timestamp"].dt.second / 3600
    df["Voc1"], df["Voc2"] = df["V1(V)"], df["V2(V)"]
    df["Voc_TEG_mV"] = df["V_TEG(V)"] * 1000.0
    df["BPW"] = df["V_BPW(V)"]
    # keep the un-smoothed temperatures for the summary table, then smooth what is plotted
    for i in TC_USED:
        df[f"TC{i}_raw"] = df[f"TC{i}"]
    if SMOOTH_MIN:
        for c in [f"TC{i}" for i in TC_USED] + ["Voc1", "Voc2", "Voc_TEG_mV", "BPW"]:
            df[c] = smooth_series(df[c], df["Timestamp"])      # smoothed on the full day, cropped afterwards
    n_logged = len(df)
    t_first, t_last = df["Timestamp"].iloc[0], df["Timestamp"].iloc[-1]
    if CROP_TO_WINDOWS and day in WINDOWS:
        a, b = WINDOWS[day]
        t0 = pd.Timestamp(f"{day} {a}:00")
        t1 = pd.Timestamp(f"{day} {b}:00") + pd.Timedelta(minutes=WINDOW_END_PAD_MIN) + pd.Timedelta(seconds=59)
        df = df[(df["Timestamp"] >= t0) & (df["Timestamp"] <= t1)].reset_index(drop=True)
    msg = (f"{day}: logged {t_first.strftime('%H:%M')}-{t_last.strftime('%H:%M')}, "
           f"{len(df)} of {n_logged} rows kept")
    if day in EXPECTED_ROWS:
        exp = EXPECTED_ROWS[day]
        msg += (f"  [matches your table: {exp[1]} of {exp[0]}]" if exp == (n_logged, len(df))
                else f"  [CHECK: your table says {exp[1]} of {exp[0]}]")
    log.append(msg)
    print(msg)
    df.attrs["n_logged"] = n_logged
    return day, df


def day_label(day):
    return pd.Timestamp(day).strftime("%d %b %Y")


def day_type(day):
    if day in HYBRID_DAYS:
        return "hybrid day (PV1 hybrid, PV2 bare)"
    if day in BASELINE_DAYS:
        return "baseline day (both panels bare)"
    return "day"


def window_shade(ax, day):
    if day in WINDOWS and not CROP_TO_WINDOWS:
        a, b = WINDOWS[day]
        h = lambda s: int(s[:2]) + int(s[3:]) / 60
        ax.axvspan(h(a), h(b), color="#f2f2f2", zorder=0.1)


def header(fig, day, df, y=0.962):
    fig.text(0.5, y, f"{day_label(day)}  --  {day_type(day)}  --  {len(df)} one-minute records, "
             f"{df['Timestamp'].iloc[0].strftime('%H:%M')} to {df['Timestamp'].iloc[-1].strftime('%H:%M')}"
             + (f" (analysis window)" if CROP_TO_WINDOWS and day in WINDOWS else ""),
             ha="center", fontsize=10, color=INK_MUTED)
    if LOCATION:
        fig.text(0.5, y - 0.016, f"Location: {LOCATION}", ha="center", fontsize=10, color=INK_MUTED)


def plot_line(ax, df, col, label, color, ls="-", lw=LW, z=3):
    ax.plot(df["hour"], df[col], color=color, ls=ls, lw=lw, label=label, zorder=z,
            solid_capstyle="round", solid_joinstyle="round")


# ===========================================================================
# Figures
# ===========================================================================
def fig_overview(df, day, out):
    hybrid = day in HYBRID_DAYS
    show_bpw = day not in BASELINE_DAYS          # BPW34 left out on the baseline days (saturated)
    if show_bpw:
        fig, axs = plt.subplots(3, 1, figsize=(8.27, 11.69), sharex=True,
                                gridspec_kw={"height_ratios": [1.6, 0.9, 0.9]})
        fig.suptitle("Temperatures, relative irradiance and open-circuit voltage through the day",
                     fontsize=13, fontweight="bold", y=0.985)
    else:
        fig, axs = plt.subplots(2, 1, figsize=(8.27, 9.4), sharex=True,
                                gridspec_kw={"height_ratios": [1.6, 0.9]})
        fig.suptitle("Temperatures and open-circuit voltage through the day",
                     fontsize=13, fontweight="bold", y=0.998)
    header(fig, day, df, y=0.962 if show_bpw else 0.958)
    xlim = (df["hour"].min(), df["hour"].max())

    ax = axs[0]
    window_shade(ax, day)
    plot_line(ax, df, "TC1", f"TC1  {ROLE['TC1']}", COL_PV2)
    plot_line(ax, df, "TC2", f"TC2  {ROLE['TC2']}", COL_PV2, ls=(0, (4, 2)))
    pv1_front = "PV1 front (hybrid)" if hybrid else "PV1 front (bare)"
    pv1_rear = "PV1 rear (hybrid)" if hybrid else "PV1 rear (bare)"
    plot_line(ax, df, "TC3", f"TC3  {pv1_front}", COL_PV1)
    plot_line(ax, df, "TC5", f"TC5  {pv1_rear}", COL_PV1, ls=(0, (4, 2)))
    if hybrid:
        plot_line(ax, df, "TC6", f"TC6  {ROLE['TC6']}", COL_PCM)
        plot_line(ax, df, "TC7", f"TC7  {ROLE['TC7']}", COL_TEG)
        ax.axhspan(PCM_MELT_LO, PCM_MELT_HI, color=COL_PCM, alpha=0.12, zorder=0.2,
                   label=f"PCM melting range ({PCM_MELT_LO:g}–{PCM_MELT_HI:g} °C)")
    plot_line(ax, df, "TC8", f"TC8  {ROLE['TC8']}", COL_AMB, ls="-", lw=1.5)
    cols = ["TC1", "TC2", "TC3", "TC5", "TC8"] + (["TC6", "TC7"] if hybrid else [])
    vals = df[cols].to_numpy(dtype=float)
    ymax = np.nanmax(vals) + (2 if not hybrid else 3)
    style_time_axes(ax, xlim, (np.nanmin(vals) - 1, ymax), nbins=7, show_xlabels=True)
    ax.set_ylabel("Temperature / °C", fontsize=12)
    ax.set_title("Thermocouple temperatures" + ("" if CROP_TO_WINDOWS else " (shaded: analysis window of Table 4.1)"), fontsize=11.5, color=INK_MUTED, pad=8)
    legend_right(ax)

    if show_bpw:
        ax = axs[1]
        window_shade(ax, day)
        plot_line(ax, df, "BPW", "BPW34 signal", COL_BPW)
        style_time_axes(ax, xlim, (0, max(df["BPW"].max(), 0.5) * 1.05), nbins=5, show_xlabels=True)
        ax.set_ylabel("BPW34 signal / V", fontsize=12)
        ax.set_title("Relative irradiance indicator (uncalibrated)", fontsize=11.5, color=INK_MUTED, pad=8)
        legend_right(ax)

    ax = axs[-1]
    window_shade(ax, day)
    plot_line(ax, df, "Voc1", "PV1  V$_{oc}$", COL_PV1)
    plot_line(ax, df, "Voc2", "PV2  V$_{oc}$", COL_PV2)
    v = df[["Voc1", "Voc2"]].to_numpy(dtype=float)
    style_time_axes(ax, xlim, (np.nanmin(v) - 0.3, np.nanmax(v) + 0.3), nbins=5)
    ax.set_ylabel("Open-circuit voltage / V", fontsize=12)
    ax.set_xlabel("Time of day (local)", fontsize=12)
    ax.set_title("Open-circuit voltages (loads off between sweeps)", fontsize=11.5, color=INK_MUTED, pad=8)
    legend_right(ax)

    for _a in axs:
        _a.set_xlabel("Time of day (local)", fontsize=12)
    fig.subplots_adjust(left=0.10, right=0.68, top=0.893 if show_bpw else 0.87, bottom=0.05 if show_bpw else 0.07, hspace=0.40)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def fig_teg(df, day, out):
    fig, axs = plt.subplots(3, 1, figsize=(8.27, 11.69), sharex=True,
                            gridspec_kw={"height_ratios": [1.3, 1.0, 0.8]})
    fig.suptitle("Temperatures and TEG open-circuit voltage through the day", fontsize=13, fontweight="bold", y=0.985)
    header(fig, day, df)
    xlim = (df["hour"].min(), df["hour"].max())

    ax = axs[0]
    window_shade(ax, day)
    plot_line(ax, df, "TC5", f"TC5  PV1 rear (hybrid)", COL_PV1)
    plot_line(ax, df, "TC6", f"TC6  {ROLE['TC6']}", COL_PCM)
    plot_line(ax, df, "TC7", f"TC7  {ROLE['TC7']}", COL_TEG)
    plot_line(ax, df, "TC8", f"TC8  {ROLE['TC8']}", COL_AMB, ls="-", lw=1.5)
    v = df[["TC5", "TC6", "TC7", "TC8"]].to_numpy(dtype=float)
    style_time_axes(ax, xlim, (np.nanmin(v) - 1, np.nanmax(v) + 2), nbins=7, show_xlabels=True)
    ax.set_ylabel("Temperature / °C", fontsize=12)
    ax.set_title("Temperatures at the TEG and the PCM", fontsize=11.5, color=INK_MUTED, pad=8)
    legend_right(ax)

    ax = axs[1]
    window_shade(ax, day)
    plot_line(ax, df, "Voc_TEG_mV", "TEG  V$_{oc}$", COL_TEG)
    style_time_axes(ax, xlim, (min(0, np.nanmin(df["Voc_TEG_mV"]) * 1.05), max(np.nanmax(df["Voc_TEG_mV"]), 10) * 1.05), nbins=6, show_xlabels=True)
    ax.set_ylabel("TEG open-circuit voltage / mV", fontsize=12)
    ax.set_title("TEG open-circuit voltage (one-minute records, resolution 0.19 mV)", fontsize=11.5, color=INK_MUTED, pad=8)
    legend_right(ax)

    ax = axs[2]
    window_shade(ax, day)
    plot_line(ax, df, "BPW", "BPW34 signal", COL_BPW)
    style_time_axes(ax, xlim, (0, max(df["BPW"].max(), 0.5) * 1.05), nbins=5)
    ax.set_ylabel("BPW34 signal / V", fontsize=12)
    ax.set_xlabel("Time of day (local)", fontsize=12)
    ax.set_title("Relative irradiance indicator (uncalibrated)", fontsize=11.5, color=INK_MUTED, pad=8)
    legend_right(ax)

    for _a in axs:
        _a.set_xlabel("Time of day (local)", fontsize=12)
    fig.subplots_adjust(left=0.10, right=0.68, top=0.893, bottom=0.05, hspace=0.40)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def grid_axes(n, ncols, figsize):
    nrows = int(np.ceil(n / ncols))
    fig, axs = plt.subplots(nrows, ncols, figsize=figsize, sharex=True, sharey=True)
    return fig, np.atleast_1d(axs).ravel()


def day_span(days, data):
    lo = min(data[d]["hour"].min() for d in days)
    hi = max(data[d]["hour"].max() for d in days)
    return (int(np.floor(lo)), int(np.ceil(hi)))


def fig_all_days(days, data, out, side="front"):
    """3 x 3 small multiples, one panel per day: PV2 (bare), PV1 (hybrid, or bare on the baseline
    days) and ambient.  side = 'front' (TC1, TC3) or 'rear' (TC2, TC5).  Drawn at the size and in
    the font of the report (ALL_DAYS_FIGSIZE, ALL_DAYS_FONT)."""
    c_pv2, c_pv1 = {"front": ("TC1", "TC3"), "rear": ("TC2", "TC5")}[side]
    fs = ALL_DAYS_FONT
    span = day_span(days, data)
    fig, axs = grid_axes(len(days), 3, ALL_DAYS_FIGSIZE)
    cols = [c_pv2, c_pv1, "TC8"]
    ymax = max(np.nanmax(data[d][cols].to_numpy(dtype=float)) for d in days) + 2
    ymin = min(np.nanmin(data[d][cols].to_numpy(dtype=float)) for d in days) - 1
    n = len(days)
    for k, (ax, d) in enumerate(zip(axs, days)):
        df = data[d]
        plot_line(ax, df, c_pv2, f"PV2 {side} (bare)", COL_PV2, lw=ALL_DAYS_LW)
        plot_line(ax, df, c_pv1, f"PV1 {side} (hybrid or bare)", COL_PV1, lw=ALL_DAYS_LW)
        plot_line(ax, df, "TC8", "ambient", COL_AMB, ls="-", lw=ALL_DAYS_LW * 1.2)
        style_time_axes(ax, span, (ymin, ymax), nbins=5, xstep=2, box_aspect=1)
        ax.tick_params(which="both", labelsize=fs - 0.5)
        ax.set_title(f"{day_label(d)}  ({'hybrid' if d in HYBRID_DAYS else 'baseline'})", fontsize=fs + 0.5,
                     color=INK, pad=3)
        if k % 3 == 0:
            ax.set_ylabel("Temperature / °C", fontsize=fs + 0.5)
        if k >= n - 3:
            ax.set_xlabel("Time of day (local)", fontsize=fs + 0.5)
    for ax in axs[n:]:
        ax.axis("off")
    h, _ = axs[0].get_legend_handles_labels()
    fig.legend(h[:3], [f"PV2 {side} (bare)", f"PV1 {side} (hybrid or bare)", "ambient"], loc="lower center",
               ncol=3, frameon=False, fontsize=fs + 0.5)
    fig.tight_layout(rect=(0, 0.045, 1, 1), w_pad=0.6, h_pad=0.8)
    fig.savefig(out, dpi=600, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def fig_pcm(days, data, out):
    span = day_span(days, data)
    fig, axs = grid_axes(len(days), 2, (8.27, 11.69))
    fig.suptitle("PCM temperature (TC6) on the hybrid days", fontsize=13, fontweight="bold", y=0.995)
    ymax = max(np.nanmax(data[d][["TC5", "TC6", "TC8"]].to_numpy(dtype=float)) for d in days) + 2
    ymin = min(np.nanmin(data[d][["TC5", "TC6", "TC8"]].to_numpy(dtype=float)) for d in days) - 1
    for ax, d in zip(axs, days):
        df = data[d]
        ax.axhspan(PCM_MELT_LO, PCM_MELT_HI, color=COL_PCM, alpha=0.15, zorder=0.2)
        plot_line(ax, df, "TC5", "PV1 rear", COL_PV1)
        plot_line(ax, df, "TC6", "PCM (TC6)", COL_PCM, lw=1.5)
        plot_line(ax, df, "TC8", "ambient", COL_AMB, ls="-", lw=1.4)
        style_time_axes(ax, span, (ymin, ymax), nbins=5, xstep=2)
        mx = np.nanmax(df["TC6_raw"])
        ax.set_title(f"{day_label(d)}  (TC6 max {mx:.1f} °C)", fontsize=10.5, color=INK_MUTED, pad=5)
    for ax in axs[len(days):]:
        ax.axis("off")
    for ax in axs[:len(days)]:
        ax.set_ylabel("Temperature / °C", fontsize=11)
        ax.set_xlabel("Time of day (local)", fontsize=11)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=COL_PV1, lw=LW), Line2D([], [], color=COL_PCM, lw=1.5),
               Line2D([], [], color=COL_AMB, lw=1.4, ls="-"),
               Patch(color=COL_PCM, alpha=0.3)]
    axs[-1].axis("off")
    axs[-1].legend(handles, ["PV1 rear (TC5)", "PCM (TC6)", "ambient (TC8)",
                             f"melting range {PCM_MELT_LO:g}–{PCM_MELT_HI:g} °C"], loc="center", frameon=False, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def fig_difference_day(df, day, out):
    """One hybrid day: how much cooler (or warmer) the front surface and the rear surface of
    PV1 (hybrid) are than those of PV2 (bare), through the day.  Single day, no baseline."""
    fig, axs = plt.subplots(2, 1, figsize=(8.27, 9.6), sharex=True)
    fig.suptitle("PV1 (hybrid) compared with PV2 (bare) through the day", fontsize=13, fontweight="bold", y=0.998)
    header(fig, day, df, y=0.958)
    xlim = (df["hour"].min(), df["hour"].max())
    in_win = np.ones(len(df), dtype=bool)
    if day in WINDOWS:
        t = lambda x: int(x[:2]) + int(x[3:]) / 60
        in_win = ((df["hour"] >= t(WINDOWS[day][0])) & (df["hour"] <= t(WINDOWS[day][1]))).to_numpy()
    specs = (("front", "TC3", "TC1", "T(PV1 front) − T(PV2 front) / °C", "Front surface:  TC3 (PV1, hybrid) − TC1 (PV2, bare)"),
             ("rear", "TC5", "TC2", "T(PV1 rear) − T(PV2 rear) / °C", "Rear surface:  TC5 (PV1, hybrid) − TC2 (PV2, bare)"))
    stats = {"date": day}
    for ax, (side, c1, c2, ylab, ttl) in zip(axs, specs):
        window_shade(ax, day)
        dT = (df[c1] - df[c2]).to_numpy(dtype=float)               # smoothed curve
        raw = (df[c1 + "_raw"] - df[c2 + "_raw"]).to_numpy(dtype=float)
        ax.plot(df["hour"], dT, color=COL_PV1, lw=2.0, zorder=4, solid_capstyle="round")
        ax.fill_between(df["hour"], dT, 0, where=~np.isnan(dT), color=COL_PV1, alpha=0.10, zorder=1, lw=0)
        ax.axhline(0, color=INK, lw=0.8, zorder=1)
        mean_win = np.nanmean(raw[in_win]) if np.any(in_win & ~np.isnan(raw)) else np.nan
        k = int(np.nanargmin(dT))
        stats[f"{side}_mean_diff_C"] = round(float(mean_win), 2)
        stats[f"{side}_largest_diff_C"] = round(float(dT[k]), 2)
        stats[f"{side}_largest_time"] = hour_fmt(df["hour"].iloc[k])
        v = dT[~np.isnan(dT)]
        style_time_axes(ax, xlim, (min(np.nanmin(v) - 0.5, -1), max(np.nanmax(v) + 1.8, 1)), nbins=6, show_xlabels=True)
        ax.set_ylabel(ylab, fontsize=12)
        ax.set_title(ttl + ("" if CROP_TO_WINDOWS else "  (shaded: analysis window)"), fontsize=11.0, color=INK_MUTED, pad=8)
    for _a in axs:
        _a.set_xlabel("Time of day (local)", fontsize=12)
    fig.subplots_adjust(left=0.11, right=0.95, top=0.87, bottom=0.07, hspace=0.30)
    fig.savefig(out, dpi=300, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return stats


# ===========================================================================
# Driver
# ===========================================================================
def find_input_files():
    if len(sys.argv) > 1:
        return sys.argv[1:]
    files = sorted(glob.glob("V*.csv") + glob.glob("V*.CSV") + glob.glob("V*.xlsx"))
    return [f for f in dict.fromkeys(files) if not os.path.basename(f).startswith("~$")]


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    out_root = "temperature_output"
    os.makedirs(os.path.join(out_root, "daily"), exist_ok=True)
    files = find_input_files()
    if not files:
        print("no V*.csv / V*.xlsx one-minute files found -- nothing to do.")
        return
    log, data, stems, rows, diff_rows = [], {}, {}, [], []
    for f in files:
        try:
            day, df = load_day(f, log)
            data[day] = df
            stems[day] = os.path.splitext(os.path.basename(f))[0]
            for i in TC_USED:
                s = df[f"TC{i}_raw"].dropna()
                rows.append(dict(date=day, channel=f"TC{i}", role=ROLE.get(f"TC{i}", "not used"),
                                 n=len(s), min=s.min(), mean=s.mean(), max=s.max()))
            print(f"loaded {f}: {day}, {len(df)} open-circuit records")
        except Exception as e:
            log.append(f"{f}: SKIPPED -- {type(e).__name__}: {e}\n{traceback.format_exc()}")
            print(f"{f}: SKIPPED -- {e}")

    for day in sorted(data):
        df, stem = data[day], stems[day]
        try:
            fig_overview(df, day, os.path.join(out_root, "daily", f"{stem}_overview.png"))
            if day in HYBRID_DAYS:
                diff_rows.append(fig_difference_day(df, day, os.path.join(out_root, "daily", f"{stem}_difference.png")))
            if day in TEG_DAYS:
                fig_teg(df, day, os.path.join(out_root, "daily", f"{stem}_teg.png"))
            print(f"{stem}: figures written")
        except Exception as e:
            log.append(f"{stem}: figure failed -- {type(e).__name__}: {e}\n{traceback.format_exc()}")
            print(f"{stem}: figure failed -- {e}")

    days = sorted(data)
    try:
        fig_all_days(days, data, os.path.join(out_root, "all_days_front_ambient.png"), "front")
        fig_all_days(days, data, os.path.join(out_root, "all_days_rear_ambient.png"), "rear")
        hyb = [d for d in sorted(HYBRID_DAYS) if d in data]
        if hyb:
            fig_pcm(hyb, data, os.path.join(out_root, "pcm_hybrid_days.png"))
    except Exception as e:
        log.append(f"summary figures failed -- {type(e).__name__}: {e}\n{traceback.format_exc()}")
        print(f"summary figures failed -- {e}")

    if diff_rows:
        pd.DataFrame(diff_rows).to_csv(os.path.join(out_root, "hybrid_difference_summary.csv"), index=False, encoding="utf-8")
    pd.DataFrame(rows).to_csv(os.path.join(out_root, "temperature_summary.csv"), index=False, encoding="utf-8")
    with open(os.path.join(out_root, "batch_log.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log) if log else "no warnings.\n")
    print(f"done. output in {out_root}/")


if __name__ == "__main__":
    main()
