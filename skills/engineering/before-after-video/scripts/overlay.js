// Drawn into every page by recorder.py (add_init_script), because headless
// video has no mouse pointer, no key feedback and no native dialogs.
// The recorder's own elements are pointer-events:none, so they never take a click.
(() => {
  if (window.__recOverlay) return; window.__recOverlay = true;
  window.__recSecret = false;
  const isFrame = window.top !== window;
  // The top page draws everything. A frame inside it reaches the top page's
  // functions when both share an origin; otherwise it draws nothing.
  const fromTop = (name) => {
    try { return isFrame ? window.top[name] : window[name]; } catch (e) { return undefined; }
  };

  // Native alert/confirm/prompt are never drawn in headless video. Draw a box
  // first; the native call then blocks until recorder.py resolves the dialog.
  for (const kind of ['alert', 'confirm', 'prompt']) {
    const native = window[kind];
    window[kind] = function (message, ...rest) {
      try { const draw = fromTop('__recDialog'); if (draw) draw(kind, message); } catch (e) { /* never break the page */ }
      return native.call(window, message, ...rest);
    };
  }

  // A modal <dialog> or a popover sits in the browser's top layer, above every
  // z-index, and would hide the pointer and captions. The overlay root is a
  // popover too; showing it again after each top-layer change puts it on top.
  const relift = (fn) => function (...args) {
    const out = fn.apply(this, args);
    if (this.id !== '__rec_root' && window.__recLift) window.__recLift();
    return out;
  };
  if (window.HTMLDialogElement) HTMLDialogElement.prototype.showModal = relift(HTMLDialogElement.prototype.showModal);
  if (HTMLElement.prototype.showPopover) HTMLElement.prototype.showPopover = relift(HTMLElement.prototype.showPopover);

  // Key presses: Python's secret=True flag lives on the top page.
  const isSecret = (e) => !!fromTop('__recSecret') || (e.target && e.target.type === 'password');

  if (isFrame) {
    // A second pointer and badge inside each frame would show twice on video,
    // so a frame only moves the top page's pointer and key box.
    const offset = () => window.frameElement.getBoundingClientRect();
    const forwardMouse = (e) => {
      try { const b = offset(); fromTop('__recPointerAt')(e.clientX + b.left, e.clientY + b.top, e.type === 'mousedown'); }
      catch (err) { /* cross-origin frame */ }
    };
    document.addEventListener('mousemove', forwardMouse, true);
    document.addEventListener('mousedown', forwardMouse, true);
    document.addEventListener('keydown', e => {
      try { fromTop('__recKeyAt')(e.key, e.metaKey, e.ctrlKey, isSecret(e)); } catch (err) { /* cross-origin frame */ }
    }, true);
    return;
  }

  const install = () => {
    const ptr = document.createElement('div');
    ptr.id = '__rec_ptr';
    ptr.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M3 2 L3 22 L8.5 16.8 L12.2 25 L15.6 23.5 L11.9 15.4 L19 15.4 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    ptr.style.cssText = 'position:fixed;left:0;top:0;width:28px;height:28px;z-index:2147483647;'
      + 'pointer-events:none;transform:translate(-100px,-100px);filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))';
    const keys = document.createElement('div');
    keys.id = '__rec_keys';
    keys.style.cssText = 'position:fixed;right:24px;top:70px;z-index:2147483646;background:#facc15;color:#111;'
      + 'font:700 22px/1.3 ui-monospace,Menlo,monospace;padding:8px 16px;border-radius:8px;'
      + 'box-shadow:0 4px 16px rgba(0,0,0,.25);display:none;pointer-events:none';
    const cap = document.createElement('div');
    cap.id = '__rec_cap';
    cap.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:2147483646;'
      + 'background:rgba(17,24,39,.92);color:#fff;font:600 20px/1.4 system-ui;padding:12px 22px;'
      + 'border-radius:10px;max-width:1100px;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.3);'
      + 'display:none;pointer-events:none';
    const badge = document.createElement('div');
    badge.id = '__rec_badge';
    badge.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:2147483646;color:#fff;'
      + 'font:800 15px/1 system-ui;letter-spacing:.06em;padding:6px 10px;border-radius:6px;'
      + 'display:none;pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.25)';
    const dlg = document.createElement('div');
    dlg.id = '__rec_dialog';
    dlg.style.cssText = 'position:fixed;left:50%;top:96px;transform:translateX(-50%);z-index:2147483646;'
      + 'background:#fff;color:#111;font:16px/1.45 system-ui;padding:16px 22px;border-radius:10px;'
      + 'min-width:320px;max-width:640px;border:1px solid #d1d5db;box-shadow:0 12px 36px rgba(0,0,0,.3);'
      + 'display:none;pointer-events:none;white-space:pre-wrap';
    const blur = document.createElement('style');
    blur.id = '__rec_blur';
    const root = document.createElement('div');
    root.id = '__rec_root';
    root.style.cssText = 'position:fixed;inset:0;width:auto;height:auto;margin:0;padding:0;border:0;'
      + 'background:transparent;overflow:visible;pointer-events:none;z-index:2147483647';
    root.append(ptr, keys, cap, badge, dlg);
    document.body.append(root);
    document.head.append(blur);
    const canLift = typeof root.showPopover === 'function';
    if (canLift) root.popover = 'manual';
    window.__recLift = () => {
      if (!canLift || !root.isConnected) return;
      try { if (root.matches(':popover-open')) root.hidePopover(); root.showPopover(); } catch (e) { /* keep z-index */ }
    };
    window.__recLift();
    // popovers opened without script (popovertarget buttons) only announce themselves with a toggle event
    document.addEventListener('toggle', e => { if (e.target !== root && e.newState === 'open') window.__recLift(); }, true);

    const movePointer = (x, y) => { ptr.style.transform = `translate(${x - 3}px, ${y - 2}px)`; };
    const ring = (x, y) => {
      const r = document.createElement('div');
      r.style.cssText = `position:fixed;left:${x - 18}px;top:${y - 18}px;width:36px;height:36px;`
        + 'border-radius:50%;border:3px solid #ef4444;z-index:2147483646;pointer-events:none;'
        + 'transition:transform .45s ease-out,opacity .45s ease-out;transform:scale(.4);opacity:1';
      root.appendChild(r);  // inside the root, so the ring shows above modal dialogs too
      requestAnimationFrame(() => { r.style.transform = 'scale(1.4)'; r.style.opacity = '0'; });
      setTimeout(() => r.remove(), 500);
    };
    document.addEventListener('mousemove', e => movePointer(e.clientX, e.clientY), true);
    document.addEventListener('mousedown', e => ring(e.clientX, e.clientY), true);
    window.__recPointerAt = (x, y, down) => { movePointer(x, y); if (down) ring(x, y); };

    let typed = '', hideTimer = 0;
    const showKey = (key, meta, ctrl, secret) => {
      if (['Meta', 'Control', 'Alt', 'Shift', 'CapsLock'].includes(key)) return;  // a modifier alone is no key press
      if (meta || ctrl) {
        typed = '';
        keys.textContent = 'Keys pressed: ' + (meta ? '⌘' : 'Ctrl+') + key.toUpperCase();
      } else if (key === 'Backspace') {
        typed = typed.slice(0, -1); keys.textContent = 'Keys pressed: ' + typed + ' ⌫';
      } else if (key.length === 1) {
        typed += secret ? '•' : key; keys.textContent = 'Keys pressed: ' + typed;  // never show secrets on video
      } else { return; }
      keys.style.display = 'block';
      clearTimeout(hideTimer);  // 6 s after the last key the box fades, so old keys don't linger
      hideTimer = setTimeout(() => { keys.style.display = 'none'; typed = ''; }, 6000);
    };
    document.addEventListener('keydown', e => showKey(e.key, e.metaKey, e.ctrlKey, isSecret(e)), true);
    window.__recKeyAt = showKey;

    let dialogTimer = 0;
    const titles = { alert: 'Browser alert', confirm: 'Browser confirm', prompt: 'Browser prompt' };
    window.__recDialog = (kind, message) => {
      dlg.textContent = '';
      const title = document.createElement('div');
      title.style.cssText = 'font-weight:700;margin-bottom:6px;color:#374151';
      title.textContent = titles[kind] || 'Browser dialog';
      dlg.append(title, document.createTextNode(String(message ?? '')));
      dlg.style.display = 'block';
      clearTimeout(dialogTimer);  // stays 6 s, long enough to read and to point at
      dialogTimer = setTimeout(() => { dlg.style.display = 'none'; }, 6000);
    };

    window.__recCaption = (t, top) => {
      cap.textContent = t; cap.style.display = t ? 'block' : 'none';
      cap.style.top = top ? '64px' : ''; cap.style.bottom = top ? '' : '28px';
    };
    window.__recKeysReset = () => { typed = ''; keys.style.display = 'none'; };
    window.__recBadge = (t, color) => {
      badge.textContent = t; badge.style.background = color; badge.style.display = t ? 'block' : 'none';
    };
    window.__recAddBlur = (selector) => {
      try { blur.sheet.insertRule(`${selector} { filter: blur(8px) !important; }`, blur.sheet.cssRules.length); }
      catch (e) { console.warn('[recorder] not a CSS selector, nothing blurred:', selector); }
    };
    if (window.__recBadgeInit) window.__recBadge(...window.__recBadgeInit);
    (window.__recBlurInit || []).forEach(window.__recAddBlur);
  };
  if (document.body) install(); else document.addEventListener('DOMContentLoaded', install);
})();
