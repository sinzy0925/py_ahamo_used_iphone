# GitHub Pages（Actions でデプロイ）が 404 で失敗するとき

`deploy-pages` が次のようなエラーで止まる場合:

```text
Error: HttpError: Not Found … Ensure GitHub Pages has been enabled
```

ほとんどは **このリポジトリで Pages が未有効／ソースが Actions になっていない** ことが原因です。ビルドとアップロードは成功しても、この設定が済んでいないとデプロイ API が **404** を返します。

## 対処（必須）

1. GitHub でリポジトリを開く  
   （例）`https://github.com/sinzy0925/py_ahamo_used_iphone/settings/pages`

2. **Settings** → **Pages** を開く

3. **Build and deployment** の **Source** で  
   **「Deploy from a branch」ではなく 「GitHub Actions」** を選ぶ

4. 画面に表示された説明どおり保存する（画面上部に「サイトは GitHub Actions で公開されています」のような説明が出ることがある）

5. **Actions** から失敗したワークフローを **Re-run** するか、Push / 手動実行で再走させる

## 初回だけの承認

- `github-pages` **Environment** が保護されていて、「Review deployments」を求められたら **Approve** する

## Private リポジトリについて

アカウントまたは Organization のプランによっては、Private での GitHub Pages に制限があることがあります。Pages の設定画面にその旨が出ないか確認してください。

## 参考（公式）

- [Publishing with a custom GitHub Actions workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site#publishing-with-a-custom-github-actions-workflow)

## ページから Actions を起動する場合

Google Apps Script 経由で `workflow_dispatch` する手順は **`docs/GAS_TRIGGER_SETUP.md`** を参照してください。
