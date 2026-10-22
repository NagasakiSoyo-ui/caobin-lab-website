(() => {
  'use strict';
  const normalize = value => (value || '').toLocaleLowerCase().replace(/\s+/g, '');

  const menu = document.querySelector('.menu-toggle');
  const nav = document.getElementById('site-nav');
  if (menu && nav) {
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
  }

  function bindFilter(form, fields, update) {
    form.addEventListener('submit', event => {event.preventDefault(); update();});
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.addEventListener('reset', event => {
      event.preventDefault();
      fields.forEach(field => {field.value = '';});
      update();
    });
  }

  const resourceForm = document.getElementById('resource-filters');
  if (resourceForm) {
    const search = document.getElementById('resource-search');
    const kind = document.getElementById('resource-kind');
    const disease = document.getElementById('resource-disease');
    const cards = [...document.querySelectorAll('#resource-grid .resource-card')];
    const filter = () => {
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
    };
    bindFilter(resourceForm, [search, kind, disease], filter);
    document.getElementById('clear-filters').addEventListener('click', () => {resourceForm.reset(); search.focus();});
  }

  const pubForm = document.getElementById('pub-filters');
  if (pubForm) {
    const search = document.getElementById('pub-search');
    const year = document.getElementById('pub-year');
    const direction = document.getElementById('pub-direction');
    const entries = [...document.querySelectorAll('#pub-list .pub-entry')];
    const groups = [...document.querySelectorAll('#pub-list .pub-year')];
    const filter = () => {
      const query = normalize(search.value);
      let count = 0;
      for (const entry of entries) {
        const matches = (!query || normalize(entry.dataset.search).includes(query)) &&
          (!year.value || entry.dataset.year === year.value) &&
          (!direction.value || entry.dataset.directions.split(' ').includes(direction.value));
        entry.hidden = !matches;
        count += Number(matches);
      }
      groups.forEach(group => {group.hidden = !group.querySelector('.pub-entry:not([hidden])');});
      document.getElementById('pub-count').textContent = `显示 ${count} / ${entries.length} 条`;
      document.getElementById('pub-empty').hidden = count > 0;
    };
    bindFilter(pubForm, [search, year, direction], filter);
  }

  // Scroll reveal: only blocks that start below the fold are animated, once, as they approach the
  // viewport. Nothing is hidden up front, so without JS, IntersectionObserver or with reduced motion
  // everything simply stays visible.
  const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!calm && 'IntersectionObserver' in window) {
    const selector = '.section-heading, .direction-card, .featured-card, .project-card, .pub-year, .direction-row, ' +
      '.detail-block, .detail-aside > section, .figure-plate, .resource-card, .member-card, .home-leader, .contact-band .container';
    const fold = window.innerHeight;
    const pending = [...document.querySelectorAll(selector)].filter(el => el.getBoundingClientRect().top > fold);
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const el = entry.target;
        observer.unobserve(el);
        const siblings = el.parentElement ? [...el.parentElement.children] : [];
        el.style.animationDelay = `${(siblings.indexOf(el) % 3) * 70}ms`;
        el.classList.add('reveal-in');
        el.addEventListener('animationend', () => {el.classList.remove('reveal-in'); el.style.animationDelay = '';}, {once: true});
      }
    }, {rootMargin: '0px 0px 12% 0px'});
    pending.forEach(el => observer.observe(el));
  }

  // Lightbox: the thumbnail is a plain link to the original image, so it still works
  // without JavaScript or <dialog> support. Native <dialog> provides Esc and focus trapping.
  // While it is open the page behind is locked, so wheel or touch scrolling past the edge of the
  // image never moves the article; closing returns to the exact reading position.
  const zooms = document.querySelectorAll('a[data-lightbox]');
  if (zooms.length && typeof HTMLDialogElement === 'function') {
    const dialog = document.createElement('dialog');
    dialog.className = 'lightbox';
    dialog.setAttribute('aria-label', '查看原图');
    dialog.innerHTML = '<div class="lightbox-inner"><div class="lightbox-bar"><p></p><a target="_blank" rel="noopener">在新窗口打开原图 ↗</a>' +
      '<button type="button" class="lightbox-close">关闭 (Esc)</button></div><div class="lightbox-stage"><img alt=""></div></div>';
    document.body.append(dialog);
    const title = dialog.querySelector('p');
    const image = dialog.querySelector('img');
    const original = dialog.querySelector('.lightbox-bar a');
    const inner = dialog.querySelector('.lightbox-inner');
    const root = document.documentElement;
    let opener = null;
    let saved = null;
    dialog.querySelector('.lightbox-close').addEventListener('click', () => dialog.close());
    // The dialog fills the viewport, so its dark margin (around the bar and the white stage) is the backdrop.
    dialog.addEventListener('click', event => {if (event.target === dialog || event.target === inner) dialog.close();});
    dialog.addEventListener('close', () => {
      image.removeAttribute('src');
      root.classList.remove('lightbox-open');
      if (saved) window.scrollTo({left: saved.x, top: saved.y, behavior: 'instant'});
      saved = null;
      if (opener) opener.focus({preventScroll: true});
    });
    zooms.forEach(link => link.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      opener = link;
      const figure = link.closest('figure');
      const heading = figure && figure.querySelector('h3');
      title.textContent = heading ? heading.textContent : '';
      image.src = link.getAttribute('href');
      image.alt = (link.querySelector('img') || {}).alt || '';
      original.href = link.getAttribute('href');
      saved = {x: window.scrollX, y: window.scrollY};
      root.classList.add('lightbox-open');
      dialog.showModal();
      dialog.querySelector('.lightbox-stage').scrollTo(0, 0);
      dialog.querySelector('.lightbox-close').focus();
    }));
  }
})();
