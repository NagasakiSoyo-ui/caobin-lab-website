// Offline export feedback. The links stay ordinary downloads of the export URL without JavaScript;
// with it, the same authorized URL is fetched so the page can show progress, the result or the error.
(() => {
  'use strict';
  const links = [...document.querySelectorAll('a[data-export]')];
  const status = document.getElementById('export-status');
  if (!links.length || !status || !window.fetch || !window.URL || !URL.createObjectURL) return;
  let busy = false;
  let objectUrl = '';

  const release = () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = '';
  };
  const setBusy = value => {
    busy = value;
    links.forEach(link => {
      link.setAttribute('aria-disabled', String(value));
      link.classList.toggle('is-busy', value);
    });
    status.setAttribute('aria-busy', String(value));
  };
  const report = (state, text, action) => {
    status.className = `export-status ${state}`;
    status.replaceChildren(document.createTextNode(text));
    if (action) status.append(' ', action);
  };
  const actionLink = (text, href, download) => {
    const link = document.createElement('a');
    link.textContent = text;
    link.href = href;
    if (download) link.download = download;
    return link;
  };
  const filename = response => {
    const match = /filename="?([^";]+)"?/.exec(response.headers.get('Content-Disposition') || '');
    return match ? match[1] : 'caobin-lab-offline.zip';
  };

  async function exportSite(url) {
    setBusy(true);
    release();
    report('working', '正在生成离线网站，内容较多时需要几十秒，请勿关闭页面……');
    try {
      const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store'});
      const type = response.headers.get('Content-Type') || '';
      if (response.redirected && /\/login\//.test(response.url)) {
        report('error', '登录已过期，未能导出。请重新登录后再试。', actionLink('重新登录', response.url));
        return;
      }
      if (response.status === 403) {
        report('error', '当前账号没有导出权限，请联系网站管理员。');
        return;
      }
      if (!response.ok) {
        report('error', `导出失败（服务器返回 ${response.status}）。可稍后重试；问题持续时请联系网站维护人员。`);
        return;
      }
      if (!type.startsWith('application/zip')) {
        report('error', '服务器返回的不是离线网站 ZIP 文件，未保存。请刷新页面后重试。');
        return;
      }
      const blob = await response.blob();
      const head = new Uint8Array(await blob.slice(0, 2).arrayBuffer());
      if (blob.size < 22 || head[0] !== 0x50 || head[1] !== 0x4b) {
        report('error', '收到的文件不完整或不是 ZIP，未保存。请重试。');
        return;
      }
      const name = filename(response);
      objectUrl = URL.createObjectURL(blob);
      const save = actionLink(`保存 ${name}`, objectUrl, name);
      const size = (blob.size / 1024 / 1024).toFixed(1);
      report('done', `离线网站已生成（${size} MB），已交给浏览器保存。请在浏览器下载列表中确认；如未出现，请点击：`, save);
      save.click();
    } catch (error) {
      report('error', '网络连接中断，未能导出。请检查网络或服务是否仍在运行后重试。');
    } finally {
      setBusy(false);
    }
  }

  links.forEach(link => link.addEventListener('click', event => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    if (!busy) exportSite(link.href);
  }));
  window.addEventListener('pagehide', release);
  window.addEventListener('pageshow', event => {
    if (event.persisted && status.classList.contains('done')) report('', '');
  });
})();
