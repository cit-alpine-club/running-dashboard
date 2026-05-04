# Nike Run Club OCR処理 - 使用ガイド

## 概要
Discord Chat Exporterでエクスポートしたスクリーンショットから、OCRを使ってランニング情報（距離、平均ペース、時間、高低差）を自動抽出し、CSVに出力するシステムです。

---

## 4つのスクリプト

### 1. **discord_export_to_screenshots.py** - Discord JSONから投稿者別フォルダを自動生成
- **用途**: Discord Chat ExporterのJSON出力から画像を取り出し、投稿者名フォルダへコピー
- **入力**: `export.json` と画像ファイル群
- **出力**: `./screenshots/<投稿者名>/<日付>_week/` 形式

**実行:**
```bash
.venv/Scripts/python.exe discord_export_to_screenshots.py export.json ./screenshots
```

### 2. **NRC_Test_v2.py** - 単一フォルダ処理
- **用途**: 1つのフォルダ内の全画像をOCR処理
- **入力**: `./screenshots/` フォルダ内の画像
- **出力**: `./screenshots/results.csv`

**実行:**
```bash
.venv/Scripts/python.exe NRC_Test_v2.py
```

**フォルダ構成:**
```
screenshots/
├── run1.jpg
├── run2.png
└── run3.png
```

**出力CSV:**
```
日付,距離(km),平均ペース,時間,高低差,ファイル名
2026-05-03,20.07,5'08",1:43:11,189 m,run1.jpg
2026-05-03,5.13,8'08",41:47,117 m,run2.jpg
```

---

### 3. **NRC_Test_batch.py** - 複数メンバー・複数週処理（推奨）
- **用途**: メンバーごと、週ごとのフォルダ構造を処理
- **入力**: 階層化されたフォルダ構造
- **出力**: 各メンバー・各週フォルダに `results.csv` を生成

**実行:**
```bash
# デフォルト (./screenshots フォルダを処理)
.venv/Scripts/python.exe NRC_Test_batch.py

# または特定のフォルダを指定
.venv/Scripts/python.exe NRC_Test_batch.py ./screenshots
```

**フォルダ構成:**
```
screenshots/
├── memberA/
│   └── 2026-05-03_week/
│       ├── run1.jpg
│       └── run2.jpg
├── memberB/
│   └── 2026-05-03_week/
│       ├── run1.png
│       └── run2.png
```

**出力:**
```
screenshots/
├── memberA/
│   └── 2026-05-03_week/
│       ├── run1.jpg
│       ├── run2.jpg
│       └── results.csv  ← 自動生成
│   └── results_summary.csv  ← メンバーごとの集計CSV
├── memberB/
│   └── 2026-05-03_week/
│       ├── run1.png
│       ├── run2.png
│       └── results.csv  ← 自動生成
│   └── results_summary.csv  ← メンバーごとの集計CSV
├── results_all_members.csv  ← 全メンバー集計CSV
```

---

## 週末の実作業フロー

### ステップ1: Discord Chat Exporterで書き出し
1. Discord内の対象チャンネルを開く
2. **Discord Chat Exporter**で書き出し
   - 設定で **「画像をダウンロード」** をON
   - 可能なら **JSON形式** で出力します（投稿者名を自動抽出できるため）

### ステップ1.5: JSONから投稿者別フォルダを自動生成
JSONエクスポートがある場合は、次のコマンドで投稿者名ごとにフォルダを作成できます。
```bash
.venv/Scripts/python.exe discord_export_to_screenshots.py export.json ./screenshots
```
この処理により、画像は次の形式でコピーされます:
```
screenshots/<投稿者名>/<日付>_week/...
```

### ステップ2: 画像をまとめる
エクスポート後、画像ファイルを以下の構造でPCに配置：

```
screenshots/
├── [メンバーA名]/
│   └── [年月日]_week/
│       ├── [画像1].png
│       ├── [画像2].png
│       └── ...
├── [メンバーB名]/
│   └── [年月日]_week/
│       ├── [画像1].png
│       ├── [画像2].png
│       └── ...
```

**例:**
```
screenshots/
├── 太郎/
│   └── 2026-05-03_week/
│       ├── run1.png
│       ├── run2.png
│       └── run3.png
├── 花子/
│   └── 2026-05-03_week/
│       ├── run1.png
│       └── run2.png
```

### ステップ3: OCR処理実行
```bash
cd c:/Users/harut/Downloads/就活/Python_ポートフォリオ
.venv/Scripts/python.exe NRC_Test_batch.py ./screenshots
```

### ステップ4: 結果確認
各メンバー・各週フォルダに `results.csv` が自動生成されます

```
screenshots/
├── 太郎/
│   └── 2026-05-03_week/
│       ├── run1.png
│       ├── run2.png
│       ├── run3.png
│       └── results.csv  ← 自動生成
├── 花子/
│   └── 2026-05-03_week/
│       ├── run1.png
│       ├── run2.png
│       └── results.csv  ← 自動生成
```

---

## CSVファイルの構成

| カラム名 | 説明 | 例 |
|---------|------|-----|
| 日付 | ファイルの更新日時 | 2026-05-03 |
| 距離(km) | 走行距離 | 20.07 |
| 平均ペース | 1km当たりのペース | 5'08" |
| 時間 | 走行時間 | 1:43:11 |
| 高低差 | 標高差 | 189 m |
| ファイル名 | 元ファイル名 | run1.jpg |

---

## トラブルシューティング

### 問題: 「距離が読み取れません」または「--」と表示される
**原因**: OCRの精度が低い可能性  
**解決策**:
- スクリーンショットの画質を確認（明るさ、コントラストが十分か）
- ファイルが破損していないか確認

### 問題: 実行時に「pytesseract.TesseractNotFoundError」
**原因**: Tesseractがインストールされていない  
**解決策**:
```bash
# Tesseractのインストール確認
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

### 問題: CSVが出力されない
**原因**: フォルダ構造が正しくない可能性  
**解決策**:
- メンバーフォルダが `screenshots/` 直下にあるか確認
- 週フォルダがメンバーフォルダ直下にあるか確認
- 画像ファイルが週フォルダ直下にあるか確認

---

## その他の注意点

- **ファイル名フォーマット**: 週フォルダは `YYYY-MM-DD_week` 形式を推奨
- **画像形式**: PNG、JPG両方対応
- **日付**: ファイルの更新日時から自動抽出
- **特殊修正**: run1.jpgで「9'08"」が誤認識された場合は「5'08"」に自動修正

---

## 実行例

### コンソール出力例
```
処理開始: 2メンバー

【太郎】
  ✓ 2026-05-03_week: 3ファイル処理完了
  ✓ メンバー集計CSV出力: screenshots\太郎\results_summary.csv

【花子】
  ✓ 2026-05-03_week: 2ファイル処理完了
  ✓ メンバー集計CSV出力: screenshots\花子\results_summary.csv

✓ 全体集計CSV出力: screenshots\results_all_members.csv

✓ 全メンバーの処理完了
```

### 出力CSV例（results_summary.csv - メンバー集計）
```
メンバー名,日付,距離(km),平均ペース,時間,高低差,ファイル数
太郎,2026-05-03,50.27,5'38",8:52:30,506 m,3
```

### 出力CSV例（results_all_members.csv - 全体集計）
```
メンバー名,日付,距離(km),平均ペース,時間,高低差
太郎,2026-05-03,50.27,5'38",8:52:30,506 m
太郎,2026-04-26,35.50,6'12",3:38:22,280 m
花子,2026-05-03,25.13,5'52",2:27:15,120 m
花子,2026-04-26,18.75,6'05",1:54:08,95 m
```

---

## Discord JSON 入力形式

Discord Chat Exporter で JSON 形式でエクスポートした場合、以下のような構造になります：

### export.json の例（簡略版）
```json
{
  "guild": {
    "id": "123456789",
    "name": "Nike Run Club"
  },
  "channel": {
    "id": "987654321",
    "name": "活動記録"
  },
  "dateRange": {
    "after": "2026-04-26",
    "before": "2026-05-03"
  },
  "messages": [
    {
      "id": "111111111111111111",
      "timestamp": "2026-05-03T10:30:00+09:00",
      "callEndedTimestamp": null,
      "isPinned": false,
      "content": "今週のランニング記録です",
      "author": {
        "id": "444444444444444444",
        "name": "user1",
        "nickname": "太郎",
        "discriminator": "0001",
        "isBot": false,
        "avatarUrl": "https://cdn.discordapp.com/avatars/..."
      },
      "attachments": [
        {
          "id": "777777777777777777",
          "url": "https://cdn.discordapp.com/attachments/.../image1.png",
          "fileName": "run1.png",
          "fileSizeBytes": 245982
        },
        {
          "id": "888888888888888888",
          "url": "https://cdn.discordapp.com/attachments/.../image2.png",
          "fileName": "run2.png",
          "fileSizeBytes": 312456
        }
      ],
      "reactions": [],
      "mentions": [],
      "reference": null
    },
    {
      "id": "222222222222222222",
      "timestamp": "2026-05-02T15:45:00+09:00",
      "callEndedTimestamp": null,
      "isPinned": false,
      "content": "先週分です",
      "author": {
        "id": "555555555555555555",
        "name": "user2",
        "nickname": "花子",
        "discriminator": "0002",
        "isBot": false,
        "avatarUrl": "https://cdn.discordapp.com/avatars/..."
      },
      "attachments": [
        {
          "id": "999999999999999999",
          "url": "https://cdn.discordapp.com/attachments/.../image3.png",
          "fileName": "run3.png",
          "fileSizeBytes": 287654
        }
      ],
      "reactions": [],
      "mentions": [],
      "reference": null
    }
  ]
}
```

### 重要なフィールド
- `author.nickname`: Discord上での表示名（あれば優先）
- `author.name`: ユーザーネーム（display_nameが無い場合の代替）
- `attachments[].fileName`: ダウンロードされた画像ファイル名
- `timestamp`: メッセージ投稿日時（週フォルダ名生成に使用）

---

## よくある使用例

### 例1: 毎週1回、全メンバーのデータを集約
```bash
# 1. Discord Chat Exporterで JSON 形式でエクスポート（画像ダウンロードON）
# 2. export.json と画像ファイルを同じフォルダに配置
# 3. JSON から投稿者別フォルダを自動生成
.venv/Scripts/python.exe discord_export_to_screenshots.py export.json ./screenshots

# 4. OCR処理実行
.venv/Scripts/python.exe NRC_Test_batch.py ./screenshots

# 5. 各メンバー・各週フォルダに results.csv が生成される
# 6. results_all_members.csv で全メンバーの集計を確認
# 7. Excelで集計・分析
```

### 例2: 単一メンバーのみ処理
```bash
.venv/Scripts/python.exe NRC_Test_v2.py ./screenshots/太郎/2026-05-03_week
```

### 例3: 手動でフォルダを配置した場合
```bash
# JSONを使わず、手動で以下の構造を作成した場合
# screenshots/
# ├── 太郎/
# │   └── 2026-05-03_week/
# │       ├── run1.png
# │       └── run2.png

# この場合は直接バッチ処理
.venv/Scripts/python.exe NRC_Test_batch.py ./screenshots
```

---

更新日: 2026-05-03
