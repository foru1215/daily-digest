# Daily Digest

GitHub Projects v2「Life Board」の毎日のタスクを **朝 / 昼 / 夜** に分けて通知するシステム。

## 仕組み

1. GitHub Actions (cron JST 6:00) が起動
2. GraphQL API で Projects v2 のアイテムを取得
3. 2層抽出:
   - **Layer 1**: `Due = 今日` のカード（週次レビューで手動設定）
   - **Layer 2**: `開始日 <= 今日 <= 終了日 AND Status = In Progress` のアクティブスプリント
4. 朝/昼/夜に分類して Issue を1本作成（GitHub通知で受信）

## セットアップ

### 1. Fine-grained PAT の作成

1. https://github.com/settings/personal-access-tokens/new にアクセス
2. 設定:
   - **Token name:** `daily-digest`
   - **Expiration:** 90 days（定期的に更新）
   - **Repository access:** `Only select repositories` → `foru1215/daily-digest` + `foru1215/life`
   - **Repository permissions:**
     - Issues: **Read and write**（daily-digest リポ用）
   - **Account permissions:**
     - Projects: **Read-only**（Life Board 読み取り用）
3. `Generate token` → コピー

### 2. Secret の登録

1. https://github.com/foru1215/daily-digest/settings/secrets/actions にアクセス
2. `New repository secret` をクリック
3. **Name:** `GH_PAT` / **Value:** 上でコピーしたトークン

### 3. 動作確認（Dry Run）

1. https://github.com/foru1215/daily-digest/actions にアクセス
2. `Daily Digest` ワークフローを選択
3. `Run workflow` → `dry_run` を `true` に設定 → `Run workflow`
4. ログで Digest 出力を確認

### 4. 本番実行

```bash
# CLI から手動実行
gh workflow run daily-digest.yml --repo foru1215/daily-digest

# dry-run
gh workflow run daily-digest.yml --repo foru1215/daily-digest -f dry_run=true
```

毎日 JST 6:00 に自動実行されます。

## Digest の見方

```markdown
## ☀️ 朝
- [ ] ⭐ **電工一種：スプリント** — 過去問5問解く (45分)

## 🌤️ 昼
- [ ] **電工一種：スプリント** — 問11〜20を解く (45分) `[Sprint]`

## 🌙 夜
- [ ] ⭐ **ポートフォリオ#1** — EDAスクリプト作成 (90分)

### 💤 Plan B（疲れた日・45分版）
- [ ] **OpenCV基礎** — pip install opencv-python (45分)
```

- `⭐` = Focus（今日の最重要）
- `[Sprint]` = アクティブスプリントからの自動抽出（Layer 2）
- `Plan B` = Energy低/中 + 45分のタスク（疲れた日用）

## トラブルシュート

| 症状 | 対処 |
|------|------|
| `401 Unauthorized` | PAT の期限切れ。再生成して Secret を更新 |
| `Resource not accessible` | PAT の権限不足。Projects: Read-only を確認 |
| Issue が作成されない | `DRY_RUN=true` になっていないか確認 |
| 空の Digest | Due が未設定かつ In Progress のスプリントもない |
| cron が動かない | GitHub Actions は空リポのデフォルトブランチでのみ動く。最初のpush後に有効化 |

## 週次レビュー手順（日曜10分）

1. [Life Board](https://github.com/users/foru1215/projects/1) を開く
2. 今週完了したタスクを **Done** にする
3. 来週取り組むタスクに **Due**（月〜金 or 土日）を振る
4. 最重要タスク1件に **Focus=⭐** を付ける
5. **Next Action** が古くなっていれば更新

## 運用ルール

1. 平日夜はAI専用。副業・電工を混ぜない
2. 7月まで土日の電工1.5hが副業より優先
3. 夜AIは同時進行2件・Focus1件まで
4. 疲れた日はPlan B(45分)を選ぶ。ゼロ禁止
5. 週次レビュー(日曜10分)で来週のDueを振る
