(() => {
  'use strict';
  const carousel = document.querySelector('[data-carousel]');
  if (!carousel) return;
  const slides = [...carousel.querySelectorAll('[data-slide]')];
  if (slides.length < 2) return;
  const dots = [...carousel.querySelectorAll('[data-carousel-dot]')];
  const play = carousel.querySelector('[data-carousel-play]');
  const status = carousel.querySelector('[data-carousel-status]');
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let current = 0;
  let enabled = !motion.matches;
  let hovering = false;
  let inView = true;
  let timer;
  let playIntent;
  let touch;

  // One timer, cancelled for every state change. Hidden/off-screen pages never catch up in a burst.
  function schedule() {
    clearTimeout(timer);
    play.textContent = enabled ? '暂停轮播' : '播放轮播';
    if (enabled && !hovering && inView && !document.hidden) {
      timer = setTimeout(() => show(current + 1, false), 8000);
    }
  }

  function show(index, manual = true) {
    if (manual) enabled = false;
    const focusIndex = [...slides[current].querySelectorAll('a,button')].indexOf(document.activeElement);
    current = (index + slides.length) % slides.length;
    // Move focus before making the old slide inert, so keyboard navigation never falls to body.
    if (focusIndex >= 0) {
      slides[current].classList.add('is-active');
      slides[current].inert = false;
      slides[current].setAttribute('aria-hidden', 'false');
      (slides[current].querySelectorAll('a,button')[focusIndex] || dots[current]).focus({preventScroll: true});
    }
    slides.forEach((slide, i) => {
      const active = i === current;
      slide.classList.toggle('is-active', active);
      slide.inert = !active;
      slide.setAttribute('aria-hidden', String(!active));
      if (active) dots[i].setAttribute('aria-disabled', 'true');
      else dots[i].removeAttribute('aria-disabled');
    });
    if (manual) status.textContent = slides[current].getAttribute('aria-label');
    schedule();
  }

  slides.forEach(slide => {slide.hidden = false;});
  carousel.classList.add('carousel-ready');
  carousel.querySelector('[data-carousel-controls]').hidden = false;
  play.hidden = false;
  carousel.querySelector('[data-carousel-prev]').addEventListener('click', () => show(current - 1));
  carousel.querySelector('[data-carousel-next]').addEventListener('click', () => show(current + 1));
  dots.forEach((dot, index) => dot.addEventListener('click', () => show(index)));
  // Preserve the pointer's intended action before focus-in pauses automatic rotation.
  play.addEventListener('pointerdown', () => {playIntent = !enabled;});
  play.addEventListener('pointercancel', () => {playIntent = undefined;});
  play.addEventListener('click', () => {
    enabled = playIntent === undefined ? !enabled : playIntent;
    playIntent = undefined;
    schedule();
  });
  carousel.addEventListener('focusin', () => {enabled = false; schedule();});
  carousel.addEventListener('pointerenter', event => {
    if (event.pointerType === 'mouse') {hovering = true; schedule();}
  });
  carousel.addEventListener('pointerleave', event => {
    if (event.pointerType === 'mouse') {hovering = false; playIntent = undefined; schedule();}
  });
  carousel.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault(); show(current + (event.key === 'ArrowLeft' ? -1 : 1));
    }
  });
  carousel.addEventListener('pointerdown', event => {
    if (event.pointerType === 'touch' && event.isPrimary && !event.target.closest('a,button')) {
      touch = {id: event.pointerId, x: event.clientX, y: event.clientY};
    }
  });
  carousel.addEventListener('pointerup', event => {
    if (!touch || touch.id !== event.pointerId) return;
    const dx = event.clientX - touch.x, dy = event.clientY - touch.y;
    touch = null;
    if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy) * 1.5) show(current + (dx < 0 ? 1 : -1));
  });
  carousel.addEventListener('pointercancel', () => {touch = null;});
  document.addEventListener('visibilitychange', schedule);
  motion.addEventListener('change', () => {if (motion.matches) enabled = false; schedule();});
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {inView = entries[0].isIntersecting; schedule();}).observe(carousel);
  }
  show(0, false);
})();
