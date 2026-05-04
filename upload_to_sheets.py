"""
Google Sheets 連携スクリプト
results_all_members.csv を Google Sheets にアップロードする

使い方:
  .venv/Scripts/python.exe upload_to_sheets.py
  .venv/Scripts/python.exe upload_to_sheets.py --id <スプレッドシートID>  # 既存シートを更新
  .venv/Scripts/python.exe upload_to_sheets.py --credentials path/to/key.json --csv path/to/data.csv

シート構成:
  1枚目「まとめ」: 全部員の集計表 + 合計距離グラフ + 走行回数グラフ
  2枚目以降: 部員ごとのランニング記録 + 距離推移の折れ線グラフ

事前準備:
  1. Google Cloud Console でサービスアカウントを作成し、キー(JSON)をダウンロード
  2. 対象スプレッドシートをサービスアカウントのメールアドレスと共有（編集者権限）
  3. credentials.json をこのスクリプトと同じフォルダに置く
"""

import csv
import sys
import io
import argparse
from pathlib import Path
from collections import defaultdict

import gspread
from google.oauth2.service_account import Credentials

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]
DEFAULT_CSV = './screenshots/results_all_members.csv'
DEFAULT_CREDENTIALS = 'credentials.json'
SPREADSHEET_TITLE = '千葉工業大学山岳部 ランニング結果'

# まとめシートのヘッダー色 (青系)
COLOR_SUMMARY = (0.20, 0.40, 0.75)
# 部員シートのヘッダー色 (緑系)
COLOR_MEMBER = (0.18, 0.49, 0.31)


# ─── データ処理 ──────────────────────────────────────────────────────────────

def read_csv(csv_path: str) -> list:
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def pace_to_seconds(pace_str: str):
    """M'SS 形式 → 秒数"""
    if not pace_str or pace_str == '--':
        return None
    try:
        m, s = pace_str.split("'")
        return int(m) * 60 + int(s)
    except Exception:
        return None


def seconds_to_pace(seconds) -> str:
    """秒数 → M'SS 形式"""
    if seconds is None:
        return '--'
    return f"{seconds // 60}'{seconds % 60:02d}"


def safe_float(val: str):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def calc_member_stats(rows: list) -> dict:
    """部員ごとの集計を計算し、合計距離の降順で返す"""
    members = defaultdict(list)
    for row in rows:
        members[row['投稿者']].append(row)

    stats = {}
    for name, member_rows in members.items():
        distances = [d for r in member_rows if (d := safe_float(r['距離(km)'])) is not None]
        paces = [p for r in member_rows if (p := pace_to_seconds(r['平均ペース'])) is not None]
        stats[name] = {
            'runs': len(member_rows),
            'total_distance': round(sum(distances), 2) if distances else 0,
            'avg_distance': round(sum(distances) / len(distances), 2) if distances else 0,
            'max_distance': round(max(distances), 2) if distances else 0,
            'best_pace': seconds_to_pace(min(paces)) if paces else '--',
            'rows': sorted(member_rows, key=lambda r: r['日付'])
        }

    return dict(sorted(stats.items(), key=lambda x: x[1]['total_distance'], reverse=True))


def build_summary_data(stats: dict) -> list:
    headers = ['部員名', '走行回数', '合計距離 (km)', '平均距離 (km)', '最長距離 (km)', '最速ペース']
    rows = [headers]
    for name, s in stats.items():
        rows.append([name, s['runs'], s['total_distance'], s['avg_distance'], s['max_distance'], s['best_pace']])
    return rows


def build_time_series_data(stats: dict) -> list:
    """全部員の日付別走行距離をピボット形式で作成（折れ線グラフ用）"""
    member_names = list(stats.keys())
    all_dates = sorted(set(
        row['日付']
        for s in stats.values()
        for row in s['rows']
        if safe_float(row['距離(km)']) is not None
    ))
    rows = [['日付'] + member_names]
    for date in all_dates:
        row_data = [date]
        for name in member_names:
            dist = next(
                (safe_float(r['距離(km)'])
                 for r in stats[name]['rows']
                 if r['日付'] == date and safe_float(r['距離(km)']) is not None),
                ''
            )
            row_data.append(dist)
        rows.append(row_data)
    return rows


def build_member_data(member_rows: list) -> list:
    headers = ['日付', '距離 (km)', '平均ペース', '時間', '高低差']
    data = [headers]
    for row in member_rows:
        dist = safe_float(row['距離(km)'])
        data.append([row['日付'], dist if dist is not None else '--', row['平均ペース'], row['時間'], row['高低差']])
    return data


# ─── Sheets API リクエスト生成 ────────────────────────────────────────────────

def req_format_header(sheet_id: int, num_cols: int, color: tuple) -> dict:
    r, g, b = color
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": num_cols},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": r, "green": g, "blue": b},
                    "textFormat": {
                        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "bold": True, "fontSize": 11
                    },
                    "horizontalAlignment": "CENTER"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }
    }


def req_auto_resize(sheet_id: int, num_cols: int) -> dict:
    return {
        "autoResizeDimensions": {
            "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS",
                           "startIndex": 0, "endIndex": num_cols}
        }
    }


def req_freeze_header(sheet_id: int) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"
        }
    }


def req_column_chart(sheet_id: int, title: str, anchor_row: int, anchor_col: int,
                     data_start: int, data_end: int, domain_col: int, value_col: int,
                     x_title: str, y_title: str) -> dict:
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "COLUMN",
                        "legendPosition": "NO_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": x_title},
                            {"position": "LEFT_AXIS", "title": y_title}
                        ],
                        "domains": [{"domain": {"sourceRange": {"sources": [{
                            "sheetId": sheet_id,
                            "startRowIndex": data_start, "endRowIndex": data_end,
                            "startColumnIndex": domain_col, "endColumnIndex": domain_col + 1
                        }]}}}],
                        "series": [{"series": {"sourceRange": {"sources": [{
                            "sheetId": sheet_id,
                            "startRowIndex": data_start, "endRowIndex": data_end,
                            "startColumnIndex": value_col, "endColumnIndex": value_col + 1
                        }]}}, "targetAxis": "LEFT_AXIS"}]
                    }
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": anchor_col},
                        "widthPixels": 500, "heightPixels": 320
                    }
                }
            }
        }
    }


def req_line_chart(sheet_id: int, title: str, anchor_row: int,
                   data_start: int, data_end: int) -> dict:
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "NO_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "日付"},
                            {"position": "LEFT_AXIS", "title": "距離 (km)"}
                        ],
                        "domains": [{"domain": {"sourceRange": {"sources": [{
                            "sheetId": sheet_id,
                            "startRowIndex": data_start, "endRowIndex": data_end,
                            "startColumnIndex": 0, "endColumnIndex": 1
                        }]}}}],
                        "series": [{"series": {"sourceRange": {"sources": [{
                            "sheetId": sheet_id,
                            "startRowIndex": data_start, "endRowIndex": data_end,
                            "startColumnIndex": 1, "endColumnIndex": 2
                        }]}}, "targetAxis": "LEFT_AXIS"}]
                    }
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": 0},
                        "widthPixels": 600, "heightPixels": 350
                    }
                }
            }
        }
    }


def req_multiline_chart(sheet_id: int, title: str, anchor_row: int,
                        data_start: int, data_end: int, num_series: int) -> dict:
    """全部員の走行距離推移を重ねた折れ線グラフ（1線=1部員）"""
    series = [
        {
            "series": {"sourceRange": {"sources": [{
                "sheetId": sheet_id,
                "startRowIndex": data_start, "endRowIndex": data_end,
                "startColumnIndex": i + 1, "endColumnIndex": i + 2
            }]}},
            "targetAxis": "LEFT_AXIS"
        }
        for i in range(num_series)
    ]
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "BOTTOM_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "日付"},
                            {"position": "LEFT_AXIS", "title": "距離 (km)"}
                        ],
                        "domains": [{"domain": {"sourceRange": {"sources": [{
                            "sheetId": sheet_id,
                            "startRowIndex": data_start, "endRowIndex": data_end,
                            "startColumnIndex": 0, "endColumnIndex": 1
                        }]}}}],
                        "series": series
                    }
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": 0},
                        "widthPixels": 1000, "heightPixels": 420
                    }
                }
            }
        }
    }


# ─── アップロード本体 ─────────────────────────────────────────────────────────

def upload_to_sheets(csv_path: str, credentials_file: str, spreadsheet_id: str = None) -> None:
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    gc = gspread.authorize(creds)

    rows = read_csv(csv_path)
    stats = calc_member_stats(rows)
    member_names = list(stats.keys())
    num_members = len(member_names)

    if spreadsheet_id:
        spreadsheet = gc.open_by_key(spreadsheet_id)
        print(f'既存スプレッドシートを開きました: {spreadsheet.title}')
    else:
        spreadsheet = gc.create(SPREADSHEET_TITLE)
        print(f'スプレッドシートを新規作成しました: {SPREADSHEET_TITLE}')

    print(f'URL: https://docs.google.com/spreadsheets/d/{spreadsheet.id}\n')

    # 既存シートを全削除（最低1枚必要なため、1枚だけ一時シートとして残す）
    existing_sheets = spreadsheet.worksheets()
    placeholder = existing_sheets[0]
    placeholder.update_title('__temp__')
    for ws in existing_sheets[1:]:
        spreadsheet.del_worksheet(ws)

    # ─── まとめシート ───────────────────────────────────────────
    print('まとめシートを作成中...')
    summary_ws = spreadsheet.add_worksheet(title='まとめ', rows=300, cols=30)
    summary_data = build_summary_data(stats)
    summary_ws.update(summary_data, 'A1')

    # 棒グラフ2本の下に時系列ピボットテーブルを書き込む
    ts_data = build_time_series_data(stats)
    ts_start_row = num_members + 22  # 0-indexed: 棒グラフ2本（高さ約320px≒15行）の下
    summary_ws.update(ts_data, f'A{ts_start_row + 1}')
    num_ts_rows = len(ts_data)

    sid = summary_ws._properties['sheetId']
    spreadsheet.batch_update({"requests": [
        req_format_header(sid, 6, COLOR_SUMMARY),
        req_auto_resize(sid, 6),
        req_freeze_header(sid),
        # 合計走行距離の棒グラフ（左）
        req_column_chart(
            sheet_id=sid, title='部員別 合計走行距離 (km)',
            anchor_row=num_members + 3, anchor_col=0,
            data_start=1, data_end=1 + num_members,
            domain_col=0, value_col=2,
            x_title='部員名', y_title='距離 (km)'
        ),
        # 走行回数の棒グラフ（右）
        req_column_chart(
            sheet_id=sid, title='部員別 走行回数',
            anchor_row=num_members + 3, anchor_col=5,
            data_start=1, data_end=1 + num_members,
            domain_col=0, value_col=1,
            x_title='部員名', y_title='回数'
        ),
        # 時系列テーブルのヘッダー書式
        {
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": ts_start_row, "endRowIndex": ts_start_row + 1,
                    "startColumnIndex": 0, "endColumnIndex": num_members + 1
                },
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.20, "green": 0.40, "blue": 0.75},
                    "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                   "bold": True, "fontSize": 11},
                    "horizontalAlignment": "CENTER"
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
            }
        },
        # 全部員の走行距離推移 折れ線グラフ（1線=1部員）
        req_multiline_chart(
            sheet_id=sid,
            title='部員別 走行距離の推移 (km)',
            anchor_row=ts_start_row + num_ts_rows + 2,
            data_start=ts_start_row,
            data_end=ts_start_row + num_ts_rows,
            num_series=num_members
        ),
    ]})
    print('✓ まとめシート完了')

    # ─── 部員シート ─────────────────────────────────────────────
    for member_name in member_names:
        sheet_title = member_name[:99]
        member_ws = spreadsheet.add_worksheet(title=sheet_title, rows=200, cols=10)
        member_data = build_member_data(stats[member_name]['rows'])
        member_ws.update(member_data, 'A1')

        msid = member_ws._properties['sheetId']
        num_rows = len(member_data)

        requests = [
            req_format_header(msid, 5, COLOR_MEMBER),
            req_auto_resize(msid, 5),
            req_freeze_header(msid),
        ]
        if num_rows >= 3:
            requests.append(req_line_chart(
                sheet_id=msid, title='走行距離の推移 (km)',
                anchor_row=num_rows + 2,
                data_start=1, data_end=num_rows
            ))

        spreadsheet.batch_update({"requests": requests})
        print(f'✓ {member_name} のシート完了 ({num_rows - 1}件)')

    # ─── 一時シートを削除 ────────────────────────────────────────
    spreadsheet.del_worksheet(placeholder)

    print(f'\n✓ アップロード完了！')
    print(f'スプレッドシート: https://docs.google.com/spreadsheets/d/{spreadsheet.id}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Google Sheetsにランニング結果をアップロード')
    parser.add_argument('--credentials', default=DEFAULT_CREDENTIALS,
                        help=f'サービスアカウントキーのJSONファイル (デフォルト: {DEFAULT_CREDENTIALS})')
    parser.add_argument('--csv', default=DEFAULT_CSV,
                        help=f'アップロードするCSVファイル (デフォルト: {DEFAULT_CSV})')
    parser.add_argument('--id', default=None,
                        help='既存スプレッドシートのID (省略時は新規作成)')
    args = parser.parse_args()

    if not Path(args.credentials).exists():
        print(f'エラー: 認証ファイルが見つかりません → {args.credentials}')
        print('Google Cloud Console からサービスアカウントキー(JSON)をダウンロードしてください。')
        sys.exit(1)

    if not Path(args.csv).exists():
        print(f'エラー: CSVファイルが見つかりません → {args.csv}')
        sys.exit(1)

    upload_to_sheets(args.csv, args.credentials, args.id)
