"""
Flask web application — 千葉工業大学山岳部 ランニング結果ダッシュボード
読み込み元: screenshots/results_all_members.csv
"""

import sys
import io
import csv
import json
import datetime
import unicodedata
from pathlib import Path
from collections import defaultdict
from flask import Flask, render_template, abort

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

app = Flask(__name__)

CSV_PATH = Path(__file__).parent / 'screenshots' / 'results_all_members.csv'
NAME_MAP_FILE = Path(__file__).parent / 'name_map.json'
MONTHLY_GOAL_KM = 10.0

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


def parse_elevation(val):
    if not val or val == '--':
        return None
    cleaned = val.replace('m', '').replace('M', '').replace(',', '').strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def calc_stats(rows):
    buckets = defaultdict(list)
    for row in rows:
        buckets[row['投稿者']].append(row)

    today = datetime.date.today()
    this_month_start = today.replace(day=1)

    stats = {}
    for member, member_rows in buckets.items():
        dists_valid = [d for d in (parse_distance(r['距離(km)']) for r in member_rows) if d is not None]
        paces_valid = [p for p in (parse_pace_seconds(r['平均ペース']) for r in member_rows) if p is not None]
        elevs_valid = [e for e in (parse_elevation(r.get('高低差', '')) for r in member_rows) if e is not None]

        monthly_dist = 0.0
        for r in member_rows:
            try:
                if datetime.date.fromisoformat(r['日付']) >= this_month_start:
                    d = parse_distance(r['距離(km)'])
                    if d:
                        monthly_dist += d
            except Exception:
                pass

        stats[member] = {
            'runs': len(dists_valid),
            'total_distance': round(sum(dists_valid), 2),
            'avg_distance': round(sum(dists_valid) / len(dists_valid), 2) if dists_valid else 0,
            'max_distance': max(dists_valid) if dists_valid else 0,
            'best_pace': format_pace(min(paces_valid)) if paces_valid else '--',
            'max_elevation': int(max(elevs_valid)) if elevs_valid else None,
            'total_elevation': int(sum(elevs_valid)) if elevs_valid else None,
            'monthly_distance': round(monthly_dist, 2),
            'rows': sorted(member_rows, key=lambda r: r['日付']),
        }

    return dict(sorted(stats.items(), key=lambda x: x[1]['total_distance'], reverse=True))


def calc_heatmap(rows):
    """Returns {member: {date: distance_km}} for days with at least one run."""
    data = defaultdict(lambda: defaultdict(float))
    for row in rows:
        d = parse_distance(row['距離(km)'])
        if d:
            data[row['投稿者']][row['日付']] += d
    return {m: dict(dates) for m, dates in data.items()}


@app.route('/')
def index():
    rows = load_data()
    stats = calc_stats(rows)
    member_names = list(stats.keys())
    colors = [COLORS[i % len(COLORS)] for i in range(len(member_names))]

    name_map = load_name_map()
    display_names = {m: get_display_name(m, name_map) for m in member_names}
    display_member_names = [display_names[m] for m in member_names]

    today = datetime.date.today()
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = datetime.date(today.year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        month_end = datetime.date(today.year, today.month + 1, 1) - datetime.timedelta(days=1)
    all_dates = []
    _d = month_start
    while _d <= month_end:
        all_dates.append(_d.isoformat())
        _d += datetime.timedelta(days=1)
    heatmap_data = calc_heatmap(rows)
    month_achieved = [m for m, s in stats.items() if s['monthly_distance'] >= MONTHLY_GOAL_KM]

    this_month_label = f"{today.year}年{today.month}月"

    return render_template('index.html',
        stats=stats,
        member_names=member_names,
        display_names=display_names,
        display_member_names=display_member_names,
        total_distances=[stats[m]['total_distance'] for m in member_names],
        monthly_distances=[stats[m]['monthly_distance'] for m in member_names],
        run_counts=[stats[m]['runs'] for m in member_names],
        all_dates=all_dates,
        colors=colors,
        all_rows=sorted(rows, key=lambda r: r['日付'], reverse=True),
        heatmap_data=heatmap_data,
        month_achieved=month_achieved,
        monthly_goal=MONTHLY_GOAL_KM,
        this_month_label=this_month_label,
    )


@app.route('/member/<name>')
def member_detail(name):
    rows = load_data()
    stats = calc_stats(rows)
    if name not in stats:
        abort(404)
    s = stats[name]
    name_map = load_name_map()

    activity_set = [r['日付'] for r in s['rows'] if parse_distance(r['距離(km)'])]
    today = datetime.date.today()
    monthly_achieved = s['monthly_distance'] >= MONTHLY_GOAL_KM

    return render_template('member.html',
        name=name,
        display_name=get_display_name(name, name_map),
        stats=s,
        member_rows=s['rows'],
        dates=[r['日付'] for r in s['rows']],
        distances=[parse_distance(r['距離(km)']) for r in s['rows']],
        activity_set=activity_set,
        monthly_achieved=monthly_achieved,
        monthly_distance=s['monthly_distance'],
        monthly_goal=MONTHLY_GOAL_KM,
        today_str=today.isoformat(),
    )


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
