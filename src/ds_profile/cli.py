"""CLI entry point for ds-profile."""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Optional

from . import __version__
from .profiler import profile_csv, diff_profiles
from .renderer import render_profile, render_summary, render_warn, render_diff, render_head
from .html_renderer import render_html


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]+m", "", text)


def _write_output(content: str, export_path: Optional[str], binary: bool = False) -> None:
    """Print to stdout or write to file, with a confirmation message."""
    if export_path:
        mode = "wb" if binary else "w"
        kwargs = {} if binary else {"encoding": "utf-8"}
        with open(export_path, mode, **kwargs) as f:
            if binary:
                f.write(content.encode("utf-8") if isinstance(content, str) else content)
            else:
                f.write(content)
        abs_path = os.path.abspath(export_path)
        size_kb = os.path.getsize(abs_path) / 1024
        print(f"✓  Saved to {abs_path}  ({size_kb:.1f} KB)", file=sys.stderr)
    else:
        print(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ds-profile",
        description="Instant Dataset Profiler — rich terminal summary for any CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ds-profile data.csv                          # full column-by-column profile
  ds-profile data.csv --summary                # one-line-per-column overview table
  ds-profile data.csv --warn                   # data quality issues only
  ds-profile data.csv --head 10                # preview first 10 rows as a table
  ds-profile data.csv --compact                # shorter output, no histograms
  ds-profile data.csv --no-color > report.txt
  ds-profile data.csv --output json
  ds-profile data.csv --output html --export report.html
  ds-profile data.csv --warn --export issues.txt
  ds-profile data.csv --cols age,salary,country
  ds-profile data.csv --sample 5000
  ds-profile before.csv --diff after.csv
        """,
    )
    parser.add_argument("csv_file", help="Path to the CSV file to profile")
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="One-line-per-column overview table — fast orientation for wide datasets",
    )
    parser.add_argument(
        "--warn", "-w",
        action="store_true",
        help="Show only data quality warnings: high missing, sentinels, skew, outliers, constant columns",
    )
    parser.add_argument(
        "--head",
        type=int,
        metavar="N",
        help="Preview the first N rows as a formatted table (default: 10)",
        const=10,
        nargs="?",
    )
    parser.add_argument(
        "--export",
        metavar="FILE",
        help="Save output to a file instead of printing (e.g. report.html, report.txt, profile.json)",
    )
    parser.add_argument(
        "--diff",
        metavar="CSV_B",
        help="Compare csv_file against a second CSV and show what changed",
    )
    parser.add_argument(
        "--compact", "-c",
        action="store_true",
        help="Compact output — no histograms, fewer top values",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors (useful for redirecting output)",
    )
    parser.add_argument(
        "--cols",
        metavar="COL1,COL2,...",
        help="Only profile specific columns (comma-separated names)",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["terminal", "json", "html"],
        default="terminal",
        help="Output format: terminal (default), json, or html",
    )
    parser.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="Profile only a random sample of N rows — useful for large files",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"ds-profile {__version__}",
    )

    args = parser.parse_args()

    path = args.csv_file
    if not os.path.exists(path):
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    if not path.lower().endswith(".csv"):
        print(f"Warning: file does not have .csv extension — attempting anyway.", file=sys.stderr)

    # ── --head: independent of profiling, just reads raw rows ─────────────────
    if args.head is not None:
        n = args.head if args.head > 0 else 10
        output = render_head(path, n)
        if args.no_color or not sys.stdout.isatty():
            output = _strip_ansi(output)
        if args.export:
            _write_output(_strip_ansi(output), args.export)
        else:
            print(output)
        return

    try:
        profile = profile_csv(path, sample_n=args.sample)
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        sys.exit(1)

    # ── Diff mode ──────────────────────────────────────────────────────────────
    if args.diff:
        path_b = args.diff
        if not os.path.exists(path_b):
            print(f"Error: diff file not found: {path_b}", file=sys.stderr)
            sys.exit(1)
        try:
            profile_b = profile_csv(path_b, sample_n=args.sample)
        except Exception as e:
            print(f"Error reading diff CSV: {e}", file=sys.stderr)
            sys.exit(1)
        diff = diff_profiles(profile, profile_b)
        output = render_diff(diff)
        if args.no_color or not sys.stdout.isatty():
            output = _strip_ansi(output)
        _write_output(_strip_ansi(output) if args.export else output, args.export)
        return

    # ── Column filter ──────────────────────────────────────────────────────────
    if args.cols:
        wanted = {c.strip() for c in args.cols.split(",")}
        filtered = [c for c in profile.columns if c.name in wanted]
        if not filtered:
            print(f"Error: none of the specified columns were found.", file=sys.stderr)
            sys.exit(1)
        profile.columns = filtered
        profile.total_cols = len(filtered)
        profile.correlation = {
            a: {b: v for b, v in row.items() if b in wanted}
            for a, row in profile.correlation.items()
            if a in wanted
        }

    # ── Build output ───────────────────────────────────────────────────────────
    if args.output == "json":
        content = profile.to_json()
        _write_output(content, args.export)
        return

    if args.output == "html":
        content = render_html(profile)
        _write_output(content, args.export)
        return

    if args.summary:
        output = render_summary(profile)
    elif args.warn:
        output = render_warn(profile)
    else:
        output = render_profile(profile, no_color=args.no_color, compact=args.compact)

    if args.no_color or not sys.stdout.isatty():
        output = _strip_ansi(output)

    # --export always writes plain text (no ANSI) regardless of --no-color
    _write_output(_strip_ansi(output) if args.export else output, args.export)


if __name__ == "__main__":
    main()
