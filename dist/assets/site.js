(() => {
  'use strict';
  const menu = document.querySelector('.menu-toggle');
  const nav = document.getElementById('site-nav');
  const closeMenu = () => {menu.setAttribute('aria-expanded', 'false'); nav.classList.remove('open');};
  menu.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    nav.classList.toggle('open', open);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && nav.classList.contains('open')) {closeMenu(); menu.focus();}
  });
  nav.addEventListener('click', event => {if (event.target.closest('a')) closeMenu();});
  const form = document.getElementById('resource-filters');
  if (!form) return;
  const search = document.getElementById('resource-search');
  const kind = document.getElementById('resource-kind');
  const disease = document.getElementById('resource-disease');
  const cards = [...document.querySelectorAll('#resource-grid .resource-card')];
  const normalize = value => value.toLocaleLowerCase().replace(/\s+/g, '');
  function filter() {
    const query = normalize(search.value);
    let count = 0;
    for (const card of cards) {
      const matches = (!query || normalize(card.dataset.search).includes(query)) &&
        (!kind.value || card.dataset.kind === kind.value) && (!disease.value || card.dataset.disease === disease.value);
      card.hidden = !matches;
      count += Number(matches);
    }
    document.getElementById('result-count').textContent = `显示 ${count} / ${cards.length} 份资料`;
    document.getElementById('resource-empty').hidden = count > 0;
  }
  form.addEventListener('submit', event => {event.preventDefault(); filter();});
  form.addEventListener('input', filter);
  form.addEventListener('change', filter);
  form.addEventListener('reset', event => {
    event.preventDefault();
    search.value = '';
    kind.value = '';
    disease.value = '';
    filter();
  });
  document.getElementById('clear-filters').addEventListener('click', () => {form.reset(); search.focus();});
})();
