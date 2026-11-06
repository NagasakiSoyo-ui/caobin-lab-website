// Keep Django's normal POST/redirect flow; only track changes within this open form.
document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  const status = document.querySelector('[data-editor-status]');
  if (!status) return;
  const form = status.closest('form');
  const initialMessage = status.textContent.trim();
  const failedSave = status.dataset.invalid === 'true';
  const snapshot = () => JSON.stringify(Array.from(new FormData(form), ([name, value]) => [
    name, value instanceof File ? (value.name ? [value.name, value.size, value.lastModified] : null) : value
  ]));
  const initial = snapshot();
  let submitting = false;
  const dirty = () => failedSave || snapshot() !== initial;
  const update = () => {
    status.classList.toggle('editor-dirty', dirty());
    status.textContent = dirty() ? (failedSave ? initialMessage : '有未保存的修改，请点击“保存”。') : initialMessage;
  };
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  // Django's Select2 fields emit jQuery change events rather than native events.
  if (window.django && window.django.jQuery) {
    window.django.jQuery(form).on('change', 'select', update);
  }
  form.addEventListener('submit', event => {
    queueMicrotask(() => {submitting = !event.defaultPrevented;});
  });
  window.addEventListener('beforeunload', event => {
    if (!submitting && dirty()) {event.preventDefault(); event.returnValue = '';}
  });
  window.addEventListener('pageshow', () => {submitting = false; update();});
  if (failedSave) {
    const invalid = form.querySelector('[aria-invalid="true"]');
    if (invalid) invalid.focus();
  }
});
