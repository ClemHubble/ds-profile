# ds-profile

A lightweight command-line tool that gives you an instant, rich terminal summary of any CSV dataset — column types, missing values, outlier counts, skewness, distribution histograms, a Pearson correlation matrix, sentinel value detection, and CSV diffing. Export to a shareable HTML report with interactive charts, or machine-readable JSON, with a single flag. Like `pandas-profiling`, but fast enough to run on every dataset you open, with no setup required.

One dependency (Rich for terminal formatting). No pandas. No numpy. Python 3.8+.

## Why?

Every data science workflow starts the same way: open a new dataset, run `.head()`, `.describe()`, `.info()`, `.value_counts()` a dozen times just to get oriented. `ds-profile` collapses all of that into a single command — and catches data quality issues (masked nulls, distribution shifts, type mismatches) that those functions silently miss.

## Installation

### Recommended — install as a global CLI tool

This makes `ds-profile` available as a command anywhere on your system:

```bash
uv tool install "git+https://github.com/ClemHubble/ds-profile.git"
```

Then run it directly from any directory:

```bash
ds-profile mydata.csv
```

If `ds-profile` is not found after installing, run this once to add uv's tool bin to your shell PATH:

```bash
uv tool update-shell
source ~/.zshrc   # or ~/.bashrc depending on your shell
```

### Alternative — install into a specific project

If you want `ds-profile` scoped to a particular project's virtualenv:

```bash
uv add "git+https://github.com/ClemHubble/ds-profile.git"
```

With this approach, prefix commands with `uv run`:

```bash
uv run ds-profile data.csv
```

### With pip

```bash
pip install "git+https://github.com/ClemHubble/ds-profile.git"
```

Requires Python 3.8 or later. Depends only on [Rich](https://github.com/Textualize/rich) for terminal formatting — no pandas, no numpy.

> **Note:** `ds-profile` works on any CSV file you point it at. The GitHub repository contains sample CSVs in `tests/` for development, but they are not included when the package is installed — just bring your own data file.

---

## Usage

```bash
ds-profile data.csv
```

### All Options

| Flag | Description |
|------|-------------|
| `--summary` / `-s` | One-line-per-column overview table — fast orientation for wide datasets |
| `--warn` / `-w` | Data quality report — only prints columns with problems |
| `--head N` | Preview the first N rows as a formatted table (default: 10) |
| `--export FILE` | Save output to a file instead of printing (auto-detects format from extension) |
| `--compact` / `-c` | Shorter output — hides histograms, fewer top values |
| `--no-color` | Strip ANSI colors (useful for saving output to a file) |
| `--cols col1,col2,...` | Only profile specific columns (comma-separated) |
| `--sample N` | Profile a random sample of N rows — fast mode for large files |
| `--output terminal` | Default: colored terminal output |
| `--output json` | Machine-readable JSON — pipe to `jq` or save for later |
| `--output html` | Self-contained HTML report with interactive charts |
| `--diff second.csv` | Compare two CSVs and show what changed |
| `--version` / `-v` | Show version and exit |

---

## Examples

```bash
# Full profile of a CSV
ds-profile titanic.csv

# One-line-per-column overview — great for wide datasets
ds-profile titanic.csv --summary

# Data quality issues only — triage before modeling
ds-profile titanic.csv --warn

# Preview the first 10 rows as a formatted table
ds-profile titanic.csv --head

# Preview the first 20 rows
ds-profile titanic.csv --head 20

# Quick summary — no histograms, fast scan
ds-profile titanic.csv --compact

# Only profile specific columns
ds-profile titanic.csv --cols age,fare,survived

# Save a plain-text report to a file
ds-profile titanic.csv --export report.txt

# Save an HTML report to a file
ds-profile titanic.csv --output html --export report.html

# Save a JSON profile to a file
ds-profile titanic.csv --output json --export profile.json

# Save warn output to a file
ds-profile titanic.csv --warn --export issues.txt

# Fast mode for large files — sample 5,000 rows
ds-profile big_data.csv --sample 5000

# Export as JSON and query with jq
ds-profile titanic.csv --output json | jq '.columns[].name'
ds-profile titanic.csv --output json > profile.json

# Generate a shareable HTML report
ds-profile titanic.csv --output html > report.html

# Compare two versions of a dataset
ds-profile train.csv --diff test.csv
ds-profile data_v1.csv --diff data_v2.csv
```

---

## What You Get

### Per-column analysis

**Numeric columns** (`[NUM]`)
- Mean, median, standard deviation
- Min, Q1, Q3, max
- Outlier count using the IQR fence method
- Skewness with interpretation: `symmetric` / `moderate right skew` / `high left skew`
- Block histogram showing the full distribution shape

**Categorical and Boolean columns** (`[CAT]`, `[BOOL]`)
- Top N values with frequency bars and percentages

**All columns**
- Inferred data type: `NUM`, `CAT`, `BOOL`, `DATE`, `TEXT`
- Missing value count with a visual percentage bar
- Unique value count and cardinality ratio
- Sample values

### `--head N` — Row Preview

Prints the first N rows of the CSV as a clean formatted table — the terminal equivalent of `df.head()`. Empty and null-like values are dimmed for easy spotting. If the dataset is too wide for the terminal, it shows as many columns as fit and tells you how many were hidden.

```bash
ds-profile data.csv --head        # first 10 rows (default)
ds-profile data.csv --head 25     # first 25 rows
```

### `--export FILE` — Save to File

Saves the output directly to a file instead of printing to the terminal. Works with every mode — terminal profile, summary, warn, diff, JSON, and HTML. Plain-text formats (terminal, summary, warn, diff) are automatically stripped of ANSI color codes when exported. The file extension doesn't need to match — you choose it.

```bash
ds-profile data.csv --export report.txt               # plain text profile
ds-profile data.csv --output html --export report.html  # HTML report
ds-profile data.csv --output json --export profile.json # JSON
ds-profile data.csv --warn --export issues.txt        # quality report
ds-profile data.csv --summary --export summary.txt    # summary table
```

A confirmation message is printed to stderr after saving:
```
✓  Saved to /path/to/report.html  (42.3 KB)
```

### `--summary` — Overview Table

A compact one-line-per-column table giving instant orientation — ideal when you open a wide dataset with 50+ columns and just need to know what you're dealing with.

Each row shows: column name, inferred type, missing %, unique count, and a type-aware summary (mean/range/skew for numeric, top value + category count for categorical). Sentinel warnings (⚠) are flagged inline. A quick issue count at the bottom tells you whether to run `--warn` next.

```bash
ds-profile data.csv --summary
```

### `--warn` — Data Quality Report

Prints only columns with problems — zero output when data is clean, loud when it isn't. Designed to be the first thing you run on an unfamiliar dataset before any preprocessing.

Checks for:
- **High missing rate** — ≥20% flagged as warning, ≥50% as error
- **Constant/quasi-constant columns** — one value in >95% of rows (useless features)
- **High skewness** — |skew| ≥ 2, with a suggested transform (log1p, sqrt)
- **High outlier rate** — >5% of non-null values outside IQR fence
- **Sentinel values** — encoded nulls like `"N/A"`, `"?"`, `"-999"` that corrupt training
- **High cardinality** — categoricals with >100 unique values (one-hot encoding risk)
- **Duplicate rows** — flagged at dataset level

Each issue is classified as **error** or **warning**, and the report closes with a "Suggested Fixes" section mapping each issue code to a concrete pandas/sklearn remedy.

```bash
ds-profile data.csv --warn
```

### Recommended workflow

```bash
ds-profile data.csv --head          # see what the raw data looks like
ds-profile data.csv --summary       # orient — what columns do I have?
ds-profile data.csv --warn          # find problems before preprocessing
ds-profile data.csv --cols age,fare # drill into suspicious columns
ds-profile data.csv --output html --export report.html  # share with teammates
```
- Row count, column count, file size
- Duplicate row count
- Column type breakdown at a glance

### Pearson Correlation Matrix
Automatically computed for all numeric columns and displayed at the end of the terminal profile. Color-coded by strength:
- **Cyan** — strong correlation (|r| ≥ 0.7)
- **Yellow** — moderate (|r| ≥ 0.4)
- **White** — weak (|r| ≥ 0.2)
- **Dim** — negligible

Hidden in `--compact` mode.

### Sentinel Value Detection
Flags values that look like encoded missing data but aren't actual empty cells — things like `"N/A"`, `"?"`, `"null"`, `"unknown"`, `"-999"`, `"--"`. These silently corrupt model training if left unfixed. Detected in both numeric and categorical columns.

```
⚠ sentinels:  'N/A'×3  '?'×1  (4 masked nulls — fix before modeling)
```

### `--sample N`
Profiles a random sample of N rows instead of the full file. All statistics (mean, std, skewness, correlation, outliers) are computed on the sample. A notice in the overview reminds you it's a sample. Useful for files with millions of rows.

---

## Output Formats

### `--output json`

Exports the complete profile as structured JSON — every stat, histogram bins and edges, top values, correlation matrix, sentinel counts, and sampling metadata. Useful for scripting, saving baselines, or feeding into other tools.

```bash
# Save a baseline profile
ds-profile data.csv --output json > baseline.json

# Extract just column names
ds-profile data.csv --output json | jq '[.columns[].name]'

# Find columns with high missing rates
ds-profile data.csv --output json | jq '[.columns[] | select(.missing_pct > 20)]'
```

### `--output html`

Generates a fully self-contained dark-themed HTML report — one file, no server needed, works offline after the first load (Chart.js loads from CDN).

```bash
ds-profile titanic.csv --output html > report.html
open report.html   # macOS
xdg-open report.html   # Linux
```

The HTML report includes:
- Overview cards (rows, columns, duplicates, file size)
- Interactive bar charts for numeric distributions and categorical frequencies
- Color-coded Pearson correlation heatmap
- Top-level sentinel alert banner if any masked nulls are detected
- Sample notice if `--sample` was used

---

## CSV Diff — `--diff second.csv`

Compare two CSVs and see exactly what changed between them. Useful for checking train vs test set drift, validating data pipeline outputs, or tracking dataset versions.

```bash
ds-profile train.csv --diff test.csv
ds-profile data_before_cleaning.csv --diff data_after_cleaning.csv
```

The diff report shows:
- Row and column count changes
- **Added columns** — present in B but not A
- **Removed columns** — present in A but not B
- **Changed columns** — with specifics:
  - Data type change (e.g. `numeric → boolean`)
  - Missing percentage delta (flagged if > 5 percentage points)
  - Mean shift in standard deviation units (flagged if > 1σ)
  - Distribution overlap score (histogram intersection, 0–100%)
- Unchanged column summary

---

## Dependencies

`ds-profile` has exactly one dependency: [**Rich**](https://github.com/Textualize/rich) — the standard Python library for beautiful terminal output. It powers the formatted tables in `--head`, `--summary`, and `--warn`, and the overview panel in the full profile.

Everything else is pure Python standard library:

- `csv` — CSV parsing
- `statistics` — mean, median, stdev
- `math` — Pearson correlation, histogram
- `collections` — frequency counting
- `argparse` — CLI
- `json` — JSON export
- `html` — HTML escaping

Rich is installed automatically when you install `ds-profile`. If for any reason it's unavailable, the tool gracefully falls back to its built-in ANSI renderer — all features still work. Requires Python 3.8 or later.

---

## License

MIT
