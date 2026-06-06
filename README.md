# ds-profile

A lightweight command-line tool that gives you an instant, rich terminal summary of any CSV dataset — column types, missing values, outlier counts, skewness, distribution histograms, a Pearson correlation matrix, sentinel value detection, and CSV diffing. Like `pandas-profiling`, but zero dependencies and fast enough to run on every dataset you open.

No pandas. No numpy. No rich. Pure Python 3.9+ standard library.

## Why?

Every data science workflow starts the same way: open a new dataset, run `.head()`, `.describe()`, `.info()`, `.value_counts()` a dozen times just to get oriented. `ds-profile` collapses all of that into a single command — and catches data quality issues (masked nulls, distribution shifts, type mismatches) that those functions silently miss.

## Installation

Install directly from GitHub using `uv`:

```bash
uv add "git+https://github.com/<your-username>/ds-profile.git"
```

Or with pip:

```bash
pip install "git+https://github.com/<your-username>/ds-profile.git"
```

Requires Python 3.9 or later. No other dependencies.

---

## Usage

```bash
uv run ds-profile data.csv
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
# Note: example CSVs are in the `tests/` folder. Either prefix filenames with
# `tests/` when running from the project root, or `cd tests` first and run the
# commands exactly as shown below.

# Full profile of a CSV
uv run ds-profile titanic.csv

# One-line-per-column overview — great for wide datasets
uv run ds-profile titanic.csv --summary

# Data quality issues only — triage before modeling
uv run ds-profile titanic.csv --warn

# Preview the first 10 rows as a formatted table
uv run ds-profile titanic.csv --head

# Preview the first 20 rows
uv run ds-profile titanic.csv --head 20

# Quick summary — no histograms, fast scan
uv run ds-profile titanic.csv --compact

# Only profile specific columns
uv run ds-profile titanic.csv --cols age,fare,survived

# Save a plain-text report to a file
uv run ds-profile titanic.csv --export report.txt

# Save an HTML report to a file
uv run ds-profile titanic.csv --output html --export report.html

# Save a JSON profile to a file
uv run ds-profile titanic.csv --output json --export profile.json

# Save warn output to a file
uv run ds-profile titanic.csv --warn --export issues.txt

# Fast mode for large files — sample 250 rows
uv run ds-profile big_data.csv --sample 250

# Export as JSON and query with jq
uv run ds-profile titanic.csv --output json | jq '.columns[].name'
uv run ds-profile titanic.csv --output json > profile.json

# Generate a shareable HTML report
uv run ds-profile titanic.csv --output html > report.html

# Compare two versions of a dataset
uv run ds-profile train.csv --diff test.csv
uv run ds-profile data_v1.csv --diff data_v2.csv
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
uv run ds-profile data.csv --head        # first 10 rows (default)
uv run ds-profile data.csv --head 25     # first 25 rows
```

### `--export FILE` — Save to File

Saves the output directly to a file instead of printing to the terminal. Works with every mode — terminal profile, summary, warn, diff, JSON, and HTML. Plain-text formats (terminal, summary, warn, diff) are automatically stripped of ANSI color codes when exported. The file extension doesn't need to match — you choose it.

```bash
uv run ds-profile data.csv --export report.txt               # plain text profile
uv run ds-profile data.csv --output html --export report.html  # HTML report
uv run ds-profile data.csv --output json --export profile.json # JSON
uv run ds-profile data.csv --warn --export issues.txt        # quality report
uv run ds-profile data.csv --summary --export summary.txt    # summary table
```

A confirmation message is printed to stderr after saving:
```
✓  Saved to /path/to/report.html  (42.3 KB)
```

### `--summary` — Overview Table

A compact one-line-per-column table giving instant orientation — ideal when you open a wide dataset with 50+ columns and just need to know what you're dealing with.

Each row shows: column name, inferred type, missing %, unique count, and a type-aware summary (mean/range/skew for numeric, top value + category count for categorical). Sentinel warnings (⚠) are flagged inline. A quick issue count at the bottom tells you whether to run `--warn` next.

```bash
uv run ds-profile data.csv --summary
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
uv run ds-profile data.csv --warn
```

### Recommended workflow

```bash
uv run ds-profile data.csv --head          # see what the raw data looks like
uv run ds-profile data.csv --summary       # orient — what columns do I have?
uv run ds-profile data.csv --warn          # find problems before preprocessing
uv run ds-profile data.csv --cols age,fare # drill into suspicious columns
uv run ds-profile data.csv --output html --export report.html  # share with teammates
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
uv run ds-profile data.csv --output json > baseline.json

# Extract just column names
uv run ds-profile data.csv --output json | jq '[.columns[].name]'

# Find columns with high missing rates
uv run ds-profile data.csv --output json | jq '[.columns[] | select(.missing_pct > 20)]'
```

### `--output html`

Generates a fully self-contained dark-themed HTML report — one file, no server needed, works offline after the first load (Chart.js loads from CDN).

```bash
uv run ds-profile titanic.csv --output html > report.html
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
uv run ds-profile train.csv --diff test.csv
uv run ds-profile data_before_cleaning.csv --diff data_after_cleaning.csv
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

## No Dependencies

`ds-profile` is implemented entirely in the Python standard library:

- `csv` — CSV parsing
- `statistics` — mean, median, stdev
- `math` — Pearson correlation, histogram
- `collections` — frequency counting
- `argparse` — CLI
- `json` — JSON export
- `html` — HTML escaping

No pandas, no numpy, no rich, no click. Installs in under a second and runs on any Python 3.9+ environment with zero setup.

---

## License

MIT

## Included example CSVs (in `tests/`)

The repository includes small example CSV files referenced in the usage examples above. They are located in the `tests/` folder — run the CLI with the `tests/` path or change into `tests/` first:

- [tests/titanic.csv](tests/titanic.csv) — sample Titanic dataset (50 rows)
- [tests/train.csv](tests/train.csv) and [tests/test.csv](tests/test.csv) — example train/test files (same sample data)
- [tests/data.csv](tests/data.csv) — small generic tabular example
- [tests/big_data.csv](tests/big_data.csv) — small representative "big" file for sampling examples
- [tests/data_v1.csv](tests/data_v1.csv) and [tests/data_v2.csv](tests/data_v2.csv) — paired files for `--diff` examples
- [tests/data_before_cleaning.csv](tests/data_before_cleaning.csv) and [tests/data_after_cleaning.csv](tests/data_after_cleaning.csv) — sentinel/cleaning examples

Examples in this README referencing plain filenames (e.g. `titanic.csv`) assume you are in the `tests/` directory; either run `ds-profile tests/titanic.csv` from the project root or `cd tests && ds-profile titanic.csv`.
