r"""
ランニング結果 自動更新パイプライン

手順:
  1. pipeline_config.json にトークンと設定を記入
  2. tools\ に DiscordChatExporter.Cli.exe を配置
  3. .venv\Scripts\python.exe run_pipeline.py

フロー:
  Discord Chat Exporter CLI
      → discord_export_to_screenshots.py
      → NRC_Test_batch.py
      → results_all_members.csv 更新 (Flask が自動反映)
"""

import sys
import io
import os
import json
import argparse
import logging
import subprocess
import time
from pathlib import Path
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent
PYTHON = sys.executable
SCREENSHOTS_DIR = str(BASE_DIR / 'screenshots')
LOG_FILE = BASE_DIR / 'pipeline.log'
CONFIG_FILE = BASE_DIR / 'pipeline_config.json'
EXPORT_JSON = BASE_DIR / 'discord_export.json'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

_EXCLUDE_JSON = {'credentials.json', 'token.json', 'pipeline_config.json'}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def find_latest_json() -> Path | None:
    """プロジェクトフォルダ内で最新の Discord export JSON を自動検索"""
    jsons = sorted(
        (p for p in BASE_DIR.glob('*.json') if p.name not in _EXCLUDE_JSON),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return jsons[0] if jsons else None


def run_step(label: str, cmd: list[str], retries: int = 0) -> bool:
    log.info(f'--- {label} 開始 ---')
    for attempt in range(retries + 1):
        if attempt > 0:
            log.warning(f'{label} リトライ {attempt}/{retries}')
            time.sleep(5)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(BASE_DIR),
        )
        for line in result.stdout.splitlines():
            if line.strip():
                log.info(f'  {line}')
        for line in result.stderr.splitlines():
            if line.strip():
                log.warning(f'  {line}')
        if result.returncode == 0:
            log.info(f'{label} 完了')
            return True
        log.error(f'{label} 失敗 (code {result.returncode})')
    return False


def step_dce_export(config: dict) -> Path | None:
    """Discord Chat Exporter CLI で最新メッセージをエクスポート"""
    dce = config.get('dce_cli_path', '')
    token = config.get('discord_token', '')
    channel = config.get('channel_id', '')

    if not all([dce, token, channel]):
        log.info('DCE CLI 未設定 → スキップ（既存 JSON を使用）')
        return None

    dce_path = Path(dce) if Path(dce).is_absolute() else BASE_DIR / dce
    if not dce_path.exists():
        log.error(f'DCE CLI が見つかりません: {dce_path}')
        return None

    # after: 設定値 or 90日前（毎日実行なら十分な余裕）
    after = config.get('export_after') or (
        datetime.now() - timedelta(days=90)
    ).strftime('%Y-%m-%d')

    media_dir = BASE_DIR / 'screenshots_backup'
    media_dir.mkdir(exist_ok=True)

    ok = run_step('Discord Chat Exporter CLI', [
        str(dce_path), 'export',
        '--token', token,
        '--bot',
        '--channel', channel,
        '--format', 'Json',
        '--output', str(EXPORT_JSON),
        '--after', after,
        '--media',
        '--media-dir', str(media_dir),
        '--reuse-media',
    ])

    return EXPORT_JSON if ok and EXPORT_JSON.exists() else None


def step_git_push() -> None:
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    csv_rel = 'screenshots/results_all_members.csv'

    github_token = os.environ.get('GITHUB_TOKEN', '')
    if github_token:
        subprocess.run(['git', 'config', 'user.email', 'bot@running-dashboard.com'], cwd=str(BASE_DIR))
        subprocess.run(['git', 'config', 'user.name', 'Running Bot'], cwd=str(BASE_DIR))
        remote = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, cwd=str(BASE_DIR),
        ).stdout.strip()
        if 'github.com' in remote and f'{github_token}@' not in remote:
            authed = remote.replace('https://github.com/', f'https://{github_token}@github.com/')
            subprocess.run(['git', 'remote', 'set-url', 'origin', authed], cwd=str(BASE_DIR))

    subprocess.run(['git', 'add', csv_rel, 'screenshots/'], cwd=str(BASE_DIR))
    result = subprocess.run(
        ['git', 'commit', '-m', f'データ自動更新 {timestamp}'],
        capture_output=True, text=True, encoding='utf-8', cwd=str(BASE_DIR),
    )
    if 'nothing to commit' in result.stdout + result.stderr:
        log.info('CSV に変更なし → push スキップ')
        return

    ok = run_step('git push', ['git', 'push'])
    if ok:
        log.info('Render への反映完了（自動再デプロイ開始）')


def run_pipeline(json_path: str | None = None, skip_dce: bool = False) -> None:
    log.info(f'======= パイプライン開始  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} =======')

    config = load_config()

    # Step 0: Discord Chat Exporter CLI
    if not skip_dce and not json_path:
        json_file = step_dce_export(config)
        if json_file is None:
            json_file = find_latest_json()
    else:
        json_file = Path(json_path) if json_path else find_latest_json()

    # Step 1: 画像を screenshots/ に振り分け
    if json_file and json_file.exists():
        log.info(f'Discord JSON: {json_file.name}')
        run_step('discord_export_to_screenshots', [
            PYTHON,
            str(BASE_DIR / 'discord_export_to_screenshots.py'),
            str(json_file),
            SCREENSHOTS_DIR,
        ])
    else:
        log.info('JSON なし → OCRのみ実行（既存の screenshots を再処理）')

    # Step 2: OCR → results_all_members.csv
    run_step('NRC_Test_batch (OCR)', [
        PYTHON,
        str(BASE_DIR / 'NRC_Test_batch.py'),
        SCREENSHOTS_DIR,
    ], retries=2)

    log.info(f'======= パイプライン完了  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} =======\n')

    # CSV を GitHub に push → Render が自動再デプロイ
    step_git_push()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ランニング結果 更新パイプライン')
    parser.add_argument('--json', metavar='PATH', help='JSON パスを直接指定（DCE CLI をスキップ）')
    parser.add_argument('--skip-dce', action='store_true', help='DCE CLI をスキップして既存 JSON を使用')
    args = parser.parse_args()
    run_pipeline(args.json, skip_dce=args.skip_dce)
