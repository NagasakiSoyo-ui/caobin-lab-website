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

  function paginate(items, navigation, pageSize, afterRender, onChange) {
    let matches = items;
    let current = 1;
    function render() {
      const total = Math.max(1, Math.ceil(matches.length / pageSize));
      current = Math.min(current, total);
      const visible = new Set(matches.slice((current - 1) * pageSize, current * pageSize));
      items.forEach(item => {item.hidden = !visible.has(item);});
      navigation.replaceChildren();
      navigation.hidden = total <= 1;
      const changePage = page => {
        current = page;
        render();
        if (onChange) onChange(current);
        const first = matches[(current - 1) * pageSize];
        if (first) {
          first.setAttribute('tabindex', '-1');
          first.focus({preventScroll: true});
          first.scrollIntoView({block: 'start', behavior: 'auto'});
        }
      };
      const previous = document.createElement('button');
      previous.type = 'button'; previous.textContent = '上一页'; previous.disabled = current === 1;
      previous.addEventListener('click', () => changePage(current - 1));
      const select = document.createElement('select');
      select.setAttribute('aria-label', '跳转到页');
      for (let page = 1; page <= total; page++) {
        const option = document.createElement('option');
        option.value = String(page); option.textContent = `第 ${page} / ${total} 页`; option.selected = page === current;
        select.append(option);
      }
      select.addEventListener('change', () => changePage(Number(select.value)));
      const next = document.createElement('button');
      next.type = 'button'; next.textContent = '下一页'; next.disabled = current === total;
      next.addEventListener('click', () => changePage(current + 1));
      navigation.append(previous, select, next);
      if (afterRender) afterRender();
    }
    return (filtered, page = 1) => {matches = filtered; current = page; render(); return current;};
  }

  const resourceForm = document.getElementById('resource-filters');
  if (resourceForm) {
    const search = document.getElementById('resource-search');
    const disease = document.getElementById('resource-disease');
    let searchHistoryEntry = false;
    let appliedFilterKey;
    const filterKey = () => JSON.stringify([search.value, disease.value]);
    const cards = [...document.querySelectorAll('#resource-grid .resource-card')];
    const saveURL = (page, mode = 'push') => {
      searchHistoryEntry = false;
      const url = new URL(location.href);
      url.searchParams.delete('kind');
      url.searchParams.delete('view');
      for (const [key, value] of Object.entries({q: search.value, disease: disease.value,
          page: page > 1 ? String(page) : ''})) {
        if (value) url.searchParams.set(key, value);
        else url.searchParams.delete(key);
      }
      url.hash = page > 1 || search.value || disease.value ? 'resource-catalog' : '';
      if (url.href !== location.href) history[mode === 'replace' ? 'replaceState' : 'pushState'](null, '', url);
    };
    const showPage = paginate(cards, document.getElementById('resource-pagination'), 12, null, saveURL);
    const filter = (page = 1, mode = 'push') => {
      const query = normalize(search.value);
      const matches = cards.filter(card => (!query || normalize(card.dataset.search).includes(query)) &&
          (!disease.value || card.dataset.disease === disease.value));
      const current = showPage(matches, page);
      document.getElementById('result-count').textContent = `找到 ${matches.length} / ${cards.length} 份资料`;
      document.getElementById('resource-empty').hidden = matches.length > 0;
      saveURL(current, mode);
      appliedFilterKey = filterKey();
    };
    const restore = () => {
      searchHistoryEntry = false;
      const params = new URL(location.href).searchParams;
      search.value = params.get('q') || '';
      const value = params.get('disease') || '';
      disease.value = [...disease.options].some(option => option.value === value) ? value : '';
      const page = Number(params.get('page'));
      filter(Number.isSafeInteger(page) && page > 0 ? page : 1, 'replace');
    };
    const updateFilter = event => {
      // A composing syllable is not a submitted query. One editing session gets one
      // history entry, so Back returns to the previous view instead of undoing letters.
      if (event && event.isComposing) return;
      const editing = event && event.target === search &&
        (event.type === 'input' || event.type === 'compositionend');
      // Blur emits change after input. Rebuilding unchanged results here removes
      // the pagination control between mousedown and click, swallowing the click.
      if (filterKey() !== appliedFilterKey) {
        filter(1, editing && searchHistoryEntry ? 'replace' : 'push');
      }
      searchHistoryEntry = Boolean(editing);
    };
    bindFilter(resourceForm, [search, disease], updateFilter);
    resourceForm.addEventListener('compositionend', updateFilter);
    document.getElementById('clear-filters').addEventListener('click', () => {resourceForm.reset(); search.focus();});
    window.addEventListener('popstate', restore);
    window.addEventListener('pageshow', restore);
    window.addEventListener('hashchange', restore);
    restore();
  }

  const yearLinks = [...document.querySelectorAll('[data-publication-year]')];
  if (yearLinks.length) {
    const catalog = document.getElementById('pub-list');
    const groups = [...catalog.querySelectorAll('[data-year-group]')];
    const papers = [...catalog.querySelectorAll('.pub-entry')];
    const showPage = paginate(papers, document.getElementById('publication-pagination'), 20, () => {
      groups.forEach(group => {group.hidden = ![...group.querySelectorAll('.pub-entry')].some(item => !item.hidden);});
    });
    const selectYear = year => {
      const matches = papers.filter(item => year === 'all' || item.dataset.year === year);
      showPage(matches);
      yearLinks.forEach(link => {
        if (link.dataset.publicationYear === year) link.setAttribute('aria-current', 'true');
        else link.removeAttribute('aria-current');
      });
      catalog.classList.toggle('single-year', year !== 'all');
      const count = matches.length;
      document.getElementById('pub-count').textContent = `${year === 'all' ? '全部年份' : year + ' 年'}，${count} 条论文`;
    };
    yearLinks.forEach(link => link.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
      event.preventDefault();
      history.replaceState(null, '', link.hash);
      selectYear(link.dataset.publicationYear);
    }));
    const selectHashYear = () => {
      const link = yearLinks.find(item => item.hash === location.hash);
      if (link) selectYear(link.dataset.publicationYear);
    };
    window.addEventListener('hashchange', selectHashYear);
    selectYear(yearLinks[0].dataset.publicationYear);
    selectHashYear();
  }

  // Scroll reveal: only blocks that start below the fold are animated, once, as they approach the
  // viewport. Nothing is hidden up front, so without JS, IntersectionObserver or with reduced motion
  // everything simply stays visible.
  const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!calm && 'IntersectionObserver' in window) {
    const selector = '.section-heading, .direction-card, .pub-entry, .project-card, .pub-year, .direction-row, ' +
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
