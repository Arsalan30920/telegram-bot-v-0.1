const Joystick = (() => {
  let vector = { x: 0, y: 0 };
  const keys = { w: false, a: false, s: false, d: false };

  function initKeyboard() {
    window.addEventListener("keydown", (e) => {
      const k = e.key.toLowerCase();
      if (k in keys) keys[k] = true;
    });
    window.addEventListener("keyup", (e) => {
      const k = e.key.toLowerCase();
      if (k in keys) keys[k] = false;
    });
  }

  function initTouch(zoneEl, knobEl) {
    let active = false;
    let originX = 0;
    let originY = 0;
    const maxRadius = 45;

    const start = (clientX, clientY) => {
      active = true;
      const rect = zoneEl.getBoundingClientRect();
      originX = rect.left + rect.width / 2;
      originY = rect.top + rect.height / 2;
    };

    const move = (clientX, clientY) => {
      if (!active) return;
      let dx = clientX - originX;
      let dy = clientY - originY;
      const dist = Math.min(Math.hypot(dx, dy), maxRadius);
      const angle = Math.atan2(dy, dx);
      const kx = Math.cos(angle) * dist;
      const ky = Math.sin(angle) * dist;
      knobEl.style.transform = `translate(${kx}px, ${ky}px)`;
      vector.x = dist < 5 ? 0 : Math.cos(angle) * (dist / maxRadius);
      vector.y = dist < 5 ? 0 : Math.sin(angle) * (dist / maxRadius);
    };

    const end = () => {
      active = false;
      vector.x = 0;
      vector.y = 0;
      knobEl.style.transform = "translate(0px, 0px)";
    };

    zoneEl.addEventListener("touchstart", (e) => {
      e.preventDefault();
      const t = e.touches[0];
      start(t.clientX, t.clientY);
      move(t.clientX, t.clientY);
    }, { passive: false });

    zoneEl.addEventListener("touchmove", (e) => {
      e.preventDefault();
      const t = e.touches[0];
      move(t.clientX, t.clientY);
    }, { passive: false });

    zoneEl.addEventListener("touchend", (e) => {
      e.preventDefault();
      end();
    }, { passive: false });
  }

  function getVector() {
    // اگر جوی‌استیک لمسی فعاله همون رو بده، وگرنه از WASD بساز
    if (vector.x !== 0 || vector.y !== 0) return vector;

    let x = 0, y = 0;
    if (keys.a) x -= 1;
    if (keys.d) x += 1;
    if (keys.w) y -= 1;
    if (keys.s) y += 1;

    if (x !== 0 && y !== 0) {
      const norm = Math.sqrt(2) / 2;
      x *= norm;
      y *= norm;
    }
    return { x, y };
  }

  function init(zoneEl, knobEl) {
    initKeyboard();
    if (zoneEl && knobEl) initTouch(zoneEl, knobEl);
  }

  return { init, getVector };
})();