"""
JSONのattachmentsに記載されたファイルだけを残し、
それ以外の画像/PDFファイルを削除するスクリプト。

使い方:
  .venv/Scripts/python.exe cleanup_attachments.py export.json
"""

import argparse
import json
from pathlib import Path


def get_attachment_filenames(export_json: Path) -> set[str]:
    """JSONからattachmentsのファイル名を抽出する。"""
    with export_json.open('r', encoding='utf-8') as f:
        data = json.load(f)

    filenames = set()

    messages = data.get('messages') or data.get('items') or data
    if not isinstance(messages, list):
        raise ValueError('JSONの形式が想定と異なります。')

    for message in messages:
        attachments = message.get('attachments') or message.get('attachments_info') or []
        if not isinstance(attachments, list):
            continue

        for attachment in attachments:
            filename = None
            if isinstance(attachment, dict):
                filename = attachment.get('url') or attachment.get('fileName') or attachment.get('filename') or attachment.get('name')
            elif isinstance(attachment, str):
                filename = Path(attachment).name

            if filename:
                filenames.add(filename)

    return filenames


def cleanup_files(export_json: Path, dry_run: bool = True) -> None:
    """attachmentsにないファイルを削除する。"""
    base_dir = export_json.parent
    valid_filenames = get_attachment_filenames(export_json)

    # 画像/PDFファイルの拡張子
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.svg'}
    doc_extensions = {'.pdf'}

    target_extensions = image_extensions | doc_extensions

    deleted = 0
    kept = 0

    for file_path in base_dir.iterdir():
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in target_extensions:
            continue

        if file_path.name in valid_filenames:
            print(f'✓ 保持: {file_path.name}')
            kept += 1
        else:
            if dry_run:
                print(f'🗑️ 削除予定: {file_path.name}')
            else:
                file_path.unlink()
                print(f'🗑️ 削除: {file_path.name}')
            deleted += 1

    print(f'\n結果: {kept} 件保持、{deleted} 件{"削除予定" if dry_run else "削除"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='JSONのattachmentsに記載されたファイルだけを残します。')
    parser.add_argument('export_json', type=str, help='Discord Chat Exporterの出力JSONファイル')
    parser.add_argument('--delete', action='store_true', help='実際に削除する（デフォルトはdry-run）')
    args = parser.parse_args()

    export_json = Path(args.export_json)
    cleanup_files(export_json, dry_run=not args.delete)