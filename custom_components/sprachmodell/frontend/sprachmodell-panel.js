// Sprachmodell – Seite in der Seitenleiste (wie VisionState, nur für Sprache)
// Reiter: Übersicht · Prüfen · Verlauf · Hochladen · Training · Qualität · Einstellungen
// Kein Abfragen im Takt: neu geladen wird nur, wenn sich ein Sprachmodell-Sensor ändert.
(() => {
  const VERSION = '0.1.0';
  const REITER = [
    ['uebersicht', 'Übersicht', 'mdi:view-dashboard-outline'],
    ['pruefen', 'Prüfen', 'mdi:playlist-check'],
    ['verlauf', 'Verlauf', 'mdi:history'],
    ['hochladen', 'Hochladen', 'mdi:upload-outline'],
    ['training', 'Training', 'mdi:school-outline'],
    ['qualitaet', 'Qualität', 'mdi:chart-bell-curve-cumulative'],
    ['einstellungen', 'Einstellungen', 'mdi:cog-outline'],
  ];
  const ART = {
    wake: ['Aufgewacht', 'mdi:microphone-message'],
    mistake: ['Aufgewacht, dann abgebrochen', 'mdi:microphone-off'],
    nearmiss: ['Knapp nicht erkannt', 'mdi:microphone-question'],
    noise: ['Geräusch', 'mdi:waveform'],
    aufnahme: ['Hochgeladen', 'mdi:upload'],
  };
  const PHASE = {
    bereit: 'Bereit', wartet: 'Wartet auf den Trainer', vorbereiten: 'Bereitet vor', daten: 'Holt Aufnahmen',
    merkmale: 'Berechnet Merkmale', training: 'Trainiert', test: 'Testet ehrlich', fertig: 'Fertig', fehler: 'Fehler',
  };
  const URTEIL = { wort: 'Wort gesagt', kein_wort: 'Nicht gesagt', verworfen: 'Unbrauchbar' };

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = (x, n = 0) => (typeof x === 'number' ? (x * 100).toFixed(n).replace('.', ',') + ' %' : '–');
  const komma = (x, n = 2) => (typeof x === 'number' ? x.toFixed(n).replace('.', ',') : '–');
  const zeit = (iso) => {
    if (!iso) return '–';
    const d = new Date(iso), s = (Date.now() - d) / 1000;
    if (s < 60) return 'gerade eben';
    if (s < 3600) return 'vor ' + Math.round(s / 60) + ' Min.';
    if (s < 86400) return 'vor ' + Math.round(s / 3600) + ' Std.';
    if (s < 7 * 86400) return d.toLocaleDateString('de-DE', { weekday: 'short' }) + ' ' + d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' }) + ' ' + d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  };
  const datum = (iso) => (iso ? new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–');

  const STIL = `
:host{display:block;min-height:100vh;background:var(--primary-background-color);color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,inherit)}
.kopf{position:sticky;top:0;z-index:3;display:flex;align-items:center;gap:4px;height:var(--header-height,56px);padding:0 8px 0 4px;background:var(--app-header-background-color,var(--primary-background-color));color:var(--app-header-text-color,var(--primary-text-color));border-bottom:1px solid var(--divider-color)}
.kopf h1{font-size:20px;font-weight:400;margin:0 0 0 8px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.reiter{position:sticky;top:var(--header-height,56px);z-index:2;display:flex;gap:4px;overflow-x:auto;padding:8px 12px;background:var(--app-header-background-color,var(--primary-background-color));border-bottom:1px solid var(--divider-color);scrollbar-width:none}
.reiter::-webkit-scrollbar{display:none}
.reiter a{display:flex;align-items:center;gap:6px;padding:7px 12px;border-radius:18px;color:var(--secondary-text-color);text-decoration:none;font-size:14px;white-space:nowrap;cursor:pointer}
.reiter a.an{background:rgba(var(--rgb-primary-color,3,169,244),.16);color:var(--primary-color)}
.reiter a .zahl{min-width:18px;padding:0 5px;border-radius:9px;background:var(--warning-color,#ff9800);color:#fff;font-size:11px;line-height:18px;text-align:center}
.reiter ha-icon{--mdc-icon-size:18px}
main{max-width:1100px;margin:0 auto;padding:16px 12px 80px}
ha-card{display:block;padding:16px;margin-bottom:12px}
h2{font-size:17px;font-weight:500;margin:0 0 12px}
h3{font-size:14px;font-weight:500;margin:14px 0 6px;color:var(--secondary-text-color)}
.raster{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin-bottom:12px}
.raster ha-card{margin:0}
.kachel{cursor:pointer}
.kachel .wert{font-size:30px;font-weight:300;margin:4px 0}
.kachel .klein,.klein{font-size:13px;color:var(--secondary-text-color)}
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
.chip{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;border-radius:16px;font-size:13px;background:rgba(var(--rgb-primary-text-color,0,0,0),.06);cursor:pointer;border:0;color:inherit;font-family:inherit}
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
select,input[type=time],input[type=text]{font:inherit;font-size:14px;padding:7px 10px;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color)}
.leer{text-align:center;padding:40px 16px;color:var(--secondary-text-color)}
.leer ha-icon{--mdc-icon-size:48px;opacity:.5}
.fortschritt{height:10px;border-radius:5px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden;margin:10px 0}
.fortschritt i{display:block;height:100%;background:var(--primary-color);transition:width .6s}
.laeuft .fortschritt i{background-image:linear-gradient(90deg,transparent 0,rgba(255,255,255,.25) 50%,transparent 100%);background-size:200% 100%;animation:schimmer 2.5s linear infinite}
@keyframes schimmer{to{background-position:-200% 0}}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--divider-color)}
th{font-weight:500;color:var(--secondary-text-color);font-size:12px}
td.z,th.z{text-align:right}
.gruen{color:var(--success-color,#4caf50)}.rot{color:var(--error-color,#f44336)}.gelb{color:var(--warning-color,#ff9800)}
.punkt{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:var(--disabled-color,#999)}
.punkt.an{background:var(--success-color,#4caf50)}
.abwurf{border:2px dashed var(--divider-color);border-radius:14px;padding:30px 16px;text-align:center;cursor:pointer}
.abwurf.ueber{border-color:var(--primary-color);background:rgba(var(--rgb-primary-color,3,169,244),.06)}
.abwurf ha-icon{--mdc-icon-size:42px;color:var(--primary-color)}
code{font-size:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);padding:2px 6px;border-radius:5px;word-break:break-all}
.schluessel{display:flex;gap:6px;align-items:center}
.hinweis{padding:10px 12px;border-radius:10px;background:rgba(var(--rgb-warning-color,255,152,0),.12);font-size:14px;margin-bottom:12px}
svg.vert text{font-size:10px;fill:var(--secondary-text-color)}
@media (max-width:600px){main{padding:12px 8px 80px}.eintrag{grid-template-columns:44px 1fr;gap:10px;padding:10px}.spielen{width:44px;height:44px}button.k kbd{display:none}}
`;

  class SprachmodellPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._daten = null;
      this._liste = null;
      this._filter = { echo: '', verlauf: 'bewertet', seite: 0 };
      this._person = localStorage.getItem('sprachmodell.person') || '';
      this._autoplay = localStorage.getItem('sprachmodell.autoplay') !== '0';
      this._blobs = new Map();
      this._audio = new Audio();
      this._audio.addEventListener('timeupdate', () => this._ring());
      this._audio.addEventListener('ended', () => { this._spielt = null; this._ring(true); });
      this._aktiv = 0;
      this._stempel = '';
      this._taste = (e) => this._tastatur(e);
    }

    set hass(h) {
      const erstes = !this._hass;
      this._hass = h;
      if (erstes) { this._aufbauen(); this._laden(); return; }
      // Neu laden, wenn sich ein Sensor der Integration geändert hat
      const st = Object.values(h.entities || {}).filter((e) => e.platform === 'sprachmodell')
        .map((e) => h.states[e.entity_id]).filter(Boolean).map((s) => s.last_updated + (s.attributes.stand ?? '') + (s.attributes.prozent ?? '')).join('|');
      if (st !== this._stempel) { const war = this._stempel; this._stempel = st; if (war) this._laden(); }
      const m = this.shadowRoot.querySelector('ha-menu-button'); if (m) { m.hass = h; }
    }
    get hass() { return this._hass; }
    set narrow(n) { this._narrow = n; const m = this.shadowRoot.querySelector('ha-menu-button'); if (m) m.narrow = n; }
    set route(r) { this._route = r; const neu = ((r && r.path) || '').replace(/^\//, '').split('/')[0] || 'uebersicht'; if (neu !== this._reiter) { this._reiter = neu; if (this._hass) { this._kopfZeichnen(); this._laden(); } } }
    set panel(p) { this._panel = p; }

    connectedCallback() { window.addEventListener('keydown', this._taste); }
    disconnectedCallback() { window.removeEventListener('keydown', this._taste); this._audio.pause(); }

    _gehe(reiter) {
      history.pushState(null, '', '/sprachmodell/' + reiter);
      window.dispatchEvent(new CustomEvent('location-changed'));
    }

    _aufbauen() {
      this.shadowRoot.innerHTML = `<style>${STIL}</style>
<div class="kopf"><ha-menu-button></ha-menu-button><h1>Sprachmodell</h1><span class="klein" id="kopfinfo"></span></div>
<nav class="reiter"></nav><main></main><input type="file" id="datei" accept=".zip,application/zip" hidden multiple>`;
      const m = this.shadowRoot.querySelector('ha-menu-button'); m.hass = this._hass; m.narrow = this._narrow;
      this._reiter = this._reiter || 'uebersicht';
      this.shadowRoot.addEventListener('click', (e) => this._klick(e));
      this.shadowRoot.addEventListener('change', (e) => this._aenderung(e));
      const main = this.shadowRoot.querySelector('main');
      main.addEventListener('dragover', (e) => { const z = e.target.closest('.abwurf'); if (z) { e.preventDefault(); z.classList.add('ueber'); } });
      main.addEventListener('dragleave', (e) => { const z = e.target.closest('.abwurf'); if (z) z.classList.remove('ueber'); });
      main.addEventListener('drop', (e) => { const z = e.target.closest('.abwurf'); if (z) { e.preventDefault(); z.classList.remove('ueber'); this._hochladen([...e.dataTransfer.files]); } });
      this._kopfZeichnen();
    }

    _kopfZeichnen() {
      const offen = this._daten ? this._daten.statistik.offen : 0;
      const nav = this.shadowRoot.querySelector('nav'); if (!nav) return;
      nav.innerHTML = REITER.map(([id, t, i]) => `<a data-reiter="${id}" class="${id === this._reiter ? 'an' : ''}"><ha-icon icon="${i}"></ha-icon>${t}${id === 'pruefen' && offen ? `<span class="zahl">${offen}</span>` : ''}</a>`).join('');
      const info = this.shadowRoot.getElementById('kopfinfo');
      if (info && this._daten) {
        const t = this._daten.training, v = this._daten.aktiv;
        info.textContent = (v ? 'v' + v + ' aktiv' : '') + (t && !['bereit', 'fertig'].includes(t.phase) ? ' · ' + (PHASE[t.phase] || t.phase) + (t.prozent != null ? ' ' + Math.round(t.prozent) + ' %' : '') : '');
      }
    }

    async _api(methode, pfad, daten) { return this._hass.callApi(methode, 'sprachmodell/' + pfad, daten); }

    async _laden() {
      try {
        this._daten = await this._api('GET', 'daten');
        if (this._reiter === 'pruefen') this._liste = await this._api('GET', 'liste?filter=offen' + (this._filter.echo ? '&echo=' + encodeURIComponent(this._filter.echo) : ''));
        if (this._reiter === 'verlauf') this._liste = await this._api('GET', `liste?filter=${this._filter.verlauf}&seite=${this._filter.seite}` + (this._filter.echo ? '&echo=' + encodeURIComponent(this._filter.echo) : ''));
        this._fehler = null;
      } catch (e) { this._fehler = (e && (e.body && e.body.message)) || e.message || String(e); }
      this._kopfZeichnen();
      this._zeichnen();
    }

    _zeichnen() {
      const main = this.shadowRoot.querySelector('main'); if (!main) return;
      if (this._fehler) { main.innerHTML = `<ha-card><div class="leer"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><p>${esc(this._fehler)}</p><button class="k" data-a="neu">Neu laden</button></div></ha-card>`; return; }
      if (!this._daten) { main.innerHTML = '<div class="leer">Lädt …</div>'; return; }
      const f = { uebersicht: this._uebersicht, pruefen: this._pruefen, verlauf: this._verlauf, hochladen: this._hochladenSeite, training: this._training, qualitaet: this._qualitaet, einstellungen: this._einstellungen }[this._reiter] || this._uebersicht;
      const scroll = window.scrollY;
      main.innerHTML = f.call(this);
      if (this._reiter === 'pruefen') this._markieren(false);
      window.scrollTo(0, scroll);
    }

    // ---------- Übersicht ----------
    _uebersicht() {
      const d = this._daten, s = d.statistik, t = d.training, v = d.versionen.find((x) => x.nr === d.aktiv), b = (v && v.bericht && v.bericht.neu) || {};
      const echos = Object.values(d.echos || {});
      const laeuft = t && !['bereit', 'fertig', 'fehler'].includes(t.phase);
      return `
<div class="raster">
  <ha-card class="kachel" data-reiter="pruefen"><div class="klein"><ha-icon icon="mdi:playlist-check"></ha-icon> Warten auf Prüfung</div><div class="wert ${s.offen ? 'gelb' : ''}">${s.offen}</div><div class="klein">${s.offen ? 'älteste ' + zeit(s.aeltestes_offen) : 'Alles geprüft'}</div></ha-card>
  <ha-card class="kachel" data-reiter="qualitaet"><div class="klein"><ha-icon icon="mdi:bullseye-arrow"></ha-icon> Aktive Version</div><div class="wert">${v ? 'v' + v.nr : '–'}</div><div class="klein">${b.trefferquote != null ? 'erkennt ' + pct(b.trefferquote) + ' · ' + komma(b.fehlausloeser_pro_stunde, 1) + ' Fehlauslöser/Std.' : v ? 'eingespielt ' + zeit(v.eingespielt) : 'Noch keine Version'}</div></ha-card>
  <ha-card class="kachel ${laeuft ? 'laeuft' : ''}" data-reiter="training"><div class="klein"><ha-icon icon="mdi:school-outline"></ha-icon> Training</div><div class="wert" style="font-size:22px">${esc(PHASE[t.phase] || t.phase)}</div>${laeuft && t.prozent != null ? `<div class="fortschritt"><i style="width:${t.prozent}%"></i></div>` : ''}<div class="klein">${laeuft ? esc(t.schritt || '') : d.trainer.online ? '<span class="punkt an"></span>Trainer verbunden' : '<span class="punkt"></span>Trainer nicht verbunden'}${!laeuft && d.neu_seit_lauf > 0 ? ' · ' + d.neu_seit_lauf + ' neue Bewertungen' : ''}</div></ha-card>
  <ha-card class="kachel" data-reiter="einstellungen"><div class="klein"><ha-icon icon="mdi:speaker-wireless"></ha-icon> Echos</div><div class="wert">${echos.length}</div><div class="klein">${echos.map(esc).join(', ') || 'Keiner mit TECHO5 gefunden'}</div></ha-card>
</div>
<ha-card><h2>Im Alltag</h2>${this._alltag()}</ha-card>
<ha-card><h2>So funktioniert es</h2><div class="klein" style="line-height:1.6">
1. Die Echos heben bei jedem Aufwachen und jedem knappen Fast-Aufwachen ein paar Sekunden Ton auf. Sie landen unter <b>Prüfen</b>.<br>
2. Anhören und sagen, ob „${esc(d.einstellungen.anzeige.replace(/ \(.*/, ''))}“ gesagt wurde. Der Vorschlag hilft – meistens reicht ein Tipp.<br>
3. Neue Aufnahmen von der Setup-Seite eines Echos lädst du unter <b>Hochladen</b> hoch.<br>
4. ${d.einstellungen.nachts ? 'Nachts um ' + esc(d.einstellungen.uhrzeit.slice(0, 5)) + ' trainiert' : 'Auf Knopfdruck trainiert'} der Trainer eine neue Version und testet sie ehrlich gegen Aufnahmen, die er nie gelernt hat. ${d.einstellungen.automatisch_einspielen ? 'Ist sie besser, kommt sie von selbst auf alle Echos.' : 'Ob sie eingespielt wird, entscheidest du unter Qualität.'}
</div></ha-card>`;
    }

    _alltag() {
      const a = this._daten.statistik.alltag;
      if (!a.aufgewacht && !a.verpasst) return '<div class="klein">Noch keine geprüften Aufnahmen der Echos.</div>';
      const quote = a.aufgewacht ? a.richtig / a.aufgewacht : null;
      return `<div class="raster" style="margin:0"><div><div class="klein">Richtig aufgewacht</div><div class="wert gruen" style="font-size:24px">${a.richtig}</div></div>
<div><div class="klein">Fälschlich aufgewacht</div><div class="wert ${a.falsch ? 'rot' : ''}" style="font-size:24px">${a.falsch}</div></div>
<div><div class="klein">Verpasst (gesagt, nicht erkannt)</div><div class="wert ${a.verpasst ? 'gelb' : ''}" style="font-size:24px">${a.verpasst}</div></div>
<div><div class="klein">Genauigkeit beim Aufwachen</div><div class="wert" style="font-size:24px">${quote == null ? '–' : pct(quote)}</div></div></div>`;
    }

    // ---------- Prüfen ----------
    _personWahl(wert, id) {
      const p = this._daten.personen;
      return `<select data-person="${id || ''}" title="Wer hat gesprochen?"><option value="">Person: unbekannt</option>${p.map((n) => `<option ${n === wert ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>`;
    }

    _pruefen() {
      const l = this._liste || { eintraege: [], gesamt: 0 }, s = this._daten.statistik;
      const echoChips = Object.entries(s.offen_je_echo || {}).map(([e, n]) => `<button class="chip ${this._filter.echo === e ? 'an' : ''}" data-echo="${esc(e)}">${esc(e)} · ${n}</button>`).join('');
      const mitVorschlag = l.eintraege.filter((a) => a.vorschlag).length;
      if (!l.gesamt) return `<ha-card><div class="leer"><ha-icon icon="mdi:check-all"></ha-icon><p>Nichts zu prüfen.</p><p class="klein">Neue Aufnahmen kommen, sobald ein Echo aufwacht oder knapp nicht aufwacht.</p><button class="k" data-a="holen"><ha-icon icon="mdi:download-outline"></ha-icon>Jetzt bei den Echos nachsehen</button></div></ha-card>`;
      return `
<div class="zeile weit" style="margin-bottom:10px"><div class="zeile"><button class="chip ${!this._filter.echo ? 'an' : ''}" data-echo="">Alle Echos · ${s.offen}</button>${echoChips}</div>
<div class="zeile"><label class="klein"><input type="checkbox" id="autoplay" ${this._autoplay ? 'checked' : ''}> Nächste gleich abspielen</label>${mitVorschlag ? `<button class="k" data-a="alle_vorschlaege"><ha-icon icon="mdi:check-all"></ha-icon>Alle ${mitVorschlag} Vorschläge übernehmen</button>` : ''}</div></div>
<div class="klein" style="margin-bottom:10px">Tasten: <b>Leertaste</b> abspielen · <b>1</b> Wort gesagt · <b>2</b> nicht gesagt · <b>0</b> unbrauchbar · <b>↑ ↓</b> wechseln</div>
<div class="liste">${l.eintraege.map((a, i) => this._eintrag(a, i, true)).join('')}</div>
${l.gesamt > l.eintraege.length ? `<div class="leer klein">Noch ${l.gesamt - l.eintraege.length} weitere – erscheinen, sobald diese geprüft sind.</div>` : ''}`;
    }

    _eintrag(a, i, pruefen) {
      const art = ART[a.art] || [a.art || '', 'mdi:waveform'];
      const sc = typeof a.score === 'number' ? a.score : null, cu = typeof a.cutoff === 'number' ? a.cutoff : null;
      const wort = this._daten.einstellungen.anzeige.replace(/ \(.*/, '');
      const urteil = a.urteil ? `<span class="${a.urteil === 'wort' ? 'gruen' : a.urteil === 'kein_wort' ? 'rot' : ''}">${URTEIL[a.urteil]}</span>` : '';
      return `<div class="eintrag" tabindex="-1" data-id="${esc(a.id)}" data-i="${i}">
<button class="spielen" data-spielen="${esc(a.id)}" title="Abspielen"><svg viewBox="0 0 52 52"><circle cx="26" cy="26" r="25"></circle></svg><ha-icon icon="mdi:play"></ha-icon></button>
<div><div class="zeile weit"><span class="titel"><ha-icon icon="${art[1]}" style="--mdc-icon-size:16px"></ha-icon> ${esc(art[0])}${a.echo ? ' · ' + esc(a.echo) : ''}</span><span class="klein">${zeit(a.zeit)}${a.dauer ? ' · ' + komma(a.dauer, 1) + ' s' : ''}${a.test ? ' · Test' : ''}</span></div>
${sc != null ? `<div class="balken" title="Wert ${komma(sc)}${cu != null ? ' · Schwelle ' + komma(cu) : ''}"><i style="width:${Math.min(100, sc * 100)}%"></i>${cu != null ? `<b style="left:${cu * 100}%"></b>` : ''}</div><div class="klein">Wert ${komma(sc)}${cu != null ? ' · Schwelle ' + komma(cu) : ''}</div>` : a.notiz ? `<div class="klein">${esc(a.notiz)}</div>` : ''}
${pruefen && a.vorschlag ? `<div class="vorschlag">Vorschlag: <strong>${a.vorschlag === 'wort' ? '„' + esc(wort) + '“ gesagt' : 'nicht gesagt'}</strong> – ${esc(a.grund || '')}</div>` : !pruefen ? `<div class="vorschlag">${urteil}${a.person ? ' · ' + esc(a.person) : ''}${a.quelle === 'hochgeladen' ? ' · hochgeladen' : ''}</div>` : ''}
<div class="knoepfe">
<button class="k gut" data-urteil="wort" data-id="${esc(a.id)}"><ha-icon icon="mdi:check"></ha-icon>${pruefen ? '„' + esc(wort) + '“ gesagt' : 'Wort'} <kbd>1</kbd></button>
<button class="k schlecht" data-urteil="kein_wort" data-id="${esc(a.id)}"><ha-icon icon="mdi:close"></ha-icon>Nicht gesagt <kbd>2</kbd></button>
<button class="k leise" data-urteil="verworfen" data-id="${esc(a.id)}" title="Zu leise, kaputt oder unklar – wird gelöscht"><ha-icon icon="mdi:delete-outline"></ha-icon>Unbrauchbar <kbd>0</kbd></button>
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
      if (this._blobs.has(id)) return this._blobs.get(id);
      const r = await this._hass.fetchWithAuth('/api/sprachmodell/audio/' + encodeURIComponent(id));
      if (!r.ok) throw new Error('Aufnahme nicht gefunden');
      const url = URL.createObjectURL(await r.blob());
      this._blobs.set(id, url);
      if (this._blobs.size > 80) { const [k, v] = this._blobs.entries().next().value; URL.revokeObjectURL(v); this._blobs.delete(k); }
      return url;
    }

    async _spielen(id) {
      try {
        if (this._spielt === id && !this._audio.paused) { this._audio.pause(); this._spielt = null; this._ring(true); return; }
        this._audio.pause(); this._ring(true);
        this._audio.src = await this._blob(id);
        this._spielt = id;
        await this._audio.play();
      } catch (e) { this._meldung('Abspielen ging nicht: ' + e.message); }
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
      try {
        await this._api('POST', 'urteil', { ids: [id], urteil, person });
      } catch (e) { this._meldung('Speichern ging nicht: ' + (e.body?.message || e.message)); return; }
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

    // ---------- Verlauf ----------
    _verlauf() {
      const l = this._liste || { eintraege: [], gesamt: 0, seiten: 1 };
      const filter = [['bewertet', 'Bewertet'], ['hochgeladen', 'Hochgeladen'], ['test', 'Testsatz'], ['alle', 'Alle']];
      return `<div class="zeile" style="margin-bottom:10px">${filter.map(([k, t]) => `<button class="chip ${this._filter.verlauf === k ? 'an' : ''}" data-verlauf="${k}">${t}</button>`).join('')}<span class="klein">${l.gesamt} Aufnahmen</span></div>
<div class="klein" style="margin-bottom:10px">Falsch getippt? Hier einfach neu bewerten. „Testsatz“ = Aufnahmen, die der Trainer nie lernt, nur für den ehrlichen Test (jede fünfte).</div>
${l.gesamt ? `<div class="liste">${l.eintraege.map((a, i) => this._eintrag(a, i, false)).join('')}</div>` : '<ha-card><div class="leer">Keine Aufnahmen.</div></ha-card>'}
${l.seiten > 1 ? `<div class="zeile" style="justify-content:center;margin-top:12px"><button class="k" data-seite="-1" ${l.seite ? '' : 'disabled'}>Zurück</button><span class="klein">Seite ${l.seite + 1} von ${l.seiten}</span><button class="k" data-seite="1" ${l.seite + 1 < l.seiten ? '' : 'disabled'}>Weiter</button></div>` : ''}`;
    }

    // ---------- Hochladen ----------
    _hochladenSeite() {
      const s = this._daten.statistik;
      return `<ha-card><h2>Aufnahmen hochladen</h2>
<div class="zeile" style="margin-bottom:12px"><span class="klein">Wer spricht?</span>${this._personWahl(this._person, 'hoch')}</div>
<div class="abwurf" data-a="datei"><ha-icon icon="mdi:folder-zip-outline"></ha-icon><p><b>Zip-Datei hierher ziehen</b> oder antippen</p><p class="klein">Ordner <code>word</code> = das Wort, <code>not_word</code> = Gegenbeispiele (so lädt die Setup-Seite sie herunter). Doppelte werden erkannt.</p></div>
<div id="hochergebnis" style="margin-top:12px">${this._hochErgebnis || ''}</div></ha-card>
<ha-card><h2>So entsteht die Zip-Datei</h2><div class="klein" style="line-height:1.6">
1. Am Echo mit Setup-Seite (Küche) den Schalter <b>Record takes of a word</b> einschalten.<br>
2. Setup-Seite im Browser öffnen → <b>Voice</b> → ganz unten <b>Record takes of a word</b>, Wort eintragen, <b>Record</b>.<br>
3. Bis zu 2 Minuten alle 2–3 Sekunden das Wort sagen: nah, weit, leise, laut, mit und ohne Musik.<br>
4. Für Gegenbeispiele bei der Aufnahme <b>not_…</b> wählen und Ähnliches sagen (Алина, Лиса, Alexa, normale Sätze).<br>
5. <b>Zip herunterladen</b> und hier hochladen. Danach den Schalter wieder aus.
</div></ha-card>
<ha-card><h2>Bisher</h2><table><tr><th>Person</th><th class="z">Wort</th><th class="z">Gegenbeispiele</th></tr>${Object.entries(s.personen).map(([p, n]) => `<tr><td>${esc(p)}</td><td class="z">${n.wort}</td><td class="z">${n.kein_wort}</td></tr>`).join('') || '<tr><td colspan="3" class="klein">Noch nichts.</td></tr>'}</table></ha-card>`;
    }

    async _hochladen(dateien) {
      const zips = dateien.filter((f) => /\.zip$/i.test(f.name));
      if (!zips.length) { this._meldung('Bitte eine Zip-Datei wählen.'); return; }
      const sel = this.shadowRoot.querySelector('select[data-person="hoch"]');
      const person = sel ? sel.value : '';
      const box = this.shadowRoot.getElementById('hochergebnis');
      let text = '';
      for (const f of zips) {
        if (box) box.innerHTML = text + `<div class="laeuft"><div class="klein">${esc(f.name)} wird hochgeladen …</div><div class="fortschritt"><i style="width:100%"></i></div></div>`;
        const fd = new FormData(); fd.append('person', person); fd.append('datei', f, f.name);
        try {
          const r = await this._hass.fetchWithAuth('/api/sprachmodell/hochladen', { method: 'POST', body: fd });
          const j = await r.json();
          if (!r.ok) throw new Error(j.message || r.statusText);
          text += `<div class="hinweis" style="background:rgba(var(--rgb-success-color,76,175,80),.14)"><b>${esc(f.name)}</b>: ${j.wort} × Wort, ${j.kein_wort} Gegenbeispiele${j.doppelt ? ', ' + j.doppelt + ' schon vorhanden' : ''}${j.kaputt ? ', ' + j.kaputt + ' unlesbar' : ''}${person ? ' · ' + esc(person) : ''}</div>`;
        } catch (e) { text += `<div class="hinweis"><b>${esc(f.name)}</b>: ${esc(e.message)}</div>`; }
      }
      this._hochErgebnis = text;
      if (box) box.innerHTML = text;
      this._laden();
    }

    // ---------- Training ----------
    _training() {
      const d = this._daten, t = d.training, e = d.einstellungen;
      const laeuft = !['bereit', 'fertig', 'fehler'].includes(t.phase);
      const kurz = (b) => (b ? `${pct(b.trefferquote)} · ${komma(b.fehlausloeser_pro_stunde, 1)}/Std.` : '–');
      return `<ha-card class="${laeuft ? 'laeuft' : ''}"><div class="zeile weit"><h2 style="margin:0">${esc(PHASE[t.phase] || t.phase)}</h2><span class="klein"><span class="punkt ${d.trainer.online ? 'an' : ''}"></span>${d.trainer.online ? 'Trainer verbunden' : d.trainer.kontakt ? 'Trainer zuletzt ' + zeit(d.trainer.kontakt) : 'Trainer noch nie verbunden'}</span></div>
${laeuft ? `<div class="fortschritt"><i style="width:${t.prozent ?? 3}%"></i></div><div class="zeile weit klein"><span>${esc(t.schritt || '')}</span><span>${t.prozent != null ? Math.round(t.prozent) + ' %' : ''}${t.restzeit_min != null ? ' · noch etwa ' + (t.restzeit_min >= 90 ? komma(t.restzeit_min / 60, 1) + ' Std.' : Math.round(t.restzeit_min) + ' Min.') : ''}</span></div>${t.start ? `<div class="klein">Gestartet ${zeit(t.start)}</div>` : ''}` : ''}
${t.phase === 'wartet' ? `<p class="klein">Auftrag „${esc(t.grund || '')}“ liegt bereit. ${d.trainer.online ? 'Der Trainer holt ihn gleich ab.' : 'Der Trainer ist nicht verbunden – er holt ihn ab, sobald er läuft.'}</p>` : ''}
${t.phase === 'fertig' && t.version ? `<p>Version v${t.version}: ${t.besser ? '<span class="gruen">besser als die alte</span>' : '<span class="gelb">nicht besser – die alte bleibt</span>'}.</p>` : ''}
${t.phase === 'fehler' ? `<p class="rot">${esc(t.schritt || t.hinweis || 'Fehler')}</p>` : ''}
<div class="zeile" style="margin-top:12px">${laeuft || t.phase === 'wartet' ? '<button class="k schlecht" data-a="abbrechen"><ha-icon icon="mdi:stop"></ha-icon>Abbrechen</button>' : `<button class="k haupt" data-a="trainieren"><ha-icon icon="mdi:play"></ha-icon>Jetzt trainieren</button><span class="klein">${d.neu_seit_lauf > 0 ? d.neu_seit_lauf + ' neue Bewertungen seit dem letzten Lauf' : 'Keine neuen Bewertungen seit dem letzten Lauf'}</span>`}</div></ha-card>
<ha-card><h2>Automatisch</h2>
<div class="zeile weit" style="margin-bottom:10px"><label><input type="checkbox" data-opt="nachts" ${e.nachts ? 'checked' : ''}> Nachts trainieren, wenn es neue Bewertungen gibt</label><input type="time" data-opt="uhrzeit" value="${esc(e.uhrzeit.slice(0, 5))}"></div>
<div class="zeile"><label><input type="checkbox" data-opt="automatisch_einspielen" ${e.automatisch_einspielen ? 'checked' : ''}> Bessere Version selbst auf allen Echos einspielen</label></div>
<p class="klein">Besser heißt: im ehrlichen Test (Aufnahmen, die nie gelernt wurden) erkennt sie mindestens so viel und löst bei russischem Gerede nicht öfter aus.</p></ha-card>
<ha-card><h2>Bisherige Läufe</h2>${d.laeufe.length ? `<table><tr><th>Wann</th><th>Ergebnis</th><th>Vorher</th><th>Nachher</th><th class="z">Dauer</th></tr>${d.laeufe.map((l) => `<tr><td>${datum(l.ende)}</td><td class="${l.ergebnis === 'eingespielt' ? 'gruen' : l.ergebnis === 'fehler' ? 'rot' : ''}">${esc(l.ergebnis)}${l.version ? ' (v' + l.version + ')' : ''}${l.hinweis ? '<div class="klein">' + esc(l.hinweis) + '</div>' : ''}</td><td>${kurz(l.alt)}</td><td>${kurz(l.neu)}</td><td class="z">${l.dauer_min != null ? Math.round(l.dauer_min) + ' Min.' : '–'}</td></tr>`).join('')}</table>` : '<div class="klein">Noch kein Lauf.</div>'}</ha-card>
${d.trainer.info && Object.keys(d.trainer.info).length ? `<ha-card><h2>Trainer</h2><div class="klein">${Object.entries(d.trainer.info).map(([k, v]) => esc(k) + ': ' + esc(v)).join(' · ')}</div></ha-card>` : ''}`;
    }

    // ---------- Qualität ----------
    _qualitaet() {
      const d = this._daten, s = d.statistik, v = d.versionen.find((x) => x.nr === d.aktiv), b = (v && v.bericht) || {};
      const neu = b.neu || {};
      const personen = neu.je_person || {};
      const schwelleJetzt = Object.values(d.schwellen || {});
      const sj = schwelleJetzt.length ? schwelleJetzt[0] : null;
      return `<ha-card><h2>Aktive Version ${v ? 'v' + v.nr : ''}</h2>${v ? `
<div class="raster" style="margin:0">
<div><div class="klein">Erkennt das Wort (Test)</div><div class="wert" style="font-size:26px">${pct(neu.trefferquote)}</div></div>
<div><div class="klein">Mit Musik im Hintergrund</div><div class="wert" style="font-size:26px">${pct(neu.trefferquote_musik)}</div></div>
<div><div class="klein">Fehlauslöser pro Stunde Gerede</div><div class="wert" style="font-size:26px">${komma(neu.fehlausloeser_pro_stunde, 1)}</div></div>
<div><div class="klein">Gegenbeispiele ausgelöst</div><div class="wert" style="font-size:26px">${pct(neu.gegenbeispiele)}</div></div></div>
${Object.keys(personen).length ? `<h3>Je Person (Test)</h3><table><tr><th>Person</th><th class="z">erkannt</th><th class="z">Aufnahmen</th></tr>${Object.entries(personen).map(([p, x]) => `<tr><td>${esc(p)}</td><td class="z">${pct(x.trefferquote)}</td><td class="z">${x.anzahl}</td></tr>`).join('')}</table>` : ''}
<div class="klein" style="margin-top:10px">Eingespielt ${zeit(v.eingespielt)}${b.cutoff ? ' · Modell-Schwelle ' + komma(b.cutoff) : ''}${b.herkunft ? ' · ' + esc(b.herkunft) : ''}</div>` : '<div class="klein">Noch keine Version.</div>'}</ha-card>
<ha-card><h2>Im Alltag (aus deinen Antworten)</h2>${this._alltag()}</ha-card>
<ha-card><h2>Schwelle aus deinen Antworten</h2>${this._verteilung(sj, s.schwelle_vorschlag)}
${s.schwelle_vorschlag != null ? `<div class="zeile weit" style="margin-top:10px"><span>Vorschlag: <b>${komma(s.schwelle_vorschlag)}</b>${sj != null ? ' (jetzt ' + komma(sj) + ')' : ''}</span><button class="k haupt" data-a="schwelle" data-wert="${s.schwelle_vorschlag}" ${sj != null && Math.abs(sj - s.schwelle_vorschlag) < 0.005 ? 'disabled' : ''}>An allen Echos übernehmen</button></div>` : '<div class="klein">Ein Vorschlag kommt, sobald mindestens 10 richtige und 5 falsche Aufwach-Aufnahmen geprüft sind.</div>'}
<div class="klein" style="margin-top:8px">Grün = Wort gesagt, Rot = nicht gesagt, Strich = jetzige Schwelle. Ein Fehlauslöser zählt so schwer wie drei verpasste Worte. Nichts ändert sich von selbst.</div></ha-card>
<ha-card><h2>Versionen</h2><table><tr><th>Version</th><th>Erkennt</th><th>Fehlauslöser</th><th>Stand</th><th></th></tr>${d.versionen.map((x) => { const n = (x.bericht && x.bericht.neu) || {}; return `<tr><td>v${x.nr}<div class="klein">${datum(x.zeit)}</div></td><td>${pct(n.trefferquote)}</td><td>${komma(n.fehlausloeser_pro_stunde, 1)}/Std.</td><td class="${x.status === 'aktiv' ? 'gruen' : ''}">${esc({ aktiv: 'aktiv', frueher: 'früher', geprueft: 'besser, nicht eingespielt', verworfen: 'nicht besser', neu: 'neu' }[x.status] || x.status)}</td><td class="z">${x.status !== 'aktiv' ? `<button class="k" data-a="einspielen" data-nr="${x.nr}">Einspielen</button>` : ''}</td></tr>`; }).join('')}</table></ha-card>`;
    }

    _verteilung(jetzt, vorschlag) {
      const v = this._daten.statistik.verteilung;
      if (!v.wort.length && !v.kein_wort.length) return '<div class="klein">Noch keine geprüften Aufnahmen mit Wert.</div>';
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
      [0.7, 0.8, 0.9, 1].forEach((t) => { s += `<text x="${Math.min(w - 14, xs(t))}" y="${h + 13}">${komma(t, 1)}</text>`; });
      return s + '</svg>';
    }

    // ---------- Einstellungen ----------
    _einstellungen() {
      const d = this._daten, e = d.einstellungen;
      const basis = d.trainer.adresse || location.origin;
      return `<ha-card><h2>Echos</h2>${Object.keys(d.echos).length ? `<table><tr><th>Echo</th><th>Aufnahmen</th></tr>${Object.entries(d.echos).map(([k, n]) => `<tr><td>${esc(n)}<div class="klein">${esc(k)}</div></td><td>${d.echo_fehler[k] ? `<span class="rot">${esc(d.echo_fehler[k]).slice(0, 140)}</span><div class="klein">Ist am Echo „Keep wake clips“ an?</div>` : '<span class="gruen">werden gesammelt</span>'}</td></tr>`).join('')}</table>` : '<div class="klein">Kein Echo mit TECHO5 gefunden.</div>'}
<div class="zeile" style="margin-top:10px"><button class="k" data-a="holen"><ha-icon icon="mdi:download-outline"></ha-icon>Jetzt nachsehen</button></div></ha-card>
<ha-card><h2>Wort und Modell</h2><table>
<tr><td>Name am Echo</td><td>${esc(e.anzeige)}</td></tr><tr><td>Modelldatei</td><td><code>/config/custom_wake_words/${esc(e.modell_id)}.tflite</code></td></tr>
<tr><td>Ablage</td><td><code>${esc(e.ordner)}</code> (im HA-Backup)</td></tr><tr><td>Schwelle jetzt</td><td>${Object.entries(d.schwellen).map(([k, v]) => esc(k.replace(/ assistant 1 Wake word threshold/i, '')) + ' ' + komma(v)).join(' · ') || '–'}</td></tr>
<tr><td>Integration</td><td>${esc(d.version_integration)}</td></tr></table>
<div class="zeile" style="margin-top:10px"><a class="k" style="text-decoration:none" href="/config/integrations/integration/sprachmodell"><button class="k"><ha-icon icon="mdi:tune"></ha-icon>Weitere Einstellungen (Personen, Erinnerung, Aufbewahren)</button></a></div></ha-card>
<ha-card><h2>Trainer verbinden</h2><div class="klein" style="line-height:1.6">Der Trainer läuft in einem eigenen Container im Heimnetz (Proxmox) und braucht diese zwei Angaben:</div>
<table><tr><td>Adresse</td><td><code>${esc(basis)}</code></td></tr><tr><td>Schlüssel</td><td><div class="schluessel"><code id="schl">${this._zeigeSchl ? esc(d.trainer.schluessel) : '••••••••••••'}</code><button class="k leise" data-a="schluessel">${this._zeigeSchl ? 'Verbergen' : 'Zeigen'}</button></div></td></tr></table>
<div class="klein" style="margin-top:8px">Anleitung: README des Repos, Abschnitt „Trainer“.</div></ha-card>`;
    }

    // ---------- Ereignisse ----------
    async _klick(e) {
      const t = e.target.closest('[data-reiter],[data-a],[data-spielen],[data-urteil],[data-echo],[data-verlauf],[data-seite]');
      if (!t) return;
      if (t.dataset.reiter) { this._gehe(t.dataset.reiter); return; }
      if (t.dataset.spielen) { const zeile = t.closest('.eintrag'); if (zeile) { const alle = [...this.shadowRoot.querySelectorAll('.eintrag:not(.weg)')]; this._aktiv = Math.max(0, alle.indexOf(zeile)); this._markieren(false); } this._spielen(t.dataset.spielen); return; }
      if (t.dataset.urteil) { this._urteilen(t.dataset.id, t.dataset.urteil); return; }
      if (t.dataset.echo !== undefined) { this._filter.echo = t.dataset.echo; this._filter.seite = 0; this._aktiv = 0; this._laden(); return; }
      if (t.dataset.verlauf) { this._filter.verlauf = t.dataset.verlauf; this._filter.seite = 0; this._laden(); return; }
      if (t.dataset.seite) { this._filter.seite = Math.max(0, this._filter.seite + Number(t.dataset.seite)); this._laden(); window.scrollTo(0, 0); return; }
      const a = t.dataset.a;
      try {
        if (a === 'neu') this._laden();
        else if (a === 'datei') this.shadowRoot.getElementById('datei').click();
        else if (a === 'holen') { t.disabled = true; await this._api('POST', 'aktion', { aktion: 'jetzt_holen' }); this._laden(); }
        else if (a === 'trainieren') { await this._api('POST', 'aktion', { aktion: 'training_starten' }); this._laden(); }
        else if (a === 'abbrechen') { if (confirm('Training abbrechen?')) { await this._api('POST', 'aktion', { aktion: 'training_abbrechen' }); this._laden(); } }
        else if (a === 'alle_vorschlaege') {
          const ids = ((this._liste && this._liste.eintraege) || []).filter((x) => x.vorschlag).map((x) => x.id);
          if (confirm(`Alle ${ids.length} Vorschläge so übernehmen, ohne sie anzuhören?`)) { await this._api('POST', 'aktion', { aktion: 'vorschlaege_uebernehmen', ids, person: this._person }); this._laden(); }
        } else if (a === 'schwelle') {
          const w = Number(t.dataset.wert);
          if (confirm(`Schwelle für Wort 1 an allen Echos auf ${komma(w)} setzen?`)) { await this._api('POST', 'aktion', { aktion: 'schwelle', wert: w }); this._meldung('Schwelle gesetzt.'); this._laden(); }
        } else if (a === 'einspielen') {
          const nr = Number(t.dataset.nr);
          if (confirm(`Version v${nr} an allen Echos einspielen? Die Echos verbinden sich dafür kurz neu.`)) { await this._api('POST', 'aktion', { aktion: 'einspielen', nr }); this._meldung('Version v' + nr + ' wird eingespielt.'); this._laden(); }
        } else if (a === 'schluessel') { this._zeigeSchl = !this._zeigeSchl; this._zeichnen(); }
      } catch (err) { this._meldung('Ging nicht: ' + (err.body?.message || err.message)); }
    }

    async _aenderung(e) {
      const t = e.target;
      if (t.id === 'datei') { this._hochladen([...t.files]); t.value = ''; return; }
      if (t.id === 'autoplay') { this._autoplay = t.checked; localStorage.setItem('sprachmodell.autoplay', t.checked ? '1' : '0'); return; }
      if (t.dataset.person !== undefined) {
        this._person = t.value; localStorage.setItem('sprachmodell.person', t.value);
        const id = t.dataset.person;
        if (id && id !== 'hoch' && this._reiter === 'verlauf') { await this._api('POST', 'urteil', { ids: [id], person: t.value }); }
        if (this._reiter === 'pruefen') this.shadowRoot.querySelectorAll('select[data-person]').forEach((s) => { s.value = t.value; });
        return;
      }
      if (t.dataset.opt) {
        const wert = t.type === 'checkbox' ? t.checked : t.value;
        try { await this._api('POST', 'aktion', { aktion: 'einstellungen', [t.dataset.opt]: wert }); this._meldung('Gespeichert.'); } catch (err) { this._meldung('Ging nicht: ' + err.message); }
        setTimeout(() => this._laden(), 1500);
      }
    }

    _meldung(text) {
      this.dispatchEvent(new CustomEvent('hass-notification', { detail: { message: text }, bubbles: true, composed: true }));
    }
  }

  if (!customElements.get('sprachmodell-panel')) customElements.define('sprachmodell-panel', SprachmodellPanel);
  console.info('%c Sprachmodell ' + VERSION + ' ', 'background:#0288d1;color:#fff;border-radius:3px');
})();
