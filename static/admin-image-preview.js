// Every image field uses the same preview and clear controls; PDF uploads are unaffected.
document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  document.querySelectorAll('.image-upload').forEach(widget => {
    const input = widget.querySelector('input[type=file]');
    const clear = widget.querySelector('input[type=checkbox]');
    const current = widget.querySelector('[data-image-current]');
    const savedUrl = current ? current.getAttribute('href') : '';
    const panel = widget.querySelector('.photo-preview');
    const image = panel.querySelector('img');
    const status = panel.querySelector('[role=status]');
    const cancel = panel.querySelector('button');
    let objectUrl = '';
    const release = () => {if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = '';};
    const render = () => {
      release();
      const file = input.files && input.files[0];
      cancel.hidden = !file;
      let src = savedUrl;
      if (file) {
        if (window.URL && URL.createObjectURL) src = objectUrl = URL.createObjectURL(file);
        panel.dataset.state = 'new';
        status.textContent = `已选择：${file.name}。点击“保存”后生效。`;
      } else if (savedUrl && clear && clear.checked) {
        panel.dataset.state = 'clear';
        status.textContent = '保存后移除当前图片；取消勾选可保留。';
      } else {
        panel.dataset.state = savedUrl ? 'saved' : 'empty';
        status.textContent = savedUrl ? '当前图片' : '尚未添加图片。';
      }
      image.hidden = !src;
      if (src) image.src = src; else image.removeAttribute('src');
      image.alt = file ? '新选择的图片预览' : '当前图片预览';
    };
    input.addEventListener('change', () => {
      if (input.files.length && clear) clear.checked = false;
      render();
    });
    if (clear) clear.addEventListener('change', () => {
      if (clear.checked) input.value = '';
      render();
    });
    cancel.addEventListener('click', () => {input.value = ''; render(); input.focus();});
    image.addEventListener('error', () => {status.textContent = '无法预览此图片。请检查文件，上传时会再次校验格式。';});
    window.addEventListener('pagehide', release);
    window.addEventListener('pageshow', event => {if (event.persisted) render();});
    render();
  });
});
