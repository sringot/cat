/* ============================
   INTRO — 3D scroll animation
   ============================ */
(function () {
  const container  = document.getElementById('introContainer');
  const cardWrap   = document.getElementById('introCardWrap');
  const header     = document.getElementById('introHeader');
  if (!container || !cardWrap) return;

  const isMobile = () => window.innerWidth <= 768;

  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

  function onScroll() {
    const rect            = container.getBoundingClientRect();
    const containerH      = container.offsetHeight;
    const viewportH       = window.innerHeight;
    const scrollable      = containerH - viewportH;
    const rawProgress     = clamp(-rect.top / scrollable, 0, 1);

    const scaleStart  = isMobile() ? 0.75 : 1.08;
    const scaleEnd    = 1;
    const rotateStart = isMobile() ? 15  : 20;
    const rotateEnd   = 0;

    const rotate  = lerp(rotateStart, rotateEnd, rawProgress);
    const scale   = lerp(scaleStart,  scaleEnd,  rawProgress);
    const transY  = lerp(0, -80, rawProgress);

    cardWrap.style.transform = `rotateX(${rotate}deg) scale(${scale})`;
    header.style.transform   = `translateY(${transY * 0.35}px)`;
    header.style.opacity     = clamp(lerp(1, 0.4, rawProgress * 1.8), 0.4, 1);
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

/* ============================
   NAV — scroll behaviour
   ============================ */
const nav    = document.getElementById('nav');
const burger = document.getElementById('burger');
const menu   = document.getElementById('mobileMenu');

window.addEventListener('scroll', () => {
  nav.classList.toggle('scrolled', window.scrollY > 60);
});

burger.addEventListener('click', () => {
  burger.classList.toggle('active');
  menu.classList.toggle('open');
  document.body.style.overflow = menu.classList.contains('open') ? 'hidden' : '';
});

document.querySelectorAll('.mobile-link').forEach(link => {
  link.addEventListener('click', () => {
    burger.classList.remove('active');
    menu.classList.remove('open');
    document.body.style.overflow = '';
  });
});

/* ============================
   CONTACT FORM — simple feedback
   ============================ */
document.getElementById('contactForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  btn.textContent = 'Message envoyé ✓';
  btn.style.background = '#4a7c59';
  btn.disabled = true;
  setTimeout(() => {
    btn.textContent = 'Envoyer le message';
    btn.style.background = '';
    btn.disabled = false;
    e.target.reset();
  }, 3500);
});

/* ============================
   REVEAL ON SCROLL
   ============================ */
const revealTargets = document.querySelectorAll(
  '.service-card, .project-card, .process-step, .testimonial, .about__text, .about__images, .contact__info, .contact__form'
);

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry, i) => {
    if (entry.isIntersecting) {
      setTimeout(() => {
        entry.target.style.opacity  = '1';
        entry.target.style.transform = 'translateY(0)';
      }, (entry.target.dataset.delay || 0));
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.12 });

revealTargets.forEach((el, i) => {
  el.style.opacity   = '0';
  el.style.transform = 'translateY(32px)';
  el.style.transition = `opacity 0.7s cubic-bezier(0.22,1,0.36,1), transform 0.7s cubic-bezier(0.22,1,0.36,1)`;
  el.dataset.delay   = (i % 4) * 80;
  observer.observe(el);
});

/* ============================
   SMOOTH SCROLL offset (nav)
   ============================ */
document.querySelectorAll('a[href^="#"]').forEach(link => {
  link.addEventListener('click', (e) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    e.preventDefault();
    const offset = 80;
    window.scrollTo({ top: target.offsetTop - offset, behavior: 'smooth' });
  });
});
