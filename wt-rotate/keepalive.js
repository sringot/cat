// wt-rotate — Maintien de session (anti-déconnexion sur inactivité)
// ─────────────────────────────────────────────────────────────────────────────
// Beaucoup de tableaux de bord — et surtout les portails SSO type WithSecure —
// ferment la session après quelques minutes SANS ACTIVITÉ RÉELLE de
// l'utilisateur. Un simple rechargement de page (notre filet « refresh » toutes
// les N heures) ne suffit pas : le minuteur d'inactivité tombe bien avant, et un
// reload peut même retomber sur un écran de login.
//
// Ce script simule en continu une activité DISCRÈTE et INVISIBLE pour que le
// minuteur d'inactivité ne se déclenche jamais : micro-mouvement de souris et de
// pointeur (coordonnées qui changent à chaque tick), défilement d'1 px aussitôt
// annulé, et une touche neutre (Maj) qui ne modifie aucun contenu. La grande
// majorité des détecteurs d'inactivité écoutent simplement ces évènements et
// remettent leur compteur à zéro — sans vérifier qu'ils viennent d'un humain.
(function () {
  if (window.__wtKeepAlive) return;            // pas de double injection
  window.__wtKeepAlive = true;

  var PERIOD = 25000;                          // ~25 s, bien sous les seuils usuels
  var n = 0;

  function emit(target, ev) { try { target && target.dispatchEvent(ev); } catch (e) {} }

  function nudge() {
    try {
      n++;
      var w = window.innerWidth  || 1024;
      var h = window.innerHeight || 768;
      // coordonnées qui se déplacent réellement à chaque tick (pas un point fixe)
      var x = 6 + (n * 37) % Math.max(12, w - 12);
      var y = 6 + (n * 53) % Math.max(12, h - 12);

      // 1) mouvement souris + pointeur
      ['mousemove', 'pointermove'].forEach(function (type) {
        var ev;
        if (type === 'pointermove' && window.PointerEvent) {
          ev = new PointerEvent(type, {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y, screenX: x, screenY: y,
            movementX: 1, movementY: 1, pointerType: 'mouse', isPrimary: true
          });
        } else {
          ev = new MouseEvent(type, {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y, screenX: x, screenY: y,
            movementX: 1, movementY: 1
          });
        }
        emit(document, ev);
        emit(window, ev);
        var el = null;
        try { el = document.elementFromPoint(x, y); } catch (e) {}
        emit(el, ev);
      });

      // 2) défilement réel d'1 px immédiatement annulé (vrai effet de mise en page)
      try {
        var sx = window.scrollX, sy = window.scrollY;
        window.scrollTo(sx, sy + 1);
        window.scrollTo(sx, sy);
      } catch (e) {}
      emit(document, new Event('scroll', { bubbles: true }));
      emit(window, new Event('scroll'));

      // 3) touche neutre (Maj) — aucun caractère saisi, aucun raccourci
      ['keydown', 'keyup'].forEach(function (type) {
        emit(document, new KeyboardEvent(type, {
          bubbles: true, cancelable: true, key: 'Shift', code: 'ShiftLeft'
        }));
      });
    } catch (e) {}
  }

  setInterval(nudge, PERIOD);
  // les onglets en arrière-plan sont throttlés : on relance un coup au retour
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') nudge();
  });
  nudge();
})();
