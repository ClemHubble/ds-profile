"""Core profiling logic for ds-profile."""

from __future__ import annotations

import math
import os
import statistics
from dataclasses import dataclass, field
from typing import Any

import csv


@dataclass
class ColumnProfile:
    name: str
    dtype: str  # "numeric", "datetime", "boolean", "categorical", "text"
    count: int
    missing: int
    unique: int
    sample_values: list[Any]

    # numeric only
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    min_val: float | None = None
    max_val: float | None = None
    q1: float | None = None
    q3: float | None = None
    skewness: float | None = None
    outlier_count: int = 0
    histogram: list[int] = field(default_factory=list)
    histogram_edges: list[float] = field(default_factory=list)

    # categorical only
    top_values: list[tuple[str, int]] = field(default_factory=list)

    # data quality
    sentinels: dict[str, int] = field(default_factory=dict)  # sentinel_str -> count


@dataclass
class DatasetProfile:
    filename: str
    total_rows: int
    total_cols: int
    file_size_bytes: int
    columns: list[ColumnProfile]
    duplicate_rows: int = 0
    sampled: bool = False
    sample_size: int | None = None
    # col_name -> col_name -> pearson r
    correlation: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize the full profile to a JSON string."""
        import json

        def col_to_dict(c: ColumnProfile) -> dict:
            return {
                "name": c.name,
                "dtype": c.dtype,
                "count": c.count,
                "missing": c.missing,
                "missing_pct": round(c.missing / max(c.count + c.missing, 1) * 100, 2),
                "unique": c.unique,
                "sample_values": c.sample_values,
                "mean": c.mean,
                "median": c.median,
                "std": c.std,
                "min": c.min_val,
                "max": c.max_val,
                "q1": c.q1,
                "q3": c.q3,
                "skewness": c.skewness,
                "outlier_count": c.outlier_count,
                "histogram": {"counts": c.histogram, "edges": c.histogram_edges},
                "top_values": [{"value": v, "count": n} for v, n in c.top_values],
                "sentinels": c.sentinels,
            }

        return json.dumps(
            {
                "filename": self.filename,
                "total_rows": self.total_rows,
                "total_cols": self.total_cols,
                "file_size_bytes": self.file_size_bytes,
                "duplicate_rows": self.duplicate_rows,
                "sampled": self.sampled,
                "sample_size": self.sample_size,
                "columns": [col_to_dict(c) for c in self.columns],
                "correlation": self.correlation,
            },
            indent=2,
        )

    def warn_issues(self) -> list[dict]:
        """
        Return a list of data quality warnings across all columns.
        Each warning is a dict with keys: column, severity, code, message.
        Severity: "error" | "warning" | "info"
        Codes: high_missing, constant_col, high_skew, high_outliers,
               sentinels, high_cardinality, duplicate_rows
        """
        issues: list[dict] = []

        # Dataset-level
        if self.duplicate_rows > 0:
            pct = self.duplicate_rows / max(self.total_rows, 1) * 100
            issues.append({
                "column": "(dataset)",
                "severity": "warning" if pct < 5 else "error",
                "code": "duplicate_rows",
                "message": f"{self.duplicate_rows:,} duplicate rows ({pct:.1f}% of data)",
            })

        for col in self.columns:
            miss_pct = col.missing / max(self.total_rows, 1) * 100

            # High missing rate
            if miss_pct >= 50:
                issues.append({
                    "column": col.name,
                    "severity": "error",
                    "code": "high_missing",
                    "message": f"{miss_pct:.1f}% missing — consider dropping this column",
                })
            elif miss_pct >= 20:
                issues.append({
                    "column": col.name,
                    "severity": "warning",
                    "code": "high_missing",
                    "message": f"{miss_pct:.1f}% missing values",
                })

            # Constant / quasi-constant column
            if col.unique <= 1:
                issues.append({
                    "column": col.name,
                    "severity": "error",
                    "code": "constant_col",
                    "message": "constant column — only 1 unique value, useless as a feature",
                })
            elif col.count > 0:
                top_freq = col.top_values[0][1] / col.count if col.top_values else 0
                if top_freq >= 0.95 and col.dtype in ("categorical", "boolean"):
                    issues.append({
                        "column": col.name,
                        "severity": "warning",
                        "code": "constant_col",
                        "message": (
                            f"quasi-constant — '{col.top_values[0][0]}' appears in "
                            f"{top_freq*100:.1f}% of rows"
                        ),
                    })

            # High skewness
            if col.skewness is not None and abs(col.skewness) >= 2:
                direction = "right" if col.skewness > 0 else "left"
                issues.append({
                    "column": col.name,
                    "severity": "warning",
                    "code": "high_skew",
                    "message": (
                        f"skewness={col.skewness:+.2f} (high {direction} skew) "
                        f"— consider log1p or sqrt transform"
                    ),
                })

            # High outlier rate
            if col.count > 0 and col.outlier_count > 0:
                outlier_pct = col.outlier_count / col.count * 100
                if outlier_pct >= 5:
                    issues.append({
                        "column": col.name,
                        "severity": "warning",
                        "code": "high_outliers",
                        "message": (
                            f"{col.outlier_count} outliers ({outlier_pct:.1f}% of non-null) "
                            f"by IQR fence"
                        ),
                    })

            # Sentinel values
            if col.sentinels:
                total_sent = sum(col.sentinels.values())
                examples = ", ".join(f'"{k}"' for k in list(col.sentinels.keys())[:3])
                issues.append({
                    "column": col.name,
                    "severity": "error",
                    "code": "sentinels",
                    "message": (
                        f"{total_sent} sentinel value(s) masking nulls: {examples} "
                        f"— replace with actual nulls before modeling"
                    ),
                })

            # High cardinality categorical
            if col.dtype == "categorical" and col.count > 0:
                card_ratio = col.unique / col.count
                if col.unique > 100:
                    issues.append({
                        "column": col.name,
                        "severity": "warning",
                        "code": "high_cardinality",
                        "message": (
                            f"{col.unique} unique values ({card_ratio*100:.1f}% cardinality) "
                            f"— one-hot encoding would produce {col.unique} columns"
                        ),
                    })

        return issues


@dataclass
class ColumnDiff:
    name: str
    status: str  # "added", "removed", "changed", "same"
    dtype_a: str | None = None
    dtype_b: str | None = None
    # numeric shifts
    mean_a: float | None = None
    mean_b: float | None = None
    std_a: float | None = None
    std_b: float | None = None
    missing_pct_a: float | None = None
    missing_pct_b: float | None = None
    # distribution shift (overlap of histograms, 0=no overlap 1=identical)
    histogram_overlap: float | None = None


@dataclass
class DiffResult:
    filename_a: str
    filename_b: str
    rows_a: int
    rows_b: int
    cols_a: int
    cols_b: int
    columns: list[ColumnDiff]

    @property
    def added_cols(self) -> list[str]:
        return [c.name for c in self.columns if c.status == "added"]

    @property
    def removed_cols(self) -> list[str]:
        return [c.name for c in self.columns if c.status == "removed"]

    @property
    def changed_cols(self) -> list[ColumnDiff]:
        return [c for c in self.columns if c.status == "changed"]


def _histogram_overlap(counts_a: list[int], counts_b: list[int]) -> float:
    """Histogram intersection similarity: 1.0 = identical, 0.0 = no overlap."""
    if not counts_a or not counts_b or len(counts_a) != len(counts_b):
        return 0.0
    total_a = sum(counts_a) or 1
    total_b = sum(counts_b) or 1
    norm_a = [c / total_a for c in counts_a]
    norm_b = [c / total_b for c in counts_b]
    return round(sum(min(a, b) for a, b in zip(norm_a, norm_b)), 4)


def diff_profiles(profile_a: DatasetProfile, profile_b: DatasetProfile) -> DiffResult:
    """Compare two DatasetProfiles and return a DiffResult."""
    cols_a = {c.name: c for c in profile_a.columns}
    cols_b = {c.name: c for c in profile_b.columns}
    all_names = list(cols_a.keys()) + [n for n in cols_b if n not in cols_a]

    col_diffs: list[ColumnDiff] = []
    for name in all_names:
        ca = cols_a.get(name)
        cb = cols_b.get(name)

        if ca is None:
            col_diffs.append(ColumnDiff(name=name, status="added", dtype_b=cb.dtype if cb else None))
            continue
        if cb is None:
            col_diffs.append(ColumnDiff(name=name, status="removed", dtype_a=ca.dtype))
            continue

        miss_pct_a = ca.missing / max(profile_a.total_rows, 1) * 100
        miss_pct_b = cb.missing / max(profile_b.total_rows, 1) * 100

        # Decide if "changed" — dtype shift, big mean shift, big missing shift
        changed = False
        if ca.dtype != cb.dtype:
            changed = True
        if ca.dtype == "numeric" and cb.dtype == "numeric":
            if ca.mean is not None and cb.mean is not None and ca.std is not None:
                # Flag if mean shifts by more than 1 std
                if ca.std > 0 and abs((cb.mean - ca.mean) / ca.std) > 1.0:
                    changed = True
        if abs(miss_pct_b - miss_pct_a) > 5:
            changed = True

        overlap = None
        if ca.histogram and cb.histogram and len(ca.histogram) == len(cb.histogram):
            overlap = _histogram_overlap(ca.histogram, cb.histogram)
            if overlap < 0.8:
                changed = True

        col_diffs.append(ColumnDiff(
            name=name,
            status="changed" if changed else "same",
            dtype_a=ca.dtype,
            dtype_b=cb.dtype,
            mean_a=ca.mean,
            mean_b=cb.mean,
            std_a=ca.std,
            std_b=cb.std,
            missing_pct_a=round(miss_pct_a, 2),
            missing_pct_b=round(miss_pct_b, 2),
            histogram_overlap=overlap,
        ))

    return DiffResult(
        filename_a=profile_a.filename,
        filename_b=profile_b.filename,
        rows_a=profile_a.total_rows,
        rows_b=profile_b.total_rows,
        cols_a=profile_a.total_cols,
        cols_b=profile_b.total_cols,
        columns=col_diffs,
    )


def _try_float(val: str) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _try_bool(val: str) -> bool | None:
    v = val.strip().lower()
    if v in ("true", "yes", "1", "t", "y"):
        return True
    if v in ("false", "no", "0", "f", "n"):
        return False
    return None


def _try_date(val: str) -> bool:
    """Heuristic: does this string look like a date?"""
    import re
    patterns = [
        r"\d{4}-\d{2}-\d{2}",
        r"\d{2}/\d{2}/\d{4}",
        r"\d{2}-\d{2}-\d{4}",
        r"\d{4}/\d{2}/\d{2}",
    ]
    for p in patterns:
        if re.fullmatch(p, val.strip()):
            return True
    return False


def _infer_dtype(values: list[str]) -> str:
    non_empty = [v for v in values if v.strip() != ""]
    if not non_empty:
        return "empty"

    sample = non_empty[:200]

    # Check boolean
    bool_hits = sum(1 for v in sample if _try_bool(v) is not None)
    if bool_hits / len(sample) > 0.9:
        return "boolean"

    # Check numeric
    num_hits = sum(1 for v in sample if _try_float(v) is not None)
    if num_hits / len(sample) > 0.8:
        return "numeric"

    # Check date
    date_hits = sum(1 for v in sample if _try_date(v))
    if date_hits / len(sample) > 0.7:
        return "datetime"

    # Check cardinality for categorical vs text
    unique_ratio = len(set(sample)) / len(sample)
    avg_len = statistics.mean(len(v) for v in sample)
    abs_unique = len(set(sample))

    # Classify as categorical if:
    # - low cardinality ratio (< 50% unique), OR
    # - absolute unique count is small (≤ 50), as long as values are short
    # This prevents small datasets where every value is unique from being misclassified as text
    if avg_len < 50 and (unique_ratio < 0.5 or abs_unique <= 50):
        return "categorical"
    return "text"


def _compute_skewness(values: list[float]) -> float | None:
    n = len(values)
    if n < 3:
        return None
    try:
        mean = statistics.mean(values)
        std = statistics.stdev(values)
        if std == 0:
            return 0.0
        skew = sum((x - mean) ** 3 for x in values) / n / (std ** 3)
        return round(skew, 4)
    except Exception:
        return None


def _compute_histogram(values: list[float], bins: int = 10) -> tuple[list[int], list[float]]:
    if not values:
        return [], []
    mn, mx = min(values), max(values)
    if mn == mx:
        return [len(values)], [mn, mx]
    step = (mx - mn) / bins
    edges = [mn + i * step for i in range(bins + 1)]
    counts = [0] * bins
    for v in values:
        idx = int((v - mn) / (mx - mn) * bins)
        if idx == bins:
            idx = bins - 1
        counts[idx] += 1
    return counts, [round(e, 4) for e in edges]


def _outliers_iqr(values: list[float], q1: float, q3: float) -> int:
    iqr = q3 - q1
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    return sum(1 for v in values if v < lo or v > hi)


def _percentile(sorted_vals: list[float], p: float) -> float:
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    idx = (n - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r between two same-length float lists."""
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 4)


def _build_correlation(columns: list[ColumnProfile]) -> dict[str, dict[str, float]]:
    """Build pairwise Pearson correlation matrix for all numeric columns."""
    numeric_cols = [(c.name, c) for c in columns if c.dtype == "numeric" and c.mean is not None]
    if len(numeric_cols) < 2:
        return {}

    # Rebuild float lists from histogram edges isn't enough — we need raw values.
    # They were already computed inside profile_csv; pass them through via a side channel.
    # We store raw floats temporarily on the column object (stripped before return).
    result: dict[str, dict[str, float]] = {}
    for i, (name_a, col_a) in enumerate(numeric_cols):
        result[name_a] = {}
        raw_a: list[float] = getattr(col_a, "_raw_floats", [])
        for j, (name_b, col_b) in enumerate(numeric_cols):
            if i == j:
                result[name_a][name_b] = 1.0
                continue
            raw_b: list[float] = getattr(col_b, "_raw_floats", [])
            # Align by index (both come from same rows, same length)
            pairs = [(a, b) for a, b in zip(raw_a, raw_b)
                     if a is not None and b is not None]
            if not pairs:
                continue
            xs, ys = zip(*pairs)
            r = _pearson(list(xs), list(ys))
            if r is not None:
                result[name_a][name_b] = r
    return result


def profile_csv(path: str, sample_n: int | None = None) -> DatasetProfile:
    """Read a CSV and return a full DatasetProfile."""
    file_size = os.path.getsize(path)

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no headers or is empty.")
        headers = list(reader.fieldnames)
        raw: dict[str, list[str]] = {h: [] for h in headers}
        rows: list[tuple[str, ...]] = []
        for row in reader:
            t = tuple(row.get(h, "") or "" for h in headers)
            rows.append(t)
            for h in headers:
                raw[h].append(row.get(h, "") or "")

    # Apply sampling after reading (reservoir would be better for huge files,
    # but this keeps it simple and dependency-free)
    sampled = False
    actual_sample_size = None
    if sample_n is not None and sample_n < len(rows):
        import random
        indices = sorted(random.sample(range(len(rows)), sample_n))
        rows = [rows[i] for i in indices]
        for h in headers:
            raw[h] = [raw[h][i] for i in indices]
        sampled = True
        actual_sample_size = sample_n

    total_rows = len(rows)

    # Duplicate detection
    seen: set[tuple] = set()
    dup_count = 0
    for r in rows:
        if r in seen:
            dup_count += 1
        seen.add(r)

    columns: list[ColumnProfile] = []

    for h in headers:
        vals = raw[h]
        missing = sum(1 for v in vals if v.strip() == "")
        non_missing = [v for v in vals if v.strip() != ""]
        unique = len(set(vals))
        dtype = _infer_dtype(vals)

        # Sample values (up to 3 non-empty)
        sample_vals = []
        for v in non_missing:
            if v not in sample_vals:
                sample_vals.append(v)
            if len(sample_vals) == 3:
                break

        col = ColumnProfile(
            name=h,
            dtype=dtype,
            count=total_rows - missing,
            missing=missing,
            unique=unique,
            sample_values=sample_vals,
        )

        if dtype == "numeric":
            # Sentinel detection: values that look like "missing" but aren't empty
            SENTINELS = {
                "n/a", "na", "nan", "null", "none", "nil", "missing",
                "?", "-", "--", ".", "unknown", "n.a.", "n.a", "#n/a",
                "999", "9999", "99999", "-999", "-9999", "-1", "999999",
            }
            sentinel_hits: dict[str, int] = {}
            for v in vals:
                vl = v.strip().lower()
                if vl in SENTINELS and _try_float(v) is None:
                    sentinel_hits[v.strip()] = sentinel_hits.get(v.strip(), 0) + 1
                # Also catch numeric sentinels that parsed but are suspiciously round extremes
            if sentinel_hits:
                col.sentinels = sentinel_hits

            floats = [_try_float(v) for v in non_missing]
            floats = [f for f in floats if f is not None]
            if floats:
                sorted_f = sorted(floats)
                col.mean = round(statistics.mean(floats), 4)
                col.median = round(statistics.median(floats), 4)
                col.std = round(statistics.stdev(floats), 4) if len(floats) > 1 else 0.0
                col.min_val = sorted_f[0]
                col.max_val = sorted_f[-1]
                col.q1 = round(_percentile(sorted_f, 25), 4)
                col.q3 = round(_percentile(sorted_f, 75), 4)
                col.skewness = _compute_skewness(floats)
                col.outlier_count = _outliers_iqr(floats, col.q1, col.q3)
                col.histogram, col.histogram_edges = _compute_histogram(floats)
                # Stash raw floats for correlation (keyed by original row index)
                # We need full-row alignment, so store per-row (None if missing)
                row_floats = [_try_float(v) for v in vals]
                object.__setattr__(col, "_raw_floats", row_floats)  # type: ignore[call-arg]
                col._raw_floats = row_floats  # type: ignore[attr-defined]

        elif dtype in ("categorical", "boolean", "text"):
            from collections import Counter
            counts = Counter(non_missing)
            col.top_values = counts.most_common()
            # Detect sentinel strings hiding as categories
            SENT_CAT = {"n/a", "na", "nan", "null", "none", "nil", "missing",
                        "?", "unknown", "n.a.", "#n/a", "-", "--"}
            sentinel_hits = {v: c for v, c in counts.items() if v.strip().lower() in SENT_CAT}
            if sentinel_hits:
                col.sentinels = sentinel_hits

        columns.append(col)

    # Build correlation matrix
    corr = _build_correlation(columns)

    # Clean up temp attributes
    for col in columns:
        if hasattr(col, "_raw_floats"):
            del col._raw_floats  # type: ignore[attr-defined]

    return DatasetProfile(
        filename=os.path.basename(path),
        total_rows=total_rows,
        total_cols=len(headers),
        file_size_bytes=file_size,
        columns=columns,
        duplicate_rows=dup_count,
        sampled=sampled,
        sample_size=actual_sample_size,
        correlation=corr,
    )
