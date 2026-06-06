"""Generate a self-contained HTML profile report."""

from __future__ import annotations

import json
import html as html_module
from .profiler import DatasetProfile, ColumnProfile


def _esc(s: str) -> str:
    return html_module.escape(str(s))


def _badge(dtype: str) -> str:
    colors = {
        "numeric":     ("#22d3ee", "#0e7490"),
        "categorical": ("#c084fc", "#7e22ce"),
        "boolean":     ("#4ade80", "#166534"),
        "datetime":    ("#fbbf24", "#92400e"),
        "text":        ("#e2e8f0", "#334155"),
        "empty":       ("#94a3b8", "#1e293b"),
    }
    bg, fg = colors.get(dtype, ("#e2e8f0", "#334155"))
    label = dtype.upper()
    return (f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:9999px;'
            f'font-size:0.7rem;font-weight:700;letter-spacing:0.05em">{label}</span>')


def _missing_bar(missing: int, total: int) -> str:
    if total == 0:
        return ""
    pct = missing / total * 100
    color = "#ef4444" if pct > 10 else "#22c55e"
    return f'''<div style="display:flex;align-items:center;gap:8px">
      <div style="width:120px;height:8px;background:#1e293b;border-radius:4px;overflow:hidden">
        <div style="width:{pct:.1f}%;height:100%;background:{color};border-radius:4px"></div>
      </div>
      <span style="color:{color};font-weight:600">{pct:.1f}%</span>
      <span style="color:#64748b">({missing:,}/{total:,})</span>
    </div>'''


def _skew_badge(skew: float | None) -> str:
    if skew is None:
        return '<span style="color:#64748b">n/a</span>'
    abs_s = abs(skew)
    if abs_s < 0.5:
        color, label = "#22c55e", "symmetric"
    elif abs_s < 1.0:
        color, label = "#fbbf24", f"{'right' if skew > 0 else 'left'} skew"
    else:
        color, label = "#ef4444", f"high {'right' if skew > 0 else 'left'} skew"
    return f'<span style="color:{color};font-weight:600">{skew:+.3f}</span> <span style="color:{color};font-size:0.8em">({label})</span>'


def _sentinel_warning(col: ColumnProfile) -> str:
    if not col.sentinels:
        return ""
    items = "  ".join(f"<code>{_esc(k)}</code>×{v}" for k, v in list(col.sentinels.items())[:5])
    total = sum(col.sentinels.values())
    return f'''<div style="margin-top:10px;padding:8px 12px;background:#450a0a;border-left:3px solid #ef4444;border-radius:4px">
      <span style="color:#ef4444;font-weight:700">⚠ Sentinel values detected:</span>
      <span style="color:#fca5a5;margin-left:8px">{items}</span>
      <span style="color:#f87171;margin-left:8px">— {total} masked nulls, fix before modeling</span>
    </div>'''


def _col_card(col: ColumnProfile, total_rows: int, idx: int) -> str:
    chart_id = f"chart_{idx}"
    missing_html = _missing_bar(col.missing, total_rows)
    badge = _badge(col.dtype)
    sentinel_html = _sentinel_warning(col)

    unique_pct = col.unique / max(col.count, 1) * 100

    stats_html = ""
    chart_html = ""

    if col.dtype == "numeric" and col.mean is not None:
        outlier_color = "#ef4444" if col.outlier_count > 0 else "#22c55e"
        stats_html = f'''
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0">
          <div class="stat-box"><div class="stat-label">Mean</div><div class="stat-val">{col.mean}</div></div>
          <div class="stat-box"><div class="stat-label">Median</div><div class="stat-val">{col.median}</div></div>
          <div class="stat-box"><div class="stat-label">Std Dev</div><div class="stat-val">{col.std}</div></div>
          <div class="stat-box"><div class="stat-label">Min</div><div class="stat-val">{col.min_val}</div></div>
          <div class="stat-box"><div class="stat-label">Q1</div><div class="stat-val">{col.q1}</div></div>
          <div class="stat-box"><div class="stat-label">Q3</div><div class="stat-val">{col.q3}</div></div>
          <div class="stat-box"><div class="stat-label">Max</div><div class="stat-val">{col.max_val}</div></div>
          <div class="stat-box"><div class="stat-label">Outliers (IQR)</div>
            <div class="stat-val" style="color:{outlier_color}">{col.outlier_count}</div></div>
          <div class="stat-box"><div class="stat-label">Skewness</div>
            <div class="stat-val">{_skew_badge(col.skewness)}</div></div>
        </div>'''

        if col.histogram and col.histogram_edges:
            labels = [f"{col.histogram_edges[i]:.3g}–{col.histogram_edges[i+1]:.3g}"
                      for i in range(len(col.histogram))]
            chart_data = json.dumps(col.histogram)
            chart_labels = json.dumps(labels)
            chart_html = f'''
        <div style="height:180px;margin-top:8px">
          <canvas id="{chart_id}"></canvas>
        </div>
        <script>
        (function(){{
          new Chart(document.getElementById('{chart_id}'), {{
            type: 'bar',
            data: {{
              labels: {chart_labels},
              datasets: [{{
                data: {chart_data},
                backgroundColor: 'rgba(34,211,238,0.7)',
                borderColor: 'rgba(34,211,238,1)',
                borderWidth: 1,
                borderRadius: 3,
              }}]
            }},
            options: {{
              responsive: true, maintainAspectRatio: false,
              plugins: {{ legend: {{ display: false }} }},
              scales: {{
                x: {{ ticks: {{ color:'#94a3b8', font:{{size:9}}, maxRotation:45 }},
                       grid: {{ color:'#1e293b' }} }},
                y: {{ ticks: {{ color:'#94a3b8' }}, grid: {{ color:'#1e293b' }} }}
              }}
            }}
          }});
        }})();
        </script>'''

    elif col.dtype in ("categorical", "boolean") and col.top_values:
        top_n = col.top_values[:8]
        top_labels = json.dumps([str(v) for v, _ in top_n])
        top_counts = json.dumps([c for _, c in top_n])
        chart_html = f'''
        <div style="height:200px;margin-top:12px">
          <canvas id="{chart_id}"></canvas>
        </div>
        <script>
        (function(){{
          new Chart(document.getElementById('{chart_id}'), {{
            type: 'bar',
            data: {{
              labels: {top_labels},
              datasets: [{{
                data: {top_counts},
                backgroundColor: 'rgba(192,132,252,0.7)',
                borderColor: 'rgba(192,132,252,1)',
                borderWidth: 1,
                borderRadius: 3,
              }}]
            }},
            options: {{
              indexAxis: 'y',
              responsive: true, maintainAspectRatio: false,
              plugins: {{ legend: {{ display: false }} }},
              scales: {{
                x: {{ ticks: {{ color:'#94a3b8' }}, grid: {{ color:'#1e293b' }} }},
                y: {{ ticks: {{ color:'#94a3b8', font:{{size:10}} }}, grid: {{ color:'#1e293b' }} }}
              }}
            }}
          }});
        }})();
        </script>'''

    samples_html = ""
    if col.sample_values:
        chips = "".join(
            f'<code style="background:#1e293b;padding:2px 6px;border-radius:4px;font-size:0.8em;color:#94a3b8">{_esc(str(v))}</code> '
            for v in col.sample_values[:3]
        )
        samples_html = f'<div style="margin-top:6px"><span style="color:#64748b;font-size:0.8em">Samples: </span>{chips}</div>'

    return f'''
    <div class="col-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="margin:0;font-size:1rem;color:#f1f5f9">{_esc(col.name)}</h3>
        {badge}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:0.85rem;color:#94a3b8;margin-bottom:10px">
        <div>Missing: {missing_html}</div>
        <div>Unique: <span style="color:#e2e8f0;font-weight:600">{col.unique:,}</span>
          <span style="color:#475569"> ({unique_pct:.1f}%)</span></div>
      </div>
      {samples_html}
      {sentinel_html}
      {stats_html}
      {chart_html}
    </div>'''


def _corr_table(corr: dict[str, dict[str, float]]) -> str:
    if not corr or len(corr) < 2:
        return ""
    names = list(corr.keys())

    def cell_color(r: float, is_diag: bool) -> str:
        if is_diag:
            return "background:#1e293b;color:#475569"
        abs_r = abs(r)
        if abs_r >= 0.7:
            intensity = int(abs_r * 200)
            if r > 0:
                return f"background:rgba(34,211,238,{abs_r*0.8:.2f});color:#0c4a6e;font-weight:700"
            else:
                return f"background:rgba(239,68,68,{abs_r*0.8:.2f});color:#fff;font-weight:700"
        elif abs_r >= 0.4:
            if r > 0:
                return f"background:rgba(34,211,238,{abs_r*0.5:.2f});color:#164e63"
            else:
                return f"background:rgba(239,68,68,{abs_r*0.5:.2f});color:#7f1d1d"
        return "background:#0f172a;color:#64748b"

    header_cells = "".join(
        f'<th style="padding:6px 10px;font-size:0.75rem;color:#94a3b8;white-space:nowrap">{_esc(n[:12])}</th>'
        for n in names
    )
    rows_html = ""
    for na in names:
        cells = "".join(
            f'<td style="padding:6px 10px;text-align:center;font-size:0.8rem;{cell_color(corr.get(na,{}).get(nb,0), na==nb)}">'
            f'{corr.get(na,{}).get(nb,0):+.2f}</td>'
            for nb in names
        )
        rows_html += f'<tr><th style="padding:6px 10px;text-align:right;font-size:0.75rem;color:#94a3b8;white-space:nowrap">{_esc(na[:12])}</th>{cells}</tr>'

    return f'''
    <div class="section">
      <h2 class="section-title">Correlation Matrix <span style="font-size:0.75rem;color:#475569;font-weight:400">(Pearson r)</span></h2>
      <div style="overflow-x:auto">
        <table style="border-collapse:collapse;font-family:monospace">
          <thead><tr><th></th>{header_cells}</tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
      <div style="margin-top:12px;font-size:0.8rem;color:#64748b">
        <span style="color:#22d3ee">■</span> positive  
        <span style="color:#ef4444;margin-left:12px">■</span> negative  
        <span style="color:#94a3b8;margin-left:12px">|r| ≥ 0.7 strong · ≥ 0.4 moderate</span>
      </div>
    </div>'''


def render_html(profile: DatasetProfile) -> str:
    """Render a complete self-contained HTML profile report."""
    import datetime

    size_kb = profile.file_size_bytes / 1024
    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    from collections import Counter
    dtype_counts = Counter(c.dtype for c in profile.columns)
    dtype_pills = "".join(_badge(dt) + f' <span style="color:#94a3b8;font-size:0.85rem">{n}</span> ' for dt, n in sorted(dtype_counts.items()))

    sentinel_cols = [c for c in profile.columns if c.sentinels]
    sentinel_alert = ""
    if sentinel_cols:
        names = ", ".join(f"<code>{_esc(c.name)}</code>" for c in sentinel_cols)
        sentinel_alert = f'''<div style="margin:16px 0;padding:12px 16px;background:#450a0a;border-left:4px solid #ef4444;border-radius:6px;color:#fca5a5">
          <strong style="color:#ef4444">⚠ Sentinel values detected in {len(sentinel_cols)} column(s):</strong> {names}<br>
          <span style="font-size:0.85rem;color:#f87171">These look like encoded missing values. Replace them with actual nulls before training.</span>
        </div>'''

    sample_notice = ""
    if profile.sampled and profile.sample_size:
        sample_notice = f'<div style="margin:12px 0;padding:8px 14px;background:#1c1917;border-left:3px solid #fbbf24;border-radius:4px;color:#fbbf24;font-size:0.85rem">Sampled: stats computed on {profile.sample_size:,} rows (random sample)</div>'

    col_cards = "\n".join(_col_card(col, profile.total_rows, i) for i, col in enumerate(profile.columns))
    corr_html = _corr_table(profile.correlation)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ds-profile · {_esc(profile.filename)}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0f172a; color: #e2e8f0; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; padding: 24px; }}
  .header {{ background: linear-gradient(135deg,#0e7490,#4f46e5); border-radius: 12px; padding: 28px 32px; margin-bottom: 24px; }}
  .header h1 {{ font-size: 1.6rem; font-weight: 800; color: #fff; margin-bottom: 4px; }}
  .header .sub {{ color: rgba(255,255,255,0.7); font-size: 0.9rem; }}
  .overview-grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(140px,1fr)); gap: 12px; margin-bottom: 24px; }}
  .overview-card {{ background: #1e293b; border-radius: 10px; padding: 16px; text-align: center; }}
  .overview-card .ov-val {{ font-size: 1.5rem; font-weight: 800; color: #f1f5f9; }}
  .overview-card .ov-label {{ font-size: 0.75rem; color: #64748b; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .section {{ background: #1e293b; border-radius: 10px; padding: 24px; margin-bottom: 24px; }}
  .section-title {{ font-size: 1rem; font-weight: 700; color: #f1f5f9; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .col-grid {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(340px,1fr)); gap: 16px; }}
  .col-card {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 10px; padding: 18px; }}
  .stat-box {{ background: #1e293b; border-radius: 6px; padding: 10px; text-align: center; }}
  .stat-label {{ font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; }}
  .stat-val {{ font-size: 0.95rem; font-weight: 700; color: #f1f5f9; margin-top: 4px; }}
  code {{ font-family: "JetBrains Mono","Fira Code",monospace; }}
  .footer {{ text-align: center; color: #334155; font-size: 0.8rem; margin-top: 32px; padding: 16px; }}
</style>
</head>
<body>

<div class="header">
  <h1>📊 {_esc(profile.filename)}</h1>
  <div class="sub">ds-profile report · generated {generated}</div>
</div>

<div class="overview-grid">
  <div class="overview-card"><div class="ov-val">{profile.total_rows:,}</div><div class="ov-label">Rows</div></div>
  <div class="overview-card"><div class="ov-val">{profile.total_cols}</div><div class="ov-label">Columns</div></div>
  <div class="overview-card"><div class="ov-val" style="color:{'#ef4444' if profile.duplicate_rows else '#22c55e'}">{profile.duplicate_rows:,}</div><div class="ov-label">Duplicates</div></div>
  <div class="overview-card"><div class="ov-val">{size_str}</div><div class="ov-label">File Size</div></div>
</div>

<div class="section">
  <div class="section-title">Column Types</div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">{dtype_pills}</div>
</div>

{sentinel_alert}
{sample_notice}

{corr_html}

<div class="section">
  <div class="section-title">Column Profiles</div>
  <div class="col-grid">
{col_cards}
  </div>
</div>

<div class="footer">ds-profile · zero dependencies · pure Python stdlib</div>

</body>
</html>'''
