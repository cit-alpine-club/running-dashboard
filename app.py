"""
Flask web application — 千葉工業大学山岳部 ランニング結果ダッシュボード
読み込み元: screenshots/results_all_members.csv
"""

import sys
import io
import csv
import json
import unicodedata
from pathlib import Path
from collections import defaultdict
from flask import Flask, render_template, abort

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

app = Flask(__name__)

CSV_PATH = Path(__file__).parent / 'screenshots' / 'results_all_members.csv'
NAME_MAP_FILE = Path(__file__).parent / 'name_map.json'

COLORS = [
    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0',
    '#9966FF', '#FF9F40', '#A8D8A8', '#7BC8A4',
    '#E8A838', '#5899DA', '#EA6B00', '#C084FC',
]


def _extract_surname(name: str) -> str:
    if '　' in name:
        return name.split('　')[0]
    if ' ' in name:
        return name.split(' ')[0]
    if '_' in name:
        return name.split('_')[0]
    if len(name) >= 3:
        return name[:2]
    return name


def load_name_map() -> dict:
    if NAME_MAP_FILE.exists():
        with open(NAME_MAP_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_display_name(name: str, name_map: dict) -> str:
    if name_map.get(name):
        return name_map[name]
    has_cjk = any(unicodedata.category(c).startswith('Lo') for c in name if c not in '_　 ')
    if has_cjk:
        return _extract_surname(name)
    return name


def load_data():
    rows = []
    try:
        with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                if all(row.get(c, '--') == '--' for c in ['距離(km)', '平均ペース', '時間', '高低差']):
                    continue
                rows.append(row)
    except FileNotFoundError:
        pass
    return rows


def parse_distance(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_pace_seconds(pace_str):
    if not pace_str or pace_str == '--':
        return None
    try:
        clean = pace_str.replace("'", ':').replace('"', '')
        parts = clean.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return None


def format_pace(secs):
    if secs is None:
        return '--'
    return f"{secs // 60}'{secs % 60:02d}"


def calc_stats(rows):
    buckets = defaultdict(list)
    for row in rows:
        buckets[row['投稿者']].append(row)

    stats = {}
    for member, member_rows in buckets.items():
        dists = [parse_distance(r['距離(km)']) for r in member_rows]
        dists = [d for d in dists if d is not None]
        paces = [parse_pace_seconds(r['平均ペース']) for r in member_rows]
        paces = [p for p in paces if p is not None]

        stats[member] = {
            'runs': len(dists),
            'total_distance': round(sum(dists), 2),
            'avg_distance': round(sum(dists) / len(dists), 2) if dists else 0,
            'max_distance': max(dists) if dists else 0,
            'best_pace': format_pace(min(paces)) if paces else '--',
            'rows': sorted(member_rows, key=lambda r: r['日付']),
        }

    return dict(sorted(stats.items(), key=lambda x: x[1]['total_distance'], reverse=True))


@app.route('/')
def index():
    rows = load_data()
    stats = calc_stats(rows)
    member_names = list(stats.keys())
    colors = [COLORS[i % len(COLORS)] for i in range(len(member_names))]

    name_map = load_name_map()
    display_names = {m: get_display_name(m, name_map) for m in member_names}
    display_member_names = [display_names[m] for m in member_names]

    all_dates = sorted(set(r['日付'] for r in rows))
    ts_totals = {m: defaultdict(float) for m in member_names}
    for row in rows:
        d = parse_distance(row['距離(km)'])
        if d:
            ts_totals[row['投稿者']][row['日付']] += d

    ts_datasets = []
    for i, member in enumerate(member_names):
        color = COLORS[i % len(COLORS)]
        ts_datasets.append({
            'label': display_names[member],
            'data': [round(ts_totals[member].get(date, 0), 2) or None for date in all_dates],
            'borderColor': color,
            'backgroundColor': color + '33',
            'tension': 0.3,
            'spanGaps': True,
            'pointRadius': 4,
        })

    return render_template('index.html',
        stats=stats,
        member_names=member_names,
        display_names=display_names,
        display_member_names=display_member_names,
        total_distances=[stats[m]['total_distance'] for m in member_names],
        run_counts=[stats[m]['runs'] for m in member_names],
        all_dates=all_dates,
        ts_datasets=ts_datasets,
        colors=colors,
        all_rows=sorted(rows, key=lambda r: r['日付'], reverse=True),
    )


@app.route('/member/<name>')
def member_detail(name):
    rows = load_data()
    stats = calc_stats(rows)
    if name not in stats:
        abort(404)
    s = stats[name]
    name_map = load_name_map()
    return render_template('member.html',
        name=name,
        display_name=get_display_name(name, name_map),
        stats=s,
        member_rows=s['rows'],
        dates=[r['日付'] for r in s['rows']],
        distances=[parse_distance(r['距離(km)']) for r in s['rows']],
    )


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
