/**
 * GitHub Actions workflow_dispatch を GAS から起動する（10 分クールダウン + WEBHOOK トークン）。
 *
 * 【スクリプトプロパティ】プロジェクト設定 → 「スクリプトのプロパティ」で設定:
 *   GITHUB_TOKEN     … Fine-grained PAT（Actions の Read and write のみでも可／古典は workflow 権限）
 *   GITHUB_REPO      … owner/repo （例 sinzy0925/py_ahamo_used_iphone）
 *   WORKFLOW_FILE    … ワークフローYAMLのファイル名（例 ahamo-screenshot-pages.yml）
 *   WEBHOOK_TOKEN    … Pages に埋める URL と同じクエリ token= の値と一致させる
 *   GIT_REF          … 省略時 main（ワークフロー dispatch の ref）
 *   PUBLIC_PAGES_URL …（省略可）成功時メッセージに出すサイト URL（既定は sinzy0925 の Pages）
 *
 * 【デプロイ】デプロイ → 新しいデプロイ → 種類:ウェブアプリ
 *   次のユーザーとして実行: 自分
 *   アクセスできるユーザー: 全員（匿名ユーザー含む）
 */

var COOLDOWN_MS = 10 * 60 * 1000;

function publicPagesUrl_(props) {
  var u = props.getProperty('PUBLIC_PAGES_URL');
  if (u && String(u).trim()) {
    return String(u).trim();
  }
  return 'https://sinzy0925.github.io/py_ahamo_used_iphone/';
}

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
      var lastJstStr = Utilities.formatDate(
        new Date(last),
        'Asia/Tokyo',
        'yyyy-MM-dd HH:mm:ss'
      );
      var cooldownMsg =
        '１０分間クールダウン中：約' +
        waitMin +
        '分で実行可能になります。\n' +
        '（前回実行日時：' +
        lastJstStr +
        ' JST）';
      return textOut_(cooldownMsg, 429);
    }

    var result = dispatchGitHub_(props);
    if (!result.ok) {
      return textOut_('GitHub API error: ' + result.detail, 502);
    }

    props.setProperty('LAST_DISPATCH_MS', String(now));
    var gitRef = props.getProperty('GIT_REF') || 'main';
    var site = publicPagesUrl_(props);
    var okMsg =
      'OK: workflow dispatched. Ref=' +
      gitRef +
      '\n\n' +
      '現在、リユース品の選択画面のスクショを取得中です。\n' +
      '２分程度お待ちの上、再度以下のURLを開いてください。\n\n' +
      'リンク\n' +
      site;
    return textOut_(okMsg, 200);
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
