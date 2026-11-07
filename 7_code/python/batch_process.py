"""
Batch pipeline: reads every sweep stored in one or more source workbooks
(each with all its sweeps in one sheet, every sweep block introduced by a
"Sweep N" marker row -- e.g. S0912.xlsx, S0913.xlsx, ...) and, for each
sweep in each file, produces the same I-V / P-V figure as the single-sweep
PV1/PV2/TEG scripts -- PV1 and PV2 fitted with the single-exponential diode
model, TEG fitted with the closed-form linear (Thevenin) model -- using the
same styling, the same device-datasheet-only uncertainty convention, and
the same sweep-metadata subtitle (sweep number, real date, start/end time,
mean BPW34 over the fitted range).

Which file(s) to process:
  - No arguments: every *.xlsx file found in the current folder is
    processed (so just drop a new file like S0913.xlsx next to this
    script and S0912.xlsx and re-run -- no editing needed).
  - Explicit arguments: `python3 batch_process.py S0913.xlsx` processes
    only the file(s) named.

This is a generalization of plot_pv1_perfect.py / plot_teg_perfect.py: the
fitting and plotting logic is written once as reusable functions and looped
over every (file, sweep, source) combination, rather than being hand-run
per file. A sweep/source combination that fails (too little signal, a
degenerate fit, etc.) is logged and skipped rather than stopping the whole
batch.

Outputs (under batch_output/<file-stem>/, one subfolder per input file --
nothing is written directly under batch_output/ itself):
  figures/sweepNN_<SOURCE>.png     -- one figure per sweep per source
  summary_all_sweeps.csv/.xlsx     -- Voc/Isc/Vmp/Imp/Pmp/Rin/R2/RMSE etc. for every sweep x source
  summary_PV1.csv/.xlsx            -- same columns as above, filtered to PV1 rows only
  summary_PV2.csv/.xlsx            -- same columns as above, filtered to PV2 rows only
  summary_TEG.csv/.xlsx            -- same columns as above, filtered to TEG rows only
  captions_all_sweeps.txt          -- generated figure caption text, one block per sweep x source
  pwm_ranges_template.csv          -- the PWM range actually used for every sweep x source
  batch_log.txt                    -- any warnings/skips encountered
  <stem>_PV1_all_sweeps.pdf, _PV2_..., _TEG_...  -- every PV1 (or PV2/TEG) figure combined into
                                     one multi-page PDF, one page per sweep (needs img2pdf)
  <stem>_all_sweeps_by_sweep.pdf   -- every figure combined into one PDF ordered sweep-by-sweep
                                     (Sweep 1 PV1, Sweep 1 PV2, Sweep 1 TEG, Sweep 2 PV1, ...)

Manual PWM-range override, per file: a file named
pwm_ranges_override_<file-stem>.csv (e.g. pwm_ranges_override_S0912.csv)
sitting next to this script, with columns sweep, source, PWM_lo, PWM_hi --
see load_pwm_overrides() below.
"""

import os
import sys
import glob
import traceback
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import medfilt
from scipy.optimize import least_squares, brentq
from matplotlib.ticker import MaxNLocator, AutoMinorLocator, FixedLocator, FormatStrFormatter

# Windows consoles/terminals often default to a legacy codepage (cp1252 or
# similar) that can't represent the special characters this script prints
# and writes (Omega, superscript 2, micro, plus-minus, degree, etc.),
# raising UnicodeEncodeError. Force UTF-8 for stdout/stderr and fall back
# gracefully (replacing anything still unrepresentable) rather than crash;
# every file this script writes also passes encoding="utf-8" explicitly.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Palette / style -- identical to the single-sweep scripts.
# ---------------------------------------------------------------------------
COL_RAW    = "#b7d3f6"
COL_MODEL  = "#2a78d6"
INK        = "#0b0b0b"
INK_MUTED  = "#3a3a38"  # darkened from #52514e -- the old mid-gray lost too much contrast at small font sizes
GRID       = "#e1e0d9"
AXIS       = "#c3c2b7"

BORDER      = "black"
GRID_MAJOR  = "#595959"
GRID_MINOR  = "#d9d9d9"

DOT_VOC = "#1baf7a"
DOT_ISC = "#d62728"
DOT_MPP = "#eda100"

DOT_PLOTTED   = "black"
DOT_UNPLOTTED = "#bdbdbd"

MARK_VOC = dict(marker="*", s=110, facecolor=DOT_VOC, edgecolor=INK, linewidth=0.6, zorder=6, clip_on=False)
MARK_ISC = dict(marker="x", s=70, facecolor=DOT_ISC, linewidth=1.8, zorder=6, clip_on=False)
MARK_MPP = dict(marker="o", s=30, facecolor=DOT_MPP, edgecolor=INK, linewidth=0.8, zorder=7, clip_on=False)
CENTER_DOT = dict(marker="o", s=6, facecolor=INK, edgecolor="none", zorder=7.5, clip_on=False)

plt.rcParams.update({
    "font.family": "Times New Roman",
    # Make mathtext ($...$) render in real Times New Roman too (roman AND
    # italic), instead of matplotlib's default math font -- this is what
    # lets a label like "$Voc$" come out as italic Times New Roman rather
    # than switching to a different-looking math font.
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
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "font.size": 10.5,
    "xtick.labelsize": 11.5,   # explicit bump -- was inheriting a smaller default tick label size
    "ytick.labelsize": 11.5,
})

# ---------------------------------------------------------------------------
# Experiment metadata that doesn't vary sweep to sweep -- set this once and
# it's stamped on every figure's subtitle and every generated caption.
# TODO: fill in with the real experiment location (e.g. paste the Google
# Maps coordinates/link here) -- left blank for now, in which case the
# location line is simply skipped rather than printed empty.
# ---------------------------------------------------------------------------
LOCATION = "6.767360° N, 79.884191° E (Moratuwa, Sri Lanka)"

# ---------------------------------------------------------------------------
# Device/sensor error models (same convention as the single-sweep scripts:
# instrument-datasheet accuracy only, applied directly to each reported
# value -- no bootstrap/covariance).
# ---------------------------------------------------------------------------
INA219_V_PCT, INA219_V_LSB = 0.005, 0.004       # V,  +/-0.5% + 4 mV LSB (12-bit bus ADC)
INA219_PCT,   INA219_LSB_MA = 0.005, 0.1        # mA, +/-0.5% + 0.1 mA LSB (calibration-dependent)

# TEG channel: PLACEHOLDER, same caveat as plot_teg_perfect.py -- INA219's
# 4 mV LSB would swamp a ~30 mV signal, so a separate, more sensitive channel
# is assumed here pending the actual sensor datasheet.
SENSOR_V_PCT, SENSOR_V_LSB_MV = 0.005, 0.1      # mV
SENSOR_I_PCT, SENSOR_I_LSB_MA = 0.005, 0.05     # mA


def ina219_v_err(V):
    return INA219_V_PCT * np.abs(V) + INA219_V_LSB


def ina219_i_err(I):
    return INA219_PCT * np.abs(I) + INA219_LSB_MA


def teg_v_err(V_mV):
    return SENSOR_V_PCT * np.abs(V_mV) + SENSOR_V_LSB_MV


def teg_i_err(I):
    return SENSOR_I_PCT * np.abs(I) + SENSOR_I_LSB_MA


# ---------------------------------------------------------------------------
# Source definitions: which columns to read, which fit family to use, and
# which units/error-model apply. One entry per source, looped for every
# sweep.
# ---------------------------------------------------------------------------
SOURCES = [
    dict(name="PV1", title="PV1", V_col="V1_PV1(V)", I_col="I1_PV1(mA)", P_col="P1_PV1(mW)",
         fit_kind="diode", v_scale=1.0, v_unit="V", p_unit="mW",
         v_err_fn=ina219_v_err, i_err_fn=ina219_i_err,
         err_desc=f"the INA219 current/power monitor's datasheet accuracy: "
                   f"V ±({INA219_V_PCT:.1%} of reading + {INA219_V_LSB*1000:.0f} mV), "
                   f"I ±({INA219_PCT:.1%} of reading + {INA219_LSB_MA} mA)"),
    dict(name="PV2", title="PV2", V_col="V2_PV2(V)", I_col="I2_PV2(mA)", P_col="P2_PV2(mW)",
         fit_kind="diode", v_scale=1.0, v_unit="V", p_unit="mW",
         v_err_fn=ina219_v_err, i_err_fn=ina219_i_err,
         err_desc=f"the INA219 current/power monitor's datasheet accuracy: "
                   f"V ±({INA219_V_PCT:.1%} of reading + {INA219_V_LSB*1000:.0f} mV), "
                   f"I ±({INA219_PCT:.1%} of reading + {INA219_LSB_MA} mA)"),
    dict(name="TEG", title="TEG", V_col="V_TEG(V)", I_col="I_TEG(mA)", P_col="P_TEG(mW)",
         fit_kind="linear", v_scale=1000.0, v_unit="mV", p_unit="µW",
         v_err_fn=teg_v_err, i_err_fn=teg_i_err,
         err_desc=f"the measurement channel's assumed accuracy (PLACEHOLDER pending the actual "
                   f"sensor datasheet): V ±({SENSOR_V_PCT:.1%} of reading + {SENSOR_V_LSB_MV} mV), "
                   f"I ±({SENSOR_I_PCT:.1%} of reading + {SENSOR_I_LSB_MA} mA)"),
]

SLOPE_FRACTION_START = 0.0005
MIN_FIT_POINTS = 5
MAX_SLOPE_FRACTION = 0.05


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_all_sweeps(path):
    raw_full = pd.read_excel(path, sheet_name=0, header=0)
    marker_mask = raw_full["Date"].apply(lambda v: isinstance(v, str) and v.strip().lower().startswith("sweep"))
    marker_positions = raw_full.index[marker_mask].tolist()
    return raw_full, marker_positions


def load_pwm_overrides(base_path):
    """
    Optional manual PWM-range override file. If present, a row with a given
    (sweep, source) and non-blank PWM_LO/PWM_HI skips auto-knee-detection
    entirely for that sweep x source and uses the given range as-is instead
    -- for the ~20% of sweeps where the automatic slope-threshold method
    picks a range that doesn't look right on inspection.

    base_path is the override file's path WITHOUT an extension (e.g.
    "pwm_ranges_override_S0912") -- both "<base_path>.csv" and
    "<base_path>.xlsx" are accepted (checked in that order), so it doesn't
    matter whether you built the file as a CSV or as an actual Excel
    workbook.

    Expected columns (case-insensitive): sweep, source, PWM_LO, PWM_HI.
    source must be one of PV1 / PV2 / TEG. Rows with a blank/missing
    PWM_LO or PWM_HI are ignored (that sweep x source keeps auto-detection).
    """
    csv_path = base_path + ".csv"
    xlsx_path = base_path + ".xlsx"
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        used_path = csv_path
    elif os.path.exists(xlsx_path):
        df = pd.read_excel(xlsx_path)
        used_path = xlsx_path
    else:
        return {}, None

    df.columns = [c.strip().lower() for c in df.columns]
    overrides = {}
    for _, row in df.iterrows():
        if pd.isna(row.get("pwm_lo")) or pd.isna(row.get("pwm_hi")):
            continue
        sweep = int(row["sweep"])
        source = str(row["source"]).strip().upper()
        overrides[(sweep, source)] = (int(row["pwm_lo"]), int(row["pwm_hi"]))
    return overrides, used_path


def get_sweep_block(raw_full, marker_positions, sweep_number):
    start_pos = marker_positions[sweep_number - 1] + 1
    end_pos = marker_positions[sweep_number] if sweep_number < len(marker_positions) else len(raw_full)
    raw = raw_full.iloc[start_pos:end_pos].reset_index(drop=True)
    raw = raw.dropna(subset=["PWM"]).reset_index(drop=True)
    sweep_date = pd.Timestamp(raw["Date"].iloc[0]).strftime("%Y-%m-%d")
    start_time = pd.Timestamp(raw["Time"].iloc[0]).strftime("%H:%M:%S")
    end_time = pd.Timestamp(raw["Time"].iloc[-1]).strftime("%H:%M:%S")
    return raw, sweep_date, start_time, end_time


# ---------------------------------------------------------------------------
# Auto-knee detection, with an adaptive fallback: if the starting slope
# threshold captures too few points (weak/noisy sweep), the threshold is
# loosened (doubled) up to MAX_SLOPE_FRACTION before giving up.
# ---------------------------------------------------------------------------
def auto_knee(pwm, V_d):
    order = np.argsort(pwm)
    pwm_sorted, V_sorted = pwm[order], V_d[order]
    dV_dPWM = np.gradient(V_sorted, pwm_sorted)
    peak = np.max(np.abs(dV_dPWM))
    if not np.isfinite(peak) or peak <= 0:
        raise ValueError("no voltage variation across the PWM sweep (peak slope <= 0)")

    frac = SLOPE_FRACTION_START
    while frac <= MAX_SLOPE_FRACTION:
        threshold = frac * peak
        knee_idx = np.where(np.abs(dV_dPWM) >= threshold)[0]
        if len(knee_idx) >= MIN_FIT_POINTS:
            PWM_LO, PWM_HI = int(pwm_sorted[knee_idx[0]]), int(pwm_sorted[knee_idx[-1]])
            return PWM_LO, PWM_HI, peak, frac
        frac *= 2
    raise ValueError(f"could not find >= {MIN_FIT_POINTS} knee-region points even at "
                      f"slope_fraction={MAX_SLOPE_FRACTION:.3%}")


# ---------------------------------------------------------------------------
# Fit families
# ---------------------------------------------------------------------------
def fit_diode_model(V_d, I_d, P_d, V_fit_data, I_fit_data):
    Voc_guess = float(V_d.max())
    Isc_guess = float(I_fit_data.max())
    if Isc_guess <= 0 or Voc_guess <= 0:
        raise ValueError("no usable signal (Isc_guess or Voc_guess <= 0)")

    mpp_guess_idx = np.argmax(P_d)
    Vmp_guess, Imp_guess = float(V_d[mpp_guess_idx]), float(I_d[mpp_guess_idx])

    ratio = 1 - Imp_guess / Isc_guess
    if not np.isfinite(ratio) or ratio <= 0:
        ratio = 1e-3
    with np.errstate(divide="ignore", invalid="ignore"):
        C2_guess = (Vmp_guess / Voc_guess - 1) / np.log(ratio)
    if not np.isfinite(C2_guess) or C2_guess <= 0:
        C2_guess = 0.05
    C1_guess = (1 - Imp_guess / Isc_guess) * np.exp(-Vmp_guess / (C2_guess * Voc_guess))
    if not np.isfinite(C1_guess) or C1_guess <= 0:
        C1_guess = 1e-6

    def I_model_params(params, V):
        Isc, Voc, C1, C2 = params
        return Isc * (1 - C1 * (np.exp(V / (C2 * Voc)) - 1))

    def residuals(params):
        return I_model_params(params, V_fit_data) - I_fit_data

    Isc_lo, Isc_hi = max(1e-6, Isc_guess * 0.3), Isc_guess * 3 + 1
    Voc_lo, Voc_hi = max(1e-6, Voc_guess * 0.5), Voc_guess * 3 + 1
    C2_guess = min(max(C2_guess, 2e-4), 1.9)
    C1_guess = min(max(C1_guess, 1e-14), 9e-2)  # clip inside the C1 bounds [1e-15, 1e-1]

    fit = least_squares(
        residuals,
        x0=[Isc_guess, Voc_guess, C1_guess, C2_guess],
        bounds=([Isc_lo, Voc_lo, 1e-15, 1e-4], [Isc_hi, Voc_hi, 1e-1, 2.0]),
        method="trf", loss="linear",
        xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=200_000,
    )
    Isc, Voc_param, C1, C2 = fit.x
    I_fit = I_model_params(fit.x, V_fit_data)
    resid = I_fit_data - I_fit
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    ss_tot = float(np.sum((I_fit_data - I_fit_data.mean()) ** 2))
    r2 = float(1 - np.sum(resid ** 2) / ss_tot) if ss_tot > 0 else float("nan")

    def I_model(V):
        return Isc * (1 - C1 * (np.exp(V / (C2 * Voc_param)) - 1))

    hi = 3 * Voc_param
    if I_model(hi) >= 0:
        hi = 10 * Voc_param
    Voc = brentq(I_model, 0, hi)

    V_model = np.linspace(0, Voc, 4000)
    I_model_curve = np.clip(I_model(V_model), 0, None)
    P_model_curve = V_model * I_model_curve
    mpp_idx = np.argmax(P_model_curve)
    Vmp, Imp, Pmp = float(V_model[mpp_idx]), float(I_model_curve[mpp_idx]), float(P_model_curve[mpp_idx])

    return dict(Isc=float(Isc), Voc=float(Voc), Vmp=Vmp, Imp=Imp, Pmp=Pmp, Rin=None,
                r2=r2, rmse=rmse, V_model=V_model, I_model_curve=I_model_curve,
                P_model_curve=P_model_curve,
                fit_desc="nonlinear least squares (diode model)",
                fit_desc_short="diode-model fit")


def fit_linear_model(V_fit_data, I_fit_data):
    slope, intercept = np.polyfit(V_fit_data, I_fit_data, 1)
    if slope == 0 or not np.isfinite(slope):
        raise ValueError("degenerate linear fit (zero/non-finite slope)")
    Isc = float(intercept)
    Voc = float(-intercept / slope)
    Rin = float(-1.0 / slope)
    if not np.isfinite(Voc) or Voc <= 0 or not np.isfinite(Rin):
        raise ValueError("degenerate linear fit (non-physical Voc/Rin)")

    I_fit = slope * V_fit_data + intercept
    resid = I_fit_data - I_fit
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    ss_tot = float(np.sum((I_fit_data - I_fit_data.mean()) ** 2))
    r2 = float(1 - np.sum(resid ** 2) / ss_tot) if ss_tot > 0 else float("nan")

    def I_model(V):
        return np.clip(Isc * (1 - V / Voc), 0, None)

    V_model = np.linspace(0, Voc, 4000)
    I_model_curve = I_model(V_model)
    P_model_curve = V_model * I_model_curve
    Vmp, Imp = Voc / 2.0, Isc / 2.0
    Pmp = Vmp * Imp

    return dict(Isc=Isc, Voc=Voc, Vmp=Vmp, Imp=Imp, Pmp=Pmp, Rin=Rin,
                r2=r2, rmse=rmse, V_model=V_model, I_model_curve=I_model_curve,
                P_model_curve=P_model_curve,
                fit_desc="closed-form ordinary-least-squares line (linear/Thevenin model)",
                fit_desc_short="linear (Thevenin) fit")


# ---------------------------------------------------------------------------
# Shared axis styling (identical to the single-sweep scripts).
# ---------------------------------------------------------------------------
def style_axes(ax, xdata, ydata, nbins=7):
    steps = [1, 2, 2.5, 4, 5, 6.25, 8, 10]
    x_ticks = MaxNLocator(nbins=nbins, steps=steps).tick_values(*xdata)
    y_ticks = MaxNLocator(nbins=nbins, steps=steps).tick_values(*ydata)
    ax.set_xlim(x_ticks[0], x_ticks[-1])
    ax.set_ylim(y_ticks[0], y_ticks[-1])
    ax.xaxis.set_major_locator(FixedLocator(x_ticks))
    ax.yaxis.set_major_locator(FixedLocator(y_ticks))
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.1f"))

    for spine in ("top", "right", "left", "bottom"):
        ax.spines[spine].set_visible(True)
        ax.spines[spine].set_color(BORDER)
    ax.set_box_aspect(1)

    ax.xaxis.set_minor_locator(AutoMinorLocator(10))
    ax.yaxis.set_minor_locator(AutoMinorLocator(10))
    ax.tick_params(which="both", direction="in", color=BORDER,
                    top=False, right=False, bottom=True, left=True)
    ax.tick_params(which="major", length=5)
    ax.tick_params(which="minor", length=3)
    ax.xaxis.grid(which="minor", color=GRID_MINOR, linewidth=0.5, linestyle="-", zorder=0.3)
    ax.yaxis.grid(which="minor", color=GRID_MINOR, linewidth=0.5, linestyle="-", zorder=0.3)
    ax.yaxis.grid(which="major", color=GRID_MAJOR, linewidth=0.8, linestyle="-", zorder=0.5)
    ax.xaxis.grid(which="major", color=GRID_MAJOR, linewidth=0.8, linestyle="-", zorder=0.7)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------
# Figure + caption generation, generalized over source/fit-kind.
# ---------------------------------------------------------------------------
def make_figure(out_path, src, fit, V_raw, I_raw, P_raw, fit_mask, PWM_LO, PWM_HI,
                 Voc, Isc, Vmp, Imp, Pmp, Voc_err, Isc_err, Vmp_err, Imp_err, Pmp_err, FF,
                 sweep_number, sweep_date, start_time, end_time, bpw_avg_fit):
    v_unit, p_unit = src["v_unit"], src["p_unit"]
    n_fit = int(fit_mask.sum())

    fig, (ax_iv, ax_pv) = plt.subplots(2, 1, figsize=(8.27, 11.69))
    STAT_FONTSIZE = 11

    # ---- Build the stat-line labels so every "=" lines up in one column ----
    # Voc/Isc/Vmp/Imp/Pmp are italic (real Times New Roman italic, via
    # mathtext "$...$" plus the mathtext.it rcParam set above); FF and Rin
    # stay upright. Times New Roman is a proportional font, so equal-width
    # padding can't be done by counting characters -- instead each bare
    # label is measured (actual rendered pixel width) and the shorter ones
    # are padded with enough spaces (measured in the same font) to match
    # the widest label, so "=" lands in the same spot on every row no
    # matter which label or value it belongs to.
    raw_labels = {"Voc": r"$Voc$", "Isc": r"$Isc$", "Vmp": r"$Vmp$",
                  "Imp": r"$Imp$", "Pmp": r"$Pmp$", "FF": "FF"}
    if fit["Rin"] is not None:
        raw_labels["Rin"] = "Rin"

    fig.canvas.draw()  # make sure a renderer exists to measure text with
    renderer = fig.canvas.get_renderer()

    def text_width(s):
        t = ax_iv.text(0, 0, s, fontsize=STAT_FONTSIZE, alpha=0)
        w = t.get_window_extent(renderer=renderer).width
        t.remove()
        return w

    label_widths = {key: text_width(s) for key, s in raw_labels.items()}
    space_width = text_width(" ")
    max_label_w = max(label_widths.values())

    def stat_line(key, value_str):
        pad_n = round((max_label_w - label_widths[key]) / space_width) if space_width > 0 else 0
        pad_n = max(0, pad_n)
        return f"{raw_labels[key]}{' ' * pad_n} = {value_str}"

    LABEL_VOC = stat_line("Voc", f"{Voc:.3f} ± {Voc_err:.3f} {v_unit}")
    LABEL_ISC = stat_line("Isc", f"{Isc:.3f} ± {Isc_err:.3f} mA")
    LABEL_VMP = stat_line("Vmp", f"{Vmp:.3f} ± {Vmp_err:.3f} {v_unit}")
    LABEL_IMP = stat_line("Imp", f"{Imp:.3f} ± {Imp_err:.3f} mA")
    LABEL_PMP = stat_line("Pmp", f"{Pmp:.2f} ± {Pmp_err:.2f} {p_unit}")
    LABEL_FF = stat_line("FF", f"{FF:.3f}")

    if fit["Rin"] is not None:
        LABEL_MODEL = "model curve (linear)"
        LABEL_RIN = stat_line("Rin", f"{fit['Rin']:.3f} Ω")
    else:
        LABEL_MODEL = "model curve"
        LABEL_RIN = None

    fit_kind_label = "linear fit" if fit["Rin"] is not None else "fit"
    fig.suptitle(
        f"{src['title']} -- IV and P-V curve ({fit_kind_label} to PWM in [{PWM_LO}, {PWM_HI}] only, {n_fit} points)",
        fontsize=13, fontweight="bold", y=0.978)

    V_model, I_model_curve, P_model_curve = fit["V_model"], fit["I_model_curve"], fit["P_model_curve"]

    # ---------------- IV curve ----------------
    ax_iv.scatter(V_raw[~fit_mask], I_raw[~fit_mask], s=16, facecolor=DOT_UNPLOTTED, edgecolor="none",
                  alpha=0.5, zorder=2, label=f"PWM outside [{PWM_LO},{PWM_HI}] (excluded)")
    ax_iv.scatter(V_raw[fit_mask], I_raw[fit_mask], s=18, facecolor=DOT_PLOTTED, edgecolor="none",
                  alpha=1.0, zorder=2, label=f"PWM in [{PWM_LO},{PWM_HI}] (fitted)")
    ax_iv.plot(V_model, I_model_curve, color=COL_MODEL, linewidth=1, zorder=3,
               solid_capstyle="round", solid_joinstyle="round", label=LABEL_MODEL)
    if LABEL_RIN is not None:
        ax_iv.plot([], [], linestyle="none", marker="None", label=LABEL_RIN)
    ax_iv.scatter([Voc], [0], **MARK_VOC, label=LABEL_VOC)
    ax_iv.scatter([0], [Isc], **MARK_ISC, label=LABEL_ISC)
    ax_iv.scatter([Vmp], [Imp], **MARK_MPP, label="MPP")
    ax_iv.scatter([Voc], [0], **CENTER_DOT)
    ax_iv.scatter([0], [Isc], **CENTER_DOT)
    ax_iv.scatter([Vmp], [Imp], **CENTER_DOT)
    # No-marker rows so each stat gets its own legend line -- this is what
    # keeps the MPP marker level with the word "MPP" instead of being
    # centered against a whole multi-line block underneath it.
    ax_iv.plot([], [], linestyle="none", marker="None", label=LABEL_VMP)
    ax_iv.plot([], [], linestyle="none", marker="None", label=LABEL_IMP)
    ax_iv.plot([], [], linestyle="none", marker="None", label=LABEL_PMP)
    ax_iv.plot([], [], linestyle="none", marker="None", label=LABEL_FF)
    ax_iv.axvline(Vmp, color=AXIS, lw=0.8, ls=(0, (3, 3)), zorder=1)
    ax_iv.axhline(Imp, color=AXIS, lw=0.8, ls=(0, (3, 3)), zorder=1)

    ax_iv.set_xlabel(f"Voltage / {v_unit}", fontsize=12)
    ax_iv.set_ylabel("Current / mA", fontsize=12)
    ax_iv.set_title("I-V curve", fontsize=12, color=INK_MUTED, pad=10)
    iv_xdata = (0, max(Voc, V_raw.max(), V_model.max()))
    iv_ydata = (0, max(Isc, I_raw.max(), I_model_curve.max()))
    style_axes(ax_iv, iv_xdata, iv_ydata)
    ax_iv.legend(loc="center left", bbox_to_anchor=(1.06, 0.5), ncol=1, frameon=False, fontsize=11)

    # ---------------- PV curve ----------------
    ax_pv.scatter(V_raw[~fit_mask], P_raw[~fit_mask], s=16, facecolor=DOT_UNPLOTTED, edgecolor="none",
                  alpha=0.5, zorder=2, label=f"PWM outside [{PWM_LO},{PWM_HI}] (excluded)")
    ax_pv.scatter(V_raw[fit_mask], P_raw[fit_mask], s=18, facecolor=DOT_PLOTTED, edgecolor="none",
                  alpha=1.0, zorder=2, label=f"PWM in [{PWM_LO},{PWM_HI}] (fitted)")
    ax_pv.plot(V_model, P_model_curve, color=COL_MODEL, linewidth=1, zorder=3,
               solid_capstyle="round", solid_joinstyle="round", label=LABEL_MODEL)
    if LABEL_RIN is not None:
        ax_pv.plot([], [], linestyle="none", marker="None", label=LABEL_RIN)
    ax_pv.scatter([Voc], [0], **MARK_VOC, label=LABEL_VOC)
    ax_pv.scatter([0], [0], **MARK_ISC, label=LABEL_ISC)
    ax_pv.scatter([Vmp], [Pmp], **MARK_MPP, label="MPP")
    ax_pv.scatter([Voc], [0], **CENTER_DOT)
    ax_pv.scatter([0], [0], **CENTER_DOT)
    ax_pv.scatter([Vmp], [Pmp], **CENTER_DOT)
    ax_pv.plot([], [], linestyle="none", marker="None", label=LABEL_VMP)
    ax_pv.plot([], [], linestyle="none", marker="None", label=LABEL_IMP)
    ax_pv.plot([], [], linestyle="none", marker="None", label=LABEL_PMP)
    ax_pv.plot([], [], linestyle="none", marker="None", label=LABEL_FF)
    ax_pv.axvline(Vmp, color=AXIS, lw=0.8, ls=(0, (3, 3)), zorder=1)
    ax_pv.axhline(Pmp, color=AXIS, lw=0.8, ls=(0, (3, 3)), zorder=1)

    pmax = max(P_raw.max(), Pmp)
    span = pmax if pmax > 0 else 1

    ax_pv.set_xlabel(f"Voltage / {v_unit}", fontsize=12)
    ax_pv.set_ylabel(f"Power / {p_unit}", fontsize=12)
    ax_pv.set_title("P-V curve", fontsize=12, color=INK_MUTED, pad=10)
    pv_xdata = (0, max(Voc, V_raw.max(), V_model.max()))
    pv_ydata = (0, pmax + 0.08 * span)
    style_axes(ax_pv, pv_xdata, pv_ydata)
    ax_pv.legend(loc="center left", bbox_to_anchor=(1.06, 0.5), ncol=1, frameon=False, fontsize=11)

    rin_bit = f", Rin={fit['Rin']:.3f} $\\Omega$" if fit["Rin"] is not None else ""
    fig.text(0.5, 0.945,
              f"{fit['fit_desc_short']} over {n_fit} points in PWM [{PWM_LO},{PWM_HI}] -- "
              f"R²={fit['r2']:.4f}, RMSE={fit['rmse']:.3f} mA{rin_bit}",
              ha="center", fontsize=10.3, color=INK_MUTED)
    fig.text(0.5, 0.925,
              f"Sweep {sweep_number}  --  {sweep_date}  --  {start_time} to {end_time}  --  "
              f"mean BPW34 (fitted range) = {bpw_avg_fit:.3f} V",
              ha="center", fontsize=9.5, color=INK_MUTED)
    if LOCATION:
        fig.text(0.5, 0.907, f"Location: {LOCATION}",
                  ha="center", fontsize=9.5, color=INK_MUTED)

    fig.subplots_adjust(left=0.11, right=0.65, top=0.86, bottom=0.05, hspace=0.19)
    # bbox_inches="tight" expands the saved canvas to fit every artist,
    # including the legend text -- this is what stops the legend (or any
    # subtitle line) from being clipped at the page edge when a sweep's
    # PWM numbers happen to make a label a bit longer/shorter than others.
    fig.savefig(out_path, dpi=300, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def write_excel_summary(df, path):
    """A real .xlsx version of a summary table (not just CSV renamed) --
    auto-sized columns and the header row frozen, so it opens in Excel
    ready to scroll through rather than needing a manual autofit first."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="summary")
        ws = writer.sheets["summary"]
        for col_idx, col in enumerate(df.columns, start=1):
            max_len = len(str(col))
            for v in df[col].tolist()[:500]:
                s = "" if pd.isna(v) else str(v)
                max_len = max(max_len, len(s))
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 40)
        ws.freeze_panes = "A2"


def bundle_source_pdfs(fig_dir, out_dir, stem, summary_df):
    """
    Combines every successfully-generated figure for each source (PV1/PV2/
    TEG) into one multi-page PDF, one page per sweep, sorted by sweep
    number -- e.g. S0912_PV1_all_sweeps.pdf with one page per PV1 figure.
    Sweeps that were skipped (no figure produced) simply don't get a page,
    rather than leaving a blank one. Needs the img2pdf package -- if it
    isn't installed, this step is skipped with a one-line notice rather
    than crashing the whole batch (the PNG figures are unaffected either
    way).
    """
    try:
        import img2pdf
        import logging
        logging.getLogger("img2pdf").setLevel(logging.ERROR)  # quiet its per-image alpha-channel notices
    except ImportError:
        print(f"[{stem}] img2pdf not installed -- skipping combined PDF export "
              f"(run: pip install img2pdf)")
        return

    for src in SOURCES:
        ok_rows = summary_df[(summary_df["source"] == src["name"]) & (summary_df["status"] == "ok")]
        ok_rows = ok_rows.sort_values("sweep")
        files = [os.path.join(fig_dir, fn) for fn in ok_rows["figure"].tolist()]
        if not files:
            continue
        pdf_path = os.path.join(out_dir, f"{stem}_{src['name']}_all_sweeps.pdf")
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(files))
        print(f"[{stem}] combined PDF: {pdf_path}  ({len(files)} pages)")

    # One more PDF ordered sweep-by-sweep instead of source-by-source --
    # Sweep 1 PV1, Sweep 1 PV2, Sweep 1 TEG, Sweep 2 PV1, ... -- so all
    # three figures for a given sweep sit together, page after page, in
    # the same order the sources are defined (PV1, PV2, TEG).
    source_order = {src["name"]: i for i, src in enumerate(SOURCES)}
    ok_rows = summary_df[summary_df["status"] == "ok"].copy()
    ok_rows["_src_order"] = ok_rows["source"].map(source_order)
    ok_rows = ok_rows.sort_values(["sweep", "_src_order"])
    files = [os.path.join(fig_dir, fn) for fn in ok_rows["figure"].tolist()]
    if files:
        pdf_path = os.path.join(out_dir, f"{stem}_all_sweeps_by_sweep.pdf")
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(files))
        print(f"[{stem}] combined PDF (by sweep): {pdf_path}  ({len(files)} pages)")


def make_caption(src, fit, PWM_LO, PWM_HI, n_fit, Voc, Isc, Vmp, Imp, Pmp, FF,
                  Voc_err, Isc_err, Vmp_err, Imp_err, Pmp_err,
                  sweep_number, sweep_date, start_time, end_time, bpw_avg_fit):
    v_unit, p_unit = src["v_unit"], src["p_unit"]
    rin_bit = f", internal resistance Rin = {fit['Rin']:.3f} Ω" if fit["Rin"] is not None else ""
    location_bit = f" Location: {LOCATION}." if LOCATION else ""
    return (
        f"Figure X. Measured and modeled I-V and P-V characteristics of {src['title']} (Sweep {sweep_number}, "
        f"{sweep_date}, {start_time}-{end_time}; mean BPW34 irradiance-proxy reading over the fitted range = "
        f"{bpw_avg_fit:.3f} V).{location_bit} The solid curve is a {fit['fit_desc']}, fitted to the {n_fit} "
        f"samples in the PWM range [{PWM_LO}, {PWM_HI}] (R² = {fit['r2']:.4f}, RMSE = {fit['rmse']:.3f} mA"
        f"{rin_bit}); filled points were used in the fit, shaded points fall outside this range and are shown "
        f"for reference only. Every reported value's uncertainty is taken from {src['err_desc']}, with power "
        f"uncertainty propagated from those two (P = V x I). Open-circuit voltage V_OC = {Voc:.3f} ± "
        f"{Voc_err:.3f} {v_unit}, short-circuit current I_SC = {Isc:.3f} ± {Isc_err:.3f} mA, fill factor "
        f"FF = {FF:.3f}, and the maximum power point occurs at P_max = {Pmp:.2f} ± {Pmp_err:.2f} {p_unit} "
        f"(V_mp = {Vmp:.3f} ± {Vmp_err:.3f} {v_unit}, I_mp = {Imp:.3f} ± {Imp_err:.3f} mA)."
    )


# ---------------------------------------------------------------------------
# Discover which workbook(s) to process
# ---------------------------------------------------------------------------
def find_input_files():
    if len(sys.argv) > 1:
        return sys.argv[1:]
    files = sorted(glob.glob("*.xlsx"))
    # Excel creates hidden "~$..." lock files for any workbook currently
    # open in Excel -- these aren't real data files and can't be read.
    files = [f for f in files if not os.path.basename(f).startswith("~$")]
    # A manually-created "pwm_ranges_override_<stem>.xlsx" file also matches
    # "*.xlsx" but is PWM-range input, not a sweep-data workbook -- reading
    # it as one crashes with "KeyError: 'Date'" since it has no such column.
    # It's only ever read via load_pwm_overrides(), keyed off each real
    # data file's own stem, so it must never be treated as a data file here.
    files = [f for f in files if not os.path.basename(f).lower().startswith("pwm_ranges_override_")]
    return files


# ---------------------------------------------------------------------------
# Per-file batch loop -- everything for one workbook (all its sweeps, all
# three sources) lands in its own batch_output/<file-stem>/ subfolder.
# ---------------------------------------------------------------------------
def process_file(input_path, base_out_dir):
    stem = os.path.splitext(os.path.basename(input_path))[0]
    out_dir = os.path.join(base_out_dir, stem)
    fig_dir = os.path.join(out_dir, "figures")
    os.makedirs(fig_dir, exist_ok=True)

    raw_full, marker_positions = load_all_sweeps(input_path)
    n_sweeps = len(marker_positions)
    print(f"[{stem}] found {n_sweeps} sweeps in {input_path}")

    OVERRIDE_BASE = f"pwm_ranges_override_{stem}"
    pwm_overrides, override_used_path = load_pwm_overrides(OVERRIDE_BASE)
    if pwm_overrides:
        print(f"loaded {len(pwm_overrides)} manual PWM-range override(s) from {override_used_path}")
    else:
        print(f"no {OVERRIDE_BASE}.csv or .xlsx found (or it has no usable rows) -- "
              f"using auto-knee-detection for every sweep")

    summary_rows = []
    captions = []
    log_lines = []

    for sweep_number in range(1, n_sweeps + 1):
        raw, sweep_date, start_time, end_time = get_sweep_block(raw_full, marker_positions, sweep_number)
        pwm = raw["PWM"].astype(float).to_numpy()
        BPW_raw = raw["V_BPW(V)"].astype(float).to_numpy()

        for src in SOURCES:
            tag = f"[{stem}] Sweep {sweep_number:02d} / {src['name']}"
            try:
                V_raw = raw[src["V_col"]].astype(float).to_numpy() * src["v_scale"]
                I_raw = raw[src["I_col"]].astype(float).to_numpy()
                if src["fit_kind"] == "linear":
                    P_raw = V_raw * I_raw
                else:
                    P_raw = raw[src["P_col"]].astype(float).to_numpy()

                V_d = medfilt(V_raw, 5)
                I_d = medfilt(I_raw, 5)
                P_d = V_d * I_d

                override_key = (sweep_number, src["name"])
                if override_key in pwm_overrides:
                    PWM_LO, PWM_HI = pwm_overrides[override_key]
                    pwm_source = "manual"
                else:
                    PWM_LO, PWM_HI, peak_slope, used_frac = auto_knee(pwm, V_d)
                    pwm_source = "auto"
                fit_mask = (pwm >= PWM_LO) & (pwm <= PWM_HI)
                V_fit_data, I_fit_data = V_d[fit_mask], I_d[fit_mask]
                bpw_avg_fit = float(BPW_raw[fit_mask].mean())

                if src["fit_kind"] == "diode":
                    fit = fit_diode_model(V_d, I_d, P_d, V_fit_data, I_fit_data)
                else:
                    fit = fit_linear_model(V_fit_data, I_fit_data)

                Isc, Voc, Vmp, Imp, Pmp = fit["Isc"], fit["Voc"], fit["Vmp"], fit["Imp"], fit["Pmp"]
                v_err_fn, i_err_fn = src["v_err_fn"], src["i_err_fn"]
                Isc_err = i_err_fn(Isc)
                Voc_err = v_err_fn(Voc)
                Vmp_err = v_err_fn(Vmp)
                Imp_err = i_err_fn(Imp)
                Pmp_err = float(np.sqrt((Imp * Vmp_err) ** 2 + (Vmp * Imp_err) ** 2))

                # Fill factor: how close the real MPP sits to the ideal
                # Voc x Isc rectangle. Voc/Isc/Pmp are already in units
                # that make this dimensionless without any conversion --
                # for PV1/PV2, V(V) x I(mA) = mW = Pmp's own unit; for TEG,
                # V(mV) x I(mA) = uW = Pmp's own unit.
                FF = float(Pmp / (Voc * Isc)) if (Voc > 0 and Isc > 0) else float("nan")

                out_name = f"sweep{sweep_number:02d}_{src['name']}.png"
                out_path = os.path.join(fig_dir, out_name)
                make_figure(out_path, src, fit, V_raw, I_raw, P_raw, fit_mask, PWM_LO, PWM_HI,
                            Voc, Isc, Vmp, Imp, Pmp, Voc_err, Isc_err, Vmp_err, Imp_err, Pmp_err, FF,
                            sweep_number, sweep_date, start_time, end_time, bpw_avg_fit)

                caption = make_caption(src, fit, PWM_LO, PWM_HI, int(fit_mask.sum()), Voc, Isc, Vmp, Imp, Pmp, FF,
                                        Voc_err, Isc_err, Vmp_err, Imp_err, Pmp_err,
                                        sweep_number, sweep_date, start_time, end_time, bpw_avg_fit)
                captions.append(f"--- {tag} ({out_name}) ---\n{caption}\n")

                summary_rows.append(dict(
                    sweep=sweep_number, source=src["name"], date=sweep_date,
                    start_time=start_time, end_time=end_time,
                    PWM_lo=PWM_LO, PWM_hi=PWM_HI, n_fit_points=int(fit_mask.sum()),
                    bpw_avg_fit_V=bpw_avg_fit,
                    Voc=Voc, Voc_err=Voc_err, Isc=Isc, Isc_err=Isc_err,
                    Vmp=Vmp, Vmp_err=Vmp_err, Imp=Imp, Imp_err=Imp_err,
                    Pmp=Pmp, Pmp_err=Pmp_err, FF=FF, Rin_ohm=fit["Rin"],
                    R2=fit["r2"], RMSE_mA=fit["rmse"],
                    v_unit=src["v_unit"], p_unit=src["p_unit"],
                    pwm_source=pwm_source,
                    status="ok", figure=out_name,
                ))
                print(f"{tag}: ok [{pwm_source}]  (Voc={Voc:.3f}{src['v_unit']} Isc={Isc:.3f}mA "
                      f"Pmp={Pmp:.2f}{src['p_unit']} FF={FF:.3f} R2={fit['r2']:.4f})")

            except Exception as e:
                msg = f"{tag}: SKIPPED -- {type(e).__name__}: {e}"
                print(msg)
                log_lines.append(msg)
                log_lines.append(traceback.format_exc())
                summary_rows.append(dict(
                    sweep=sweep_number, source=src["name"], date=sweep_date,
                    start_time=start_time, end_time=end_time,
                    PWM_lo=np.nan, PWM_hi=np.nan, n_fit_points=np.nan,
                    bpw_avg_fit_V=np.nan,
                    Voc=np.nan, Voc_err=np.nan, Isc=np.nan, Isc_err=np.nan,
                    Vmp=np.nan, Vmp_err=np.nan, Imp=np.nan, Imp_err=np.nan,
                    Pmp=np.nan, Pmp_err=np.nan, FF=np.nan, Rin_ohm=np.nan,
                    R2=np.nan, RMSE_mA=np.nan,
                    v_unit=src["v_unit"], p_unit=src["p_unit"],
                    pwm_source="manual" if (sweep_number, src["name"]) in pwm_overrides else "auto",
                    status=f"skipped: {e}", figure="",
                ))

    summary_df = pd.DataFrame(summary_rows)
    summary_path = os.path.join(out_dir, "summary_all_sweeps.csv")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8")
    summary_xlsx_path = os.path.join(out_dir, "summary_all_sweeps.xlsx")
    write_excel_summary(summary_df, summary_xlsx_path)

    # In addition to the combined summary above, also split it out into one
    # summary file per source (summary_PV1.csv/.xlsx, summary_PV2.csv/.xlsx,
    # summary_TEG.csv/.xlsx) -- same columns, just pre-filtered to that
    # source's rows, for anyone who only wants e.g. the TEG numbers without
    # picking through the combined file.
    per_source_paths = []
    for src in SOURCES:
        src_df = summary_df[summary_df["source"] == src["name"]].reset_index(drop=True)
        src_csv_path = os.path.join(out_dir, f"summary_{src['name']}.csv")
        src_df.to_csv(src_csv_path, index=False, encoding="utf-8")
        src_xlsx_path = os.path.join(out_dir, f"summary_{src['name']}.xlsx")
        write_excel_summary(src_df, src_xlsx_path)
        per_source_paths.append((src["name"], src_csv_path, src_xlsx_path))

    # Template for the manual-override file: every sweep x source that was
    # actually run, with the PWM range that was used (auto-detected or
    # already-manual). Copy this to pwm_ranges_override.csv, edit only the
    # rows whose auto-detected range looks wrong on inspection, and leave
    # the rest as-is (or delete rows you don't want to override) -- then
    # re-run the script and those rows will be used verbatim instead of
    # auto-detection.
    template_path = os.path.join(out_dir, "pwm_ranges_template.csv")
    summary_df[["sweep", "source", "PWM_lo", "PWM_hi", "pwm_source", "status", "figure"]].to_csv(
        template_path, index=False, encoding="utf-8")

    captions_path = os.path.join(out_dir, "captions_all_sweeps.txt")
    with open(captions_path, "w", encoding="utf-8") as f:
        f.write("\n".join(captions))

    log_path = os.path.join(out_dir, "batch_log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        if log_lines:
            f.write("\n".join(log_lines))
        else:
            f.write("no warnings -- every sweep x source combination fit successfully.\n")

    bundle_source_pdfs(fig_dir, out_dir, stem, summary_df)

    n_ok = int((summary_df["status"] == "ok").sum())
    n_total = len(summary_df)
    print(f"[{stem}] done: {n_ok}/{n_total} sweep x source figures generated successfully.")
    print(f"[{stem}] summary: {summary_path}  (and {summary_xlsx_path})")
    for src_name, src_csv_path, src_xlsx_path in per_source_paths:
        print(f"[{stem}] {src_name} summary: {src_csv_path}  (and {src_xlsx_path})")
    print(f"[{stem}] captions: {captions_path}")
    print(f"[{stem}] log: {log_path}\n")

    return summary_df


# ---------------------------------------------------------------------------
# Top-level entry point: process every input file, then combine all of
# their summaries (with a "file" column) into one master CSV.
# ---------------------------------------------------------------------------
def main():
    # Always look for input files (and write output) next to this script
    # itself, regardless of what folder the terminal happens to be sitting
    # in when it's launched -- e.g. running it as
    # `python C:\some\other\folder\python.exe D:\project\batch_process.py`
    # from a terminal that's still parked somewhere else would otherwise
    # search that other, unrelated folder for .xlsx files instead.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    base_out_dir = "batch_output"
    os.makedirs(base_out_dir, exist_ok=True)

    input_files = find_input_files()
    if not input_files:
        print(f"no .xlsx files found in {script_dir} (and none given as arguments) -- nothing to do.")
        return
    print(f"processing {len(input_files)} file(s): {', '.join(input_files)}\n")

    # Each file's own summary already lands inside its own
    # batch_output/<stem>/ folder (written by process_file below) -- that's
    # the one to use. This loop no longer also writes a second, combined
    # summary_all_files.csv/.xlsx at the batch_output root, since with a
    # single input file that was just a duplicate of the per-file one.
    for input_path in input_files:
        process_file(input_path, base_out_dir)


if __name__ == "__main__":
    main()
