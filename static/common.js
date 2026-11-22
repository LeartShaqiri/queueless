const $ = (s, el = document) => el.querySelector(s);

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = data.detail;
    const err = new Error(typeof d === 'string' ? d : (d && d.message) || r.statusText);
    err.fields = d && d.fields;
    throw err;
  }
  return data;
}
const post = (p, body) => api(p, { method: 'POST', body: JSON.stringify(body || {}) });

function connectWS(onMsg, onStatus) {
  const go = () => {
    const ws = new WebSocket((location.protocol === 'https:' ? 'wss' : 'ws') + '://' + location.host + '/ws');
    ws.onopen = () => { onStatus && onStatus(true); onMsg({ type: 'update' }); };
    ws.onmessage = e => onMsg(JSON.parse(e.data));
    ws.onclose = () => { onStatus && onStatus(false); setTimeout(go, 1500); };
  };
  go();
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmtMin(s) {
  if (s == null) return '—';
  const m = Math.round(s / 60);
  return m < 1 ? '<1 min' : m + ' min';
}
function fmtRange(lo, hi) {
  if (lo == null) return 'Paused';
  const a = Math.round(lo / 60), b = Math.round(hi / 60);
  if (b < 1) return 'Any moment';
  if (a === b) return `~${a} min`;
  return `${a}–${b} min`;
}
function fmtClock(sec) {
  sec = Math.max(0, Math.floor(sec));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}

let toastTimer;
function toast(msg, err = false) {
  let el = $('#toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  el.className = 'toast' + (err ? ' err' : '');
  el.textContent = msg;
  el.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.style.display = 'none', 3500);
}

let audioCtx;
function unlockAudio() {
  audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
  audioCtx.resume();
}
function chime() {
  if (!audioCtx) return;
  [784, 1175, 1568].forEach((f, i) => {
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = 'sine'; o.frequency.value = f;
    o.connect(g); g.connect(audioCtx.destination);
    const t = audioCtx.currentTime + i * 0.22;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.35, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
    o.start(t); o.stop(t + 0.75);
  });
}
function speak(text) {
  if (!('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.92;
  speechSynthesis.speak(u);
}
const spokenNumber = n => n.replace('-', ' ').replace(/\b0+(\d)/, '$1');

const LOGO_MARK = '<svg viewBox="0 0 26 17" aria-hidden="true"><path fill="currentColor" d="M0 0h26v5.5a3 3 0 0 0 0 6V17H0v-5.5a3 3 0 0 0 0-6z"/></svg>';
document.querySelectorAll('[data-logo]').forEach(el => el.insertAdjacentHTML('afterbegin', LOGO_MARK));

function detailRows(rows, cls = 'rcpt') {
  if (!rows || !rows.length) return '';
  return `<dl class="${cls}">${rows.map(r => {
    const logo = r.logo ? `<span class="rcpt-logo" ${r.logo_bg ? `style="background:${esc(r.logo_bg)}"` : ''}><img src="${esc(r.logo)}" alt=""></span>` : '';
    const value = r.lines ? `<span class="lines">${String(r.value).split('\n').map(esc).join('<br>')}</span>` : esc(r.value);
    return `<div class="${r.strong ? 'strong' : ''}"><dt>${esc(r.label)}</dt><dd>${logo}${value}</dd></div>`;
  }).join('')}</dl>`;
}

const CONF_TAG ={ high: 'go', medium: 'hold', low: 'stop' };
function liveStatus(el) {
  return ok => { if (!el) return; el.classList.toggle('off', !ok); el.textContent = ok ? 'Live' : 'Reconnecting'; };
}

function storage(key, val) {
  try {
    if (val === undefined) return localStorage.getItem(key);
    if (val === null) localStorage.removeItem(key); else localStorage.setItem(key, val);
  } catch (e) { return null; }
}
