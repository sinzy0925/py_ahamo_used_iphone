# py_ahamo_used_iphone

ワークフローで取得している **ahamo の「リユース品の選択」画面のスクショ** と取得日時は、次の **GitHub Pages** からブラウザで確認できます。

[https://sinzy0925.github.io/py_ahamo_used_iphone/](https://sinzy0925.github.io/py_ahamo_used_iphone/)

自分の環境では表示が異なることがあるため、公開 URL はリポジトリの **Settings → Pages** で確かめてください。

---

## 必須メンテナンス：GITHUB_TOKEN の期限とローテーション

Google Apps Script（GAS）のスクリプトプロパティ **`GITHUB_TOKEN`** には、Fine-grained 個人アクセストークン（多くが `github_pat_` で始まる値）を入れています。**期限付きのトークンは必ず失効します。** 期限を「無期限」にしない限りいつか切れるので、運用として **期限前にローテーションする義務がある** と考えるのがよいです。無期限にしていても、漏えいや権限変更のときはあらためて発行します。

### 期限切れの症状

GAS の Web アプリ URL（末尾に `?token=〈WEBHOOK_TOKEN〉`）をブラウザで開いたとき、本文が **`GitHub API error:`** や **`401`** を含んだ失敗になり、`workflow_dispatch` が動かない。

※ スクショ取得のみのワークフロー（GitHub 上から直接実行する側）は、この PAT に依存しません。**GAS 経由の「スクショの再取得を依頼」だけ**が止まりやすいです。

### ローテーション手順（失効したあとも同じ）

1. **GitHub** → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** で **Generate new token** を開く。
2. 対象は **選択したリポジトリのみ**、権限は初回発行時と同様で **Actions: Read and write**（など [docs/GAS_TRIGGER_SETUP.md](docs/GAS_TRIGGER_SETUP.md) と揃える）。
3. 生成直後に表示される文字列だけをコピーする。
4. [script.google.com](https://script.google.com) の該当プロジェクト → **プロジェクトの設定** → **スクリプト プロパティ** で **`GITHUB_TOKEN`** を **その新しい文字列だけ** に差し替え、保存する。
5. ブラウザで `…/exec?token=〈WEBHOOK_TOKEN〉` を再度開き、**`OK: workflow dispatched`** など成功が返るか確認する。（直前に実行済みなら **`１０分間クールダウン中：…`** の日本語メッセージだけでもトークンは生きている。）
6. GitHub の **Fine-grained tokens** 一覧で、**もう使わない旧トークンを削除（Revoke）** する。
7. PC のカレンダーやノートで **「次に切れる日付」** と **見直す日（例: 期限の 2 週間前）** を決めておく。

この作業だけでは **`WEBHOOK_TOKEN`・GitHub の `GAS_TRIGGER_URL`・Pages のワークフロー定義・リポジトリのコード変更は通常不要です。**

---

## 概要

Playwright で ahamo の申込〜リユース品選択ページまで自動操作し、全体スクショを取得するツールです。GitHub Actions で定期実行し、Google Apps Script と連携した「再取得依頼」ボタン付きの GitHub Pages までを含んだ構成になっています。

---

## 今日まで進めた作業の詳細（全体像）

構成は次のとおりです。

| 構成要素 | 役割 |
|-----------|------|
| **main.py** | Playwright で申込タイプ〜「リユース品を見る」まで自動操作。**used_term_select_full.png** にページ全体スクショ。`--user-agent` で Stable 最新 UA、`--chrome-channel` など。CI では `python main.py --user-agent --headless`。 |
| **build_site.py** | PNG と **取得日時（JST）** から **`site/`**（`index.html` + PNG）を出力。環境変数 **`GAS_TRIGGER_URL`** が空でないと **「表示を更新」** と **「スクショの再取得を依頼」** の 2 ボタンになる。ログに `build_site: GAS_TRIGGER_URL …` と出る。 |
| **`.github/workflows/ahamo-screenshot-pages.yml`** | `pip` → Chromium インストール → **main.py** → **build_site.py**（`secrets.GAS_TRIGGER_URL` を `env` で渡す）→ **upload-pages-artifact** → **deploy-pages**。cron は毎時 0 分 UTC、あわせて **`workflow_dispatch`（手動）** あり。 |
| **gas/Code.gs**（GAS に貼る） | クエリ **`token`** が **`WEBHOOK_TOKEN`** と一致したときだけ、スクリプトプロパティの **`GITHUB_TOKEN`** で GitHub の **`workflow_dispatch`** API を呼ぶ。**過去実行から 10 分以内**は拒否。**`LockService`** で並行ヒット時の競合を抑える。 |
| **GitHub Secret `GAS_TRIGGER_URL`** | GAS の **デプロイ済みウェブアプリの実行 URL に `token=WEBHOOK_TOKEN` を付けた 1 行**。ビルドで HTML に埋め込むため **閲覧者はソースにトークン付き URL を見られる** が、GitHub PAT 自体は含めない。 |
| **GITHUB_PAGES_SETUP.md** | Pages の Source を **GitHub Actions** にする、`deploy-pages` の 404 対処など。 |
| **docs/GAS_TRIGGER_SETUP.md** | スクリプトプロパティ表、ウェブアプリ公開、動作確認、トラブルシュート。 |
| **scripts/gen_random_token.py** | **`WEBHOOK_TOKEN`** 用として英数字のみの長いランダム文字列を標準出力（例 `python scripts/gen_random_token.py`）。 |

### ローカル実行の例（Windows）

```powershell
cd c:\Users\sinzy\py_ahamo_used_iphone
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python main.py --headless --user-agent
.\.venv\Scripts\python build_site.py   # PNG が無いと失敗
```

ローカルの `build_site.py` で **`GAS_TRIGGER_URL` が未設定**なら、`index.html` は **ボタン 1 つ（在庫状況確認）** と **`GAS_TRIGGER_URL` を Secret に入れる説明付きノート**のパターンになる。

### GAS と GitHub Secret のひも付け（概要）

1. GAS で **`GITHUB_TOKEN`**（Fine-grained PAT）、**`GITHUB_REPO`**、**`WORKFLOW_FILE`**（ファイル名のみ、例 **`ahamo-screenshot-pages.yml`**）、**`WEBHOOK_TOKEN`**（長いランダム。必要なら **`GIT_REF`**）を設定。  
2. ウェブアプリをデプロイし **`…/exec?token=WEBHOOK_TOKEN`** で検証。  
3. GitHub リポジトリの Actions **Secrets** に **`GAS_TRIGGER_URL`** として、その **完全一致の URL を 1 行**で追加。  
4. ワークフローを **一通り成功させる**。Build static site のログで **`GAS_TRIGGER_URL is set（再取得ボタンを出力）`** を確認すると、公開 Pages に **再取得ボタン** が出る。

細部は **[docs/GAS_TRIGGER_SETUP.md](docs/GAS_TRIGGER_SETUP.md)** へ。

### 「公開ページに再取得ボタンが無い」（在庫状況確認しか無い）

**Secret 値が空でビルドされた HTML が公開されている状態**です。`GAS_TRIGGER_URL` の名前・保存場所（Repository secrets）、直近ワークフローがデプロイまで成功しているか、`build_site` ログが **`未設定`** になっていないかを確認し、問題なければ **再走** で解消することが多いです。

---

## 関連ファイル一覧

| パス | 説明 |
|------|------|
| `main.py` | 自動操作・スクショ |
| `build_site.py` | Pages 静的ファイル生成 |
| `requirements.txt` | Python 依存 |
| `gas/Code.gs` | GAS 用ソース（プロジェクトへコピー） |
| `.github/workflows/ahamo-screenshot-pages.yml` | CI / Pages |

ライセンス表記は別途、この README で足りない点は追記して構いません。
