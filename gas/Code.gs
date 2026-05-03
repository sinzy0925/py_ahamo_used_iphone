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

/**
 * GAS エディタの「実行」から、手動で GitHub Actions（workflow_dispatch）を起動する。
 * ※ WEBHOOK_TOKEN の URL チェックは行わない（エディタに入れる人だけが実行できる前提）。
 * ※ ウェブアプリ経由と同じ 10 分クールダウンが効く。
 * 実行: 関数を runWorkflowFromEditor にして ▶ 実行 → ログで成否を確認。
 */
function runWorkflowFromEditor() {
  var props = PropertiesService.getScriptProperties();
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);

    var now = Date.now();
    var lastStr = props.getProperty('LAST_DISPATCH_MS') || '0';
    var last = parseInt(lastStr, 10);
    if (last && !isNaN(last) && (now - last) < COOLDOWN_MS) {
      var waitMs = COOLDOWN_MS - (now - last);
      var waitMin = Math.max(1, Math.ceil(waitMs / 60000));
      throw new Error(
        '１０分間クールダウン中：約' + waitMin + '分で実行可能になります。'
      );
    }

    var result = dispatchGitHub_(props);
    if (!result.ok) {
      throw new Error(result.detail);
    }

    props.setProperty('LAST_DISPATCH_MS', String(now));
  } finally {
    try {
      lock.releaseLock();
    } catch (relErr) {}
  }

  var gitRef = props.getProperty('GIT_REF') || 'main';
  var site = publicPagesUrl_(props);
  Logger.log(
    'OK: workflow dispatched. Ref=' +
      gitRef +
      ' / しばらくしたら Pages を確認: ' +
      site
  );
}

/**
 * 時間主導トリガーから呼ぶ用。クールダウン・エラー時はログのみ（トリガーの失敗連発を抑える）。
 * トリガーは **everyMinutes(30)**（GAS が許す間隔）。
 */
function runWorkflowFromEditorScheduled() {
  try {
    runWorkflowFromEditor();
  } catch (e) {
    Logger.log('runWorkflowFromEditorScheduled: ' + String(e));
  }
}

/**
 * **30 分ごと**に `runWorkflowFromEditorScheduled` を実行する時計トリガーを 1 本登録する。
 * ※エディタから 1 回だけ実行。**二重登録を避けるため**、同関数向けの既存時計トリガーを先に削除する。
 */
function installTriggerEvery30Minutes() {
  var removed = deleteClockTriggersFor_(['runWorkflowFromEditorScheduled']);
  var trig = ScriptApp.newTrigger('runWorkflowFromEditorScheduled')
    .timeBased()
    .everyMinutes(30)
    .create();
  Logger.log(
    '[installTriggerEvery30Minutes] 既存の時計トリガー（runWorkflowFromEditorScheduled）を ' +
      removed +
      ' 件削除しました。'
  );
  Logger.log(
    '[installTriggerEvery30Minutes] 新規登録: everyMinutes(30)。' +
      ' triggerUniqueId=' +
      trig.getUniqueId()
  );
  Logger.log(
    '[installTriggerEvery30Minutes] 初回実行の「分」は作成時刻に依存します。表示 → ログで確認してください。'
  );
}

/** installTriggerEvery30Minutes で作った時計トリガーを消す */
function uninstallTriggerEvery30Minutes() {
  var removed = deleteClockTriggersFor_(['runWorkflowFromEditorScheduled']);
  Logger.log(
    '[uninstallTriggerEvery30Minutes] runWorkflowFromEditorScheduled 向けの時計トリガーを ' +
      removed +
      ' 件削除しました（残っていた分）。'
  );
}

/**
 * @deprecated {@link installTriggerEvery30Minutes} に変更されました。中身は 30 分トリガーへ委譲します。
function installTriggerEvery20Minutes() {
  Logger.log(
    '[installTriggerEvery20Minutes] 非推奨です。installTriggerEvery30Minutes に置き換わります。'
  );
  installTriggerEvery30Minutes();
}
 */

/**
 * @deprecated {@link uninstallTriggerEvery30Minutes} を使用してください。
function uninstallTriggerEvery20Minutes() {
  uninstallTriggerEvery30Minutes();
}
 */

/**
 * CLOCK トリガーを削除し、削除件数を返す。
 * @param {string[]} handlerNames
 * @return {number}
 */
function deleteClockTriggersFor_(handlerNames) {
  var set = {};
  for (var i = 0; i < handlerNames.length; i++) {
    set[handlerNames[i]] = true;
  }
  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  for (var j = 0; j < triggers.length; j++) {
    var t = triggers[j];
    if (
      t.getEventType() === ScriptApp.EventType.CLOCK &&
      set[t.getHandlerFunction()]
    ) {
      ScriptApp.deleteTrigger(t);
      removed++;
    }
  }
  return removed;
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
