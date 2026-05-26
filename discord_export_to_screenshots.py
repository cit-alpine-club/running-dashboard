"""
Discord Chat ExporterのJSONエクスポートから画像を抽出し、
投稿者名ごとのフォルダにコピーするスクリプト。

使い方:
  .venv/Scripts/python.exe discord_export_to_screenshots.py export.json ./screenshots

注: JSON形式でのエクスポートを推奨します。
"""

import argparse
import io
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

_JST = timezone(timedelta(hours=9))

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

INVALID_PATH_CHARS = '<>:"/\\|?*'


def sanitize_folder_name(name: str) -> str:
    """投稿者名をフォルダ名として使えるように整形する。"""
    name = name.strip()
    for ch in INVALID_PATH_CHARS:
        name = name.replace(ch, '_')
    name = name.replace(' ', '_')
    if not name:
        return 'unknown'
    return name


def parse_timestamp(timestamp: str) -> str:
    """ISO形式のタイムスタンプから日付文字列を生成する。"""
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.astimezone(_JST).strftime('%Y-%m-%d')
    except Exception:
        try:
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return datetime.now().strftime('%Y-%m-%d')


def find_attachment_file(base_dir: Path, filename: str) -> Path | None:
    """エクスポート先ディレクトリ内で画像ファイルを検索する。
    DCE は {stem}-{hash}{suffix} で保存するため glob でも検索する。
    """
    # URL クエリパラメータを除去
    clean = filename.split('?')[0]
    stem = Path(clean).stem
    suffix = Path(clean).suffix

    search_dirs = [base_dir, base_dir / 'attachments', base_dir / 'screenshots_backup']

    for d in search_dirs:
        if not d.exists():
            continue
        # 完全一致
        if (d / clean).exists():
            return d / clean
        # DCEが付与するハッシュサフィックス付き (例: IMG_7847-8a2036a23bc3f2b1.png)
        for p in d.glob(f'{stem}-*{suffix}'):
            if p.is_file():
                return p

    # フォルダ全体から再帰検索
    for p in base_dir.rglob(f'{stem}-*{suffix}'):
        if p.is_file():
            return p
    for p in base_dir.rglob(clean):
        if p.is_file():
            return p

    return None


def process_export(export_json: Path, output_root: Path) -> None:
    """JSONエクスポートを読み、投稿者名別に画像を保存する。"""
    with export_json.open('r', encoding='utf-8') as f:
        data = json.load(f)

    base_dir = export_json.parent
    output_root.mkdir(parents=True, exist_ok=True)

    copied = 0
    missing = 0
    # メンバーごとに既存ファイル名を追跡（同一ファイルの重複コピーを防ぐ）
    seen_per_author: dict[str, set[str]] = {}

    # Discord Chat Exporter JSONがメッセージの配列を含む想定
    messages = data.get('messages') or data.get('items') or data
    if not isinstance(messages, list):
        raise ValueError('JSONの形式が想定と異なります。messagesまたはitems配列を含む必要があります。')

    for message in messages:
        author_name = None
        if isinstance(message, dict):
            author = message.get('author', {})
            if isinstance(author, dict):
                author_name = author.get('nickname') or author.get('display_name') or author.get('username') or author.get('name')
            else:
                author_name = author
        else:
            author_name = None

        if not author_name:
            author_name = 'unknown'

        author_folder = sanitize_folder_name(str(author_name))

        # このメンバーの既存ファイル名セットを初期化（ディスク上のファイルも含む）
        if author_folder not in seen_per_author:
            author_root = output_root / author_folder
            seen_per_author[author_folder] = {
                p.name for p in author_root.rglob('*') if p.is_file()
            } if author_root.exists() else set()

        timestamp = message.get('timestamp') or message.get('createdAt') or message.get('created_at') or ''
        date_str = parse_timestamp(timestamp) if timestamp else datetime.now().strftime('%Y-%m-%d')
        week_folder_name = f'{date_str}_week'
        dest_folder = output_root / author_folder / week_folder_name
        dest_folder.mkdir(parents=True, exist_ok=True)

        attachments = message.get('attachments') or message.get('attachments_info') or []
        if not isinstance(attachments, list):
            continue

        for attachment in attachments:
            filename = None
            if isinstance(attachment, dict):
                # DCE JSON: fileName が元ファイル名、url は CDN URL
                filename = (attachment.get('fileName') or attachment.get('filename')
                            or attachment.get('name') or attachment.get('url', ''))
            elif isinstance(attachment, str):
                filename = Path(attachment).name

            if not filename:
                continue

            # 同じメンバーの別フォルダに既に存在する場合はスキップ（重複防止）
            if filename in seen_per_author[author_folder]:
                continue

            source_file = find_attachment_file(base_dir, filename)
            if not source_file:
                print(f'⚠️  添付ファイルが見つかりません: {filename}')
                missing += 1
                continue

            dest_file = dest_folder / filename
            shutil.copy2(source_file, dest_file)
            seen_per_author[author_folder].add(filename)
            copied += 1
            print(f'コピー: {source_file} -> {dest_file}')

    print(f'\n完了: {copied} 件コピー、{missing} 件見つからず')
    if missing > 0:
        print(f'⚠️  WARNING: {missing} 件の添付ファイルが見つかりませんでした。')
        print('   考えられる原因: Discord CDN の URL 期限切れ、または DCE の --media オプションが未指定。')
        print('   対処: pipeline_config.json に export_after を指定して再実行するか、手動で screenshots/ に配置してください。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Discord Chat Exporter JSONから画像を投稿者別にコピーします。')
    parser.add_argument('export_json', type=str, help='Discord Chat Exporterの出力JSONファイル')
    parser.add_argument('output_dir', type=str, help='画像を保存する親ディレクトリ (例: ./screenshots)')
    args = parser.parse_args()

    export_json = Path(args.export_json)
    output_dir = Path(args.output_dir)
    process_export(export_json, output_dir)
