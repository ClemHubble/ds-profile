"""Terminal rendering for ds-profile output."""

from __future__ import annotations

import math
import os
import shutil
from typing import Any

from .profiler import ColumnProfile, DatasetProfile, DiffResult


# ─── Color / style helpers ───────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

BLACK  = "\033[30m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
MAGENTA= "\033[35m"
CYAN   = "\033[36m"
WHITE  = "\033[37m"

BG_BLUE    = "\033[44m"
BG_MAGENTA = "\033[45m"
BG_CYAN    = "\033[46m"
BG_WHITE   = "\033[47m"

BRIGHT_RED    = "\033[91m"
BRIGHT_GREEN  = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE   = "\033[94m"
BRIGHT_MAGENTA= "\033[95m"
BRIGHT_CYAN   = "\033[96m"
BRIGHT_WHITE  = "\033[97m"

def b(s: str) -> str:
    return f"{BOLD}{s}{RESET}"

def dim(s: str) -> str:
    return f"{DIM}{s}{RESET}"

def color(s: str, c: str) -> str:
    return f"{c}{s}{RESET}"


# ─── Histogram renderer ───────────────────────────────────────────────────────

BARS = " ▁▂▃▄▅▆▇█"

def spark(counts: list[int], width: int = 20) -> str:
    """Render a unicode sparkline histogram."""
    if not counts:
        return dim("(no data)")
    mx = max(counts)
    if mx == 0:
        return "▁" * len(counts)
    chars = []
    for c in counts:
        ratio = c / mx
        idx = math.floor(ratio * (len(BARS) - 1))
        chars.append(BARS[idx])
    bar = "".join(chars)
    return color(bar, BRIGHT_CYAN)


def block_histogram(counts: list[int], edges: list[float], col_width: int = 40) -> list[str]:
    """Multi-line block histogram with labels."""
    if not counts:
        return [dim("  (no data)")]

    lines = []
    mx = max(counts) if counts else 1
    bar_max = col_width - 22  # space for labels

    for i, cnt in enumerate(counts):
        if i >= len(edges) - 1:
            break
        lo = edges[i]
        hi = edges[i + 1]
        bar_len = max(1, int(cnt / mx * bar_max)) if cnt > 0 else 0
        bar = "█" * bar_len
        # color bar by fill density
        if bar_len / bar_max > 0.7:
            bar_colored = color(bar, BRIGHT_CYAN)
        elif bar_len / bar_max > 0.3:
            bar_colored = color(bar, CYAN)
        else:
            bar_colored = color(bar, BLUE)

        label = f"{lo:>8.3g}–{hi:<8.3g}"
        count_label = dim(f" {cnt}")
        lines.append(f"  {label} {bar_colored}{count_label}")

    return lines


# ─── Skewness label ──────────────────────────────────────────────────────────

def skew_label(skew: float | None) -> str:
    if skew is None:
        return dim("n/a")
    abs_s = abs(skew)
    if abs_s < 0.5:
        label = "symmetric"
        c = BRIGHT_GREEN
    elif abs_s < 1.0:
        direction = "right" if skew > 0 else "left"
        label = f"moderate {direction} skew"
        c = BRIGHT_YELLOW
    else:
        direction = "right" if skew > 0 else "left"
        label = f"high {direction} skew"
        c = BRIGHT_RED
    return color(f"{skew:+.3f} ({label})", c)


# ─── Missing value bar ────────────────────────────────────────────────────────

def missing_bar(missing: int, total: int, width: int = 20) -> str:
    if total == 0:
        return ""
    ratio = missing / total
    filled = int(ratio * width)
    empty = width - filled
    bar = color("█" * filled, RED) + color("░" * empty, DIM)
    pct = f"{ratio*100:.1f}%"
    pct_colored = color(pct, RED) if ratio > 0.1 else color(pct, BRIGHT_GREEN)
    return f"[{bar}] {pct_colored} ({missing}/{total})"


# ─── dtype badge ─────────────────────────────────────────────────────────────

DTYPE_COLORS = {
    "numeric":     (BRIGHT_CYAN,   "NUM"),
    "categorical": (BRIGHT_MAGENTA,"CAT"),
    "boolean":     (BRIGHT_GREEN,  "BOOL"),
    "datetime":    (BRIGHT_YELLOW, "DATE"),
    "text":        (BRIGHT_WHITE,  "TEXT"),
    "empty":       (DIM,           "EMPTY"),
}

def dtype_badge(dtype: str) -> str:
    c, label = DTYPE_COLORS.get(dtype, (WHITE, dtype.upper()))
    return color(f"[{label}]", c)


# ─── Main render ──────────────────────────────────────────────────────────────

def _hr(char: str = "─", width: int | None = None) -> str:
    w = width or shutil.get_terminal_size((100, 40)).columns
    return color(char * w, DIM)


def _header_box(title: str, subtitle: str = "") -> list[str]:
    term_w = shutil.get_terminal_size((100, 40)).columns
    lines = []
    lines.append(color("╔" + "═" * (term_w - 2) + "╗", BRIGHT_CYAN))
    pad = (term_w - 2 - len(title)) // 2
    lines.append(color("║", BRIGHT_CYAN) + " " * pad + b(color(title, BRIGHT_WHITE)) + " " * (term_w - 2 - pad - len(title)) + color("║", BRIGHT_CYAN))
    if subtitle:
        pad2 = (term_w - 2 - len(subtitle)) // 2
        lines.append(color("║", BRIGHT_CYAN) + " " * pad2 + color(subtitle, DIM) + " " * (term_w - 2 - pad2 - len(subtitle)) + color("║", BRIGHT_CYAN))
    lines.append(color("╚" + "═" * (term_w - 2) + "╝", BRIGHT_CYAN))
    return lines


def _corr_color(r: float) -> str:
    """Color a correlation value: strong=cyan, moderate=yellow, weak=dim."""
    abs_r = abs(r)
    if abs_r >= 0.7:
        return BRIGHT_CYAN
    if abs_r >= 0.4:
        return BRIGHT_YELLOW
    if abs_r >= 0.2:
        return WHITE
    return DIM


def render_correlation(corr: dict[str, dict[str, float]]) -> list[str]:
    """Render a pairwise correlation heatmap as a text grid."""
    if not corr:
        return []

    names = list(corr.keys())
    n = len(names)
    if n < 2:
        return []

    # Truncate names to fit
    max_label = min(12, max(len(nm) for nm in names))
    short = [nm[:max_label] for nm in names]

    cell_w = 7  # " +0.99 "
    col_w = cell_w

    lines: list[str] = []

    # Header row
    row_label_w = max_label + 2
    header = " " * row_label_w
    for s in short:
        header += f"{s[:col_w]:>{col_w}}"
    lines.append(color(header, DIM))

    for i, name_a in enumerate(names):
        row = f"  {short[i]:<{max_label}}"
        for j, name_b in enumerate(names):
            r = corr.get(name_a, {}).get(name_b)
            if r is None:
                cell = f"{'n/a':>{col_w}}"
                row += color(cell, DIM)
            elif i == j:
                row += color(f"{'  1.00':>{col_w}}", DIM)
            else:
                c = _corr_color(r)
                row += color(f"{r:>+{col_w}.2f}", c)
        lines.append(row)

    # Legend
    lines.append("")
    lines.append(
        "  " + color("■", BRIGHT_CYAN) + " strong (≥0.7)  " +
        color("■", BRIGHT_YELLOW) + " moderate (≥0.4)  " +
        color("■", WHITE) + " weak (≥0.2)  " +
        color("■", DIM) + " negligible"
    )
    return lines


def render_head(path: str, n: int) -> str:
    """Read first N rows of a CSV and render as a formatted table."""
    import csv as csv_mod

    lines: list[str] = []
    term_w = shutil.get_terminal_size((100, 40)).columns

    def add(*parts: str):
        lines.append("".join(parts))

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv_mod.DictReader(f)
        if not reader.fieldnames:
            return "Error: CSV has no headers or is empty."
        headers = list(reader.fieldnames)
        rows: list[dict] = []
        for i, row in enumerate(reader):
            if i >= n:
                break
            rows.append(row)

    total_cols = len(headers)
    filename = os.path.basename(path)

    add()
    for l in _header_box(f"  ds-profile --head {n}  ·  {filename}  ", f"First {len(rows)} rows  ·  {total_cols} columns"):
        add(l)
    add()

    if not rows:
        add(color("  (file has headers but no data rows)", DIM))
        add()
        return "\n".join(lines)

    # Compute column widths: max of header length and longest value, capped
    max_col_w = max(6, (term_w - 4) // min(total_cols, 8) - 3)
    col_widths = {
        h: min(max_col_w, max(len(h), max((len(str(r.get(h, ""))) for r in rows), default=0)))
        for h in headers
    }

    # If too many columns to fit, show first N that fit
    visible_headers: list[str] = []
    used = 4  # left margin
    for h in headers:
        needed = col_widths[h] + 3  # " | " separator
        if used + needed > term_w - 5:
            break
        visible_headers.append(h)
        used += needed
    hidden = total_cols - len(visible_headers)

    # Header row
    header_row = "  "
    for h in visible_headers:
        w = col_widths[h]
        header_row += color(f"{h[:w]:<{w}}", BRIGHT_WHITE) + color("  │  ", DIM)
    add(header_row.rstrip(" │"))
    add(_hr("─", min(used + 2, term_w)))

    # Data rows
    for i, row in enumerate(rows):
        row_str = "  "
        for h in visible_headers:
            w = col_widths[h]
            val = str(row.get(h, ""))
            val_display = val[:w]
            # Color empty/null-ish values differently
            is_empty = val.strip() == "" or val.lower() in ("nan", "null", "none", "na", "n/a")
            val_colored = color(f"{val_display:<{w}}", DIM if is_empty else BRIGHT_CYAN if not is_empty and h else WHITE)
            row_str += val_colored + color("  │  ", DIM)
        add(row_str.rstrip(" │"))

    if hidden > 0:
        add()
        add(dim(f"  ... {hidden} more column(s) not shown (terminal too narrow — use --cols to select)"))

    add()
    add(_hr("─", min(used + 2, term_w)))
    add(dim(f"  {len(rows)} row(s) shown · {total_cols} total columns"))
    add()

    return "\n".join(lines)


def render_summary(profile: DatasetProfile) -> str:
    """Render a compact one-line-per-column summary table."""
    lines: list[str] = []
    term_w = shutil.get_terminal_size((100, 40)).columns

    def add(*parts: str):
        lines.append("".join(parts))

    add()
    for l in _header_box(f"  ds-profile  ·  {profile.filename}  ", "Instant Dataset Profiler"):
        add(l)
    add()

    size_kb = profile.file_size_bytes / 1024
    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
    add(f"  {b('Rows:')} {color(f'{profile.total_rows:,}', BRIGHT_GREEN)}  "
        f"{b('Cols:')} {color(str(profile.total_cols), BRIGHT_GREEN)}  "
        f"{b('Size:')} {color(size_str, BRIGHT_YELLOW)}  "
        f"{b('Duplicates:')} {color(str(profile.duplicate_rows), BRIGHT_RED if profile.duplicate_rows else BRIGHT_GREEN)}")
    if profile.sampled and profile.sample_size:
        add(f"  {color(f'(sampled {profile.sample_size:,} rows)', BRIGHT_YELLOW)}")
    add()

    # Column widths
    name_w  = min(24, max(len(c.name) for c in profile.columns))
    type_w  = 6   # [NUM]
    miss_w  = 9   # 100.0%
    uniq_w  = 9   # 99999
    stat_w  = term_w - name_w - type_w - miss_w - uniq_w - 14

    # Header
    header = (
        f"  {'COLUMN':<{name_w}}  {'TYPE':<{type_w}}  "
        f"{'MISSING':>{miss_w}}  {'UNIQUE':>{uniq_w}}  SUMMARY"
    )
    add(color(header, DIM))
    add(_hr("─", term_w))

    for col in profile.columns:
        name_str = col.name[:name_w]
        badge_raw = DTYPE_COLORS.get(col.dtype, (WHITE, col.dtype.upper()))[1]
        miss_pct = col.missing / max(profile.total_rows, 1) * 100
        miss_c = BRIGHT_RED if miss_pct > 10 else (BRIGHT_YELLOW if miss_pct > 0 else BRIGHT_GREEN)
        miss_str = f"{miss_pct:.1f}%"

        uniq_str = str(col.unique)

        # Summary snippet — most useful single fact per dtype
        if col.dtype == "numeric" and col.mean is not None:
            skew_c = BRIGHT_GREEN
            if col.skewness and abs(col.skewness) >= 2:
                skew_c = BRIGHT_RED
            elif col.skewness and abs(col.skewness) >= 0.5:
                skew_c = BRIGHT_YELLOW
            summary = (
                f"mean={color(str(col.mean), BRIGHT_CYAN)}  "
                f"[{col.min_val}, {col.max_val}]  "
                f"skew={color(f'{col.skewness:+.2f}' if col.skewness else 'n/a', skew_c)}"
            )
            if col.outlier_count > 0:
                summary += f"  {color(f'{col.outlier_count} outliers', BRIGHT_RED)}"
        elif col.dtype in ("categorical", "boolean") and col.top_values:
            top_val, top_cnt = col.top_values[0]
            top_pct = top_cnt / max(col.count, 1) * 100
            summary = (
                f"top={color(repr(top_val[:20]), BRIGHT_MAGENTA)} "
                f"{color(f'({top_pct:.0f}%)', DIM)}  "
                f"{color(str(col.unique), BRIGHT_MAGENTA)} categories"
            )
        elif col.dtype == "datetime":
            samples = "  ".join(str(v) for v in col.sample_values[:2])
            summary = color(f"e.g. {samples}", DIM)
        else:
            samples = "  ".join(repr(str(v)[:20]) for v in col.sample_values[:2])
            summary = color(f"e.g. {samples}", DIM)

        # Sentinel flag
        sent_flag = f"  {color('⚠', BRIGHT_RED)}" if col.sentinels else ""

        add(
            f"  {color(f'{name_str:<{name_w}}', BRIGHT_WHITE)}  "
            f"{color(f'{badge_raw:<{type_w}}', BRIGHT_CYAN if col.dtype == 'numeric' else BRIGHT_MAGENTA if col.dtype == 'categorical' else BRIGHT_GREEN if col.dtype == 'boolean' else BRIGHT_YELLOW if col.dtype == 'datetime' else WHITE)}  "
            f"{color(f'{miss_str:>{miss_w}}', miss_c)}  "
            f"{color(f'{uniq_str:>{uniq_w}}', DIM)}  "
            f"{summary}{sent_flag}"
        )

    add(_hr("─", term_w))
    issues = profile.warn_issues()
    if issues:
        n_err  = sum(1 for i in issues if i["severity"] == "error")
        n_warn = sum(1 for i in issues if i["severity"] == "warning")
        add(f"  {color(f'{n_err} error(s)', BRIGHT_RED)}  {color(f'{n_warn} warning(s)', BRIGHT_YELLOW)}  "
            f"{dim('— run with --warn to see details')}")
    else:
        add(f"  {color('✓ No data quality issues detected', BRIGHT_GREEN)}")
    add()

    return "\n".join(lines)


def render_warn(profile: DatasetProfile) -> str:
    """Render only data quality warnings — errors first, then warnings, then info."""
    lines: list[str] = []
    term_w = shutil.get_terminal_size((100, 40)).columns

    def add(*parts: str):
        lines.append("".join(parts))

    add()
    for l in _header_box(f"  ds-profile --warn  ·  {profile.filename}  ", "Data Quality Report"):
        add(l)
    add()

    issues = profile.warn_issues()

    if not issues:
        add(f"  {color('✓  No data quality issues detected.', BRIGHT_GREEN)}")
        add(f"  {dim('This dataset looks clean — no high missing rates, sentinels, constant columns,')}")
        add(f"  {dim('high skew, or excessive outliers found.')}")
        add()
        add(_hr("═", term_w))
        add(color(f"  ds-profile warn complete · {profile.total_cols} columns checked", DIM))
        add()
        return "\n".join(lines)

    errors   = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    SEV_ICON  = {"error": color("✖ ERROR  ", BRIGHT_RED),
                 "warning": color("⚠ WARNING", BRIGHT_YELLOW),
                 "info":    color("ℹ INFO   ", BRIGHT_CYAN)}
    CODE_COLOR = {
        "duplicate_rows":    BRIGHT_YELLOW,
        "high_missing":      BRIGHT_RED,
        "constant_col":      BRIGHT_RED,
        "high_skew":         BRIGHT_YELLOW,
        "high_outliers":     BRIGHT_YELLOW,
        "sentinels":         BRIGHT_RED,
        "high_cardinality":  BRIGHT_YELLOW,
    }

    def render_group(group: list[dict], title: str, title_color: str) -> None:
        if not group:
            return
        add(b(color(f"  {title}", title_color)))
        add(_hr("─", term_w))
        for issue in group:
            icon  = SEV_ICON[issue["severity"]]
            col_c = CODE_COLOR.get(issue["code"], WHITE)
            col_label = color(f"[{issue['column']}]", col_c)
            add(f"  {icon}  {col_label}")
            add(f"           {issue['message']}")
            add()

    render_group(errors,   f"ERRORS ({len(errors)})",    BRIGHT_RED)
    render_group(warnings, f"WARNINGS ({len(warnings)})", BRIGHT_YELLOW)

    # Summary counts
    add(_hr("─", term_w))
    add(f"  {color(str(len(errors)),   BRIGHT_RED)}    error(s)    "
        f"{color(str(len(warnings)), BRIGHT_YELLOW)} warning(s)  "
        f"across {profile.total_cols} columns")
    add()

    # Quick fix suggestions by code
    codes_found = {i["code"] for i in issues}
    add(b(color("  SUGGESTED FIXES", BRIGHT_WHITE)))
    add(_hr("─", term_w))
    fixes = {
        "high_missing":     "Drop columns with >50% missing, or impute with median/mode",
        "constant_col":     "Drop constant/quasi-constant columns before training",
        "high_skew":        "Apply log1p() or sqrt() transform to reduce skewness",
        "high_outliers":    "Investigate outliers — clip with IQR fence or use robust scalers",
        "sentinels":        "Replace sentinel strings with np.nan before any preprocessing",
        "high_cardinality": "Use target encoding, hashing, or embeddings instead of one-hot",
        "duplicate_rows":   "Call df.drop_duplicates() before splitting into train/test",
    }
    for code, fix in fixes.items():
        if code in codes_found:
            add(f"  {color('→', BRIGHT_CYAN)} {b(code)}: {fix}")
    add()
    add(_hr("═", term_w))
    add(color(f"  ds-profile warn complete · {len(issues)} issue(s) found", DIM))
    add()

    return "\n".join(lines)


def render_diff(diff: DiffResult) -> str:
    """Render a DiffResult to a terminal string."""
    lines: list[str] = []
    term_w = shutil.get_terminal_size((100, 40)).columns

    def add(*parts: str):
        lines.append("".join(parts))

    # Header
    add()
    title = f"  ds-profile diff  ·  {diff.filename_a}  vs  {diff.filename_b}  "
    box_top = color("╔" + "═" * (term_w - 2) + "╗", BRIGHT_CYAN)
    pad = (term_w - 2 - len(title)) // 2
    box_mid = (color("║", BRIGHT_CYAN) + " " * pad + b(color(title, BRIGHT_WHITE))
               + " " * (term_w - 2 - pad - len(title)) + color("║", BRIGHT_CYAN))
    box_bot = color("╚" + "═" * (term_w - 2) + "╝", BRIGHT_CYAN)
    add(box_top); add(box_mid); add(box_bot)
    add()

    # Row/col summary
    row_delta = diff.rows_b - diff.rows_a
    row_sign = f"+{row_delta}" if row_delta >= 0 else str(row_delta)
    row_col = BRIGHT_GREEN if row_delta >= 0 else BRIGHT_RED
    add(f"  {b('Rows:')}     {color(f'{diff.rows_a:,}', DIM)} → {color(f'{diff.rows_b:,}', BRIGHT_WHITE)}  "
        f"{color(f'({row_sign})', row_col)}")

    col_delta = diff.cols_b - diff.cols_a
    col_sign = f"+{col_delta}" if col_delta >= 0 else str(col_delta)
    col_c = BRIGHT_GREEN if col_delta >= 0 else BRIGHT_RED
    add(f"  {b('Columns:')}  {color(str(diff.cols_a), DIM)} → {color(str(diff.cols_b), BRIGHT_WHITE)}  "
        f"{color(f'({col_sign})', col_c)}")
    add()

    # Added / removed columns
    if diff.added_cols:
        add(color("  ADDED COLUMNS", BRIGHT_GREEN))
        for name in diff.added_cols:
            add(f"  {color('＋', BRIGHT_GREEN)}  {b(name)}")
        add()

    if diff.removed_cols:
        add(color("  REMOVED COLUMNS", BRIGHT_RED))
        for name in diff.removed_cols:
            add(f"  {color('－', BRIGHT_RED)}  {b(name)}")
        add()

    # Changed columns
    changed = diff.changed_cols
    if changed:
        add(color("  CHANGED COLUMNS", BRIGHT_YELLOW))
        add(_hr("─", term_w))
        for cd in changed:
            add()
            add(f"  {b(color(cd.name, BRIGHT_WHITE))}")

            # dtype change
            if cd.dtype_a != cd.dtype_b:
                add(f"    {b('type:')}     {color(cd.dtype_a or '?', BRIGHT_RED)} → "
                    f"{color(cd.dtype_b or '?', BRIGHT_GREEN)}  {color('← type changed!', BRIGHT_RED)}")

            # missing pct change
            if cd.missing_pct_a is not None and cd.missing_pct_b is not None:
                delta = cd.missing_pct_b - cd.missing_pct_a
                sign = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
                mc = BRIGHT_RED if abs(delta) > 5 else DIM
                add(f"    {b('missing:')}  {cd.missing_pct_a:.1f}% → {cd.missing_pct_b:.1f}%  "
                    f"{color(f'({sign}pp)', mc)}")

            # mean shift
            if cd.mean_a is not None and cd.mean_b is not None:
                delta = cd.mean_b - cd.mean_a
                sign = f"+{delta:.4g}" if delta >= 0 else f"{delta:.4g}"
                shift_ratio = abs(delta / cd.std_a) if cd.std_a and cd.std_a > 0 else 0
                mc = BRIGHT_RED if shift_ratio > 1 else (BRIGHT_YELLOW if shift_ratio > 0.3 else DIM)
                add(f"    {b('mean:')}     {cd.mean_a} → {cd.mean_b}  "
                    f"{color(f'(Δ={sign})', mc)}"
                    + (f"  {color(f'{shift_ratio:.1f}σ shift', mc)}" if cd.std_a else ""))

            # histogram overlap
            if cd.histogram_overlap is not None:
                oc = BRIGHT_RED if cd.histogram_overlap < 0.5 else (BRIGHT_YELLOW if cd.histogram_overlap < 0.8 else BRIGHT_GREEN)
                bar_w = int(cd.histogram_overlap * 20)
                bar = color("█" * bar_w, oc) + color("░" * (20 - bar_w), DIM)
                add(f"    {b('dist overlap:')}  [{bar}] {color(f'{cd.histogram_overlap*100:.0f}%', oc)}")
    else:
        add(color("  No significant column changes detected.", BRIGHT_GREEN))

    # Unchanged summary
    same = [c for c in diff.columns if c.status == "same"]
    if same:
        add()
        add(dim(f"  {len(same)} column(s) unchanged: " +
                ", ".join(c.name for c in same[:8]) +
                (f" +{len(same)-8} more" if len(same) > 8 else "")))

    add()
    add(_hr("═", term_w))
    add(color(f"  ds-profile diff complete · {len(diff.columns)} columns compared", DIM))
    add()
    return "\n".join(lines)


def render_profile(profile: DatasetProfile, no_color: bool = False, compact: bool = False) -> str:
    """Render a DatasetProfile to a terminal string."""
    lines: list[str] = []
    term_w = shutil.get_terminal_size((100, 40)).columns

    def add(*parts: str):
        lines.append("".join(parts))

    # ── Header ──
    add()
    for l in _header_box(f"  ds-profile  ·  {profile.filename}  ", "Instant Dataset Profiler"):
        add(l)
    add()

    # ── Overview ──
    size_kb = profile.file_size_bytes / 1024
    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"

    add(b(color("  DATASET OVERVIEW", BRIGHT_WHITE)))
    add(_hr("─", term_w))
    add(f"  {b('File:')}        {color(profile.filename, BRIGHT_CYAN)}")
    add(f"  {b('Size:')}        {color(size_str, BRIGHT_YELLOW)}")
    add(f"  {b('Rows:')}        {color(f'{profile.total_rows:,}', BRIGHT_GREEN)}")
    add(f"  {b('Columns:')}     {color(str(profile.total_cols), BRIGHT_GREEN)}")

    dup_color = BRIGHT_RED if profile.duplicate_rows > 0 else BRIGHT_GREEN
    add(f"  {b('Duplicates:')}  {color(str(profile.duplicate_rows), dup_color)}")

    if profile.sampled and profile.sample_size:
        add(f"  {b('Sample:')}      {color(f'{profile.sample_size:,} rows (random sample)', BRIGHT_YELLOW)}  {color('← stats computed on sample only', DIM)}")

    # dtype summary
    from collections import Counter
    dtype_counts = Counter(c.dtype for c in profile.columns)
    dtype_summary = "  ".join(f"{dtype_badge(dt)} {n}" for dt, n in sorted(dtype_counts.items()))
    add(f"  {b('Col types:')}   {dtype_summary}")
    add(_hr("─", term_w))
    add()

    # ── Per-column ──
    add(b(color("  COLUMN PROFILES", BRIGHT_WHITE)))

    for i, col in enumerate(profile.columns):
        add()
        add(_hr("╌", term_w))
        # Column header line
        num_str = color(f"[{i+1}/{profile.total_cols}]", DIM)
        add(f"  {num_str}  {b(color(col.name, BRIGHT_WHITE))}  {dtype_badge(col.dtype)}")
        add()

        # Missing
        add(f"  {b('Missing:')}  {missing_bar(col.missing, profile.total_rows)}")

        # Unique
        unique_ratio = col.unique / max(col.count, 1)
        unique_color = BRIGHT_CYAN if unique_ratio > 0.9 else (BRIGHT_YELLOW if unique_ratio > 0.3 else BRIGHT_MAGENTA)
        add(f"  {b('Unique:')}   {color(str(col.unique), unique_color)}  {dim(f'({unique_ratio*100:.1f}% of non-null)')}")

        if col.sample_values:
            samples = "  ".join(color(f'"{v}"', DIM) for v in col.sample_values[:3])
            add(f"  {b('Samples:')}  {samples}")

        if col.dtype == "numeric" and col.mean is not None:
            add()
            add(f"  {b('Stats:')}")
            add(f"    mean={color(str(col.mean), BRIGHT_CYAN)}  "
                f"median={color(str(col.median), BRIGHT_CYAN)}  "
                f"std={color(str(col.std), BRIGHT_YELLOW)}")
            add(f"    min={color(str(col.min_val), BRIGHT_GREEN)}  "
                f"Q1={color(str(col.q1), BRIGHT_GREEN)}  "
                f"Q3={color(str(col.q3), BRIGHT_GREEN)}  "
                f"max={color(str(col.max_val), BRIGHT_GREEN)}")

            outlier_color = BRIGHT_RED if col.outlier_count > 0 else BRIGHT_GREEN
            add(f"    outliers (IQR)={color(str(col.outlier_count), outlier_color)}  "
                f"skewness={skew_label(col.skewness)}")

            if not compact and col.histogram:
                add()
                add(f"  {b('Distribution:')}")
                hist_lines = block_histogram(col.histogram, col.histogram_edges, col_width=min(term_w, 80))
                for hl in hist_lines:
                    add(hl)

        elif col.dtype in ("categorical", "boolean"):
            if col.top_values:
                add()
                add(f"  {b('Top values:')}")
                total_non_null = col.count
                max_shown = 5 if compact else 10
                for val, cnt in col.top_values[:max_shown]:
                    pct = cnt / max(total_non_null, 1)
                    bar_w = int(pct * 20)
                    bar = color("█" * bar_w, BRIGHT_MAGENTA) + color("░" * (20 - bar_w), DIM)
                    add(f"    [{bar}] {color(f'{pct*100:5.1f}%', BRIGHT_MAGENTA)}  {color(repr(val)[:40], BRIGHT_WHITE)}  {dim(str(cnt))}")
                remaining = col.unique - max_shown
                if remaining > 0:
                    add(f"    {dim(f'... and {remaining} more unique value(s) not shown')}")

        elif col.dtype == "text":
            add(f"  {dim('(free text column — skipping frequency analysis)')}")

        # Sentinel warnings (any dtype)
        if col.sentinels:
            total_sent = sum(col.sentinels.values())
            sent_list = "  ".join(
                f"{color(repr(k), BRIGHT_RED)}×{v}" for k, v in list(col.sentinels.items())[:5]
            )
            add(f"  {color('⚠ sentinels:', BRIGHT_RED)}  {sent_list}  "
                f"{color(f'({total_sent} masked nulls — fix before modeling)', BRIGHT_RED)}")

    # ── Correlation matrix ──
    if profile.correlation and not compact:
        add()
        add(b(color("  CORRELATION MATRIX  ", BRIGHT_WHITE)) + color("(Pearson r — numeric columns only)", DIM))
        add(_hr("─", term_w))
        for cl in render_correlation(profile.correlation):
            add(cl)
        add()

    add()
    add(_hr("═", term_w))
    add(color(f"  ds-profile complete · {profile.total_cols} columns analyzed", DIM))
    add()

    return "\n".join(lines)
