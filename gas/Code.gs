/**
 * GitHub Actions workflow_dispatch を GAS から起動する（10 分クールダウン + WEBHOOK トークン）。
 *
 * 【スクリプトプロパティ】プロジェクト設定 → 「スクリプトのプロパティ」で設定:
 *   GITHUB_TOKEN     … Fine-grained PAT（Actions の Read and write のみでも可／古典は workflow 権限）
 *   GITHUB_REPO      … owner/repo （例 sinzy0925/py_ahamo_used_iphone）
 *   WORKFLOW_FILE    … ワークフローYAMLのファイル名（例 ahamo-screenshot-pages.yml）
 *   WEBHOOK_TOKEN    … Pages に埋める URL と同じクエリ token= の値と一致させる
 *   GIT_REF          … 省略時 main（ワークフロー dispatch の ref）
 *
 * 【デプロイ】デプロイ → 新しいデプロイ → 種類:ウェブアプリ
 *   次のユーザーとして実行: 自分
 *   アクセスできるユーザー: 全員（匿名ユーザー含む）
 */

var COOLDOWN_MS = 10 * 60 * 1000;

function doGet(e) {
  return handleRequest_(e);
}

function doPost(e) {
  return handleRequest_(e);
}

function handleRequest_(e) {
  var props = PropertiesService.getScriptProperties();
  var expected = props.getProperty('WEBHOOK_TOKEN');
  var got = '';
  try {
    if (e && e.parameter && e.parameter.token) {
      got = String(e.parameter.token);
    }
  } catch (err) {
    got = '';
  }

  if (!expected || got !== expected) {
    return textOut_('Forbidden', 403);
  }

  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);

    var now = Date.now();
    var lastStr = props.getProperty('LAST_DISPATCH_MS') || '0';
    var last = parseInt(lastStr, 10);
    if (last && !isNaN(last) && (now - last) < COOLDOWN_MS) {
      var waitMs = COOLDOWN_MS - (now - last);
      var waitMin = Math.max(1, Math.ceil(waitMs / 60000));
      return textOut_(
        'Cooldown: wait about ' +
          waitMin +
          ' min (last dispatched at script time ' +
          new Date(last).toISOString() +
          ')',
        429
      );
    }

    var result = dispatchGitHub_(props);
    if (!result.ok) {
      return textOut_('GitHub API error: ' + result.detail, 502);
    }

    props.setProperty('LAST_DISPATCH_MS', String(now));
    return textOut_(
      'OK: workflow dispatched. Ref=' + (props.getProperty('GIT_REF') || 'main'),
      200
    );
  } finally {
    try {
      lock.releaseLock();
    } catch (relErr) {}
  }
}

function textOut_(message, httpStatusHint) {
  // GAS は HTTP ステータスを細かく制御できないことが多い。本文のみ区別します。
  var out = ContentService.createTextOutput(message).setMimeType(
    ContentService.MimeType.TEXT
  );
  return out;
}

function dispatchGitHub_(props) {
  var token = props.getProperty('GITHUB_TOKEN');
  var repo = props.getProperty('GITHUB_REPO');
  var wf = props.getProperty('WORKFLOW_FILE');
  var ref = props.getProperty('GIT_REF') || 'main';

  if (!token || !repo || !wf) {
    return { ok: false, detail: 'Missing GITHUB_TOKEN / GITHUB_REPO / WORKFLOW_FILE in script properties.' };
  }

  var segments = repo.split('/');
  if (segments.length !== 2) {
    return { ok: false, detail: 'GITHUB_REPO must be owner/repo.' };
  }

  var url =
    'https://api.github.com/repos/' +
    encodeURIComponent(segments[0]) +
    '/' +
    encodeURIComponent(segments[1]) +
    '/actions/workflows/' +
    encodeURIComponent(wf) +
    '/dispatches';

  var payload = { ref: ref, inputs: {} };

  try {
    var response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'gas-github-workflow-dispatch'
      },
      payload: JSON.stringify(payload)
    });

    var code = response.getResponseCode();
    if (code === 204 || code === 200 || code === 201) {
      return { ok: true, detail: '' };
    }
    return {
      ok: false,
      detail: 'HTTP ' + code + ' — ' + response.getContentText().slice(0, 500),
    };
  } catch (err) {
    return { ok: false, detail: String(err) };
  }
}
