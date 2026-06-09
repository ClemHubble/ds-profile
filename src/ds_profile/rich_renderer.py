"""Rich-powered terminal rendering for ds-profile."""

from __future__ import annotations

import csv as csv_mod
import os
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text
from rich.columns import Columns
from rich.rule import Rule
from rich.padding import Padding
from rich import print as rprint

from .profiler import DatasetProfile, ColumnProfile

# Shared console — used by all renderers
console = Console(highlight=False)


# ─── dtype styling ────────────────────────────────────────────────────────────

DTYPE_STYLE = {
    "numeric":     ("bold cyan",    "NUM"),
    "categorical": ("bold magenta", "CAT"),
    "boolean":     ("bold green",   "BOOL"),
    "datetime":    ("bold yellow",  "DATE"),
    "text":        ("bold white",   "TEXT"),
    "empty":       ("dim",          "EMPTY"),
}

def dtype_badge(dtype: str) -> Text:
    style, label = DTYPE_STYLE.get(dtype, ("white", dtype.upper()))
    return Text(f"[{label}]", style=style)


def _miss_text(missing: int, total: int) -> Text:
    if total == 0:
        return Text("n/a", style="dim")
    pct = missing / total * 100
    style = "bold red" if pct > 10 else ("yellow" if pct > 0 else "green")
    t = Text()
    t.append(f"{pct:.1f}%", style=style)
    t.append(f" ({missing:,}/{total:,})", style="dim")
    return t


def _skew_text(skew: Optional[float]) -> Text:
    if skew is None:
        return Text("n/a", style="dim")
    abs_s = abs(skew)
    if abs_s < 0.5:
        style, label = "green", "symmetric"
    elif abs_s < 1.0:
        direction = "right" if skew > 0 else "left"
        style, label = "yellow", f"moderate {direction} skew"
    else:
        direction = "right" if skew > 0 else "left"
        style, label = "bold red", f"high {direction} skew"
    t = Text()
    t.append(f"{skew:+.3f}", style=style)
    t.append(f" ({label})", style=style)
    return t


# ─── --head ───────────────────────────────────────────────────────────────────

def rich_head(path: str, n: int) -> None:
    """Render the first N rows of a CSV as a Rich table."""
    filename = os.path.basename(path)

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv_mod.DictReader(f)
        if not reader.fieldnames:
            console.print("[red]Error: CSV has no headers or is empty.[/red]")
            return
        headers = list(reader.fieldnames)
        rows: List[Dict[str, Any]] = []
        for i, row in enumerate(reader):
            if i >= n:
                break
            rows.append(row)

    console.print()
    console.print(Panel(
        f"[bold cyan]{filename}[/bold cyan]  [dim]·[/dim]  "
        f"[dim]First {len(rows)} of {len(rows)} rows shown  ·  {len(headers)} columns[/dim]",
        title="[bold white]ds-profile --head[/bold white]",
        border_style="cyan",
    ))

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold white",
        show_lines=True,
        expand=False,
    )

    # Add row number column
    table.add_column("#", style="dim", justify="right", no_wrap=True)

    for h in headers:
        table.add_column(h, overflow="fold", max_width=30)

    NULL_LIKE = {"", "nan", "null", "none", "na", "n/a", "n.a.", "nil"}

    for i, row in enumerate(rows):
        cells: List[Any] = [str(i + 1)]
        for h in headers:
            val = row.get(h, "")
            if val.strip().lower() in NULL_LIKE:
                cells.append(Text(val or "∅", style="dim red italic"))
            else:
                cells.append(Text(val, style="cyan"))
        table.add_row(*cells)

    console.print(table)
    console.print(f"  [dim]{len(rows)} row(s) shown · {len(headers)} total columns[/dim]")
    console.print()


# ─── --summary ────────────────────────────────────────────────────────────────

def rich_summary(profile: DatasetProfile) -> None:
    """Render a Rich summary table — one row per column."""
    size_kb = profile.file_size_bytes / 1024
    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"

    issues = profile.warn_issues()
    n_err  = sum(1 for i in issues if i["severity"] == "error")
    n_warn = sum(1 for i in issues if i["severity"] == "warning")

    if n_err or n_warn:
        issue_str = f"[bold red]{n_err} error(s)[/bold red]  [yellow]{n_warn} warning(s)[/yellow]  [dim]— run --warn for details[/dim]"
    else:
        issue_str = "[bold green]✓ No data quality issues[/bold green]"

    dup_style = "bold red" if profile.duplicate_rows else "green"
    sample_note = (
        f"\n[yellow]Sampled: {profile.sample_size:,} rows (random sample)[/yellow]"
        if profile.sampled and profile.sample_size else ""
    )

    overview = (
        f"[bold white]{profile.filename}[/bold white]\n"
        f"[dim]Rows:[/dim] [green]{profile.total_rows:,}[/green]   "
        f"[dim]Cols:[/dim] [green]{profile.total_cols}[/green]   "
        f"[dim]Size:[/dim] [yellow]{size_str}[/yellow]   "
        f"[dim]Duplicates:[/dim] [{dup_style}]{profile.duplicate_rows}[/{dup_style}]"
        f"{sample_note}\n"
        f"{issue_str}"
    )

    console.print()
    console.print(Panel(
        overview,
        title="[bold white]ds-profile --summary[/bold white]",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()

    # Main summary table — ROUNDED + show_lines matches --head and --warn style
    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold white",
        show_lines=True,
        expand=True,
    )

    table.add_column("COLUMN",  no_wrap=True, max_width=24)
    table.add_column("TYPE",    justify="center", no_wrap=True)
    table.add_column("MISSING", justify="right",  no_wrap=True)
    table.add_column("UNIQUE",  justify="right",  no_wrap=True)
    table.add_column("SUMMARY", no_wrap=True, ratio=1, overflow="fold")
    table.add_column("⚠",       justify="center", no_wrap=True, width=3)

    for col in profile.columns:
        miss_pct = col.missing / max(profile.total_rows, 1) * 100
        miss_style = "bold red" if miss_pct > 10 else ("yellow" if miss_pct > 0 else "green")

        # Build summary cell
        if col.dtype == "numeric" and col.mean is not None:
            skew_val = abs(col.skewness) if col.skewness else 0
            skew_style = "bold red" if skew_val >= 2 else ("yellow" if skew_val >= 0.5 else "green")
            summary = Text()
            summary.append(f"mean=", style="dim")
            summary.append(f"{col.mean}", style="cyan")
            summary.append(f"  [{col.min_val}, {col.max_val}]", style="dim")
            summary.append(f"  skew=")
            summary.append(f"{col.skewness:+.2f}" if col.skewness else "n/a", style=skew_style)
            if col.outlier_count > 0:
                summary.append(f"  {col.outlier_count} outliers", style="bold red")
        elif col.dtype in ("categorical", "boolean") and col.top_values:
            top_val, top_cnt = col.top_values[0]
            top_pct = top_cnt / max(col.count, 1) * 100
            summary = Text()
            summary.append("top=", style="dim")
            summary.append(f"{repr(top_val[:20])}", style="magenta")
            summary.append(f" ({top_pct:.0f}%)", style="dim")
            summary.append(f"  {col.unique} categories", style="magenta")
        elif col.dtype == "datetime":
            samples = "  ".join(str(v) for v in col.sample_values[:2])
            summary = Text(f"e.g. {samples}", style="dim")
        else:
            samples = "  ".join(repr(str(v)[:18]) for v in col.sample_values[:2])
            summary = Text(f"e.g. {samples}", style="dim")

        badge_style, badge_label = DTYPE_STYLE.get(col.dtype, ("white", col.dtype.upper()))
        sent_flag = Text("⚠", style="bold red") if col.sentinels else Text("")

        table.add_row(
            Text(col.name, style="bold white"),
            Text(badge_label, style=badge_style),
            Text(f"{miss_pct:.1f}%", style=miss_style),
            Text(str(col.unique), style="dim"),
            summary,
            sent_flag,
        )

    console.print(table)
    console.print()


# ─── --warn ───────────────────────────────────────────────────────────────────

def rich_warn(profile: DatasetProfile) -> None:
    """Render data quality warnings using Rich panels and tables."""
    issues = profile.warn_issues()

    console.print()
    console.print(Panel(
        f"[bold white]{profile.filename}[/bold white]  [dim]·[/dim]  [dim]{profile.total_cols} columns checked[/dim]",
        title="[bold white]ds-profile --warn[/bold white]",
        subtitle="[dim]Data Quality Report[/dim]",
        border_style="cyan",
    ))

    if not issues:
        console.print(Panel(
            "[bold green]✓  No data quality issues detected.[/bold green]\n"
            "[dim]This dataset looks clean — no high missing rates, sentinels,\n"
            "constant columns, high skew, or excessive outliers found.[/dim]",
            border_style="green",
            padding=(1, 2),
        ))
        console.print()
        return

    errors   = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    ISSUE_STYLE = {
        "high_missing":     "red",
        "constant_col":     "red",
        "sentinels":        "red",
        "high_skew":        "yellow",
        "high_outliers":    "yellow",
        "high_cardinality": "yellow",
        "duplicate_rows":   "yellow",
    }

    def render_issue_table(group: List[Dict[str, Any]], title: str, border: str) -> None:
        if not group:
            return
        table = Table(
            box=box.ROUNDED,
            border_style=border,
            header_style=f"bold {border}",
            show_lines=True,
            expand=True,
            title=f"[bold {border}]{title}[/bold {border}]",
            title_justify="left",
        )
        table.add_column("COLUMN",  style="bold white", no_wrap=True, max_width=24)
        table.add_column("CODE",    style="dim",        no_wrap=True)
        table.add_column("DETAILS", ratio=1)

        for issue in group:
            code_style = ISSUE_STYLE.get(issue["code"], "white")
            table.add_row(
                issue["column"],
                Text(issue["code"], style=code_style),
                issue["message"],
            )
        console.print(table)

    render_issue_table(errors,   f"✖  ERRORS ({len(errors)})",    "red")
    if errors and warnings:
        console.print()
    render_issue_table(warnings, f"⚠  WARNINGS ({len(warnings)})", "yellow")

    # Suggested fixes
    codes_found = {i["code"] for i in issues}
    fixes = {
        "high_missing":     "Drop columns with >50% missing, or impute with median/mode",
        "constant_col":     "Drop constant/quasi-constant columns before training",
        "high_skew":        "Apply log1p() or sqrt() transform to reduce skewness",
        "high_outliers":    "Investigate outliers — clip with IQR fence or use robust scalers",
        "sentinels":        "Replace sentinel strings with np.nan before any preprocessing",
        "high_cardinality": "Use target encoding, hashing, or embeddings instead of one-hot",
        "duplicate_rows":   "Call df.drop_duplicates() before splitting into train/test",
    }
    relevant_fixes = {k: v for k, v in fixes.items() if k in codes_found}

    if relevant_fixes:
        console.print()
        fix_table = Table(
            box=box.SIMPLE,
            border_style="dim",
            header_style="bold dim",
            show_edge=False,
            expand=True,
            title="[bold white]SUGGESTED FIXES[/bold white]",
            title_justify="left",
        )
        fix_table.add_column("ISSUE",  style="bold cyan", no_wrap=True)
        fix_table.add_column("ACTION", ratio=1)
        for code, fix in relevant_fixes.items():
            fix_table.add_row(code, fix)
        console.print(fix_table)

    console.print()
    console.rule(
        f"[dim]{len(errors)} error(s)  ·  {len(warnings)} warning(s)  ·  "
        f"{profile.total_cols} columns checked[/dim]"
    )
    console.print()


# ─── Correlation matrix ───────────────────────────────────────────────────────

def _corr_cell_style(r: float, is_diag: bool) -> Tuple[str, str]:
    """Return (text_style, bg_style) for a correlation value."""
    if is_diag:
        return "dim white", ""
    abs_r = abs(r)
    positive = r > 0

    if abs_r >= 0.7:
        bg    = "on dark_cyan"     if positive else "on dark_red"
        text  = "bold bright_white"
    elif abs_r >= 0.4:
        bg    = "on cyan4"         if positive else "on red4"
        text  = "bold white"
    elif abs_r >= 0.2:
        bg    = "on grey23"
        text  = "cyan" if positive else "red"
    else:
        bg    = ""
        text  = "dim"
    return text, bg


def rich_correlation(corr: Dict[str, Dict[str, float]]) -> None:
    """Render the Pearson correlation matrix as a Rich heatmap table."""
    if not corr or len(corr) < 2:
        return

    names = list(corr.keys())

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        header_style="bold white",
        show_lines=True,
        title="[bold white]Correlation Matrix[/bold white]  [dim](Pearson r — numeric columns only)[/dim]",
        title_justify="left",
        caption="[cyan]■[/cyan] strong ≥0.7   [yellow]■[/yellow] moderate ≥0.4   [dim]■[/dim] weak ≥0.2   [dim]diagonal = 1.00[/dim]",
        caption_justify="left",
    )

    # Row-label column
    table.add_column("", style="bold white", no_wrap=True, justify="right")

    # One column per variable — use full names, Rich handles width
    for name in names:
        table.add_column(name, justify="center", no_wrap=True)

    for i, name_a in enumerate(names):
        cells: List[Any] = [Text(name_a, style="bold white")]
        for j, name_b in enumerate(names):
            r = corr.get(name_a, {}).get(name_b)
            is_diag = (i == j)

            if r is None:
                cells.append(Text("n/a", style="dim"))
                continue

            text_style, bg_style = _corr_cell_style(r, is_diag)
            full_style = f"{text_style} {bg_style}".strip()

            if is_diag:
                label = "1.00"
            else:
                label = f"{r:+.2f}"

            cells.append(Text(label, style=full_style, justify="center"))

        table.add_row(*cells)

    console.print()
    console.print(table)
    console.print()


# ─── Rich overview panel for full --profile ───────────────────────────────────

def rich_overview_panel(profile: DatasetProfile) -> None:
    """Print a Rich overview panel at the top of a full profile run."""
    from collections import Counter

    size_kb = profile.file_size_bytes / 1024
    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
    dup_style = "bold red" if profile.duplicate_rows else "green"

    dtype_counts = Counter(c.dtype for c in profile.columns)
    dtype_parts = "  ".join(
        f"[{DTYPE_STYLE.get(dt, ('white','?'))[0]}]{label}[/{DTYPE_STYLE.get(dt, ('white','?'))[0]}] {n}"
        for dt, n in sorted(dtype_counts.items())
        for _, label in [DTYPE_STYLE.get(dt, ("white", dt.upper()))]
    )
    sample_note = (
        f"\n[yellow]Sampled: {profile.sample_size:,} rows (random sample)[/yellow]"
        if profile.sampled and profile.sample_size else ""
    )

    issues = profile.warn_issues()
    n_err  = sum(1 for i in issues if i["severity"] == "error")
    n_warn = sum(1 for i in issues if i["severity"] == "warning")
    if n_err or n_warn:
        issue_line = f"\n[bold red]{n_err} error(s)[/bold red]  [yellow]{n_warn} warning(s)[/yellow]  [dim]— run --warn for details[/dim]"
    else:
        issue_line = "\n[bold green]✓ No data quality issues[/bold green]"

    content = (
        f"[bold white]{profile.filename}[/bold white]\n"
        f"[dim]Rows:[/dim] [green]{profile.total_rows:,}[/green]   "
        f"[dim]Columns:[/dim] [green]{profile.total_cols}[/green]   "
        f"[dim]Size:[/dim] [yellow]{size_str}[/yellow]   "
        f"[dim]Duplicates:[/dim] [{dup_style}]{profile.duplicate_rows}[/{dup_style}]"
        f"{sample_note}\n"
        f"[dim]Types:[/dim]  {dtype_parts}"
        f"{issue_line}"
    )

    console.print()
    console.print(Panel(
        content,
        title="[bold white]ds-profile[/bold white]",
        subtitle="[dim]Instant Dataset Profiler[/dim]",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()
