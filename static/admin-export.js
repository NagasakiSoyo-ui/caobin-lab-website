// Offline export feedback. The links stay ordinary downloads of the export URL without JavaScript;
// With JavaScript, stream the same authorized response and report received bytes.
(() => {
  'use strict';
  const links = [...document.querySelectorAll('a[data-export]')];
  const status = document.getElementById('export-status');
  if (!links.length || !status || !window.fetch || !window.ReadableStream || !window.AbortController || !window.URL || !URL.createObjectURL) return;
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
  };
  const report = (state, text, action) => {
    status.className = `export-status ${state}`;
    status.replaceChildren(document.createTextNode(text));
    if (action) status.append(' ', action);
    if (state !== 'working') {
      const close = document.createElement('button');
      close.type = 'button';
      close.textContent = '关闭提示';
      close.addEventListener('click', () => status.replaceChildren());
      status.append(' ', close);
    }
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
    const controller = new AbortController();
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = '取消导出';
    cancel.addEventListener('click', () => controller.abort());
    report('working', '正在打包离线网站……', cancel);
    const message = status.firstChild;
    const progress = document.createElement('progress');
    progress.setAttribute('aria-label', '离线网站下载进度');
    status.append(progress);
    let received = 0;
    let total = 0;
    let downloading = false;
    const started = performance.now();
    let lastReceived = started;
    const mb = bytes => (bytes / 1024 / 1024).toFixed(1);
    const update = () => {
      const now = performance.now();
      if (!downloading) {
        message.textContent = `正在打包离线网站，已等待 ${Math.floor((now - started) / 1000)} 秒。包含 PDF 资料，请保持本页打开。`;
        return;
      }
      const amount = total ? `${mb(received)} / ${mb(total)} MB（${Math.floor(received / total * 100)}%）` : `${mb(received)} MB`;
      const waiting = now - lastReceived > 15000 ? '网络传输较慢，正在等待数据；也可取消后重试。' : '下载完成后会弹出保存提示，请保持本页打开。';
      message.textContent = `打包完成，正在下载：${amount}。${waiting}`;
      if (total) {
        progress.max = total;
        progress.value = received;
      }
    };
    update();
    const ticker = window.setInterval(update, 1000);
    try {
      const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
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
      total = Number(response.headers.get('Content-Length')) || 0;
      downloading = true;
      lastReceived = performance.now();
      update();
      const reader = response.body.getReader();
      const chunks = [];
      try {
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          chunks.push(value);
          received += value.byteLength;
          lastReceived = performance.now();
        }
      } finally {
        reader.releaseLock();
      }
      if (total && received !== total) throw new Error('Incomplete export response');
      const blob = new Blob(chunks, {type: 'application/zip'});
      chunks.length = 0;
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
      if (controller.signal.aborted) {
        report('done', '已取消导出，未保存文件。可以重新点击导出。');
      } else {
        console.error('Offline website export failed:', error);
        report('error', '网络连接中断或文件传输不完整，未保存。请检查网络后重新导出。');
      }
    } finally {
      window.clearInterval(ticker);
      controller.abort();
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
