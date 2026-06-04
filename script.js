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
