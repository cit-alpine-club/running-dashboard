"""
複数メンバー・複数週のフォルダ構造に対応したOCR処理
フォルダ構造: screenshots/[メンバー名]/[週フォルダ]/画像ファイル
出力: 各メンバー・各週のフォルダにresults.csvを生成
"""

import sys
import io
import pytesseract
import re
import csv
from datetime import datetime
from PIL import Image, ImageEnhance
from pathlib import Path

# Windows コンソールの文字化け対策
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Tesseract のパスを設定
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def extract_data_from_image(image_path: str) -> dict:
    """
    スクショから日付、距離、平均ペース、時間、高低差を抽出
    
    Args:
        image_path: 画像ファイルのパス
    
    Returns:
        辞書形式のデータ
    """
    try:
        # 画像を開く
        img = Image.open(image_path)

        # 週フォルダ名（例: 2026-04-08_week）から日付を取得
        file_path = Path(image_path)
        week_folder_name = file_path.parent.name
        date_match = re.match(r'(\d{4}-\d{2}-\d{2})', week_folder_name)
        if date_match:
            date_str = date_match.group(1)
        else:
            date_str = datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d')
        
        # まず前処理なしでOCR
        text = pytesseract.image_to_string(img, lang='eng+jpn')
        match_distance = re.search(r'(\d+\.\d+)', text)
        
        if not match_distance:
            # 前処理ありで再試行
            enhancer = ImageEnhance.Contrast(img)
            img_processed = enhancer.enhance(2.0)
            img_processed = img_processed.convert('L')
            img_processed = img_processed.resize((img_processed.width * 2, img_processed.height * 2), Image.LANCZOS)
            text = pytesseract.image_to_string(img_processed, lang='eng+jpn')
            match_distance = re.search(r'(\d+\.\d+)', text)
        
        distance = float(match_distance.group(1)) if match_distance else None
        
        # ペース: M'SS 形式で抽出（末尾の " は除去して正規化）
        # OCRは '（アポストロフィ）を "（ダブルクォート）や '（右シングルクォート）と誤読することがある
        match_pace = re.search(r"(\d+)['’\"](\d{2})[\"']*", text)
        pace = f"{match_pace.group(1)}'{match_pace.group(2)}" if match_pace else None
        
        # 時間: : を含むパターン (最後のものを時間とする)
        matches_time = re.findall(r'(\d+:\d+(?::\d+)?)', text)
        time_str = matches_time[-1] if matches_time else None
        
        # 高低差: 'm' のパターン
        match_elevation = re.search(r'(\d+)\s*m', text, re.IGNORECASE)
        elevation = match_elevation.group(1) + ' m' if match_elevation else None
        
        return {
            'date': date_str,
            'filename': file_path.name,
            'distance': distance,
            'pace': pace,
            'time': time_str,
            'elevation': elevation
        }
    
    except Exception as e:
        print(f"  エラー ({Path(image_path).name}): {e}")
        return {
            'date': '',
            'filename': Path(image_path).name,
            'distance': None,
            'pace': None,
            'time': None,
            'elevation': None
        }


def process_week_folder(week_folder: Path) -> list:
    """
    週ごとのフォルダ内の画像を処理
    
    Args:
        week_folder: 週フォルダのパス
    
    Returns:
        処理結果のリスト
    """
    # PNG と JPG ファイルを全て取得
    image_files = sorted(list(week_folder.glob('*.png')) + list(week_folder.glob('*.jpg')))
    
    if not image_files:
        return []
    
    results = []
    for image_path in image_files:
        data = extract_data_from_image(str(image_path))
        results.append(data)
    
    return results


def process_member_folder(member_folder: Path) -> None:
    """
    メンバーフォルダ内の週フォルダを処理
    
    Args:
        member_folder: メンバーフォルダのパス
    """
    member_name = member_folder.name
    print(f"\n【{member_name}】")
    
    # 週フォルダを取得（サブフォルダのみ）
    week_folders = sorted([f for f in member_folder.iterdir() if f.is_dir()])
    
    if not week_folders:
        # サブフォルダがない場合、このフォルダ直下の画像を処理
        results = process_week_folder(member_folder)
        if results:
            output_csv = member_folder / 'results.csv'
            _write_csv(output_csv, results)
            print(f"  ✓ CSV出力: {output_csv}")
        else:
            print("  スクショが見つかりません")
        return
    
    for week_folder in week_folders:
        results = process_week_folder(week_folder)
        
        if results:
            output_csv = week_folder / 'results.csv'
            _write_csv(output_csv, results)
            print(f"  ✓ {week_folder.name}: {len(results)}ファイル処理完了")
        else:
            print(f"  - {week_folder.name}: スクショなし")

    # メンバー単位の集計CSVを生成
    aggregate_member_csv(member_folder)


def _write_csv(csv_path: Path, results: list) -> None:
    """
    結果をCSVに書き込み
    
    Args:
        csv_path: 出力CSVのパス
        results: 処理結果のリスト
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['日付', '距離(km)', '平均ペース', '時間', '高低差', 'ファイル名'])
        writer.writeheader()
        
        for data in results:
            writer.writerow({
                '日付': data['date'],
                '距離(km)': data['distance'] if data['distance'] else '--',
                '平均ペース': data['pace'] if data['pace'] else '--',
                '時間': data['time'] if data['time'] else '--',
                '高低差': data['elevation'] if data['elevation'] else '--',
                'ファイル名': data['filename']
            })


def aggregate_member_csv(member_folder: Path) -> None:
    """
    各メンバーの週別CSVをまとめて、メンバー別集計CSVを生成する。
    """
    summary_rows = []
    for week_folder in sorted([f for f in member_folder.iterdir() if f.is_dir()]):
        csv_path = week_folder / 'results.csv'
        if not csv_path.exists():
            continue
        with open(csv_path, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            summary_rows.extend(list(reader))

    if not summary_rows:
        return

    summary_path = member_folder / 'results_summary.csv'
    with open(summary_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['日付', '距離(km)', '平均ペース', '時間', '高低差', 'ファイル名'])
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"  ✓ メンバー集計CSV出力: {summary_path}")


def process_all_screenshots(screenshots_dir: str) -> None:
    """
    スクリーンショットフォルダ内のすべてのメンバーを処理
    
    Args:
        screenshots_dir: スクリーンショット親フォルダのパス
    """
    root_dir = Path(screenshots_dir)
    
    # メンバーフォルダを取得
    member_folders = sorted([f for f in root_dir.iterdir() if f.is_dir()])
    
    if not member_folders:
        print("メンバーフォルダが見つかりません")
        return
    
    print(f"処理開始: {len(member_folders)}メンバー\n")
    
    all_rows = []
    for member_folder in member_folders:
        process_member_folder(member_folder)
        summary_path = member_folder / 'results_summary.csv'
        if summary_path.exists():
            with open(summary_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row['投稿者'] = member_folder.name
                    all_rows.append(row)
    
    overall_csv = root_dir / 'results_all_members.csv'
    if all_rows:
        with open(overall_csv, 'w', newline='', encoding='utf-8-sig') as f:
            fieldnames = ['投稿者', '日付', '距離(km)', '平均ペース', '時間', '高低差', 'ファイル名']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"\n✓ 全体集計CSV出力: {overall_csv}")
    
    print("\n✓ 全メンバーの処理完了")


if __name__ == '__main__':
    # スクリーンショットのディレクトリを指定
    import sys
    if len(sys.argv) > 1:
        screenshot_dir = sys.argv[1]
    else:
        screenshot_dir = './screenshots'
    process_all_screenshots(screenshot_dir)
