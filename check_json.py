import json

with open('千葉工業大学山岳部 - メイン活動 - トレーニング [1351771478999306251] (after 2026-04-01).json', 'r', encoding='utf-8') as f:
    data = json.load(f)

messages = data.get('messages', [])
print(f'メッセージ数: {len(messages)}')

for i, msg in enumerate(messages[:3]):
    attachments = msg.get('attachments', [])
    print(f'メッセージ{i+1}: {len(attachments)} 件添付')
    for j, att in enumerate(attachments[:2]):
        print(f'  添付{j+1}: {att}')