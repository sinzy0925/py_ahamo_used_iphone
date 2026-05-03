# GitHub Actions を GAS から起動する（設定手順）

概要: Google Apps Script が **Script Properties に保存した GitHub PAT** で `workflow_dispatch` を実行します。Pages に載せるのは **GAS の Web アプリ URL＋共通トークン**だけで、GitHub PAT はブラウザに出しません。**10 分以内の二度目は拒否**します（連打対策）。

## 1. Google Apps Script で新規プロジェクト

1. [script.google.com](https://script.google.com) で **新しいプロジェクト**。
2. このリポジトリの `gas/Code.gs` をコピーし、エディタに貼り付け（既存の `Code.gs` を置き換え）。

## 2. スクリプトプロパティ（秘密情報）

プロジェクト編集画面 → **⚙️ プロジェクトの設定** → **スクリプト プロパティ** で次を追加。

| プロパティ | 説明 |
|------------|------|
| `GITHUB_TOKEN` | GitHub の **Fine-grained 個人アクセストークン**。対象リポジトリについて **Actions: Read and write**。 |
| `GITHUB_REPO` | `オーナー/リポジトリ名` 例 `sinzy0925/py_ahamo_used_iphone` |
| `WORKFLOW_FILE` | ワークフロー YAML の**ファイル名**（例 `ahamo-screenshot-pages.yml`。`.github/workflows/` は含めません） |
| `WEBHOOK_TOKEN` | **長くランダムな文字列**（例 32〜64 文字の英数字）。後で Pages 用シークレットと一致させます。 |
| `GIT_REF` | （省略可）`workflow_dispatch` のブランチ。省略時は GAS 内で `main` を使用。**既定ブランチが `main` でないときは必須**。 |
| `PUBLIC_PAGES_URL` | （省略可）成功時レスポンスに表示するサイト URL。**省略時は** `https://sinzy0925.github.io/py_ahamo_used_iphone/` が使われます。自分の Pages に合わせて設定してください。 |

Classic PAT を使う場合は **`workflow` スコープ**が必要になります。

## 3. ウェブアプリとしてデプロイ

**デプロイ** → **新しいデプロイ** → 種類 **ウェブアプリ** を選択し、設定:

| 項目 | 値 |
|------|-----|
| 説明 | 任意 |
| **次のユーザーとして実行** | 自分 |
| **アクセスできるユーザー** | **全員**（または「Google アカウントを持っている全員」— 匿名ユーザーに開けたければ「全員」） |

**デプロイ**すると **ウェブアプリの URL** が表示されます。  
ブラウザで次のような URL が動くか試します（値は自分の環境で置換）。

```
https://script.google.com/macros/s/......./exec?token=【WEBHOOK_TOKENと同一の値】
```

期待される応答:

- 初回: `OK: workflow dispatched...`
- **10 分以内に再度**: 「１０分間クールダウン中：約◯分で…（前回実行日時：… JST）」のような文言
- **`token` 不一致または未指定**: `Forbidden`

※ 画面上は HTTP 200 のままで本文のみ変わる場合がありますが、問題ありません。

## 4. GitHub リポジトリシークレット

リポジトリ → **Settings** → **Secrets and variables** → **Actions** で **repository secret**:

| Name | Value |
|------|-------|
| `GAS_TRIGGER_URL` | **上記ウェブアプリ URL の末尾に** `token=` を付けた**完全な URL**。**例**: `https://script.google.com/macros/s/xxxxx/exec?token=あなたのWEBHOOK_TOKEN` |

`/exec` から改行や余分なスペースを入れないでください。**トークンは秘密として扱い、リポジトリにコミットしないでください。**（Secrets にのみ保存。）

ワークフロー `Build static site` が `build_site.py` に `GAS_TRIGGER_URL` を渡し、公開 HTML にボタン用の URL が埋め込まれます。**HTML に含まれるため、トークンを知っている人なら単体でその URL にアクセスすることもできます。**用途に応じて `WEBHOOK_TOKEN` を適宜ローテーションしてください。

## 5. Actions ワークフロー

このリポジトリのワークフローでは **Build static site** ステップに `secrets.GAS_TRIGGER_URL` を渡しているので、Secret を保存したうえで **ワークフローを再実行**すれば Pages に「スクショの再取得を依頼」ボタンが出ます。

`GAS_TRIGGER_URL` を**未設定**のままでもビルドは成功し、このときは Pages 側は **「表示を更新」ボタンのみ**になります。

## 6. Pages 側の動き（生成 HTML）

| ボタン | 動き |
|--------|------|
| **スクショの再取得を依頼** | `GAS_TRIGGER_URL` を**新しいタブ**で開く（実行結果はそのタブのテキストで表示）。**Secret 未設定時は表示されません。** |
| **表示を更新** | 現在のサイトをクエリ付きで再読み込み（キャッシュの切り離し）。常にあります。

## GAS エディタから手動でワークフローを叩く場合

コードに **`runWorkflowFromEditor`** があります。**関数一覧でこれを選び ▶ を押す**と、`WEBHOOK_TOKEN` は不要ですが、`GITHUB_TOKEN` などのスクリプトプロパティはウェブ経由と同じく必要です。**10 分クールダウン**も同様に適用されます。ログ（表示 → ログ）に `OK: workflow dispatched` が出れば GitHub に dispatch 済みです。

## 約30分ごとに GAS から自動実行する場合

GAS が許す間隔 **`everyMinutes(30)`** で、およそ **30 分おき**に `runWorkflowFromEditorScheduled` が動きます（**初回はトリガー作成時刻から 30 分刻み**。きっちり :00/:30 とは限りません）。

- **登録:** エディタから **`installTriggerEvery30Minutes`** を **1 回だけ**実行する。
- **解除:** **`uninstallTriggerEvery30Minutes`** を実行する。
- **`installTriggerEvery20Minutes`／`uninstallTriggerEvery20Minutes`** は名前のまま残していますが **非推奨**です。実行すると **`Every30Minutes` と同等**の処理になります（ログに注意が出ます）。

**GitHub Actions の定期実行とも二重**になるので、どちらかに寄せるのが無難です。**10 分クールダウン**は共通のため、30 分間隔でも問題になりにくいです。

## トラブルシュート

- **`GitHub API error: HTTP 404`**: `GITHUB_REPO`／`WORKFLOW_FILE`／`GIT_REF`（ブランチ名）が正しいか確認。workflow ファイル名だけで API が通らないときは、[Workflows API で ID を確認](https://docs.github.com/en/rest/actions/workflows)して数値 ID を `WORKFLOW_FILE` に入れる試しもできます。
- **`403 Forbidden`**: Fine-grained PAT の対象リポジトリと権限が合っているか。
- **すぐクールダウン文言**: 直前に成功済み。**10 分後**か、GAS の `LAST_DISPATCH_MS` を削除（プロパティを消してリセット）は開発時のみ。
- **`Forbidden` と GAS が出る**: `token=` が Script Properties の `WEBHOOK_TOKEN` と一致しているか、`GAS_TRIGGER_URL` のシークレットに誤りがないか確認。
