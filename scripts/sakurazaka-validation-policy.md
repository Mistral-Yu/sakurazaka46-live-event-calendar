# sakurazaka-validation-policy

このファイルは、`live/event` 運用の実務ルールを集約します。

## 1. データ入力ルール（要点）
- 予定追加は対象 `summary/*.md` の見出し単位で行う。
  - live: `summary/sakurazaka46_live_summary.md`
    - `### ライブ公演の日程`
    - `### 抽選の日程`
    - `### 公式ソース`
  - event/CD/ミーグリ/リアルミーグリ: `summary/sakurazaka46_event_summary.md`
    - `## イベント名`
    - `### イベント開催の日程`
    - `### 抽選の日程`
    - `### 公式ソース`
- live日付は曜日付き、同月連番は1行整理。
- 抽選は原則として時間・祝日を省略する。ただし公式の受付開始/締切時刻が確認対象になる場合は、`6/3(水)昼12:15〜6/9(火)16:00` のように曜日後へ時刻を付ける。
- 公式情報は対象URL/日時/曜日/会場/対象/応募期間で分離して整理。
- 出典は `### 公式ソース` に明記。

## 2. live/event 運用ルール（表示・分類）
- eventの開催は live と同じ開催色を使う。
- event の応募/抽選開始・期間は青、締切は赤。
- `一般発売`/`一般発売中`/`販売終了` は発売系として扱う。
- `オフィシャル先着受付` は抽選扱いではなく販売扱い。
- メッセージキャンペーンは応募として扱い、開催扱いしない。
- `支払い方法選択期限` は応募締切色（deadline）だが、表記はそのまま。
- `四期生 LIVE` → `四期生ライブ`、`BACKS LIVE` → `バックスライブ`。
- 全国ツアー日程のライブは `静岡公演`/`神戸公演`/`広島公演`/`千葉公演`/`宮城公演`/`香川公演`。
- ミニライブ視聴用IDは開催のみ `ミニライブ`、締切は `ミニライブ応募締切`。
- CD封入ミーグリ関連は
  - オンラインミーグリ(全国)
  - 開催は `ミーグリ(全国)`
  - 同一応募帯は `ミーグリ(シリアルコード)応募*` に統合
  - forTUNEの通常オンラインミーグリは `ミーグリ応募*`
- 長いCD/シリアル応募帯は端点のみ日付表示（中間日は塗らない）。
- live抽選は中間日を `中` とし、`継続` は使わない。

## 3. PLAN/UI 補足（要実装反映）
- PLAN参加ルールは `summary` ではなく `index.html` 側の実装規約に従う。
- `#` などの簡易入力制御（チップ種別、参加状態、メンバー入力）仕様は既存実装に合わせる。
- 直近2週間は `Asia/Tokyo` ベースの当日含む14日。
- 祝日のみの日は「祝」表示のみ。詳細パネル・行為者案内は作らない。
- 詳細は同月カード内で1件表示、他月を強制クローズしない。

## 4. 実行ノート（Skill運用側より）
- `scripts/fortune_meet_html_to_plan_json.py` の入力はブラウザ内のみ。
- `scripts/sakurazaka46_members_template.json` を用いたPLANのメンバー候補は維持。
- `forTUNE` HTMLは日付見出し/複数日の抽出・同一メンバー同一部合算。

## 5. 検証チェック
- テスト: `python3 -m pytest tests/test_render_live_calendar.py -q`
- 再生成: `python3 scripts/render_live_calendar.py`
- `summary` 変更時は `index.html`/`ics/*.ics` の再生成差分確認。
- all-mode 検証: `?mode=live/event/all/plan/next14` 切替、色/文言、詳細統合。
- `?mode=next14` は祝日は「祝」だけ、行詳細は当日14日分を表示。
- JSエラーが出ないことを確認。
- 必要に応じてローカルCDP起動:
  - `open -na "Google Chrome" --args --remote-debugging-port=9333 --user-data-dir="/Users/mistralyu/Library/Application Support/Chrome-Hermes"`
  - `file://.../index.html?mode=all&verify=...` を開いて検証。
