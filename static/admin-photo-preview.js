// Member photo preview in the admin form. Shows the saved photo, or the newly chosen file before it is
// uploaded; nothing is sent to the server until the form is saved. Works on Django's ClearableFileInput.
// ModelAdmin.Media scripts load in <head>, so start once the form exists.
document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  const input = document.getElementById('id_photo');
  if (!input || !window.URL || !URL.createObjectURL) return;
  const clear = document.getElementById('photo-clear_id');
  const current = input.closest('.file-upload') ? input.closest('.file-upload').querySelector('a') : null;
  const savedUrl = current ? current.getAttribute('href') : '';

  const panel = document.createElement('div');
  panel.className = 'photo-preview';
  panel.innerHTML = '<img alt="" hidden><p role="status" aria-live="polite"></p>' +
    '<button type="button" class="button" hidden>取消新选择的照片</button>';
  const image = panel.querySelector('img');
  const status = panel.querySelector('p');
  const cancel = panel.querySelector('button');
  (input.closest('.file-upload') || input).after(panel);

  let objectUrl = '';
  const release = () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = '';
  };
  const show = (src, alt, text, state) => {
    image.hidden = !src;
    if (src) image.src = src; else image.removeAttribute('src');
    image.alt = alt;
    status.textContent = text;
    panel.dataset.state = state;
  };

  const render = () => {
    const file = input.files && input.files[0];
    release();
    cancel.hidden = !file;
    if (file) {
      objectUrl = URL.createObjectURL(file);
      const note = clear && clear.checked ? '同时勾选了「清除」，保存时会提示二选一，请取消勾选。' : '';
      show(objectUrl, '新选择的照片预览', `新选择：${file.name}（尚未上传，点击「保存」后才会替换）。${note}`, 'new');
    } else if (savedUrl && clear && clear.checked) {
      show(savedUrl, '当前照片预览（保存后将清除）', '保存后将清除当前照片；取消勾选「清除」可保留。', 'clear');
    } else if (savedUrl) {
      show(savedUrl, '当前照片预览', '当前照片', 'saved');
    } else {
      show('', '', '暂无照片。选择文件后可在此预览。', 'empty');
    }
  };

  input.addEventListener('change', render);
  if (clear) clear.addEventListener('change', render);
  cancel.addEventListener('click', () => {
    input.value = '';
    render();
    input.focus();
  });
  window.addEventListener('pagehide', release);
  window.addEventListener('pageshow', event => {if (event.persisted) render();});
  render();
});
