// Wake Word Studio – sidebar panel: create own wake words, review, record, train and roll out.
// Everything is set here (words, devices, slots, trainer). Changing the setup needs an administrator.
// Addresses: /wake-word-studio/<tab>?wort=<id>   tabs without a word: zentrale, geraete, einstellungen, neu
// No polling: the page reloads only when one of the integration's sensors changes.
import { TEXTE, SPRACHNAMEN } from './sprachmodell-texte.js';

const VERSION = '1.0.1';
const REPO = 'https://github.com/Wadim-dev/wake-word-studio_ha';
const BILD = 'ghcr.io/wadim-dev/wake-word-studio-trainer:latest';
const PROXMOX = 'https://raw.githubusercontent.com/Wadim-dev/wake-word-studio_ha/main/sprachmodell_trainer/proxmox.sh';
const WORT_REITER = [
  ['uebersicht', 'mdi:view-dashboard-outline'],
  ['pruefen', 'mdi:playlist-check'],
  ['aufnehmen', 'mdi:microphone-outline'],
  ['verlauf', 'mdi:history'],
  ['hochladen', 'mdi:upload-outline'],
  ['training', 'mdi:school-outline'],
  ['qualitaet', 'mdi:chart-bell-curve-cumulative'],
  ['wort', 'mdi:tune-variant'],
];
const OHNE_WORT = ['zentrale', 'geraete', 'einstellungen', 'neu'];
const ART_ICON = { wake: 'mdi:microphone-message', mistake: 'mdi:microphone-off', nearmiss: 'mdi:microphone-question', noise: 'mdi:waveform', aufnahme: 'mdi:upload', browser: 'mdi:microphone' };
const LAEUFT = ['vorbereiten', 'daten', 'merkmale', 'training', 'test'];
const FARBEN = ['#03a9f4', '#8bc34a', '#ff9800', '#e91e63', '#9c27b0', '#009688', '#ff5722', '#607d8b'];

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const STIL = `
:host{display:block;min-height:100vh;background:var(--primary-background-color);color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,inherit)}
.kopf{position:sticky;top:0;z-index:3;display:flex;align-items:center;gap:4px;height:var(--header-height,56px);padding:0 8px 0 4px;background:var(--app-header-background-color,var(--primary-background-color));color:var(--app-header-text-color,var(--primary-text-color));border-bottom:1px solid var(--divider-color)}
.kopf h1{font-size:20px;font-weight:400;margin:0 0 0 8px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kopf .ikon{width:40px;height:40px;border-radius:50%;border:0;background:none;color:inherit;cursor:pointer;display:flex;align-items:center;justify-content:center}
.kopf .ikon.an{color:var(--primary-color);background:rgba(var(--rgb-primary-color,3,169,244),.14)}
.leisten{position:sticky;top:var(--header-height,56px);z-index:2;background:var(--app-header-background-color,var(--primary-background-color));border-bottom:1px solid var(--divider-color)}
.woerter,.reiter{display:flex;gap:6px;overflow-x:auto;padding:8px 12px;scrollbar-width:none}
.reiter{padding-top:0}
.woerter::-webkit-scrollbar,.reiter::-webkit-scrollbar{display:none}
.reiter a,.woerter a{display:flex;align-items:center;gap:6px;padding:7px 12px;border-radius:18px;color:var(--secondary-text-color);text-decoration:none;font-size:14px;white-space:nowrap;cursor:pointer}
.reiter a.an,.woerter a.an{background:rgba(var(--rgb-primary-color,3,169,244),.16);color:var(--primary-color)}
.woerter a .farbe{width:10px;height:10px;border-radius:50%}
.woerter a.wortchip{border:1px solid var(--divider-color)}
.zahl{min-width:18px;padding:0 5px;border-radius:9px;background:var(--warning-color,#ff9800);color:#fff;font-size:11px;line-height:18px;text-align:center}
.reiter ha-icon,.woerter ha-icon{--mdc-icon-size:18px}
main{max-width:1100px;margin:0 auto;padding:16px 12px 80px}
ha-card{display:block;padding:16px;margin-bottom:12px}
h2{font-size:17px;font-weight:500;margin:0 0 12px}
h3{font-size:14px;font-weight:500;margin:18px 0 6px;color:var(--secondary-text-color)}
.raster{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin-bottom:12px}
.raster ha-card{margin:0}
.kachel{cursor:pointer}
.kachel .wert{font-size:30px;font-weight:300;margin:4px 0}
.kachel .klein,.klein{font-size:13px;color:var(--secondary-text-color)}
.wortkarte{cursor:pointer;border-top:4px solid var(--wf,var(--primary-color))}
.wortkarte .name{font-size:22px;font-weight:500;margin:2px 0 8px}
.wortkarte .reihe{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.zeile{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.zeile.weit{justify-content:space-between}
button.k{display:inline-flex;align-items:center;gap:6px;border:0;border-radius:18px;padding:8px 14px;font:inherit;font-size:14px;cursor:pointer;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);color:var(--primary-text-color)}
button.k:disabled{opacity:.45;cursor:default}
button.k.haupt{background:var(--primary-color);color:var(--text-primary-color,#fff)}
button.k.gut{background:rgba(var(--rgb-success-color,76,175,80),.2);color:var(--success-color,#4caf50)}
button.k.schlecht{background:rgba(var(--rgb-error-color,244,67,54),.18);color:var(--error-color,#f44336)}
button.k.leise{background:none;color:var(--secondary-text-color)}
button.k ha-icon{--mdc-icon-size:18px}
button.k kbd{font:11px monospace;opacity:.6;border:1px solid currentColor;border-radius:4px;padding:0 4px}
.chip{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;border-radius:16px;font-size:13px;background:rgba(var(--rgb-primary-text-color,0,0,0),.06);cursor:pointer;border:0;color:inherit;font-family:inherit;text-decoration:none}
.chip.an{background:rgba(var(--rgb-primary-color,3,169,244),.18);color:var(--primary-color)}
.liste{display:flex;flex-direction:column;gap:10px}
.eintrag{display:grid;grid-template-columns:52px 1fr;gap:12px;padding:12px;border-radius:var(--ha-card-border-radius,12px);background:var(--ha-card-background,var(--card-background-color));border:1px solid var(--divider-color);outline:none}
.eintrag.aktiv{border-color:var(--primary-color);box-shadow:0 0 0 1px var(--primary-color)}
.eintrag.weg{opacity:.35;pointer-events:none;transition:opacity .25s}
.spielen{width:52px;height:52px;border-radius:50%;border:0;background:rgba(var(--rgb-primary-color,3,169,244),.15);color:var(--primary-color);cursor:pointer;position:relative}
.spielen ha-icon{--mdc-icon-size:28px}
.spielen svg{position:absolute;inset:0;transform:rotate(-90deg)}
.spielen circle{fill:none;stroke:var(--primary-color);stroke-width:3;stroke-dasharray:157;stroke-dashoffset:157}
.titel{font-weight:500}
.balken{position:relative;height:6px;border-radius:3px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);margin:8px 0 4px;max-width:340px}
.balken i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--primary-color)}
.balken b{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--error-color,#f44336)}
.vorschlag{font-size:13px;margin:6px 0 8px;color:var(--secondary-text-color)}
.vorschlag strong{color:var(--primary-text-color)}
.knoepfe{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
select,input[type=time],input[type=text],input[type=number]{font:inherit;font-size:14px;padding:8px 10px;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);box-sizing:border-box}
input[type=text]{width:100%;max-width:440px}
input[type=number]{width:96px}
label.feld{display:block;margin:14px 0 5px;font-size:13px;color:var(--secondary-text-color)}
.leer{text-align:center;padding:40px 16px;color:var(--secondary-text-color)}
.leer ha-icon{--mdc-icon-size:48px;opacity:.5}
.fortschritt{height:10px;border-radius:5px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden;margin:10px 0}
.fortschritt i{display:block;height:100%;background:var(--primary-color);transition:width .6s}
.laeuft .fortschritt i{background-image:linear-gradient(90deg,transparent 0,rgba(255,255,255,.25) 50%,transparent 100%);background-size:200% 100%;animation:schimmer 2.5s linear infinite}
@keyframes schimmer{to{background-position:-200% 0}}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--divider-color);vertical-align:top}
th{font-weight:500;color:var(--secondary-text-color);font-size:12px}
td.z,th.z{text-align:right}
.gruen{color:var(--success-color,#4caf50)}.rot{color:var(--error-color,#f44336)}.gelb{color:var(--warning-color,#ff9800)}
.punkt{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:var(--disabled-color,#999)}
.punkt.an{background:var(--success-color,#4caf50)}
.abwurf{border:2px dashed var(--divider-color);border-radius:14px;padding:30px 16px;text-align:center;cursor:pointer}
.abwurf.ueber{border-color:var(--primary-color);background:rgba(var(--rgb-primary-color,3,169,244),.06)}
.abwurf ha-icon{--mdc-icon-size:42px;color:var(--primary-color)}
code,pre{font-size:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);padding:2px 6px;border-radius:5px;word-break:break-all}
pre{display:block;padding:10px;white-space:pre-wrap;margin:6px 0}
.schluessel{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.hinweis{padding:10px 12px;border-radius:10px;background:rgba(var(--rgb-warning-color,255,152,0),.12);font-size:14px;margin-bottom:12px;line-height:1.5}
.hinweis.ok{background:rgba(var(--rgb-success-color,76,175,80),.14)}
svg.vert text{font-size:10px;fill:var(--secondary-text-color)}
.platz{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:10px 0;border-bottom:1px solid var(--divider-color)}
.platz:last-child{border-bottom:0}
.farbwahl{display:flex;gap:8px;flex-wrap:wrap}
.farbwahl button{width:28px;height:28px;border-radius:50%;border:3px solid transparent;cursor:pointer;outline:2px solid transparent}
.farbwahl button.an{outline-color:var(--primary-text-color)}
.rec{display:flex;flex-direction:column;align-items:center;gap:14px;padding:16px 0 8px}
.rec .gross{width:120px;height:120px;border-radius:50%;border:0;cursor:pointer;display:flex;align-items:center;justify-content:center;background:var(--primary-color);color:#fff}
.rec .gross:disabled{opacity:.4;cursor:default}
.rec .gross.an{background:var(--error-color,#f44336);animation:puls 1.6s ease-out infinite}
.rec .gross ha-icon{--mdc-icon-size:52px}
@keyframes puls{from{box-shadow:0 0 0 0 rgba(244,67,54,.5)}to{box-shadow:0 0 0 22px rgba(244,67,54,0)}}
.pegel{width:100%;max-width:420px;height:12px;border-radius:6px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden}
.pegel i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--success-color,#4caf50),var(--warning-color,#ff9800) 75%,var(--error-color,#f44336));transition:width .08s}
.takes{display:flex;flex-wrap:wrap;gap:8px}
.take{display:flex;align-items:center;gap:4px;padding:4px 4px 4px 10px;border-radius:16px;background:rgba(var(--rgb-primary-text-color,0,0,0),.06);font-size:13px}
.take.gegen{background:rgba(var(--rgb-error-color,244,67,54),.12)}
.take button{border:0;background:none;color:inherit;cursor:pointer;padding:2px;display:flex}
.take ha-icon{--mdc-icon-size:18px}
@media (max-width:600px){main{padding:12px 8px 80px}.eintrag{grid-template-columns:44px 1fr;gap:10px;padding:10px}.spielen{width:44px;height:44px}button.k kbd{display:none}}
`;

class SprachmodellPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._daten = null;
    this._liste = null;
    this._filter = { echo: '', verlauf: 'bewertet', seite: 0 };
    this._person = this._merk('person') || '';
    this._autoplay = this._merk('autoplay') !== '0';
    this._blobs = new Map();
    this._audio = new Audio();
    this._audio.addEventListener('timeupdate', () => this._ring());
    this._audio.addEventListener('ended', () => { this._spielt = null; this._ring(true); });
    this._aktiv = 0;
    this._stempel = '';
    this._taste = (e) => this._tastatur(e);
    this._rec = { modus: 'wort', takes: [], an: false, notiz: '' };
    this._entwurf = null;
  }

  // ---------- Hilfen ----------
  _merk(k, v) { try { if (v === undefined) return localStorage.getItem('sprachmodell.' + k); localStorage.setItem('sprachmodell.' + k, v); } catch (e) { return null; } return null; }
  get _spr() { const l = String((this._hass && ((this._hass.locale && this._hass.locale.language) || this._hass.language)) || navigator.language || 'en'); return l.slice(0, 2) === 'de' ? 'de' : 'en'; }
  get _loc() { return this._spr === 'de' ? 'de-DE' : ((this._hass && this._hass.locale && this._hass.locale.language) || 'en'); }
  t(k, v) { let s = (TEXTE[this._spr] && TEXTE[this._spr][k]) ?? TEXTE.en[k] ?? k; if (v) for (const [a, b] of Object.entries(v)) s = s.split('{' + a + '}').join(b); return s; }
  _schritt(x) { if (!x) return ''; const i = x.indexOf(':'), k = i < 0 ? x : x.slice(0, i), d = i < 0 ? '' : x.slice(i + 1); const s = this.t('s_' + k, { d }); return s === 's_' + k ? x : (k === 'aufnahmen' && d ? s + ' (' + d + ')' : s); }
  _zahl(x, n = 2) { return typeof x === 'number' ? x.toLocaleString(this._loc, { minimumFractionDigits: n, maximumFractionDigits: n }) : '–'; }
  _pct(x, n = 0) { return typeof x === 'number' ? this._zahl(x * 100, n) + ' %' : '–'; }
  _zeit(iso) {
    if (!iso) return '–';
    const d = new Date(iso), s = (Date.now() - d) / 1000;
    if (s < 60) return this.t('gerade');
    if (s < 3600) return this.t('vor_min', { n: Math.round(s / 60) });
    if (s < 86400) return this.t('vor_std', { n: Math.round(s / 3600) });
    if (s < 7 * 86400) return d.toLocaleDateString(this._loc, { weekday: 'short' }) + ' ' + d.toLocaleTimeString(this._loc, { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString(this._loc, { day: '2-digit', month: '2-digit', year: '2-digit' }) + ' ' + d.toLocaleTimeString(this._loc, { hour: '2-digit', minute: '2-digit' });
  }
  _datum(iso) { return iso ? new Date(iso).toLocaleString(this._loc, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–'; }
  _dauer(min) { return min >= 90 ? this._zahl(min / 60, 1) + ' ' + this.t('std') : Math.round(min) + ' ' + this.t('min'); }
  get _basis() { return '/' + ((this._panel && this._panel.url_path) || 'wake-word-studio'); }
  get _admin() { return !!(this._daten && this._daten.admin); }
  _fehlerText(e) { const c = (e && e.body && e.body.message) || (e && e.message) || String(e); const s = this.t('f_' + c); return s === 'f_' + c ? c : s; }
  _wortKurz() { return this._daten && this._daten.woerter.find((w) => w.id === this._wortId); }
  _wortName() { const w = this._wortKurz(); return w ? w.wort : ''; }
  _farbe(w, i) { if (!w) return FARBEN[0]; return w.farbe || FARBEN[(i ?? this._daten.woerter.indexOf(w)) % FARBEN.length]; }

  // ---------- HA-Anbindung ----------
  set hass(h) {
    const erstes = !this._hass;
    this._hass = h;
    if (erstes) { this._aufbauen(); this._laden(); return; }
    const st = Object.values(h.entities || {}).filter((e) => e.platform === 'sprachmodell')
      .map((e) => h.states[e.entity_id]).filter(Boolean).map((s) => s.state + s.last_updated + (s.attributes.prozent ?? '')).join('|');
    if (st !== this._stempel) { const war = this._stempel; this._stempel = st; if (war && !this._rec.an && !this._bearbeitet()) this._laden(); }
    const m = this.shadowRoot.querySelector('ha-menu-button'); if (m) m.hass = h;
  }
  get hass() { return this._hass; }
  set narrow(n) { this._narrow = n; const m = this.shadowRoot.querySelector('ha-menu-button'); if (m) m.narrow = n; }
  set route(r) {
    this._route = r;
    const neu = ((r && r.path) || '').replace(/^\//, '').split('/')[0] || 'zentrale';
    const wort = new URLSearchParams(location.search).get('wort') || this._wortId || this._merk('wort') || null;
    if (neu !== this._reiter || wort !== this._wortId) {
      if (neu !== this._reiter) this._recStopp();
      this._reiter = neu; this._wortId = wort;
      if (this._hass) { this._kopfZeichnen(); this._laden(); }
    }
  }
  set panel(p) { this._panel = p; }
  connectedCallback() { window.addEventListener('keydown', this._taste); }
  disconnectedCallback() { window.removeEventListener('keydown', this._taste); this._audio.pause(); this._recStopp(); }

  // Formular offen und geändert? Dann nicht unter den Fingern neu zeichnen
  _bearbeitet() { return ['neu', 'wort'].includes(this._reiter) && this._entwurf && this._entwurf._geaendert; }

  _gehe(reiter, wort) {
    if (wort) { this._wortId = wort; this._merk('wort', wort); }
    const q = !OHNE_WORT.includes(reiter) && this._wortId ? '?wort=' + encodeURIComponent(this._wortId) : '';
    history.pushState(null, '', this._basis + '/' + reiter + q);
    window.dispatchEvent(new CustomEvent('location-changed'));
  }

  _aufbauen() {
    this.shadowRoot.innerHTML = `<style>${STIL}</style>
<div class="kopf"><ha-menu-button></ha-menu-button><h1>${esc(this.t('titel'))}</h1>
<button class="ikon" data-reiter="geraete" title="${esc(this.t('r_geraete'))}"><ha-icon icon="mdi:speaker-wireless"></ha-icon></button>
<button class="ikon" data-reiter="einstellungen" title="${esc(this.t('r_einstellungen'))}"><ha-icon icon="mdi:cog-outline"></ha-icon></button></div>
<div class="leisten"><nav class="woerter"></nav><nav class="reiter"></nav></div><main></main><input type="file" id="datei" accept=".zip,application/zip,.wav,audio/wav" hidden multiple>`;
    const m = this.shadowRoot.querySelector('ha-menu-button'); m.hass = this._hass; m.narrow = this._narrow;
    this._reiter = this._reiter || 'zentrale';
    this.shadowRoot.addEventListener('click', (e) => this._klick(e));
    this.shadowRoot.addEventListener('change', (e) => this._aenderung(e));
    this.shadowRoot.addEventListener('input', (e) => this._eingabe(e));
    const main = this.shadowRoot.querySelector('main');
    main.addEventListener('dragover', (e) => { const z = e.target.closest('.abwurf'); if (z) { e.preventDefault(); z.classList.add('ueber'); } });
    main.addEventListener('dragleave', (e) => { const z = e.target.closest('.abwurf'); if (z) z.classList.remove('ueber'); });
    main.addEventListener('drop', (e) => { const z = e.target.closest('.abwurf'); if (z) { e.preventDefault(); z.classList.remove('ueber'); this._hochladen([...e.dataTransfer.files]); } });
    this._kopfZeichnen();
  }

  _mitWort() { return !OHNE_WORT.includes(this._reiter) && !!(this._daten && this._daten.wort); }

  _kopfZeichnen() {
    const sr = this.shadowRoot, d = this._daten;
    const wn = sr.querySelector('nav.woerter'), rn = sr.querySelector('nav.reiter'); if (!wn) return;
    const woerter = (d && d.woerter) || [];
    const mit = this._mitWort();
    wn.innerHTML = `<a data-reiter="zentrale" class="${this._reiter === 'zentrale' ? 'an' : ''}"><ha-icon icon="mdi:view-grid-outline"></ha-icon>${esc(this.t('alle_woerter'))}${d && d.offen ? `<span class="zahl">${d.offen}</span>` : ''}</a>`
      + woerter.map((w, i) => `<a class="wortchip ${mit && w.id === this._wortId ? 'an' : ''}" data-reiter="${mit ? this._reiter : 'uebersicht'}" data-wort="${esc(w.id)}"><span class="farbe" style="background:${this._farbe(w, i)}"></span>${esc(w.wort)}${w.offen ? `<span class="zahl">${w.offen}</span>` : ''}</a>`).join('')
      + (this._admin ? `<a data-reiter="neu" class="${this._reiter === 'neu' ? 'an' : ''}"><ha-icon icon="mdi:plus"></ha-icon>${esc(this.t('neues_wort'))}</a>` : '');
    const w = this._wortKurz();
    rn.style.display = mit ? '' : 'none';
    rn.innerHTML = mit ? WORT_REITER.filter(([id]) => id !== 'wort' || this._admin).map(([id, i]) => `<a data-reiter="${id}" class="${id === this._reiter ? 'an' : ''}"><ha-icon icon="${i}"></ha-icon>${esc(this.t('r_' + id))}${id === 'pruefen' && w && w.offen ? `<span class="zahl">${w.offen}</span>` : ''}</a>`).join('') : '';
    sr.querySelectorAll('.kopf .ikon').forEach((b) => b.classList.toggle('an', b.dataset.reiter === this._reiter));
  }

  async _api(methode, pfad, daten) { return this._hass.callApi(methode, 'sprachmodell/' + pfad, daten); }

  async _laden() {
    try {
      const q = new URLSearchParams();
      if (this._wortId) q.set('wort', this._wortId);
      if (this._reiter === 'neu') q.set('modelle', '1');
      this._daten = await this._api('GET', 'daten?' + q);
      // Kein (gültiges) Wort gewählt: erstes mit offenen Aufnahmen, sonst erstes
      if (!OHNE_WORT.includes(this._reiter) && !this._daten.wort) {
        const w = this._daten.woerter.find((x) => x.offen) || this._daten.woerter[0];
        if (w && w.id !== this._wortId) {
          this._wortId = w.id; this._merk('wort', w.id);
          history.replaceState(null, '', this._basis + '/' + this._reiter + '?wort=' + encodeURIComponent(w.id));
          return this._laden();
        }
      }
      const ew = this._wortId ? '&wort=' + encodeURIComponent(this._wortId) : '';
      const ef = this._filter.echo ? '&echo=' + encodeURIComponent(this._filter.echo) : '';
      if (this._daten.wort && this._reiter === 'pruefen') this._liste = await this._api('GET', 'liste?filter=offen' + ew + ef);
      if (this._daten.wort && this._reiter === 'verlauf') this._liste = await this._api('GET', `liste?filter=${this._filter.verlauf}&seite=${this._filter.seite}` + ew + ef);
      this._fehler = null;
    } catch (e) { this._fehler = this._fehlerText(e); }
    this._kopfZeichnen();
    this._zeichnen();
  }

  _zeichnen() {
    const main = this.shadowRoot.querySelector('main'); if (!main) return;
    if (this._fehler) { main.innerHTML = `<ha-card><div class="leer"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><p>${esc(this._fehler)}</p><button class="k" data-a="neu">${esc(this.t('neu_laden'))}</button></div></ha-card>`; return; }
    if (!this._daten) { main.innerHTML = `<div class="leer">${esc(this.t('laedt'))}</div>`; return; }
    const seiten = {
      zentrale: this._zentrale, geraete: this._geraete, einstellungen: this._einstellungen, neu: this._neu,
      uebersicht: this._uebersicht, pruefen: this._pruefen, aufnehmen: this._aufnehmen, verlauf: this._verlauf,
      hochladen: this._hochladenSeite, training: this._training, qualitaet: this._qualitaet, wort: this._wortSeite,
    };
    let f = seiten[this._reiter] || this._zentrale;
    if (!OHNE_WORT.includes(this._reiter) && !this._daten.wort) f = this._zentrale;
    const scroll = window.scrollY;
    main.innerHTML = f.call(this);
    if (this._reiter === 'pruefen') this._markieren(false);
    if (this._reiter === 'aufnehmen') this._recZeichnen();
    window.scrollTo(0, scroll);
  }

  // ---------- Zentrale ----------
  _trainerKachel() {
    const tr = this._daten.trainer;
    return `<ha-card class="kachel" data-reiter="einstellungen"><div class="klein"><ha-icon icon="mdi:school-outline"></ha-icon> ${esc(this.t('z_trainer'))}</div><div class="wert" style="font-size:22px"><span class="punkt ${tr.online ? 'an' : ''}"></span>${esc(tr.online ? this.t('z_trainer_an') : tr.kontakt ? this.t('z_trainer_aus') : this.t('z_trainer_nie'))}</div><div class="klein">${tr.info && tr.info.name ? esc(tr.info.name) + ' · ' : ''}${tr.kontakt ? this._zeit(tr.kontakt) : ''}</div></ha-card>`;
  }

  _geraeteKachel() {
    const d = this._daten;
    return `<ha-card class="kachel" data-reiter="geraete"><div class="klein"><ha-icon icon="mdi:speaker-wireless"></ha-icon> ${esc(this.t('z_geraete_titel'))}</div><div class="wert">${d.geraete.length}</div><div class="klein">${d.geraete.map((g) => esc(g.name)).join(', ') || esc(this.t('z_geraete_leer'))}</div></ha-card>`;
  }

  _zentrale() {
    const d = this._daten;
    if (!d.woerter.length) {
      return `<ha-card><div class="leer" style="padding:28px 12px"><ha-icon icon="mdi:waveform"></ha-icon><h2 style="margin-top:12px;color:var(--primary-text-color)">${esc(this.t('z_leer_titel'))}</h2><p style="max-width:560px;margin:0 auto 16px;line-height:1.5">${esc(this.t('z_leer_text'))}</p>${this._admin ? `<button class="k haupt" data-reiter="neu"><ha-icon icon="mdi:plus"></ha-icon>${esc(this.t('z_wort_anlegen'))}</button>` : `<p class="klein">${esc(this.t('nur_admin_hinweis'))}</p>`}</div></ha-card>
<div class="raster">${this._trainerKachel()}${this._geraeteKachel()}</div>`;
    }
    const karten = d.woerter.map((w, i) => {
      const t = w.training || {}, laeuft = LAEUFT.includes(t.phase), n = Object.keys(w.geraete || {}).length;
      return `<ha-card class="kachel wortkarte ${laeuft ? 'laeuft' : ''}" style="--wf:${this._farbe(w, i)}" data-reiter="${w.offen ? 'pruefen' : 'uebersicht'}" data-wort="${esc(w.id)}">
<div class="klein">${esc(SPRACHNAMEN[this._spr][w.sprache] || w.sprache)} · ${esc(n === 1 ? this.t('z_geraet') : n ? this.t('z_geraete', { n }) : this.t('z_kein_geraet'))}</div>
<div class="name">${esc(w.wort)}</div>
<div class="zeile weit"><span class="${w.offen ? 'gelb' : 'klein'}">${w.offen} ${esc(this.t('z_offen'))}</span><span class="klein">${w.aktiv ? 'v' + w.aktiv : esc(this.t('z_keine_version'))}</span></div>
${laeuft ? `<div class="fortschritt"><i style="width:${t.prozent ?? 3}%"></i></div><div class="klein">${esc(this.t('p_' + t.phase))}${t.prozent != null ? ' · ' + Math.round(t.prozent) + ' %' : ''}</div>` : `<div class="reihe klein">${w.trefferquote != null ? `<span>${esc(this.t('z_erkennt', { q: this._pct(w.trefferquote) }))}</span>` : ''}${w.fehlausloeser != null ? `<span>${esc(this.t('z_fehl', { n: this._zahl(w.fehlausloeser, 1) }))}</span>` : ''}${t.phase === 'wartet' ? `<span class="gelb">${esc(this.t('p_wartet'))}</span>` : ''}${t.phase === 'fehler' ? `<span class="rot">${esc(this.t('p_fehler'))}</span>` : ''}</div>`}
</ha-card>`;
    }).join('');
    const reihe = d.reihe.map((id) => (d.woerter.find((w) => w.id === id) || {}).wort).filter(Boolean);
    return `<div class="raster">${karten}${this._admin ? `<ha-card class="kachel" data-reiter="neu" style="display:flex;align-items:center;justify-content:center;min-height:130px;color:var(--secondary-text-color)"><div style="text-align:center"><ha-icon icon="mdi:plus-circle-outline" style="--mdc-icon-size:36px"></ha-icon><div>${esc(this.t('neues_wort'))}</div></div></ha-card>` : ''}</div>
<div class="raster">${this._trainerKachel()}
<ha-card class="kachel" data-reiter="einstellungen"><div class="klein"><ha-icon icon="mdi:format-list-numbered"></ha-icon> ${esc(this.t('z_reihe'))}</div><div class="wert" style="font-size:22px">${reihe.length}</div><div class="klein">${reihe.length ? reihe.map(esc).join(' → ') : esc(this.t('z_reihe_leer'))}</div></ha-card>
${this._geraeteKachel()}</div>`;
  }

  // ---------- Übersicht eines Worts ----------
  _uebersicht() {
    const d = this._daten, w = d.wort, s = w.statistik, t = w.training, v = w.versionen.find((x) => x.nr === w.aktiv), b = (v && v.bericht && v.bericht.neu) || {};
    const e = w.einstellungen, laeuft = LAEUFT.includes(t.phase);
    const namen = Object.fromEntries(d.geraete.map((g) => [g.knoten, g.name]));
    const geraete = Object.entries(e.geraete || {}).map(([k, p]) => (namen[k] || k) + ' · ' + this.t('w_platz', { n: p }));
    return `
<div class="raster">
  <ha-card class="kachel" data-reiter="pruefen"><div class="klein"><ha-icon icon="mdi:playlist-check"></ha-icon> ${esc(this.t('ue_warten'))}</div><div class="wert ${s.offen ? 'gelb' : ''}">${s.offen}</div><div class="klein">${s.offen ? esc(this.t('ue_aelteste', { z: this._zeit(s.aeltestes_offen) })) : esc(this.t('ue_alles'))}</div></ha-card>
  <ha-card class="kachel" data-reiter="qualitaet"><div class="klein"><ha-icon icon="mdi:bullseye-arrow"></ha-icon> ${esc(this.t('ue_aktiv'))}</div><div class="wert">${v ? 'v' + v.nr : '–'}</div><div class="klein">${b.trefferquote != null ? esc(this.t('z_erkennt', { q: this._pct(b.trefferquote) }) + ' · ' + this.t('z_fehl', { n: this._zahl(b.fehlausloeser_pro_stunde, 1) })) : v ? esc(this.t('ue_eingespielt', { z: this._zeit(v.eingespielt) })) : esc(this.t('q_keine'))}</div></ha-card>
  <ha-card class="kachel ${laeuft ? 'laeuft' : ''}" data-reiter="training"><div class="klein"><ha-icon icon="mdi:school-outline"></ha-icon> ${esc(this.t('r_training'))}</div><div class="wert" style="font-size:22px">${esc(this.t('p_' + t.phase))}</div>${laeuft && t.prozent != null ? `<div class="fortschritt"><i style="width:${t.prozent}%"></i></div>` : ''}<div class="klein">${laeuft ? esc(this._schritt(t.schritt)) : `<span class="punkt ${d.trainer.online ? 'an' : ''}"></span>${esc(d.trainer.online ? this.t('t_trainer_an') : this.t('t_kein_trainer'))}`}${!laeuft && w.neu_seit_lauf > 0 ? ' · ' + esc(this.t('ue_neue_bew', { n: w.neu_seit_lauf })) : ''}</div></ha-card>
  <ha-card class="kachel" data-reiter="${this._admin ? 'wort' : 'geraete'}"><div class="klein"><ha-icon icon="mdi:speaker-wireless"></ha-icon> ${esc(this.t('ue_geraete'))}</div><div class="wert">${geraete.length}</div><div class="klein">${geraete.map(esc).join(', ') || esc(this.t('z_kein_geraet'))}</div></ha-card>
</div>
<ha-card><h2>${esc(this.t('ue_alltag'))}</h2>${this._alltag()}</ha-card>
<ha-card><h2>${esc(this.t('ue_so'))}</h2><div class="klein" style="line-height:1.6">
1. ${this.t('ue_so_1')}<br>2. ${esc(this.t('ue_so_2', { w: e.wort }))}<br>3. ${this.t('ue_so_3')}<br>
4. ${esc(e.nachts ? this.t('ue_so_4n', { u: String(d.einstellungen.uhrzeit).slice(0, 5) }) : this.t('ue_so_4h'))} ${esc(this.t('ue_so_4b'))} ${esc(e.automatisch_einspielen ? this.t('ue_so_5a') : this.t('ue_so_5h'))}
</div></ha-card>`;
  }

  _alltag() {
    const a = this._daten.wort.statistik.alltag;
    if (!a.aufgewacht && !a.verpasst) return `<div class="klein">${esc(this.t('al_leer'))}</div>`;
    const quote = a.aufgewacht ? a.richtig / a.aufgewacht : null;
    return `<div class="raster" style="margin:0"><div><div class="klein">${esc(this.t('al_richtig'))}</div><div class="wert gruen" style="font-size:24px">${a.richtig}</div></div>
<div><div class="klein">${esc(this.t('al_falsch'))}</div><div class="wert ${a.falsch ? 'rot' : ''}" style="font-size:24px">${a.falsch}</div></div>
<div><div class="klein">${esc(this.t('al_verpasst'))}</div><div class="wert ${a.verpasst ? 'gelb' : ''}" style="font-size:24px">${a.verpasst}</div></div>
<div><div class="klein">${esc(this.t('al_genau'))}</div><div class="wert" style="font-size:24px">${quote == null ? '–' : this._pct(quote)}</div></div></div>`;
  }

  // ---------- Prüfen ----------
  _personWahl(wert, id) {
    const p = this._daten.personen;
    return `<select data-person="${id || ''}" title="${esc(this.t('pr_wer'))}"><option value="">${esc(this.t('pr_person'))}</option>${p.map((n) => `<option ${n === wert ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>`;
  }

  _pruefen() {
    const l = this._liste || { eintraege: [], gesamt: 0 }, s = this._daten.wort.statistik;
    const echoChips = Object.entries(s.offen_je_echo || {}).map(([e, n]) => `<button class="chip ${this._filter.echo === e ? 'an' : ''}" data-echo="${esc(e)}">${esc(e)} · ${n}</button>`).join('');
    const mitVorschlag = l.eintraege.filter((a) => a.vorschlag).length;
    if (!l.gesamt) return `<ha-card><div class="leer"><ha-icon icon="mdi:check-all"></ha-icon><p>${esc(this.t('pr_leer'))}</p><p class="klein">${esc(this.t('pr_leer_text'))}</p><button class="k" data-a="holen"><ha-icon icon="mdi:download-outline"></ha-icon>${esc(this.t('pr_holen'))}</button></div></ha-card>`;
    return `
<div class="zeile weit" style="margin-bottom:10px"><div class="zeile"><button class="chip ${!this._filter.echo ? 'an' : ''}" data-echo="">${esc(this.t('pr_alle'))} · ${s.offen}</button>${echoChips}</div>
<div class="zeile"><label class="klein"><input type="checkbox" id="autoplay" ${this._autoplay ? 'checked' : ''}> ${esc(this.t('pr_autoplay'))}</label>${mitVorschlag ? `<button class="k" data-a="alle_vorschlaege"><ha-icon icon="mdi:check-all"></ha-icon>${esc(this.t('pr_vorschlaege', { n: mitVorschlag }))}</button>` : ''}</div></div>
<div class="klein" style="margin-bottom:10px">${this.t('pr_tasten')}</div>
<div class="liste">${l.eintraege.map((a, i) => this._eintrag(a, i, true)).join('')}</div>
${l.gesamt > l.eintraege.length ? `<div class="leer klein">${esc(this.t('pr_weitere', { n: l.gesamt - l.eintraege.length }))}</div>` : ''}`;
  }

  _eintrag(a, i, pruefen) {
    const art = a.quelle === 'browser' ? 'browser' : a.art;
    const sc = typeof a.score === 'number' ? a.score : null, cu = typeof a.cutoff === 'number' ? a.cutoff : null;
    const wort = this._daten.wort.einstellungen.wort;
    const urteil = a.urteil ? `<span class="${a.urteil === 'wort' ? 'gruen' : a.urteil === 'kein_wort' ? 'rot' : ''}">${esc(this.t('u_' + a.urteil))}</span>` : '';
    const grund = a.grund ? this.t('g_' + a.grund) : '';
    return `<div class="eintrag" tabindex="-1" data-id="${esc(a.id)}" data-i="${i}">
<button class="spielen" data-spielen="${esc(a.id)}" title="${esc(this.t('pr_abspielen'))}"><svg viewBox="0 0 52 52"><circle cx="26" cy="26" r="25"></circle></svg><ha-icon icon="mdi:play"></ha-icon></button>
<div><div class="zeile weit"><span class="titel"><ha-icon icon="${ART_ICON[art] || 'mdi:waveform'}" style="--mdc-icon-size:16px"></ha-icon> ${esc(this.t('a_' + art))}${a.echo ? ' · ' + esc(a.echo) : ''}</span><span class="klein">${this._zeit(a.zeit)}${a.dauer ? ' · ' + this._zahl(a.dauer, 1) + ' s' : ''}${a.test ? ' · ' + esc(this.t('pr_test')) : ''}</span></div>
${sc != null ? `<div class="balken"><i style="width:${Math.min(100, sc * 100)}%"></i>${cu != null ? `<b style="left:${cu * 100}%"></b>` : ''}</div><div class="klein">${esc(this.t('pr_wert', { w: this._zahl(sc) }))}${cu != null ? ' · ' + esc(this.t('pr_schwelle', { w: this._zahl(cu) })) : ''}</div>` : a.notiz ? `<div class="klein">${esc(a.notiz)}</div>` : ''}
${pruefen && a.vorschlag ? `<div class="vorschlag">${esc(this.t('pr_vorschlag'))}: <strong>${esc(a.vorschlag === 'wort' ? this.t('pr_gesagt', { w: wort }) : this.t('pr_nicht'))}</strong>${grund ? ' – ' + esc(grund) : ''}</div>` : !pruefen ? `<div class="vorschlag">${urteil}${a.person ? ' · ' + esc(a.person) : ''}${a.quelle === 'hochgeladen' ? ' · ' + esc(this.t('pr_hochgeladen')) : a.quelle === 'browser' ? ' · ' + esc(this.t('pr_aufgenommen')) : ''}</div>` : ''}
<div class="knoepfe">
<button class="k gut" data-urteil="wort" data-id="${esc(a.id)}"><ha-icon icon="mdi:check"></ha-icon>${esc(pruefen ? this.t('pr_gesagt', { w: wort }) : this.t('pr_wort_k'))} <kbd>1</kbd></button>
<button class="k schlecht" data-urteil="kein_wort" data-id="${esc(a.id)}"><ha-icon icon="mdi:close"></ha-icon>${esc(this.t('pr_nicht_k'))} <kbd>2</kbd></button>
<button class="k leise" data-urteil="verworfen" data-id="${esc(a.id)}" title="${esc(this.t('pr_unbrauchbar_t'))}"><ha-icon icon="mdi:delete-outline"></ha-icon>${esc(this.t('u_verworfen'))} <kbd>0</kbd></button>
${this._personWahl(a.person || (pruefen ? this._person : ''), a.id)}
</div></div></div>`;
  }

  _markieren(fokus = true) {
    const alle = [...this.shadowRoot.querySelectorAll('.eintrag:not(.weg)')];
    alle.forEach((e, i) => e.classList.toggle('aktiv', i === this._aktiv));
    const e = alle[this._aktiv];
    if (e && fokus) e.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    return e;
  }

  _tastatur(e) {
    if (this._reiter !== 'pruefen' || e.ctrlKey || e.metaKey || e.altKey) return;
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes((e.composedPath()[0] || {}).tagName)) return;
    const alle = [...this.shadowRoot.querySelectorAll('.eintrag:not(.weg)')];
    if (!alle.length) return;
    const akt = alle[this._aktiv] || alle[0];
    if (e.key === 'ArrowDown') { this._aktiv = Math.min(alle.length - 1, this._aktiv + 1); this._markieren(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { this._aktiv = Math.max(0, this._aktiv - 1); this._markieren(); e.preventDefault(); }
    else if (e.key === ' ') { this._spielen(akt.dataset.id); e.preventDefault(); }
    else if (e.key === '1') this._urteilen(akt.dataset.id, 'wort');
    else if (e.key === '2') this._urteilen(akt.dataset.id, 'kein_wort');
    else if (e.key === '0') this._urteilen(akt.dataset.id, 'verworfen');
  }

  async _blob(id) {
    const schl = this._wortId + '/' + id;
    if (this._blobs.has(schl)) return this._blobs.get(schl);
    const r = await this._hass.fetchWithAuth('/api/sprachmodell/audio/' + encodeURIComponent(this._wortId) + '/' + encodeURIComponent(id));
    if (!r.ok) throw new Error(r.statusText);
    const url = URL.createObjectURL(await r.blob());
    this._blobs.set(schl, url);
    if (this._blobs.size > 80) { const [k, v] = this._blobs.entries().next().value; URL.revokeObjectURL(v); this._blobs.delete(k); }
    return url;
  }

  async _spielen(id, url) {
    try {
      if (this._spielt === id && !this._audio.paused) { this._audio.pause(); this._spielt = null; this._ring(true); return; }
      this._audio.pause(); this._ring(true);
      this._audio.src = url || await this._blob(id);
      this._spielt = id;
      await this._audio.play();
    } catch (e) { this._meldung(this.t('ging_nicht', { f: e.message })); }
  }

  _ring(aus) {
    this.shadowRoot.querySelectorAll('.spielen').forEach((b) => {
      const an = !aus && b.dataset.spielen === this._spielt;
      const c = b.querySelector('circle'), d = this._audio.duration || 1;
      c.style.strokeDashoffset = an ? 157 - 157 * (this._audio.currentTime / d) : 157;
      b.querySelector('ha-icon').setAttribute('icon', an && !this._audio.paused ? 'mdi:pause' : 'mdi:play');
    });
  }

  async _urteilen(id, urteil) {
    const zeile = this.shadowRoot.querySelector(`.eintrag[data-id="${CSS.escape(id)}"]`);
    const sel = zeile && zeile.querySelector('select[data-person]');
    const person = urteil === 'wort' ? (sel ? sel.value : this._person) : '';
    try { await this._api('POST', 'urteil', { wort: this._wortId, ids: [id], urteil, person }); }
    catch (e) { this._meldung(this.t('ging_nicht', { f: this._fehlerText(e) })); return; }
    if (this._reiter === 'pruefen' && zeile) {
      zeile.classList.add('weg');
      if (this._spielt === id) this._audio.pause();
      const rest = [...this.shadowRoot.querySelectorAll('.eintrag:not(.weg)')];
      this._aktiv = Math.min(this._aktiv, rest.length - 1);
      const naechste = this._markieren();
      if (naechste && this._autoplay) this._spielen(naechste.dataset.id);
      clearTimeout(this._nachladen); this._nachladen = setTimeout(() => this._laden(), rest.length ? 4000 : 300);
    } else this._laden();
  }

  // ---------- Aufnehmen ----------
  _aufnehmen() {
    const s = this._daten.wort.statistik, r = this._rec;
    const bisher = Object.values(s.personen || {}).reduce((x, p) => x + (r.modus === 'wort' ? p.wort : p.kein_wort), 0);
    const sicher = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
    return `<ha-card><h2>${esc(this.t('au_titel'))}</h2>
${sicher ? '' : `<div class="hinweis">${esc(this.t('au_kein_mikro'))}</div>`}
<div class="zeile" style="margin-bottom:8px"><button class="chip ${r.modus === 'wort' ? 'an' : ''}" data-recmodus="wort">${esc(this.t('au_wort'))}: „${esc(this._daten.wort.einstellungen.wort)}“</button><button class="chip ${r.modus === 'kein_wort' ? 'an' : ''}" data-recmodus="kein_wort">${esc(this.t('au_gegen'))}</button></div>
<div class="klein" style="line-height:1.5">${esc(this.t(r.modus === 'wort' ? 'au_hilfe_wort' : 'au_hilfe_gegen'))}</div>
<div class="zeile" style="margin-top:10px"><span class="klein">${esc(this.t('h_wer'))}</span>${this._personWahl(this._person, 'rec')}<input type="text" id="recnotiz" style="max-width:260px" placeholder="${esc(this.t('au_umgebung_bsp'))}" value="${esc(r.notiz || '')}" title="${esc(this.t('au_umgebung'))}"></div>
<div class="rec"><button class="gross ${r.an ? 'an' : ''}" data-a="rec" ${sicher ? '' : 'disabled'}><ha-icon icon="${r.an ? 'mdi:stop' : 'mdi:microphone'}"></ha-icon></button><div class="pegel" title="${esc(this.t('au_pegel'))}"><i id="pegel"></i></div><div class="klein" id="recinfo">${esc(this.t(r.an ? 'au_stopp' : 'au_start'))}</div></div>
<div id="takes"></div>
<div class="klein" style="margin-top:12px">${esc(this.t('au_wieviel', { n: bisher }))}</div></ha-card>`;
  }

  _recZeichnen() {
    const box = this.shadowRoot.getElementById('takes'); if (!box) return;
    const r = this._rec;
    box.innerHTML = r.takes.length ? `<div class="takes">${r.takes.map((t, i) => `<span class="take ${t.modus === 'kein_wort' ? 'gegen' : ''}">${this._zahl(t.dauer, 1)} s<button data-takespielen="${i}" title="${esc(this.t('pr_abspielen'))}"><ha-icon icon="mdi:play"></ha-icon></button><button data-takeweg="${i}"><ha-icon icon="mdi:close"></ha-icon></button></span>`).join('')}</div>
<div class="zeile" style="margin-top:12px"><button class="k haupt" data-a="recspeichern"><ha-icon icon="mdi:content-save-outline"></ha-icon>${esc(this.t('au_speichern', { n: r.takes.length }))}</button><button class="k leise" data-a="recverwerfen">${esc(this.t('au_verwerfen'))}</button></div>` : `<div class="klein" style="text-align:center">${esc(this.t('au_leer'))}</div>`;
    const knopf = this.shadowRoot.querySelector('[data-a="rec"]');
    if (knopf) { knopf.classList.toggle('an', r.an); knopf.querySelector('ha-icon').setAttribute('icon', r.an ? 'mdi:stop' : 'mdi:microphone'); }
    const info = this.shadowRoot.getElementById('recinfo'); if (info) info.textContent = this.t(r.an ? 'au_stopp' : 'au_start');
  }

  async _recStart() {
    const r = this._rec;
    try {
      r.strom = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } });
    } catch (e) { this._meldung(this.t('au_erlaubnis', { f: e.message })); return; }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const quelle = ctx.createMediaStreamSource(r.strom);
    const proz = ctx.createScriptProcessor(2048, 1, 1);
    const rate = ctx.sampleRate, block = 2048 / rate;
    // Einfache Trennung nach Lautstärke: Sprache = deutlich über dem Grundrauschen
    let rauschen = 0.004, imWort = false, still = 0, puffer = [], vorlauf = [];
    const VOR = Math.ceil(0.3 / block), NACH = Math.ceil(0.35 / block), LANG = Math.ceil(3.0 / block);
    proz.onaudioprocess = (ev) => {
      const x = new Float32Array(ev.inputBuffer.getChannelData(0));
      let s = 0; for (let i = 0; i < x.length; i++) s += x[i] * x[i];
      const rms = Math.sqrt(s / x.length);
      const p = this.shadowRoot.getElementById('pegel'); if (p) p.style.width = Math.min(100, Math.sqrt(rms) * 300) + '%';
      const laut = rms > Math.max(0.012, rauschen * 4);
      if (!imWort) {
        rauschen = rauschen * 0.97 + rms * 0.03;
        vorlauf.push(x); if (vorlauf.length > VOR) vorlauf.shift();
        if (laut) { imWort = true; still = 0; puffer = [...vorlauf]; }
      } else {
        puffer.push(x);
        still = laut ? 0 : still + 1;
        if (still >= NACH || puffer.length >= LANG) {
          imWort = false; vorlauf = [];
          if (puffer.length * block >= 0.45) this._takeNeu(puffer, rate);
          puffer = [];
        }
      }
    };
    quelle.connect(proz); proz.connect(ctx.destination);
    Object.assign(r, { ctx, quelle, proz, an: true });
    this._recZeichnen();
  }

  _recStopp() {
    const r = this._rec;
    if (!r.an) return;
    try { r.proz.disconnect(); r.quelle.disconnect(); r.strom.getTracks().forEach((t) => t.stop()); r.ctx.close(); } catch (e) { /* schon zu */ }
    r.an = false;
    this._recZeichnen();
  }

  _takeNeu(stuecke, rate) {
    // Zusammenfügen, auf 16 kHz bringen (Mittelwert je Fenster), als WAV 16 bit mono ablegen
    const n = stuecke.reduce((a, b) => a + b.length, 0), roh = new Float32Array(n);
    let o = 0; for (const s of stuecke) { roh.set(s, o); o += s.length; }
    const faktor = rate / 16000, m = Math.floor(n / faktor), aus = new Int16Array(m);
    for (let i = 0; i < m; i++) {
      const a = Math.floor(i * faktor), b = Math.max(a + 1, Math.min(n, Math.floor((i + 1) * faktor)));
      let s = 0; for (let j = a; j < b; j++) s += roh[j];
      aus[i] = Math.max(-32768, Math.min(32767, (s / (b - a)) * 32767));
    }
    const kopf = new DataView(new ArrayBuffer(44));
    const schreib = (p, t) => { for (let i = 0; i < t.length; i++) kopf.setUint8(p + i, t.charCodeAt(i)); };
    schreib(0, 'RIFF'); kopf.setUint32(4, 36 + m * 2, true); schreib(8, 'WAVE'); schreib(12, 'fmt ');
    kopf.setUint32(16, 16, true); kopf.setUint16(20, 1, true); kopf.setUint16(22, 1, true); kopf.setUint32(24, 16000, true);
    kopf.setUint32(28, 32000, true); kopf.setUint16(32, 2, true); kopf.setUint16(34, 16, true); schreib(36, 'data'); kopf.setUint32(40, m * 2, true);
    const blob = new Blob([kopf, aus.buffer], { type: 'audio/wav' });
    this._rec.takes.push({ blob, url: URL.createObjectURL(blob), dauer: m / 16000, modus: this._rec.modus });
    this._recZeichnen();
  }

  async _recSpeichern() {
    const r = this._rec, sel = this.shadowRoot.querySelector('select[data-person="rec"]');
    const person = sel ? sel.value : this._person, notiz = (this.shadowRoot.getElementById('recnotiz') || {}).value || '';
    let n = 0;
    for (const t of [...r.takes]) {
      const fd = new FormData();
      fd.append('wort', this._wortId); fd.append('urteil', t.modus); fd.append('person', person); fd.append('notiz', notiz);
      fd.append('datei', t.blob, 'aufnahme.wav');
      const antwort = await this._hass.fetchWithAuth('/api/sprachmodell/aufnahme', { method: 'POST', body: fd });
      if (antwort.ok) { n += 1; URL.revokeObjectURL(t.url); r.takes.splice(r.takes.indexOf(t), 1); }
    }
    this._meldung(this.t('au_gespeichert', { n }));
    this._laden();
  }

  // ---------- Verlauf ----------
  _verlauf() {
    const l = this._liste || { eintraege: [], gesamt: 0, seiten: 1 };
    const filter = ['bewertet', 'hochgeladen', 'test', 'alle'];
    return `<div class="zeile" style="margin-bottom:10px">${filter.map((k) => `<button class="chip ${this._filter.verlauf === k ? 'an' : ''}" data-verlauf="${k}">${esc(this.t('v_' + k))}</button>`).join('')}<span class="klein">${esc(this.t('v_anzahl', { n: l.gesamt }))}</span></div>
<div class="klein" style="margin-bottom:10px">${esc(this.t('v_hilfe'))}</div>
${l.gesamt ? `<div class="liste">${l.eintraege.map((a, i) => this._eintrag(a, i, false)).join('')}</div>` : `<ha-card><div class="leer">${esc(this.t('v_leer'))}</div></ha-card>`}
${l.seiten > 1 ? `<div class="zeile" style="justify-content:center;margin-top:12px"><button class="k" data-seite="-1" ${l.seite ? '' : 'disabled'}>${esc(this.t('zurueck'))}</button><span class="klein">${esc(this.t('seite', { a: l.seite + 1, b: l.seiten }))}</span><button class="k" data-seite="1" ${l.seite + 1 < l.seiten ? '' : 'disabled'}>${esc(this.t('weiter'))}</button></div>` : ''}`;
  }

  // ---------- Hochladen ----------
  _hochladenSeite() {
    const s = this._daten.wort.statistik;
    return `<ha-card><h2>${esc(this.t('h_titel'))}</h2>
<div class="zeile" style="margin-bottom:12px"><span class="klein">${esc(this.t('h_wer'))}</span>${this._personWahl(this._person, 'hoch')}</div>
<div class="abwurf" data-a="datei"><ha-icon icon="mdi:folder-zip-outline"></ha-icon><p>${this.t('h_ziehen')}</p><p class="klein">${this.t('h_ordner')}</p></div>
<div id="hochergebnis" style="margin-top:12px">${this._hochErgebnis || ''}</div></ha-card>
<ha-card><h2>${esc(this.t('h_woher'))}</h2><div class="klein" style="line-height:1.6">${this.t('h_woher_text')}</div></ha-card>
<ha-card><h2>${esc(this.t('h_bisher'))}</h2><table><tr><th>${esc(this.t('h_person'))}</th><th class="z">${esc(this.t('pr_wort_k'))}</th><th class="z">${esc(this.t('h_gegen'))}</th></tr>${Object.entries(s.personen).map(([p, n]) => `<tr><td>${esc(p === 'Unbekannt' ? this.t('unbekannt') : p)}</td><td class="z">${n.wort}</td><td class="z">${n.kein_wort}</td></tr>`).join('') || `<tr><td colspan="3" class="klein">${esc(this.t('h_nichts'))}</td></tr>`}</table></ha-card>`;
  }

  async _hochladen(dateien) {
    const passend = dateien.filter((f) => /\.(zip|wav)$/i.test(f.name));
    if (!passend.length) { this._meldung(this.t('h_nur_zip')); return; }
    const sel = this.shadowRoot.querySelector('select[data-person="hoch"]');
    const person = sel ? sel.value : '';
    const box = this.shadowRoot.getElementById('hochergebnis');
    let text = '';
    for (const f of passend) {
      if (box) box.innerHTML = text + `<div class="laeuft"><div class="klein">${esc(this.t('h_laeuft', { d: f.name }))}</div><div class="fortschritt"><i style="width:100%"></i></div></div>`;
      const fd = new FormData(); fd.append('wort', this._wortId); fd.append('person', person);
      try {
        const wav = /\.wav$/i.test(f.name);
        if (wav) { fd.append('urteil', 'wort'); fd.append('notiz', f.name); }
        fd.append('datei', f, f.name);
        const r = await this._hass.fetchWithAuth('/api/sprachmodell/' + (wav ? 'aufnahme' : 'hochladen'), { method: 'POST', body: fd });
        const j = await r.json();
        if (!r.ok) throw new Error(this._fehlerText({ message: j.message || r.statusText }));
        const w = wav ? 1 : j.wort, k = wav ? 0 : j.kein_wort;
        text += `<div class="hinweis ok"><b>${esc(f.name)}</b>: ${esc(this.t('h_ergebnis', { w, k }))}${j.doppelt ? ', ' + esc(this.t('h_doppelt', { n: j.doppelt })) : ''}${j.kaputt ? ', ' + esc(this.t('h_kaputt', { n: j.kaputt })) : ''}${person ? ' · ' + esc(person) : ''}</div>`;
      } catch (e) { text += `<div class="hinweis"><b>${esc(f.name)}</b>: ${esc(e.message)}</div>`; }
    }
    this._hochErgebnis = text;
    if (box) box.innerHTML = text;
    this._laden();
  }

  // ---------- Training ----------
  _ergebnisText(e) { return this.t({ eingespielt: 'e_eingespielt', besser: 'e_besser', nicht_besser: 'e_nicht_besser', 'nicht besser': 'e_nicht_besser', fehler: 'e_fehler' }[e] || e); }

  _training() {
    const d = this._daten, w = d.wort, t = w.training, e = w.einstellungen, tr = d.trainer;
    const laeuft = LAEUFT.includes(t.phase);
    const kurz = (b) => (b ? `${this._pct(b.trefferquote)} · ${this._zahl(b.fehlausloeser_pro_stunde, 1)}/${this.t('std')}` : '–');
    const platz = d.reihe.indexOf(w.id);
    return `${!tr.online && !tr.kontakt ? `<div class="hinweis"><b>${esc(this.t('t_kein_trainer'))}</b><br>${this.t('t_kein_trainer_text')}</div>` : ''}
<ha-card class="${laeuft ? 'laeuft' : ''}"><div class="zeile weit"><h2 style="margin:0">${esc(this.t('p_' + t.phase))}</h2><span class="klein"><span class="punkt ${tr.online ? 'an' : ''}"></span>${esc(tr.online ? this.t('t_trainer_an') : tr.kontakt ? this.t('t_trainer_zuletzt', { z: this._zeit(tr.kontakt) }) : this.t('t_trainer_nie'))}</span></div>
${laeuft ? `<div class="fortschritt"><i style="width:${t.prozent ?? 3}%"></i></div><div class="zeile weit klein"><span>${esc(this._schritt(t.schritt))}</span><span>${t.prozent != null ? Math.round(t.prozent) + ' %' : ''}${t.restzeit_min != null ? ' · ' + esc(this.t('t_noch', { z: this._dauer(t.restzeit_min) })) : ''}</span></div>${t.start ? `<div class="klein">${esc(this.t('t_gestartet', { z: this._zeit(t.start) }))}</div>` : ''}` : ''}
${t.phase === 'wartet' ? `<p class="klein">${esc(this.t('t_auftrag', { g: this.t('grund_' + (t.grund || 'von_hand')) }))} ${esc(tr.online ? this.t('t_holt') : this.t('t_holt_nicht'))} ${platz > 0 ? esc(this.t('t_platz', { n: platz + 1 })) : ''}</p>` : ''}
${t.phase === 'fertig' && t.version ? `<p>v${t.version}: ${t.besser ? `<span class="gruen">${esc(this.t('t_besser'))}</span>` : `<span class="gelb">${esc(this.t('t_nicht_besser'))}</span>`}.</p>` : ''}
${t.phase === 'fehler' ? `<p class="rot">${esc(this._schritt(t.schritt || t.hinweis) || this.t('p_fehler'))}</p>` : ''}
<div class="zeile" style="margin-top:12px">${laeuft || t.phase === 'wartet' ? `<button class="k schlecht" data-a="abbrechen"><ha-icon icon="mdi:stop"></ha-icon>${esc(this.t('t_abbrechen'))}</button>` : `<button class="k haupt" data-a="trainieren"><ha-icon icon="mdi:play"></ha-icon>${esc(this.t('t_jetzt'))}</button><span class="klein">${esc(w.neu_seit_lauf > 0 ? this.t('t_neue', { n: w.neu_seit_lauf }) : this.t('t_keine_neuen'))}</span>`}</div></ha-card>
<ha-card><h2>${esc(this.t('t_auto'))}</h2>
<div class="zeile" style="margin-bottom:10px"><label><input type="checkbox" data-wopt="nachts" ${e.nachts ? 'checked' : ''} ${this._admin ? '' : 'disabled'}> ${esc(this.t('t_nachts'))} · ${esc(String(d.einstellungen.uhrzeit).slice(0, 5))}</label></div>
<div class="zeile"><label><input type="checkbox" data-wopt="automatisch_einspielen" ${e.automatisch_einspielen ? 'checked' : ''} ${this._admin ? '' : 'disabled'}> ${esc(this.t('t_einspielen'))}</label></div>
<p class="klein">${esc(this.t('t_besser_heisst'))}</p></ha-card>
<ha-card><h2>${esc(this.t('t_laeufe'))}</h2>${w.laeufe.length ? `<table><tr><th>${esc(this.t('t_wann'))}</th><th>${esc(this.t('t_ergebnis'))}</th><th>${esc(this.t('t_vorher'))}</th><th>${esc(this.t('t_nachher'))}</th><th class="z">${esc(this.t('t_dauer'))}</th></tr>${w.laeufe.map((l) => `<tr><td>${this._datum(l.ende)}</td><td class="${l.ergebnis === 'eingespielt' ? 'gruen' : l.ergebnis === 'fehler' ? 'rot' : ''}">${esc(this._ergebnisText(l.ergebnis))}${l.version ? ' (v' + l.version + ')' : ''}${l.hinweis ? '<div class="klein">' + esc(l.hinweis) + '</div>' : ''}</td><td>${kurz(l.alt)}</td><td>${kurz(l.neu)}</td><td class="z">${l.dauer_min != null ? this._dauer(l.dauer_min) : '–'}</td></tr>`).join('')}</table>` : `<div class="klein">${esc(this.t('t_kein_lauf'))}</div>`}</ha-card>`;
  }

  // ---------- Qualität ----------
  _qualitaet() {
    const w = this._daten.wort, s = w.statistik, v = w.versionen.find((x) => x.nr === w.aktiv), b = (v && v.bericht) || {};
    const neu = b.neu || {}, personen = neu.je_person || {};
    const sjl = Object.values(w.schwellen || {}), sj = sjl.length ? sjl[0] : null;
    const herkunft = b.herkunft === 'vor der Integration eingespielt' ? this.t('q_herkunft') : b.herkunft;
    return `<ha-card><h2>${esc(this.t('q_aktiv'))} ${v ? 'v' + v.nr : ''}</h2>${v ? `
<div class="raster" style="margin:0">
<div><div class="klein">${esc(this.t('q_erkennt'))}</div><div class="wert" style="font-size:26px">${this._pct(neu.trefferquote)}</div></div>
<div><div class="klein">${esc(this.t('q_musik'))}</div><div class="wert" style="font-size:26px">${this._pct(neu.trefferquote_musik)}</div></div>
<div><div class="klein">${esc(this.t('q_fehl'))}</div><div class="wert" style="font-size:26px">${this._zahl(neu.fehlausloeser_pro_stunde, 1)}</div></div>
<div><div class="klein">${esc(this.t('q_gegen'))}</div><div class="wert" style="font-size:26px">${this._pct(neu.gegenbeispiele)}</div></div></div>
${Object.keys(personen).length ? `<h3>${esc(this.t('q_je_person'))}</h3><table><tr><th>${esc(this.t('h_person'))}</th><th class="z">${esc(this.t('q_erkannt'))}</th><th class="z">${esc(this.t('q_aufnahmen'))}</th></tr>${Object.entries(personen).map(([p, x]) => `<tr><td>${esc(p)}</td><td class="z">${this._pct(x.trefferquote)}</td><td class="z">${x.anzahl}</td></tr>`).join('')}</table>` : ''}
<div class="klein" style="margin-top:10px">${esc(this.t('ue_eingespielt', { z: this._zeit(v.eingespielt) }))}${b.cutoff ? ' · ' + esc(this.t('q_modell_schwelle', { w: this._zahl(b.cutoff) })) : ''}${herkunft ? ' · ' + esc(herkunft) : ''}</div>` : `<div class="klein">${esc(this.t('q_keine'))}</div>`}</ha-card>
<ha-card><h2>${esc(this.t('q_alltag'))}</h2>${this._alltag()}</ha-card>
<ha-card><h2>${esc(this.t('q_schwelle'))}</h2>${this._verteilung(sj, s.schwelle_vorschlag)}
${s.schwelle_vorschlag != null ? `<div class="zeile weit" style="margin-top:10px"><span>${this.t('q_vorschlag', { w: this._zahl(s.schwelle_vorschlag) })} ${sj != null ? esc(this.t('q_jetzt', { w: this._zahl(sj) })) : ''}</span><button class="k haupt" data-a="schwelle" data-wert="${s.schwelle_vorschlag}" ${!this._admin || (sj != null && Math.abs(sj - s.schwelle_vorschlag) < 0.005) ? 'disabled' : ''}>${esc(this.t('q_uebernehmen'))}</button></div>` : `<div class="klein">${esc(this.t('q_vorschlag_spaeter'))}</div>`}
<div class="klein" style="margin-top:8px">${esc(this.t('q_legende'))}</div></ha-card>
<ha-card><h2>${esc(this.t('q_versionen'))}</h2>${w.versionen.length ? `<table><tr><th>${esc(this.t('q_version'))}</th><th>${esc(this.t('q_erkannt'))}</th><th>${esc(this.t('q_fehl'))}</th><th>${esc(this.t('q_stand'))}</th><th></th></tr>${w.versionen.map((x) => { const n = (x.bericht && x.bericht.neu) || {}; return `<tr><td>v${x.nr}<div class="klein">${this._datum(x.zeit)}</div></td><td>${this._pct(n.trefferquote)}</td><td>${this._zahl(n.fehlausloeser_pro_stunde, 1)}/${esc(this.t('std'))}</td><td class="${x.status === 'aktiv' ? 'gruen' : ''}">${esc(this.t('s_' + x.status))}</td><td class="z">${x.status !== 'aktiv' && this._admin ? `<button class="k" data-a="einspielen" data-nr="${x.nr}">${esc(this.t('q_einspielen'))}</button>` : ''}</td></tr>`; }).join('')}</table>` : `<div class="klein">${esc(this.t('q_keine'))}</div>`}</ha-card>`;
  }

  _verteilung(jetzt, vorschlag) {
    const v = this._daten.wort.statistik.verteilung;
    if (!v.wort.length && !v.kein_wort.length) return `<div class="klein">${esc(this.t('q_keine_werte'))}</div>`;
    const B = 30, lo = 0.7, w = 600, h = 120, bw = w / B;
    const zaehl = (arr) => { const z = new Array(B).fill(0); arr.forEach((x) => { const i = Math.max(0, Math.min(B - 1, Math.floor((x - lo) / (1 - lo) * B))); z[i] += 1; }); return z; };
    const g = zaehl(v.wort), r = zaehl(v.kein_wort), max = Math.max(1, ...g, ...r);
    const xs = (x) => ((x - lo) / (1 - lo)) * w;
    let s = `<svg class="vert" viewBox="0 0 ${w} ${h + 16}" width="100%" preserveAspectRatio="none" style="max-height:170px">`;
    for (let i = 0; i < B; i++) {
      const hg = (g[i] / max) * h, hr = (r[i] / max) * h;
      if (g[i]) s += `<rect x="${i * bw + 1}" y="${h - hg}" width="${bw / 2 - 1}" height="${hg}" fill="var(--success-color,#4caf50)" rx="2"/>`;
      if (r[i]) s += `<rect x="${i * bw + bw / 2}" y="${h - hr}" width="${bw / 2 - 1}" height="${hr}" fill="var(--error-color,#f44336)" rx="2"/>`;
    }
    if (jetzt != null && jetzt >= lo) s += `<line x1="${xs(jetzt)}" x2="${xs(jetzt)}" y1="0" y2="${h}" stroke="var(--primary-text-color)" stroke-width="2"/>`;
    if (vorschlag != null) s += `<line x1="${xs(vorschlag)}" x2="${xs(vorschlag)}" y1="0" y2="${h}" stroke="var(--primary-color)" stroke-width="2" stroke-dasharray="4 3"/>`;
    [0.7, 0.8, 0.9, 1].forEach((t) => { s += `<text x="${Math.min(w - 14, xs(t))}" y="${h + 13}">${this._zahl(t, 1)}</text>`; });
    return s + '</svg>';
  }

  // ---------- Wort-Einstellungen und neues Wort ----------
  _sprachWahl(wert) {
    return `<select data-feld="sprache">${this._daten.sprachen.map((s) => `<option value="${s}" ${s === wert ? 'selected' : ''}>${esc(SPRACHNAMEN[this._spr][s] || s)}</option>`).join('')}</select>`;
  }

  _plaetze(e, eigeneId) {
    const d = this._daten;
    if (!d.geraete.length) return `<div class="klein" style="margin-top:8px">${esc(this.t('z_geraete_leer'))}</div>`;
    const name = (id) => (d.woerter.find((w) => w.id === id) || {}).wort || id;
    return d.geraete.map((g) => {
      const jetzt = (e.geraete || {})[g.knoten] || '';
      const plaetze = Object.keys(g.plaetze);
      const belegt = plaetze.map((p) => { const w = g.plaetze[p].wort; return w && w !== eigeneId ? ' – ' + this.t('w_belegt', { w: name(w) }) : ''; });
      const gewaehlt = jetzt && g.plaetze[jetzt] && g.plaetze[jetzt].auswahl;
      return `<div class="platz"><div><div>${esc(g.name)}</div><div class="klein">${esc(g.knoten)}${gewaehlt ? ' · ' + esc(this.t('w_auswahl', { w: gewaehlt })) : ''}${g.fehler ? ' · <span class="rot">' + esc(this.t('ge_nicht_gefunden')) + '</span>' : ''}${g.clips ? '' : ' · ' + esc(this.t('ge_ohne_clips'))}</div></div>
<select data-platz="${esc(g.knoten)}"><option value="">${esc(this.t('w_platz_aus'))}</option>${plaetze.map((p, i) => `<option value="${p}" ${jetzt === p ? 'selected' : ''}>${esc(this.t('w_platz', { n: p }) + belegt[i])}</option>`).join('')}</select></div>`;
    }).join('');
  }

  _farbWahl(wert) {
    return `<div class="farbwahl">${FARBEN.map((f) => `<button data-farbe="${f}" class="${f === wert ? 'an' : ''}" style="background:${f}" aria-label="${f}"></button>`).join('')}</div>`;
  }

  _neu() {
    const d = this._daten;
    if (!this._entwurf || this._entwurf.id) {
      const spr = String((this._hass.config && this._hass.config.language) || 'en').slice(0, 2);
      this._entwurf = { wort: '', anzeige: '', sprache: d.sprachen.includes(spr) ? spr : 'en', geraete: {}, modell_id: '', farbe: FARBEN[d.woerter.length % FARBEN.length], automatisch_einspielen: true, nachts: true };
    }
    const e = this._entwurf;
    const modelle = (d.vorhandene_modelle || []).filter((m) => !d.woerter.some((w) => w.modell_id === m.modell_id));
    return `<ha-card><h2>${esc(this.t('w_neu_titel'))}</h2><div class="klein" style="line-height:1.5">${this.t('w_neu_text')}</div>
<label class="feld">${esc(this.t('w_text'))}</label><input type="text" data-feld="wort" value="${esc(e.wort)}" placeholder="${esc(this.t('w_text_bsp'))}">
<label class="feld">${esc(this.t('w_sprache'))}</label>${this._sprachWahl(e.sprache)}<div class="klein" style="margin-top:4px">${esc(this.t('w_sprache_hilfe'))}</div>
${modelle.length ? `<label class="feld">${esc(this.t('w_vorhanden'))}</label><select data-feld="modell_id"><option value="">${esc(this.t('w_vorhanden_keins'))}</option>${modelle.map((m) => `<option value="${esc(m.modell_id)}" ${m.modell_id === e.modell_id ? 'selected' : ''}>${esc(m.anzeige || m.modell_id)} (${esc(m.modell_id)}.tflite)</option>`).join('')}</select><div class="klein" style="margin-top:4px">${esc(this.t('w_modell_hilfe'))}</div>` : ''}
<label class="feld">${esc(this.t('w_anzeige'))}</label><input type="text" data-feld="anzeige" value="${esc(e.anzeige)}" placeholder="${esc(this.t('w_anzeige_hilfe', { w: e.wort || '…' }))}">
<label class="feld">${esc(this.t('w_farbe'))}</label>${this._farbWahl(e.farbe)}
<h3>${esc(this.t('w_geraete'))}</h3><div class="klein">${esc(this.t('w_geraete_hilfe'))}</div>${this._plaetze(e, null)}
<div class="zeile" style="margin-top:16px"><button class="k haupt" data-a="anlegen"><ha-icon icon="mdi:plus"></ha-icon>${esc(this.t('w_anlegen'))}</button></div></ha-card>`;
  }

  _wortSeite() {
    const d = this._daten, w = d.wort;
    if (!this._entwurf || this._entwurf.id !== w.id) this._entwurf = { ...w.einstellungen, id: w.id, geraete: { ...(w.einstellungen.geraete || {}) } };
    const e = this._entwurf;
    return `<ha-card><h2>${esc(this.t('w_titel'))}</h2>
<label class="feld">${esc(this.t('w_text'))}</label><input type="text" data-feld="wort" value="${esc(e.wort)}">
<label class="feld">${esc(this.t('w_anzeige'))}</label><input type="text" data-feld="anzeige" value="${esc(e.anzeige)}">
<label class="feld">${esc(this.t('w_sprache'))}</label>${this._sprachWahl(e.sprache)}<div class="klein" style="margin-top:4px">${esc(this.t('w_sprache_hilfe'))}</div>
<label class="feld">${esc(this.t('w_farbe'))}</label>${this._farbWahl(e.farbe || this._farbe(this._wortKurz()))}
<h3>${esc(this.t('w_geraete'))}</h3><div class="klein">${esc(this.t('w_geraete_hilfe'))}</div>${this._plaetze(e, w.id)}
<div class="zeile" style="margin-top:16px"><button class="k haupt" data-a="wort_speichern"><ha-icon icon="mdi:content-save-outline"></ha-icon>${esc(this.t('w_speichern'))}</button>${w.aktiv ? `<button class="k" data-a="auswaehlen"><ha-icon icon="mdi:check-circle-outline"></ha-icon>${esc(this.t('w_auswaehlen'))}</button>` : `<span class="klein">${esc(this.t('w_nicht_auswaehlbar'))}</span>`}</div></ha-card>
<ha-card><table>
<tr><td>${esc(this.t('w_modell'))}</td><td><code>/config/custom_wake_words/${esc(w.einstellungen.modell_id)}.tflite</code></td></tr>
<tr><td>${esc(this.t('w_ablage'))}</td><td><code>${esc(w.ordner)}</code> ${esc(this.t('w_backup'))}</td></tr>
<tr><td>${esc(this.t('w_schwelle_jetzt'))}</td><td>${Object.entries(w.schwellen).map(([k, v]) => esc(k) + ' ' + this._zahl(v)).join(' · ') || '–'}</td></tr></table>
<div class="zeile" style="margin-top:14px"><button class="k schlecht" data-a="wort_loeschen"><ha-icon icon="mdi:delete-outline"></ha-icon>${esc(this.t('w_loeschen'))}</button></div></ha-card>`;
  }

  // ---------- Geräte ----------
  _geraete() {
    const d = this._daten;
    if (!d.geraete.length) return `<ha-card><div class="leer"><ha-icon icon="mdi:speaker-off"></ha-icon><p>${esc(this.t('z_geraete_leer'))}</p></div></ha-card>`;
    const wort = (id) => d.woerter.find((w) => w.id === id);
    return d.geraete.map((g) => `<ha-card><div class="zeile weit"><h2 style="margin:0">${esc(g.name)}</h2><span class="klein">${esc(g.knoten)}${g.clips ? ' · ' + esc(this.t('ge_mit_clips')) : ''}${g.zaehler != null ? ' · ' + esc(this.t('ge_zaehler', { n: g.zaehler })) : ''}</span></div>
${g.clips ? '' : `<div class="klein" style="margin-top:8px">${esc(this.t('ge_ohne_clips'))}</div>`}
${g.fehler ? `<div class="hinweis" style="margin-top:10px">${esc(String(g.fehler).slice(0, 160))}<br>${esc(this.t('ge_fehler_hinweis'))}</div>` : ''}
<table style="margin-top:8px"><tr><th></th><th>${esc(this.t('ge_wort'))}</th><th>${esc(this.t('ge_gewaehlt'))}</th><th class="z">${esc(this.t('ge_schwelle'))}</th></tr>
${Object.keys(g.plaetze).map((p) => { const pl = g.plaetze[p], w = wort(pl.wort); return `<tr><td>${esc(this.t('ge_platz', { n: p }))}</td><td>${w ? `<a class="chip" data-reiter="${this._admin ? 'wort' : 'uebersicht'}" data-wort="${esc(w.id)}"><span class="punkt" style="background:${this._farbe(w)}"></span>${esc(w.wort)}</a>` : `<span class="klein">${esc(this.t('ge_nicht'))}</span>`}</td><td>${esc(pl.auswahl || '–')}</td><td class="z">${pl.schwelle != null ? this._zahl(pl.schwelle) : '–'}</td></tr>`; }).join('')}</table></ha-card>`).join('') + `<div class="klein">${esc(this.t('ge_hilfe'))}</div>`;
  }

  // ---------- Einstellungen ----------
  _einstellungen() {
    const d = this._daten, e = d.einstellungen, tr = d.trainer;
    const basis = tr.adresse || location.origin;
    const schl = this._zeigeSchl && tr.schluessel ? tr.schluessel : '••••••';
    const docker = `docker run -d --name wake-word-studio-trainer --restart unless-stopped \\\n  -v wake-word-studio-trainer:/data \\\n  -e HA_URL=${basis} \\\n  -e KEY=${schl} \\\n  ${BILD}`;
    const proxmox = `bash -c "$(curl -fsSL ${PROXMOX})" -- ${basis} ${schl}`;
    if (!this._admin) return `<ha-card><div class="zeile weit"><h2 style="margin:0">${esc(this.t('es_trainer'))}</h2><span class="klein"><span class="punkt ${tr.online ? 'an' : ''}"></span>${esc(tr.online ? this.t('t_trainer_an') : tr.kontakt ? this.t('t_trainer_zuletzt', { z: this._zeit(tr.kontakt) }) : this.t('t_trainer_nie'))}</span></div><p class="klein">${esc(this.t('nur_admin_hinweis'))}</p></ha-card>
<div class="klein">${esc(this.t('es_info', { v: d.version_integration, a: d.ablage }))}</div>`;
    return `<ha-card><h2>${esc(this.t('es_allgemein'))}</h2>
<label class="feld">${esc(this.t('es_zeit'))}</label><input type="time" data-zopt="uhrzeit" value="${esc(String(e.uhrzeit).slice(0, 5))}">
<label class="feld">${esc(this.t('es_erinnerung'))}</label><input type="number" min="0" max="60" data-zopt="erinnerung_tage" value="${e.erinnerung_tage}">
<label class="feld">${esc(this.t('es_aufbewahren'))}</label><input type="number" min="7" max="365" data-zopt="unbewertet_tage" value="${e.unbewertet_tage}">
<label class="feld">${esc(this.t('es_personen'))}</label><input type="text" data-zopt="personen" value="${esc((e.personen || []).join(', '))}" placeholder="${esc(d.personen.join(', '))}"></ha-card>
<ha-card><div class="zeile weit"><h2 style="margin:0">${esc(this.t('es_trainer'))}</h2><span class="klein"><span class="punkt ${tr.online ? 'an' : ''}"></span>${esc(tr.online ? this.t('t_trainer_an') : tr.kontakt ? this.t('t_trainer_zuletzt', { z: this._zeit(tr.kontakt) }) : this.t('t_trainer_nie'))}</span></div>
<p class="klein" style="line-height:1.5">${esc(this.t('es_trainer_text'))}</p>
<p class="klein" style="line-height:1.6">${this.t('es_app', { r: esc(REPO) })}</p>
<p class="klein" style="line-height:1.6">${this.t('es_proxmox')}</p><pre>${esc(proxmox)}</pre>
<p class="klein" style="line-height:1.6">${this.t('es_docker')}</p><pre>${esc(docker)}</pre>
<table><tr><td>${esc(this.t('es_adresse'))}</td><td><code>${esc(basis)}</code></td></tr><tr><td>${esc(this.t('es_schluessel'))}</td><td><div class="schluessel"><code>${this._zeigeSchl ? esc(tr.schluessel) : '••••••••••••'}</code><button class="k leise" data-a="schluessel">${esc(this.t(this._zeigeSchl ? 'es_verbergen' : 'es_zeigen'))}</button><button class="k leise" data-a="schluessel_neu">${esc(this.t('es_neu_schluessel'))}</button></div></td></tr></table>
${tr.info && Object.keys(tr.info).length ? `<div class="klein" style="margin-top:10px">${Object.entries(tr.info).map(([k, v]) => esc(k) + ': ' + esc(v)).join(' · ')}</div>` : ''}</ha-card>
<ha-card><h2>${esc(this.t('es_ablage'))}</h2><p class="klein" style="line-height:1.6">${this.t('es_ablage_text', { a: esc(d.ablage) })}</p></ha-card>
<div class="klein">${esc(this.t('es_info', { v: d.version_integration, a: d.ablage }))}</div>`;
  }

  // ---------- Ereignisse ----------
  async _klick(e) {
    const t = e.target.closest('[data-reiter],[data-a],[data-spielen],[data-urteil],[data-echo],[data-verlauf],[data-seite],[data-recmodus],[data-takespielen],[data-takeweg],[data-farbe]');
    if (!t) return;
    if (t.dataset.reiter) { if (t.dataset.reiter === 'neu') this._entwurf = null; this._gehe(t.dataset.reiter, t.dataset.wort); return; }
    if (t.dataset.spielen) { const zeile = t.closest('.eintrag'); if (zeile) { const alle = [...this.shadowRoot.querySelectorAll('.eintrag:not(.weg)')]; this._aktiv = Math.max(0, alle.indexOf(zeile)); this._markieren(false); } this._spielen(t.dataset.spielen); return; }
    if (t.dataset.urteil) { this._urteilen(t.dataset.id, t.dataset.urteil); return; }
    if (t.dataset.echo !== undefined) { this._filter.echo = t.dataset.echo; this._filter.seite = 0; this._aktiv = 0; this._laden(); return; }
    if (t.dataset.verlauf) { this._filter.verlauf = t.dataset.verlauf; this._filter.seite = 0; this._laden(); return; }
    if (t.dataset.seite) { this._filter.seite = Math.max(0, this._filter.seite + Number(t.dataset.seite)); this._laden(); window.scrollTo(0, 0); return; }
    if (t.dataset.recmodus) { this._rec.modus = t.dataset.recmodus; this._zeichnen(); return; }
    if (t.dataset.takespielen) { const tk = this._rec.takes[Number(t.dataset.takespielen)]; if (tk) this._spielen('take' + t.dataset.takespielen, tk.url); return; }
    if (t.dataset.takeweg) { const [tk] = this._rec.takes.splice(Number(t.dataset.takeweg), 1); if (tk) URL.revokeObjectURL(tk.url); this._recZeichnen(); return; }
    if (t.dataset.farbe) { if (this._entwurf) { this._entwurf.farbe = t.dataset.farbe; this._entwurf._geaendert = true; } this.shadowRoot.querySelectorAll('[data-farbe]').forEach((b) => b.classList.toggle('an', b === t)); return; }
    const a = t.dataset.a;
    try {
      if (a === 'neu') this._laden();
      else if (a === 'datei') this.shadowRoot.getElementById('datei').click();
      else if (a === 'holen') { t.disabled = true; await this._api('POST', 'aktion', { aktion: 'jetzt_holen' }); this._laden(); }
      else if (a === 'trainieren') { await this._api('POST', 'aktion', { aktion: 'training_starten', wort: this._wortId }); this._laden(); }
      else if (a === 'abbrechen') { if (confirm(this.t('t_abbrechen_frage'))) { await this._api('POST', 'aktion', { aktion: 'training_abbrechen', wort: this._wortId }); this._laden(); } }
      else if (a === 'alle_vorschlaege') {
        const ids = ((this._liste && this._liste.eintraege) || []).filter((x) => x.vorschlag).map((x) => x.id);
        if (confirm(this.t('pr_alle_frage', { n: ids.length }))) { await this._api('POST', 'aktion', { aktion: 'vorschlaege_uebernehmen', wort: this._wortId, ids, person: this._person }); this._laden(); }
      } else if (a === 'schwelle') {
        const w = Number(t.dataset.wert);
        if (confirm(this.t('q_schwelle_frage', { w: this._zahl(w) }))) { await this._api('POST', 'aktion', { aktion: 'schwelle', wort: this._wortId, wert: w }); this._meldung(this.t('q_schwelle_ok')); this._laden(); }
      } else if (a === 'einspielen') {
        const nr = Number(t.dataset.nr);
        if (confirm(this.t('q_einspielen_frage', { n: nr }))) { await this._api('POST', 'aktion', { aktion: 'einspielen', wort: this._wortId, nr }); this._meldung(this.t('q_wird', { n: nr })); this._laden(); }
      } else if (a === 'schluessel') { this._zeigeSchl = !this._zeigeSchl; this._zeichnen(); }
      else if (a === 'schluessel_neu') { if (confirm(this.t('es_neu_frage'))) { await this._api('POST', 'aktion', { aktion: 'schluessel_neu' }); this._zeigeSchl = true; this._laden(); } }
      else if (a === 'rec') { if (this._rec.an) this._recStopp(); else await this._recStart(); }
      else if (a === 'recspeichern') { t.disabled = true; await this._recSpeichern(); }
      else if (a === 'recverwerfen') { this._rec.takes.forEach((x) => URL.revokeObjectURL(x.url)); this._rec.takes = []; this._recZeichnen(); }
      else if (a === 'anlegen') {
        const e2 = this._entwurfDaten();
        if (!String(e2.wort || '').trim()) { this._meldung(this.t('w_fehlt')); return; }
        t.disabled = true;
        const r = await this._api('POST', 'aktion', { aktion: 'wort_neu', einstellungen: e2 });
        this._entwurf = null; this._gehe('uebersicht', r.id);
      } else if (a === 'wort_speichern') {
        const e2 = this._entwurfDaten(); delete e2.modell_id;
        if (!String(e2.wort || '').trim()) { this._meldung(this.t('w_fehlt')); return; }
        await this._api('POST', 'aktion', { aktion: 'wort_aendern', wort: this._wortId, einstellungen: e2 });
        this._entwurf = null; this._meldung(this.t('gespeichert')); this._laden();
      } else if (a === 'auswaehlen') {
        const r = await this._api('POST', 'aktion', { aktion: 'auswaehlen', wort: this._wortId });
        this._meldung(this.t('w_ausgewaehlt', { n: (r.gesetzt || []).length })); this._laden();
      } else if (a === 'wort_loeschen') {
        const name = this._wortName();
        if (!confirm(this.t('w_loeschen_frage', { w: name }))) return;
        const dateien = confirm(this.t('w_dateien_frage', { w: name }));
        await this._api('POST', 'aktion', { aktion: 'wort_loeschen', wort: this._wortId, dateien });
        this._merk('wort', ''); this._wortId = null; this._entwurf = null; this._meldung(this.t('w_geloescht')); this._gehe('zentrale');
      }
    } catch (err) { this._meldung(this.t('ging_nicht', { f: this._fehlerText(err) })); }
  }

  _entwurfDaten() {
    const e = { ...this._entwurf };
    delete e.id; delete e._geaendert;
    for (const k of Object.keys(e)) if (!['wort', 'anzeige', 'sprache', 'geraete', 'modell_id', 'farbe', 'automatisch_einspielen', 'nachts'].includes(k)) delete e[k];
    return e;
  }

  _eingabe(e) {
    const t = e.target;
    if (t.dataset.feld && this._entwurf && t.tagName === 'INPUT') {
      this._entwurf[t.dataset.feld] = t.value; this._entwurf._geaendert = true;
      if (t.dataset.feld === 'wort' && !this._entwurf.id) { const an = this.shadowRoot.querySelector('input[data-feld="anzeige"]'); if (an) an.placeholder = this.t('w_anzeige_hilfe', { w: t.value || '…' }); }
    }
  }

  async _aenderung(e) {
    const t = e.target;
    if (t.id === 'datei') { this._hochladen([...t.files]); t.value = ''; return; }
    if (t.id === 'autoplay') { this._autoplay = t.checked; this._merk('autoplay', t.checked ? '1' : '0'); return; }
    if (t.id === 'recnotiz') { this._rec.notiz = t.value; return; }
    if (t.dataset.feld && this._entwurf) { this._entwurf[t.dataset.feld] = t.value; this._entwurf._geaendert = true; return; }
    if (t.dataset.platz !== undefined && this._entwurf) {
      const g = { ...(this._entwurf.geraete || {}) };
      if (t.value) g[t.dataset.platz] = t.value; else delete g[t.dataset.platz];
      this._entwurf.geraete = g; this._entwurf._geaendert = true; return;
    }
    if (t.dataset.person !== undefined) {
      this._person = t.value; this._merk('person', t.value);
      const id = t.dataset.person;
      if (id && !['hoch', 'rec'].includes(id) && this._reiter === 'verlauf') await this._api('POST', 'urteil', { wort: this._wortId, ids: [id], person: t.value });
      if (this._reiter === 'pruefen') this.shadowRoot.querySelectorAll('select[data-person]').forEach((s) => { s.value = t.value; });
      return;
    }
    try {
      if (t.dataset.wopt) {
        await this._api('POST', 'aktion', { aktion: 'wort_aendern', wort: this._wortId, einstellungen: { [t.dataset.wopt]: t.checked } });
        this._meldung(this.t('gespeichert'));
      } else if (t.dataset.zopt) {
        let wert = t.type === 'number' ? Number(t.value) : t.value;
        if (t.dataset.zopt === 'personen') wert = t.value.split(',').map((x) => x.trim()).filter(Boolean);
        await this._api('POST', 'aktion', { aktion: 'einstellungen', einstellungen: { [t.dataset.zopt]: wert } });
        this._meldung(this.t('gespeichert'));
      }
    } catch (err) { this._meldung(this.t('ging_nicht', { f: this._fehlerText(err) })); }
  }

  _meldung(text) {
    this.dispatchEvent(new CustomEvent('hass-notification', { detail: { message: text }, bubbles: true, composed: true }));
  }
}

if (!customElements.get('sprachmodell-panel')) customElements.define('sprachmodell-panel', SprachmodellPanel);
console.info('%c Wake Word Studio ' + VERSION + ' ', 'background:#6d5dfc;color:#fff;border-radius:3px');
