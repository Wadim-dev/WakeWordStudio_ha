// Wake Word Studio – sidebar panel: create own wake words, review, record, train and roll out.
// Everything is set here (words, devices, slots, trainer). Changing the setup needs an administrator.
// Addresses: /wake-word-studio/<tab>?wort=<id>   tabs without a word: zentrale, geraete, einstellungen, neu
// No polling: the page reloads only when one of the integration's sensors changes.
// Texts are loaded with the panel's own ?v= so a browser never mixes a new panel with old cached texts.
// Not with a top-level await: Home Assistant creates the panel element as soon as this script has run, so the
// element must be defined right away - otherwise the first opening stays black (its hass/route would be lost).
let TEXTE = { en: {} }, SPRACHNAMEN = { de: {}, en: {} };
const TEXTE_DA = import(`./sprachmodell-texte.js${new URL(import.meta.url).search}`)
  .then((m) => { TEXTE = m.TEXTE; SPRACHNAMEN = m.SPRACHNAMEN; })
  .catch((e) => console.error('Wake Word Studio: texts could not be loaded', e));

const VERSION = '1.0.46';
const KURVE_VERSIONEN = 12; // how many of the newest versions the curve shows
const REPO = 'https://github.com/Wadim-dev/WakeWordStudio_ha';
const BILD = 'ghcr.io/wadim-dev/wake-word-studio-trainer:latest';
const PROXMOX = 'https://raw.githubusercontent.com/Wadim-dev/WakeWordStudio_ha/main/sprachmodell_trainer/proxmox.sh';
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
.kopf{position:sticky;top:0;z-index:3;display:flex;align-items:center;gap:4px;height:var(--header-height,56px);padding:0 8px 0 4px;background:linear-gradient(var(--app-header-background-color,transparent),var(--app-header-background-color,transparent)),var(--primary-background-color);color:var(--app-header-text-color,var(--primary-text-color));border-bottom:1px solid var(--divider-color)}
.kopf h1{font-size:20px;font-weight:400;margin:0 0 0 8px;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kopf .ikon{width:40px;height:40px;border-radius:50%;border:0;background:none;color:inherit;cursor:pointer;display:flex;align-items:center;justify-content:center}
.kopf .ikon.an{color:var(--primary-color);background:rgba(var(--rgb-primary-color,3,169,244),.14)}
.leisten{position:sticky;top:var(--header-height,56px);z-index:2;background:linear-gradient(var(--app-header-background-color,transparent),var(--app-header-background-color,transparent)),var(--primary-background-color);border-bottom:1px solid var(--divider-color)}
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
.wortkarte .name{font-weight:500}
.wortkarte .reihe{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.zeile{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.zeile.weit{justify-content:space-between}
.zeile.unter{margin:6px 0 0 26px}.zeile.unter.aus{opacity:.5}.unter-text{margin:4px 0 0 26px;line-height:1.6}
.v-karte{padding:6px 16px!important}.v-hinweis{display:flex;align-items:center;gap:12px;padding:10px 0;flex-wrap:wrap}.v-hinweis+.v-hinweis{border-top:1px solid var(--divider-color)}
.v-hinweis>ha-icon{color:var(--primary-color);flex:none}.v-hinweis.warn>ha-icon{color:var(--warning-color)}.v-text{flex:1 1 220px;line-height:1.45}
.dreher{display:inline-block;width:16px;height:16px;border:2px solid var(--divider-color);border-top-color:var(--primary-color);border-radius:50%;animation:drehen 1s linear infinite;flex:none}
button.startet{gap:8px}.klein.warn{color:var(--warning-color);margin-top:4px}
@media (prefers-reduced-motion:reduce){.dreher{animation:none}}
button.k{display:inline-flex;align-items:center;gap:6px;border:0;border-radius:18px;padding:8px 14px;font:inherit;font-size:14px;cursor:pointer;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);color:var(--primary-text-color)}
button.k:disabled{opacity:.45;cursor:default}
button.k.rund{width:36px;height:36px;padding:0;justify-content:center;font-size:18px;border-radius:50%}
.sw-hand{margin-top:14px;padding-top:12px;border-top:1px solid var(--divider-color,rgba(127,127,127,.2))}
.sw-hand input.sw-wert{width:76px;text-align:center;font:inherit;font-size:16px;font-variant-numeric:tabular-nums;padding:7px 6px;border-radius:10px;border:1px solid var(--divider-color,rgba(127,127,127,.35));background:var(--card-background-color,transparent);color:var(--primary-text-color)}
button.k.haupt{background:var(--primary-color);color:var(--text-primary-color,#fff)}
button.k.gut{background:rgba(var(--rgb-success-color,76,175,80),.2);color:var(--success-color,#4caf50)}
button.k.schlecht{background:rgba(var(--rgb-error-color,244,67,54),.18);color:var(--error-color,#f44336)}
button.k.gut.gewaehlt{background:color-mix(in srgb,var(--success-color,#4caf50) 72%,#000);color:#fff;box-shadow:0 2px 10px rgba(var(--rgb-success-color,76,175,80),.35)}button.k.schlecht.gewaehlt{background:color-mix(in srgb,var(--error-color,#f44336) 78%,#000);color:#fff;box-shadow:0 2px 10px rgba(var(--rgb-error-color,244,67,54),.35)}button.k{transition:background .2s,box-shadow .2s,transform .1s}button.k:active{transform:scale(.97)}button.k.leise.gewaehlt{background:var(--secondary-text-color);color:var(--card-background-color,#fff)}
.ablauf{display:grid;grid-template-columns:22px 1fr auto;gap:6px 10px;align-items:center;font-size:14px}.ablauf .klein{text-align:right;white-space:nowrap}.ablauf ha-icon{--mdc-icon-size:18px}.ablauf .spaeter{opacity:.45}
.drehen{animation:drehen 1.2s linear infinite}@keyframes drehen{to{transform:rotate(360deg)}}
.last{display:grid;grid-template-columns:auto 1fr auto;gap:8px 12px;align-items:center;font-size:14px}.last .fortschritt{margin:0;height:8px}
.protokoll{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;line-height:1.5;max-height:min(70vh,640px);overflow:auto;background:rgba(var(--rgb-primary-text-color,0,0,0),.05);border-radius:8px;padding:8px 10px;white-space:pre-wrap;word-break:break-word}
.aktiv{display:grid;gap:14px}.aktiv-z{display:grid;grid-template-columns:32px 1fr;gap:0 12px;align-items:start}.aktiv-z>ha-icon{--mdc-icon-size:20px;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(var(--rgb-primary-color,3,169,244),.14);color:var(--primary-color)}.aktiv-z b{font-weight:500}.aktiv-z .proz{font-variant-numeric:tabular-nums;font-weight:500;color:var(--primary-color)}.aktiv-z .fortschritt{margin:6px 0 4px;height:8px}.aktiv-z .klein{font-variant-numeric:tabular-nums}.lebt{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--success-color,#4caf50);margin-right:10px;vertical-align:middle;animation:lebt 1.8s ease-out infinite}@keyframes lebt{0%{box-shadow:0 0 0 0 rgba(var(--rgb-success-color,76,175,80),.6)}100%{box-shadow:0 0 0 9px rgba(var(--rgb-success-color,76,175,80),0)}}.protokoll>div{padding:1px 0 1px 8px;border-left:2px solid transparent}.protokoll .l-warnung,.protokoll .l-warnung_aus{border-left-color:var(--warning-color,#ff9800)}.protokoll .l-fehler{border-left-color:var(--error-color,#f44336)}.protokoll .l-info{border-left-color:rgba(var(--rgb-primary-color,3,169,244),.5)}@media (prefers-reduced-motion:reduce){.lebt,.laeuft .fortschritt i{animation:none}}
.protokoll .z{color:var(--secondary-text-color);margin-right:8px}.protokoll .l-aus,.protokoll .l-balken,.protokoll .l-schritt{color:var(--secondary-text-color)}.protokoll .l-warnung,.protokoll .l-warnung_aus{color:var(--warning-color,#ff9800)}.protokoll .l-fehler{color:var(--error-color,#f44336)}
button.k.leise{background:none;color:var(--secondary-text-color)}
button.k ha-icon{--mdc-icon-size:18px}
button.k kbd{font:11px monospace;opacity:.6;border:1px solid currentColor;border-radius:4px;padding:0 4px}
.chip{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;border-radius:16px;font-size:13px;background:rgba(var(--rgb-primary-text-color,0,0,0),.06);cursor:pointer;border:0;color:inherit;font-family:inherit;text-decoration:none}
.chip.an{background:rgba(var(--rgb-primary-color,3,169,244),.18);color:var(--primary-color)}
.liste{display:flex;flex-direction:column;gap:10px}
.eintrag{display:grid;grid-template-columns:52px minmax(0,1fr);gap:14px;padding:14px 16px;transition:border-color .2s,box-shadow .2s;border-radius:var(--ha-card-border-radius,12px);background:var(--ha-card-background,var(--card-background-color));border:1px solid var(--divider-color);outline:none}
.eintrag.aktiv{border-color:var(--primary-color);box-shadow:0 0 0 1px var(--primary-color)}
.eintrag.weg{pointer-events:none}
.eintrag{position:relative}
.eintrag .stempel{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:10px;border-radius:inherit;font-size:18px;font-weight:600;color:#fff;pointer-events:none;animation:stempel .28s cubic-bezier(.2,.9,.3,1.3) both;z-index:4}
.eintrag .stempel ha-icon{--mdc-icon-size:30px}
.stempel.u-wort{background:color-mix(in srgb,var(--success-color,#4caf50) 82%,transparent)}.stempel.u-kein_wort{background:color-mix(in srgb,var(--error-color,#f44336) 82%,transparent)}.stempel.u-verworfen{background:color-mix(in srgb,var(--secondary-text-color,#777) 85%,transparent)}
@keyframes stempel{from{opacity:0;transform:scale(.92)}to{opacity:1;transform:none}}
.knoepfe button.k.drueck{animation:drueck .35s ease-out}@keyframes drueck{0%{box-shadow:0 0 0 0 rgba(var(--rgb-primary-color,3,169,244),.45)}100%{box-shadow:0 0 0 12px rgba(var(--rgb-primary-color,3,169,244),0)}}
@media (prefers-reduced-motion:reduce){.eintrag .stempel,.knoepfe button.k.drueck,.umzug,.lage-balken i,.vgl.auf,.d-spur i{animation:none}}
.spielen{width:52px;height:52px;border-radius:50%;border:0;background:rgba(var(--rgb-primary-color,3,169,244),.15);color:var(--primary-color);cursor:pointer;position:relative}
.spielen ha-icon{--mdc-icon-size:28px}
.spielen svg{position:absolute;inset:0;transform:rotate(-90deg)}
.spielen circle{fill:none;stroke:var(--primary-color);stroke-width:3;stroke-dasharray:157;stroke-dashoffset:157}
.titel{font-weight:500;display:inline-flex;align-items:center;gap:6px}
.welle{position:relative;height:40px;margin:8px 0 6px;border-radius:8px;background:rgba(var(--rgb-primary-text-color,0,0,0),.05);overflow:hidden;cursor:pointer;touch-action:manipulation}
.welle canvas{position:absolute;inset:0;width:100%;height:100%}
.welle .spielkopf{position:absolute;top:0;bottom:0;width:2px;margin-left:-1px;background:var(--primary-text-color);opacity:0;pointer-events:none;transition:opacity .2s}.welle .spielkopf.an{opacity:.9}
.wertzeile{display:flex;flex-direction:row;align-items:center;gap:10px;font-size:12px;color:var(--secondary-text-color);flex-wrap:wrap}
.wertzeile .balken{flex:1 1 auto;width:auto;min-width:120px;height:6px;margin:0;max-width:260px}
.knoepfe .rechts{margin-left:auto;display:flex;gap:6px;align-items:center}
.balken{position:relative;height:6px;border-radius:3px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);margin:8px 0 4px;max-width:340px}
.balken i{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--primary-color)}
.balken b{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--error-color,#f44336)}
.vorschlag{font-size:13px;margin:6px 0 8px;color:var(--secondary-text-color)}
.vorschlag strong{color:var(--primary-text-color)}
.gehoert{margin:4px 0 2px;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.v-entscheid{margin-bottom:8px;flex-wrap:wrap;gap:6px}.v-trenn{width:1px;height:20px;background:var(--divider-color);margin:0 4px}
.e-zweifel{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--warning-color,#ff9800);margin-top:6px}.e-zweifel ha-icon{--mdc-icon-size:18px}
.marke{border-radius:999px;padding:1px 8px;background:color-mix(in srgb,var(--primary-color) 14%,transparent);color:var(--primary-text-color);font-size:11px}
.schnitt:empty{display:none}
.lagen{display:grid;gap:8px;margin:4px 0 6px}
.blick{display:grid;gap:8px 32px;margin-top:6px}.blick.zwei{grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:start}
@media (max-width:900px){.blick.zwei{grid-template-columns:minmax(0,1fr)}}
.blick-duell button.link{display:inline-flex;align-items:center;gap:2px;margin-top:2px;border:0;background:none;padding:4px 0;color:var(--primary-color);font:inherit;font-size:14px;cursor:pointer}.blick-duell button.link:hover{text-decoration:underline}.blick-duell button.link ha-icon{--mdc-icon-size:18px}
.duell{display:grid;gap:16px;margin:4px 0 10px}
.d-kopf{display:flex;justify-content:space-between;gap:8px;align-items:baseline;font-size:14px;font-weight:500;margin-bottom:4px}.d-kopf .klein{font-weight:400;white-space:nowrap}
.d-zeile{display:grid;grid-template-columns:52px 1fr 56px;gap:10px;align-items:center;font-size:13px;margin-top:5px}
.d-zeile b{text-align:right;font-weight:500;font-variant-numeric:tabular-nums}.d-name{color:var(--secondary-text-color)}
.d-spur{height:10px;border-radius:5px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden}
.d-spur i{display:block;height:100%;width:var(--w);border-radius:5px;animation:balken-wachsen .7s cubic-bezier(.2,.8,.3,1) both}
.d-spur i.neu{background:var(--primary-color)}.d-spur i.alt{background:var(--secondary-text-color);opacity:.5}
.d-fuss{margin-top:5px;font-size:12px}.d-urteil{display:inline-flex;gap:4px;align-items:center;color:var(--secondary-text-color)}.d-urteil ha-icon{--mdc-icon-size:16px}
.d-urteil.u-besser{color:var(--success-color,#4caf50)}.d-urteil.u-schlechter{color:var(--error-color,#f44336)}
.still .lage-balken i,.still .d-spur i{animation:none}
.lage{display:grid;grid-template-columns:minmax(110px,190px) 1fr 48px;gap:10px;align-items:center;font-size:13px}
.lage b{text-align:right;font-weight:500}
.lage-balken{height:8px;border-radius:4px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden}
.lage-balken i{display:block;height:100%;width:var(--w);border-radius:4px;background:var(--success-color,#4caf50);animation:balken-wachsen .7s cubic-bezier(.2,.8,.3,1) both}
.lage-balken i.mittel{background:var(--warning-color,#ff9800)}.lage-balken i.schwach{background:var(--error-color,#f44336)}.lage-balken i.hart{background:var(--primary-color,#03a9f4)}
@keyframes balken-wachsen{from{width:0}}
.tabelle-scroll{overflow-x:auto;margin:0 -4px;padding:0 4px}
table.versionen>tbody>tr>td:nth-child(n+2):nth-child(-n+4),.vgl-tab td.z{white-space:nowrap}
@media (max-width:600px){table.versionen>tbody>tr>:nth-child(2){display:none}.vgl{padding:10px}.lage{grid-template-columns:minmax(90px,1fr) 1fr 42px}}
table.versionen tr.klickbar{cursor:pointer;transition:background .15s}
table.versionen tr.klickbar:hover{background:rgba(var(--rgb-primary-text-color,0,0,0),.04)}
table.versionen .pfeil{--mdc-icon-size:18px;margin:-2px 2px 0 -4px;color:var(--secondary-text-color);transition:transform .2s}
table.versionen tr.offen .pfeil{transform:rotate(90deg)}
table.versionen tr.vdetail>td{padding:0 0 12px;background:transparent}
.vgl{padding:12px 14px;border-radius:12px;background:color-mix(in srgb,var(--primary-text-color) 4%,transparent)}
.vgl.auf{animation:aufklappen .25s cubic-bezier(.2,.8,.3,1) both}
.vgl-urteil{display:flex;gap:8px;align-items:flex-start;font-size:14px;margin-bottom:10px;line-height:1.4}
.vgl-urteil ha-icon{--mdc-icon-size:20px;flex:none;color:var(--secondary-text-color)}
.vgl-urteil.u-besser ha-icon,.vgl-tab .u-besser{color:var(--success-color,#4caf50)}
.vgl-urteil.u-schlechter ha-icon,.vgl-tab .u-schlechter{color:var(--error-color,#f44336)}
.vgl-tab .u-gleich{color:var(--secondary-text-color)}
.vgl-tab td,.vgl-tab th{padding:6px 4px}.vgl-tab ha-icon{--mdc-icon-size:18px}
.vgl-tab tr.wichtig td:first-child{font-weight:600}
.legende i.neu{background:var(--primary-color)}.legende i.alt{background:var(--secondary-text-color)}
.umzug:empty{display:none}
.umzug{margin-top:10px;padding:10px 12px;border-radius:10px;background:color-mix(in srgb,var(--primary-text-color) 5%,transparent);animation:aufklappen .22s cubic-bezier(.2,.8,.3,1) both}
.umzug-woerter{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.wortwahl{padding:8px 14px;font-size:14px;border:1px solid color-mix(in srgb,var(--wf) 45%,transparent);transition:background .15s,transform .12s}
.wortwahl .farbe{width:10px;height:10px;border-radius:50%;background:var(--wf)}
.wortwahl:hover,.wortwahl:focus-visible,.wortwahl.an{background:color-mix(in srgb,var(--wf) 22%,transparent);outline:none}
.wortwahl:active{transform:scale(.96)}.wortwahl:disabled{cursor:default}
.umzug-hilfe{line-height:1.45}
.wortmarke{display:inline-flex;align-items:center;gap:5px;background:color-mix(in srgb,var(--wf) 18%,transparent)}
.wortmarke i{width:7px;height:7px;border-radius:50%;background:var(--wf)}
.wortmarke .link{border:0;background:none;padding:0 0 0 4px;color:var(--primary-color);font:inherit;cursor:pointer;text-decoration:underline}
.stempel.u-umzug{background:color-mix(in srgb,var(--wf) 85%,transparent)}
@keyframes aufklappen{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
.schnitt{margin-top:10px;padding:10px;border-radius:10px;background:color-mix(in srgb,var(--primary-text-color) 5%,transparent)}
.studio{position:relative;height:120px;border-radius:10px;background:#0e1014;overflow:hidden;touch-action:none;cursor:crosshair;user-select:none;-webkit-user-select:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.07),0 6px 18px rgba(0,0,0,.25)}
.studio canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.studio .aus{position:absolute;top:0;bottom:18px;background:rgba(5,6,8,.62);pointer-events:none;transition:background .2s}.studio .links{left:0}.studio .rechts{right:0}
.studio .wahl{position:absolute;top:0;bottom:18px;cursor:grab;box-shadow:inset 0 2px 0 var(--primary-color),inset 0 -2px 0 var(--primary-color);background:rgba(var(--rgb-primary-color,3,169,244),.07)}.studio.zieht .wahl{cursor:grabbing}
.studio .griff{position:absolute;top:0;bottom:18px;width:28px;margin-left:-14px;cursor:ew-resize;outline:none;z-index:2}
.studio .griff::before{content:'';position:absolute;left:13px;top:0;bottom:0;width:2px;background:var(--primary-color)}
.studio .griff span{position:absolute;top:50%;width:14px;height:34px;margin-top:-17px;background:var(--primary-color);box-shadow:0 2px 8px rgba(0,0,0,.55);transition:transform .15s}
.studio [data-griff="von"] span{left:15px;border-radius:0 6px 6px 0}.studio [data-griff="bis"] span{right:15px;border-radius:6px 0 0 6px}
.studio .griff span::after{content:'';position:absolute;left:4px;top:10px;width:6px;height:14px;border-left:2px solid rgba(255,255,255,.75);border-right:2px solid rgba(255,255,255,.75);box-sizing:border-box}
.studio .griff:hover span,.studio .griff.zieht span{transform:scaleY(1.12)}.studio .griff:focus-visible span{outline:2px solid #fff;outline-offset:2px}
.studio .spielkopf{position:absolute;top:0;bottom:0;width:2px;margin-left:-1px;background:#fff;box-shadow:0 0 10px rgba(255,255,255,.8);pointer-events:none;opacity:0;transition:opacity .25s;z-index:3}
.studio .spielkopf::before{content:'';position:absolute;top:0;left:-5px;border:6px solid transparent;border-top-color:#fff}.studio .spielkopf.an{opacity:1}
.studio-leiste{margin-top:10px;flex-wrap:wrap;gap:8px}.zeitanzeige{font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.k.rund{width:40px;height:40px;padding:0;justify-content:center;border-radius:50%}
@media (prefers-reduced-motion:reduce){.studio .spielkopf{transition:none}}
.knoepfe{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
select,input[type=time],input[type=text],input[type=number]{font:inherit;font-size:14px;padding:8px 10px;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);box-sizing:border-box}
input[type=text]{width:100%;max-width:440px}
input[type=number]{width:96px}
label.feld{display:block;margin:14px 0 5px;font-size:13px;color:var(--secondary-text-color)}
.neustart{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.neustart select{flex:1 1 260px;min-width:0}
.leer{text-align:center;padding:40px 16px;color:var(--secondary-text-color)}
.leer ha-icon{--mdc-icon-size:48px;opacity:.5}
.fortschritt{height:10px;border-radius:5px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden;margin:10px 0}
.fortschritt i{display:block;height:100%;background:var(--primary-color);transition:width .6s}
.laeuft .fortschritt i{background-image:linear-gradient(90deg,transparent 0,rgba(255,255,255,.25) 50%,transparent 100%);background-size:200% 100%;animation:schimmer 2.5s linear infinite}
@keyframes schimmer{to{background-position:-200% 0}}
.laeuft .fortschritt{overflow:visible;position:relative}.laeuft .fortschritt i{position:relative;border-radius:5px}
.laeuft .fortschritt i::after{content:'';position:absolute;right:-3px;top:50%;width:12px;height:12px;margin-top:-6px;border-radius:50%;background:var(--primary-color);box-shadow:0 0 10px 3px rgba(var(--rgb-primary-color,3,169,244),.65);animation:funkeln 1.5s ease-in-out infinite}
@keyframes funkeln{50%{transform:scale(.55);opacity:.6}}
.magie{display:block;width:100%;height:96px;margin:6px 0 2px;color:var(--farbe,var(--primary-color));overflow:visible}
.magie .m-linie{stroke:currentColor;stroke-opacity:.14;stroke-width:1}
.magie .m-welle rect{fill:currentColor;transform-box:fill-box;transform-origin:center;animation:m-welle 1.2s ease-in-out infinite;animation-delay:calc(var(--d0,0s) - var(--i) * .09s)}
@keyframes m-welle{0%,100%{transform:scaleY(.22)}50%{transform:scaleY(1)}}
.magie .m-knoten circle{fill:currentColor;transform-box:fill-box;transform-origin:center;animation:m-feuern 2s ease-in-out infinite;animation-delay:calc(var(--d0,0s) + var(--s) * .35s)}
@keyframes m-feuern{0%,100%{opacity:.3;transform:scale(.8)}18%{opacity:1;transform:scale(1.25);filter:drop-shadow(0 0 5px currentColor)}40%{opacity:.45;transform:scale(1)}}
.magie .m-teil circle{fill:#fff;filter:drop-shadow(0 0 3px currentColor);opacity:0;animation:m-fliegen 2s cubic-bezier(.45,0,.55,1) infinite;animation-delay:calc(var(--d0,0s) + var(--s) * .35s)}
@keyframes m-fliegen{0%{transform:translate(0,0);opacity:0}15%{opacity:1}85%{opacity:1}100%{transform:translate(var(--dx),var(--dy));opacity:0}}
.magie .m-ziel{fill:none;stroke:currentColor;stroke-width:2;transform-box:fill-box;transform-origin:center;animation:m-ring 2s ease-out infinite;animation-delay:calc(var(--d0,0s) + 1.05s)}
@keyframes m-ring{0%{transform:scale(.6);opacity:0}25%{opacity:.9}100%{transform:scale(2.3);opacity:0}}
.magie .m-stern{fill:#fff;transform-box:fill-box;transform-origin:center;animation:m-stern 3s ease-in-out infinite;animation-delay:calc(var(--d0,0s) + var(--s) * 1s)}
@keyframes m-stern{0%,100%{transform:scale(0) rotate(0);opacity:0}30%{transform:scale(1) rotate(45deg);opacity:1}60%{transform:scale(0) rotate(90deg);opacity:0}}
.magie.st-vorbereiten .m-netz,.magie.st-daten .m-netz{opacity:.4}.magie.st-test .m-welle{opacity:.4}
.feier{position:relative;height:0;pointer-events:none}.feier i{position:absolute;left:var(--x,50%);top:0;width:8px;height:8px;border-radius:2px;background:var(--c);opacity:0;animation:konfetti 1.6s cubic-bezier(.15,.7,.3,1) forwards;animation-delay:var(--v)}
@keyframes konfetti{0%{transform:translate(0,0) rotate(0) scale(.4);opacity:1}100%{transform:translate(var(--dx),var(--dy)) rotate(var(--rot)) scale(1);opacity:0}}
.gefeiert{animation:gefeiert 1.2s ease-out}@keyframes gefeiert{0%{box-shadow:0 0 0 0 rgba(76,175,80,.55)}100%{box-shadow:0 0 0 18px rgba(76,175,80,0)}}
main:not(.still)>ha-card,main:not(.still)>.raster>ha-card{animation:auftauchen .45s cubic-bezier(.2,.8,.3,1) both}
main:not(.still)>ha-card:nth-of-type(2){animation-delay:50ms}main:not(.still)>ha-card:nth-of-type(3){animation-delay:100ms}main:not(.still)>ha-card:nth-of-type(n+4){animation-delay:150ms}
@keyframes auftauchen{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.magie *,.feier i,.laeuft .fortschritt i::after,main>ha-card,main>.raster>ha-card,.gefeiert{animation:none!important}.magie .m-teil,.feier{display:none}}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--divider-color);vertical-align:top}
th{font-weight:500;color:var(--secondary-text-color);font-size:12px}
td.z,th.z{text-align:right}
.gruen{color:var(--success-color,#4caf50)}.rot{color:var(--error-color,#f44336)}.gelb{color:var(--warning-color,#ff9800)}
.punkt{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:var(--disabled-color,#999)}
.punkt.an{background:var(--success-color,#4caf50)}
.sgeraete{display:grid;gap:10px}
.sgeraet{padding:12px 14px;border-radius:12px;border:1px solid var(--divider-color);display:grid;gap:10px;transition:border-color .2s}
.sgeraet-regler{gap:10px 18px}
.pille{font-size:12px;padding:3px 10px;border-radius:999px;white-space:nowrap}.pille.gruen{background:rgba(var(--rgb-success-color,76,175,80),.16);color:var(--success-color,#4caf50)}.pille.gelb{background:rgba(var(--rgb-warning-color,255,152,0),.16);color:var(--warning-color,#ff9800)}.pille.rot{background:rgba(var(--rgb-error-color,244,67,54),.16);color:var(--error-color,#f44336)}
.schalter{display:inline-flex;align-items:center;gap:8px;cursor:pointer;font-size:14px;user-select:none}
.schalter input{position:absolute;opacity:0;width:0;height:0}
.schalter i{position:relative;width:36px;height:20px;border-radius:10px;background:rgba(var(--rgb-primary-text-color,0,0,0),.25);transition:background .2s;flex:none}
.schalter i::after{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.4);transition:transform .2s cubic-bezier(.4,0,.2,1)}
.schalter input:checked+i{background:var(--primary-color)}.schalter input:checked+i::after{transform:translateX(16px)}
.schalter input:focus-visible+i{outline:2px solid var(--primary-color);outline-offset:2px}.schalter input:disabled+i{opacity:.4}
.abwurf{border:2px dashed color-mix(in srgb,var(--primary-color) 35%,var(--divider-color));border-radius:20px;padding:30px 16px;text-align:center;cursor:pointer;background:radial-gradient(ellipse at 50% 0%,color-mix(in srgb,var(--primary-color) 10%,transparent),transparent 70%);transition:border-color .25s,background .25s,transform .25s}
.abwurf:hover{border-color:var(--primary-color)}
.abwurf.ueber{border-color:var(--primary-color);border-style:solid;background:radial-gradient(ellipse at 50% 30%,color-mix(in srgb,var(--primary-color) 22%,transparent),transparent 75%);transform:scale(1.015);box-shadow:0 0 0 4px color-mix(in srgb,var(--primary-color) 18%,transparent),0 10px 40px color-mix(in srgb,var(--primary-color) 25%,transparent)}
.ab-ikon{position:relative;display:flex;margin:0 auto 4px;width:72px;height:72px;align-items:center;justify-content:center;border-radius:50%;background:color-mix(in srgb,var(--primary-color) 14%,transparent)}
.abwurf .ab-ikon ha-icon{--mdc-icon-size:38px;color:var(--primary-color);transition:transform .3s cubic-bezier(.2,.9,.3,1.4)}
.ab-ikon i{position:absolute;inset:0;border-radius:50%;border:2px solid var(--primary-color);opacity:0}
main:not(.still) .ab-ikon i{animation:raum-welle 3.2s ease-out infinite}main:not(.still) .ab-ikon i+i{animation-delay:1.6s}
.abwurf.ueber .ab-ikon ha-icon{transform:translateY(6px) scale(1.15)}main:not(.still) .abwurf.ueber .ab-ikon i{animation-duration:1.1s}
@media (prefers-reduced-motion:reduce){.ab-ikon i{animation:none!important}}
code,pre{font-size:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);padding:2px 6px;border-radius:5px;word-break:break-all}
pre{display:block;padding:10px;white-space:pre-wrap;margin:6px 0}
.schluessel{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.g-info{display:flex;gap:10px;margin:10px 0 4px 26px;padding:10px 12px;border-radius:10px;background:rgba(var(--rgb-primary-text-color,0,0,0),.04);font-size:13px;line-height:1.6;transition:background .2s}
.g-info.an{background:rgba(var(--rgb-primary-color,3,169,244),.1)}.g-info>ha-icon{--mdc-icon-size:20px;color:var(--primary-color);flex:none;margin-top:1px}
.g-info b{font-weight:500;font-size:14px}.g-rat{display:flex;gap:8px;align-items:center;margin-top:2px}.g-rat .punkt{flex:none}
.g-info>div{min-width:0}.g-info select{max-width:100%;margin:2px 0}
.tr-liste{display:grid;gap:4px;margin:6px 0}.tr-zeile{display:flex;gap:4px;align-items:baseline;padding:6px 8px;border-radius:8px;border:1px solid transparent}
.tr-zeile.ziel{border-color:rgba(var(--rgb-primary-color,3,169,244),.5);background:rgba(var(--rgb-primary-color,3,169,244),.06)}.tr-zeile .punkt{flex:none}
.tr-eintrag{border:1px solid var(--divider-color);border-radius:12px;padding:4px 12px;margin:8px 0}.tr-eintrag[open]{padding-bottom:12px}
.tr-eintrag summary{cursor:pointer;display:flex;flex-wrap:wrap;gap:4px 8px;align-items:center;padding:8px 0;list-style:none}.tr-eintrag summary::-webkit-details-marker{display:none}
.tr-eintrag summary::after{content:'';margin-left:auto;width:8px;height:8px;border-right:2px solid var(--secondary-text-color);border-bottom:2px solid var(--secondary-text-color);transform:rotate(45deg);transition:transform .2s}
.tr-eintrag[open] summary::after{transform:rotate(-135deg)}.tr-eintrag summary .punkt{margin-right:0}
.schalter-zeile{display:flex;gap:8px;align-items:center;margin:10px 0 2px;font-size:14px;cursor:pointer}.schalter-zeile input{width:18px;height:18px;margin:0}
.ei-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 10px}.ei-schritte{margin:8px 0;padding-left:20px;font-size:14px;line-height:1.6}
.befehl{display:grid;gap:6px;justify-items:start;margin:6px 0}.befehl pre{width:100%;box-sizing:border-box;margin:0}
@media (max-width:600px){.g-info{margin-left:0}}
.hinweis{padding:10px 12px;border-radius:10px;background:rgba(var(--rgb-warning-color,255,152,0),.12);font-size:14px;margin-bottom:12px;line-height:1.5}
.hinweis.ok{background:rgba(var(--rgb-success-color,76,175,80),.14)}
svg.vert text{font-size:10px;fill:var(--secondary-text-color)}
.platz{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:center;padding:10px 12px;margin:8px 0;border-radius:16px;border:1px solid var(--divider-color);background:rgba(var(--rgb-primary-text-color,0,0,0),.025);transition:border-color .3s,background .3s,box-shadow .3s}
.pl-ikon{width:36px;height:36px;border-radius:12px;display:flex;align-items:center;justify-content:center;color:var(--secondary-text-color);background:rgba(var(--rgb-primary-text-color,0,0,0),.06);transition:color .3s,background .3s}.pl-ikon ha-icon{--mdc-icon-size:20px}
.pl-name{font-weight:500}
.platz.an{border-color:color-mix(in srgb,var(--primary-color) 45%,transparent);background:color-mix(in srgb,var(--primary-color) 7%,transparent);box-shadow:0 4px 18px color-mix(in srgb,var(--primary-color) 12%,transparent)}
.platz.an .pl-ikon{color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 16%,transparent)}main:not(.still) .platz.an .pl-ikon ha-icon{animation:atmen 2.6s ease-in-out infinite}
.platz select{border-radius:12px}
@media (max-width:600px){.platz{grid-template-columns:auto minmax(0,1fr)}.platz select{grid-column:1 / -1}}
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
.held{display:grid;grid-template-columns:auto 1fr auto;gap:16px;align-items:center;padding:20px;position:relative;overflow:hidden;background:linear-gradient(120deg,color-mix(in srgb,var(--hf) 16%,var(--ha-card-background,var(--card-background-color))) 0%,var(--ha-card-background,var(--card-background-color)) 70%)}
.held-ikon{width:56px;height:56px;border-radius:16px;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--hf) 22%,transparent);color:var(--hf)}
.held-ikon ha-icon{--mdc-icon-size:30px}
.held.laeuft .held-ikon ha-icon{animation:wippen 2.4s ease-in-out infinite}@keyframes wippen{50%{transform:translateY(-3px)}}
.held-titel{font-size:22px;font-weight:500;margin-bottom:2px}
.held .fortschritt{max-width:520px;margin:10px 0 2px}
.pillen{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
.pille{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:14px;font-size:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.06);color:var(--secondary-text-color)}
.pille ha-icon{--mdc-icon-size:15px}
h3.abschnitt{margin:20px 2px 8px;font-size:13px;text-transform:uppercase;letter-spacing:.06em}
.wortkarte{border-top:0;position:relative;overflow:hidden;background:linear-gradient(160deg,color-mix(in srgb,var(--wf) 13%,var(--ha-card-background,var(--card-background-color))) 0%,var(--ha-card-background,var(--card-background-color)) 55%)}
.wortkarte::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--wf)}
.wortkarte .name{font-size:26px;margin:2px 0 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wk-kopf{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:start;margin-bottom:12px}
.ring{position:relative;width:72px;height:72px;flex:none}
.ring svg{width:72px;height:72px;transform:rotate(-90deg)}
.ring circle{fill:none;stroke-width:6;stroke-linecap:round}.ring .hinten{stroke:rgba(var(--rgb-primary-text-color,0,0,0),.08)}.ring .vorn{transition:stroke-dashoffset .8s}
.ring span{position:absolute;inset:0 0 12px;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:500}
.ring small{position:absolute;left:0;right:0;bottom:19px;text-align:center;font-size:9px;color:var(--secondary-text-color)}
.mini{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:10px;font-size:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);color:var(--secondary-text-color);white-space:nowrap}
.mini[style*="--wf"]{background:color-mix(in srgb,var(--wf) 18%,transparent);color:var(--primary-text-color)}
.mini.gelb-f{background:rgba(var(--rgb-warning-color,255,152,0),.18);color:var(--warning-color,#ff9800)}.mini.rot-f{background:rgba(var(--rgb-error-color,244,67,54),.16);color:var(--error-color,#f44336)}
.tage{display:flex;align-items:flex-end;gap:3px;height:34px;margin:2px 0 6px}
.tage i{flex:1;border-radius:2px;background:rgba(var(--rgb-primary-text-color,0,0,0),.1);min-height:2px;opacity:.85}
.neu-karte{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:150px;color:var(--secondary-text-color);border:2px dashed var(--divider-color);background:none;box-shadow:none}
.neu-karte ha-icon{--mdc-icon-size:30px;width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(var(--rgb-primary-color,3,169,244),.12);color:var(--primary-color)}
.neu-karte:hover{border-color:var(--primary-color);color:var(--primary-color)}
.status{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:3px 9px;border-radius:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);color:var(--secondary-text-color)}
.status i{width:8px;height:8px;border-radius:50%;background:var(--disabled-color,#999)}
.status.an,.status.arbeitet{background:rgba(var(--rgb-success-color,76,175,80),.15);color:var(--success-color,#4caf50)}.status.an i,.status.arbeitet i{background:var(--success-color,#4caf50)}
.status.arbeitet i{animation:atmen 1.6s ease-in-out infinite}@keyframes atmen{50%{opacity:.3}}
.tr-name{font-size:18px;margin:10px 0 8px}
.messer-liste{display:flex;flex-direction:column;gap:7px}
.messer{display:flex;flex-direction:column;gap:4px;font-size:13px}
.spur{height:6px;border-radius:3px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden}.spur i{display:block;height:100%;background:var(--primary-color);border-radius:3px;transition:width .6s}
.spur.gruen i{background:var(--success-color,#4caf50)}.spur.gelb i{background:var(--warning-color,#ff9800)}.spur.rot i{background:var(--error-color,#f44336)}
.ger-liste{display:flex;flex-direction:column;gap:2px;margin-top:8px}
.ger{display:grid;grid-template-columns:auto 1fr auto;gap:6px;align-items:center;padding:6px 0;border-bottom:1px solid var(--divider-color);font-size:14px}.ger:last-child{border-bottom:0}
.ger-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ger-woerter{display:flex;gap:4px}
.reihe-liste{margin:8px 0 0;padding-left:20px;font-size:14px;line-height:1.9}
.leer-klein{display:flex;align-items:center;gap:8px;margin-top:12px;color:var(--secondary-text-color);font-size:13px}.leer-klein ha-icon{opacity:.6}
.steckbrief td:first-child{color:var(--secondary-text-color);width:40%}
@media (max-width:600px){.neu-karte{min-height:64px;flex-direction:row}.neu-karte ha-icon{width:36px;height:36px;--mdc-icon-size:24px}.held{grid-template-columns:auto 1fr;padding:16px}.held-knopf{grid-column:1/-1}.held-knopf .k{width:100%;justify-content:center}.held-ikon{width:44px;height:44px;border-radius:12px}.held-titel{font-size:19px}}
.tb-rahmen{overflow-x:auto}
table.tb{border-collapse:separate;border-spacing:3px;width:auto;min-width:100%}
table.tb th,table.tb td{border:0;padding:0;vertical-align:middle}
.tb-k{font-size:11px;font-weight:400;text-align:center;color:var(--secondary-text-color);padding:0 2px 4px!important;white-space:nowrap}
.tb-k.tb-sw{color:var(--primary-color);font-weight:600}
.tb-r{text-align:left;font-weight:400;font-size:13px;white-space:nowrap;padding-right:10px!important;color:var(--primary-text-color)}
.tb-z{min-width:42px;height:34px;text-align:center;font-size:13px;border-radius:6px;cursor:pointer;background:color-mix(in srgb,var(--tf) var(--ta),transparent);transition:transform .15s}
.tb-z:hover{transform:scale(1.08)}
.tb-z.leer{background:rgba(var(--rgb-primary-text-color,0,0,0),.04);cursor:default}.tb-z.leer:hover{transform:none}
.tb-z.auff{outline:2px solid var(--warning-color,#ff9800);outline-offset:-2px;font-weight:600}
.tb-muster{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px}.tb-muster.auff{outline:2px solid var(--warning-color,#ff9800);outline-offset:-2px}.tb-muster.sw{background:var(--primary-color)}
@media (max-width:600px){main{padding:12px 8px 80px}.eintrag{grid-template-columns:44px minmax(0,1fr);gap:10px;padding:10px}.spielen{width:44px;height:44px}button.k kbd{display:none}}
.raum{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:12px;padding:12px;border-radius:14px;background:linear-gradient(120deg,rgba(var(--rgb-primary-color,3,169,244),.07),rgba(var(--rgb-primary-color,3,169,244),.02))}
.raum.an{background:linear-gradient(120deg,rgba(var(--rgb-success-color,76,175,80),.12),rgba(var(--rgb-primary-color,3,169,244),.05))}
.raum-ikon{position:relative;width:44px;height:44px;flex:none;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(var(--rgb-primary-color,3,169,244),.16);color:var(--primary-color)}
.raum.an .raum-ikon{background:rgba(var(--rgb-success-color,76,175,80),.2);color:var(--success-color,#4caf50)}
.raum-ikon i{position:absolute;inset:0;border-radius:50%;border:2px solid currentColor;opacity:0;animation:raum-welle 3.2s ease-out infinite;animation-delay:calc(var(--i) * .64s)}
.raum:not(.an) .raum-ikon i:nth-child(n+3){display:none}
@keyframes raum-welle{0%{transform:scale(.8);opacity:.5}100%{transform:scale(1.9);opacity:0}}
.raum-text{flex:1 1 220px;min-width:0}.raum-warum{margin-top:3px;line-height:1.45}
.raum-knoepfe{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.raum-wurzel:empty{display:none}
.rd-hinter{position:fixed;inset:0;z-index:20;background:rgba(0,0,0,.45);backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px);animation:rd-hell .25s ease-out both}
.rd{position:fixed;z-index:21;left:50%;top:50%;width:min(460px,calc(100vw - 24px));max-height:calc(100vh - 24px);overflow:auto;transform:translate(-50%,-50%);border-radius:24px;background:var(--card-background-color,var(--ha-card-background,#fff));box-shadow:0 18px 60px rgba(0,0,0,.35);animation:rd-auf .35s cubic-bezier(.2,.9,.3,1.2) both;box-sizing:border-box}
.rd.geht{animation:rd-zu .25s ease-in both}
@keyframes rd-hell{from{opacity:0}}@keyframes rd-auf{from{opacity:0;transform:translate(-50%,-46%) scale(.94)}}@keyframes rd-zu{to{opacity:0;transform:translate(-50%,-48%) scale(.96)}}
.rd-kopf{display:flex;align-items:center;gap:12px;padding:16px 12px 6px 20px}.rd-kopf>ha-icon{color:var(--primary-color)}.rd-kopf>div{flex:1;min-width:0}.rd-kopf b{font-size:18px;font-weight:500}
.rd-kopf .ikon{width:40px;height:40px;border-radius:50%;border:0;background:none;color:inherit;cursor:pointer;display:flex;align-items:center;justify-content:center}
.rd-inhalt{padding:4px 20px 20px}.rd-schritt{animation:auftauchen .4s cubic-bezier(.2,.8,.3,1) both}
.rd-mitte{text-align:center;line-height:1.5}
.rd-knoepfe{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;margin-top:16px}
.rd-schritte{margin:8px 0;padding-left:22px;line-height:1.6}.rd-schritte li{margin:3px 0;animation:auftauchen .45s both}.rd-schritte li:nth-child(2){animation-delay:.12s}.rd-schritte li:nth-child(3){animation-delay:.24s}
.rd-tipp{line-height:1.5}
.rd-szene{display:block;width:100%;height:auto;color:var(--primary-color)}
.rd-szene .sz-boden{fill:var(--divider-color,rgba(127,127,127,.3))}
.rd-szene .sz-geraet rect{fill:var(--secondary-text-color);opacity:.55}.rd-szene .sz-geraet circle{fill:var(--primary-color);animation:atmen 1.6s ease-in-out infinite}
.rd-szene .sz-handy rect{fill:var(--primary-text-color);opacity:.75}.rd-szene .sz-handy .sz-schirm{fill:var(--primary-color);opacity:1}
.rd-szene .sz-person circle,.rd-szene .sz-person path{fill:none;stroke:var(--primary-text-color);stroke-width:3;stroke-linecap:round;opacity:.8}
.rd-szene .sz-l{transform-origin:250px 52px;animation:sz-klatsch 1.1s ease-in-out infinite}.rd-szene .sz-r{transform-origin:250px 56px;animation:sz-klatsch2 1.1s ease-in-out infinite}
@keyframes sz-klatsch{0%,100%{transform:rotate(-14deg)}45%{transform:rotate(2deg)}}@keyframes sz-klatsch2{0%,100%{transform:rotate(14deg)}45%{transform:rotate(-2deg)}}
.rd-szene .sz-ringe circle{fill:none;stroke:var(--primary-color);stroke-width:2;opacity:0;transform-box:fill-box;transform-origin:center;animation:sz-ring 1.1s ease-out infinite}
.rd-szene .sz-ringe circle:nth-child(2){animation-delay:.18s}.rd-szene .sz-ringe circle:nth-child(3){animation-delay:.36s}
@keyframes sz-ring{0%,40%{transform:scale(.4);opacity:0}48%{opacity:.9}100%{transform:scale(3.2);opacity:0}}
.rd-szene .sz-weg{fill:none;stroke:var(--primary-color);stroke-width:2;stroke-dasharray:5 7;opacity:.55;animation:sz-weg 1.1s linear infinite}@keyframes sz-weg{to{stroke-dashoffset:-24}}
.rd-zaehler{position:relative;width:160px;height:160px;margin:10px auto}.rd-zaehler svg{width:100%;height:100%;transform:rotate(-90deg)}
.rd-ring-grund{fill:none;stroke:rgba(var(--rgb-primary-color,3,169,244),.14);stroke-width:8}
.rd-ring{fill:none;stroke:var(--primary-color);stroke-width:8;stroke-linecap:round;stroke-dasharray:327;stroke-dashoffset:0;animation:rd-ablauf var(--dauer) linear forwards;filter:drop-shadow(0 0 6px rgba(var(--rgb-primary-color,3,169,244),.6))}
@keyframes rd-ablauf{to{stroke-dashoffset:327}}
.rd-zaehler b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:64px;font-weight:300;font-variant-numeric:tabular-nums}
.rd-zaehler b.tick{animation:rd-tick .5s cubic-bezier(.2,.9,.3,1.3)}@keyframes rd-tick{from{transform:scale(1.5);opacity:.2}}
.rd-live{position:relative;border-radius:16px;overflow:hidden;background:radial-gradient(ellipse at center,rgba(var(--rgb-primary-color,3,169,244),.16),rgba(var(--rgb-primary-color,3,169,244),.03))}
.rd-live canvas{display:block;width:100%;height:120px}
.rd-aufnahme{position:absolute;left:12px;top:8px;font-size:12px;color:var(--secondary-text-color)}
.rd-blitz{position:absolute;inset:0;background:radial-gradient(circle at center,rgba(255,255,255,.55),transparent 60%);animation:rd-blitz .7s ease-out forwards;pointer-events:none}@keyframes rd-blitz{from{opacity:1;transform:scale(.6)}to{opacity:0;transform:scale(1.6)}}
.rd-punkte{display:flex;justify-content:center;gap:14px;margin:14px 0 4px}
.rd-punkt{position:relative;width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(var(--rgb-primary-text-color,0,0,0),.06);color:var(--secondary-text-color);transition:background .3s,color .3s}
.rd-punkt.an{background:var(--primary-color);color:var(--text-primary-color,#fff);animation:rd-pop .5s cubic-bezier(.2,.9,.3,1.5)}
.rd-punkt.an::after{content:'';position:absolute;inset:0;border-radius:50%;border:2px solid var(--primary-color);animation:m-ring .9s ease-out forwards}
@keyframes rd-pop{0%{transform:scale(.6)}60%{transform:scale(1.2)}100%{transform:none}}
.rd-zeit{height:6px}
.rd-denkt{font-size:15px;min-height:24px}.rd-denkt.neu{animation:auftauchen .35s both}
.rd-ergebnis{display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;margin-top:6px}
.rd-kurven{width:100%;height:110px;border-radius:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.04)}
.rd-kurven line{stroke:var(--divider-color,rgba(127,127,127,.3))}
.rd-kurven polyline{fill:none;stroke:var(--c);stroke-width:2;stroke-linejoin:round;vector-effect:non-scaling-stroke;stroke-dasharray:1200;stroke-dashoffset:1200;animation:rd-zeichnen 1.4s cubic-bezier(.3,.7,.3,1) forwards;animation-delay:var(--v)}
@keyframes rd-zeichnen{to{stroke-dashoffset:0}}
.rd-kurven polygon{fill:var(--c);opacity:0;animation:rd-flaeche .9s ease-out forwards;animation-delay:var(--v)}@keyframes rd-flaeche{to{opacity:.05}}
.rd-wert{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:96px}.rd-wert b{font-size:30px;font-weight:400;font-variant-numeric:tabular-nums;animation:rd-pop .6s .3s both}
.rd-art{cursor:default}.rd-trocken{background:rgba(255,152,0,.18)}.rd-normal{background:rgba(var(--rgb-success-color,76,175,80),.2)}.rd-hallig{background:rgba(156,39,176,.2)}
.rd-fertig{display:flex;justify-content:center;margin:12px 0 0}.rd-fertig ha-icon{--mdc-icon-size:72px;color:var(--success-color,#4caf50);animation:rd-pop .6s cubic-bezier(.2,.9,.3,1.5) both}
.rd-fertig.rd-nein ha-icon{color:var(--warning-color,#ff9800)}
@media (max-width:420px){.rd-ergebnis{grid-template-columns:1fr}.rd{border-radius:20px}}
@media (prefers-reduced-motion:reduce){.raum-ikon i,.rd *,.rd,.rd-hinter{animation:none!important}.rd-kurven polyline{stroke-dashoffset:0}}
.schalter-raster{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin:4px 0 14px}
.kschalter{border-radius:16px;padding:12px 14px;background:rgba(var(--rgb-primary-text-color,0,0,0),.04);border:1px solid transparent;transition:background .35s,border-color .35s,box-shadow .35s}
.kschalter.an{background:linear-gradient(135deg,rgba(var(--rgb-primary-color,3,169,244),.14),rgba(var(--rgb-primary-color,3,169,244),.04));border-color:rgba(var(--rgb-primary-color,3,169,244),.25)}
.kschalter-kopf{display:flex;gap:12px;align-items:center;cursor:pointer}
.kschalter-ikon{width:40px;height:40px;flex:none;border-radius:12px;display:flex;align-items:center;justify-content:center;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);color:var(--secondary-text-color);transition:background .35s,color .35s,box-shadow .35s,transform .35s}
.kschalter.an .kschalter-ikon{background:var(--primary-color);color:var(--text-primary-color,#fff);box-shadow:0 4px 14px rgba(var(--rgb-primary-color,3,169,244),.45)}
.kschalter.an.neu .kschalter-ikon{animation:k-funke .6s cubic-bezier(.2,.9,.3,1.4)}@keyframes k-funke{0%{transform:scale(.7) rotate(-12deg)}60%{transform:scale(1.15) rotate(4deg)}100%{transform:none}}
.kschalter-text{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.kschalter-text b{font-weight:500}.kschalter-text .klein{line-height:1.4}
input.schieber{appearance:none;-webkit-appearance:none;flex:none;width:42px;height:24px;border-radius:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.22);position:relative;cursor:pointer;margin:0;transition:background .25s}
input.schieber::after{content:'';position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.35);transition:transform .25s cubic-bezier(.3,.9,.4,1.3)}
input.schieber:checked{background:var(--primary-color)}input.schieber:checked::after{transform:translateX(18px)}
input.schieber:disabled{opacity:.45;cursor:default}
.unter-schalter{display:flex;gap:10px;align-items:center;margin:10px 0 0 52px;padding-top:10px;border-top:1px solid rgba(var(--rgb-primary-text-color,0,0,0),.08);cursor:pointer;transition:opacity .3s}
.unter-schalter>span{display:flex;flex-direction:column;gap:2px;flex:1}.unter-schalter b{font-weight:500;font-size:14px}.unter-schalter.aus{opacity:.45}
.kachel-info{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:8px 0 0 52px}.kachel-info ha-icon{--mdc-icon-size:16px;color:var(--success-color,#4caf50)}
@media (max-width:500px){.schalter-raster{grid-template-columns:1fr}.unter-schalter,.kachel-info{margin-left:0}}
@media (prefers-reduced-motion:reduce){.kschalter-ikon{animation:none!important}}
main:not(.still) .ring .vorn{animation:ring-fuellen 1.1s cubic-bezier(.3,.8,.3,1) both}@keyframes ring-fuellen{from{stroke-dashoffset:var(--voll)}}
.weg{display:flex;align-items:flex-start;gap:0;margin:6px 0 4px}
.weg-station{flex:0 0 auto;width:120px;display:flex;flex-direction:column;align-items:center;text-align:center;gap:4px;cursor:pointer;color:inherit;text-decoration:none;border-radius:14px;padding:6px 4px}
.weg-station:hover{background:rgba(var(--rgb-primary-text-color,0,0,0),.04)}
.weg-station b{font-weight:500;font-size:14px}.weg-station .klein{line-height:1.35}
.weg-punkt{width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);color:var(--secondary-text-color);position:relative;transition:background .4s,color .4s}
main:not(.still) .weg-punkt{animation:rd-pop .55s cubic-bezier(.2,.9,.3,1.5) both;animation-delay:calc(var(--n) * .15s)}
.weg-station.erledigt .weg-punkt{background:rgba(var(--rgb-success-color,76,175,80),.2);color:var(--success-color,#4caf50)}
.weg-station.jetzt .weg-punkt{background:var(--primary-color);color:var(--text-primary-color,#fff);box-shadow:0 4px 16px rgba(var(--rgb-primary-color,3,169,244),.5)}
.weg-station.jetzt .weg-punkt::after{content:'';position:absolute;inset:-4px;border-radius:50%;border:2px solid var(--primary-color);animation:weg-puls 2s ease-out infinite}
@keyframes weg-puls{0%{transform:scale(.9);opacity:.8}100%{transform:scale(1.45);opacity:0}}
.weg-linie{flex:1 1 20px;min-width:16px;height:4px;margin-top:28px;border-radius:2px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden;position:relative}
.weg-linie i{position:absolute;inset:0;width:0;background:var(--success-color,#4caf50);border-radius:2px}
.weg-linie.durch i{width:100%}main:not(.still) .weg-linie.durch i{animation:balken-wachsen .5s ease-out both;animation-delay:calc(.15s + var(--n,0) * .15s)}
.weg-linie:not(.durch)::after{content:'';position:absolute;inset:0;background:repeating-linear-gradient(90deg,rgba(var(--rgb-primary-color,3,169,244),.5) 0 6px,transparent 6px 14px);background-size:28px 100%;opacity:.0}
.weg-linie.durch+.weg-station.jetzt{}
.weg .weg-linie.durch:has(+.weg-station.jetzt) i{background:linear-gradient(90deg,var(--success-color,#4caf50),var(--primary-color))}
.weg-mehr{margin-top:10px}.weg-mehr summary{cursor:pointer}.weg-mehr ol{margin:8px 0 0;padding-left:20px;line-height:1.6}
@media (max-width:560px){.weg{flex-direction:column;align-items:stretch}.weg-station{width:auto;flex-direction:row;text-align:left;gap:12px}.weg-station b{min-width:84px}.weg-linie{width:4px;min-width:0;height:18px;flex:0 0 18px;margin:0 0 0 26px}.weg-linie i{height:100%}}
@media (prefers-reduced-motion:reduce){.weg *,main .ring .vorn{animation:none!important}}
.rec-welle{width:100%;max-width:520px;border-radius:14px;overflow:hidden;background:radial-gradient(ellipse at center,rgba(var(--rgb-primary-color,3,169,244),.1),transparent 70%);transition:background .4s}
.rec-welle canvas{display:block;width:100%;height:72px}
.rec-welle:not(.an){opacity:.5}
.take.neu{animation:rd-pop .5s cubic-bezier(.2,.9,.3,1.5)}
.mini-form{width:48px;height:16px;margin-right:6px;fill:var(--primary-color)}.take.gegen .mini-form{fill:var(--error-color,#f44336)}
.rec-ziel{display:flex;align-items:center;gap:12px;margin-top:14px}
.ziel-ring{position:relative;width:44px;height:44px;flex:none}.ziel-ring svg{width:44px;height:44px;transform:rotate(-90deg)}
.ziel-ring circle{fill:none;stroke-width:4;stroke-linecap:round}.ziel-ring .hinten{stroke:rgba(var(--rgb-primary-text-color,0,0,0),.08)}.ziel-ring .vorn{stroke:var(--primary-color);transition:stroke-dashoffset .8s}
.ziel-ring.voll .vorn{stroke:var(--success-color,#4caf50)}
main:not(.still) .ziel-ring .vorn{animation:ring-fuellen 1.1s cubic-bezier(.3,.8,.3,1) both}
.ziel-ring span,.ziel-ring ha-icon{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:500}.ziel-ring ha-icon{--mdc-icon-size:20px;color:var(--success-color,#4caf50)}
ha-card.abschnitt{padding:0}
.abschnitt summary{display:flex;align-items:center;gap:14px;padding:16px;cursor:pointer;list-style:none;border-radius:var(--ha-card-border-radius,12px)}
.abschnitt summary::-webkit-details-marker{display:none}
.inklapp{margin-top:12px}.inklapp>summary{display:inline-flex;align-items:center;gap:6px;cursor:pointer;list-style:none;color:var(--primary-color);font-size:14px;padding:6px 10px 6px 4px;border-radius:999px}.inklapp>summary::-webkit-details-marker{display:none}
.inklapp>summary ha-icon{--mdc-icon-size:20px;transition:transform .25s}.inklapp[open]>summary ha-icon{transform:rotate(180deg)}.inklapp[open]>summary~*{animation:aufklappen .35s ease-out}
.abschnitt summary:hover{background:rgba(var(--rgb-primary-text-color,0,0,0),.03)}
.ab-ikon{width:40px;height:40px;flex:none;border-radius:12px;display:flex;align-items:center;justify-content:center;background:rgba(var(--rgb-primary-color,3,169,244),.14);color:var(--primary-color);transition:transform .35s}
.abschnitt details[open] .ab-ikon{transform:rotate(-8deg) scale(1.05)}
.ab-titel{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px}.ab-titel h2{margin:0}
.ab-pfeil{color:var(--secondary-text-color);transition:transform .3s cubic-bezier(.3,.8,.3,1)}
.abschnitt details[open] .ab-pfeil{transform:rotate(180deg)}
.ab-inhalt{padding:0 16px 16px}
.abschnitt details[open] .ab-inhalt{animation:aufklappen .35s ease-out}
.neu-vorschau{position:relative;overflow:hidden;margin:0 0 16px;padding:22px 20px;border-radius:var(--ha-card-border-radius,12px);text-align:center;background:linear-gradient(135deg,color-mix(in srgb,var(--farbe) 22%,transparent),color-mix(in srgb,var(--farbe) 6%,transparent));border:1px solid color-mix(in srgb,var(--farbe) 35%,transparent);transition:background .5s,border-color .5s}
.nv-wort{font-size:34px;font-weight:300;letter-spacing:.5px;margin:4px 0;color:var(--secondary-text-color);transition:color .4s,text-shadow .4s;word-break:break-word}
.neu-vorschau.da .nv-wort{color:var(--primary-text-color);text-shadow:0 0 22px color-mix(in srgb,var(--farbe) 70%,transparent)}
.nv-funken i{position:absolute;left:calc(8% + var(--i) * 9%);top:50%;width:6px;height:6px;border-radius:50%;background:var(--farbe);opacity:0}
.neu-vorschau.da .nv-funken i{animation:nv-funke 3.4s ease-in-out infinite;animation-delay:calc(var(--i) * .33s)}
@keyframes nv-funke{0%{opacity:0;transform:translateY(18px) scale(.4)}30%{opacity:.85}100%{opacity:0;transform:translateY(-46px) scale(1)}}
.neu-vorschau.funkt{animation:gefeiert 1.1s ease-out}.neu-vorschau.funkt .nv-wort{animation:rd-pop .55s cubic-bezier(.2,.9,.3,1.5)}
.neu-schritt{display:grid;grid-template-columns:30px 1fr;gap:0 12px;align-items:start;margin-top:6px}
.neu-nr{width:26px;height:26px;margin-top:12px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:500;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);color:var(--secondary-text-color);transition:background .35s,color .35s}
.neu-schritt.fertig .neu-nr{background:var(--primary-color);color:var(--text-primary-color,#fff);animation:rd-pop .45s cubic-bezier(.2,.9,.3,1.5)}
.neu-schritt h3{margin-top:14px}
button.k.gross-k{padding:11px 20px;font-size:15px;box-shadow:0 4px 16px rgba(var(--rgb-primary-color,3,169,244),.35)}
.rd.erschaffen{padding:22px 20px 26px;text-align:center}.rd.erschaffen .magie{color:var(--farbe)}
.er-wort{font-size:30px;font-weight:300;margin:6px 0;text-shadow:0 0 24px color-mix(in srgb,var(--farbe) 75%,transparent);animation:rd-pop .7s .3s cubic-bezier(.2,.9,.3,1.5) both}
@media (prefers-reduced-motion:reduce){.nv-funken,.neu-vorschau *{animation:none!important}}
.kurve{display:block;width:100%;height:auto;max-height:150px;margin:2px 0 10px;overflow:visible;color:var(--farbe)}
.ku-linie{fill:none;stroke:var(--farbe);stroke-width:3;stroke-linejoin:round;stroke-linecap:round;stroke-dasharray:2000;stroke-dashoffset:0}
main:not(.still) .ku-linie{animation:ku-zeichnen 1.6s cubic-bezier(.3,.7,.3,1) both}@keyframes ku-zeichnen{from{stroke-dashoffset:2000}}
.ku-flaeche{fill:var(--farbe);opacity:.1}main:not(.still) .ku-flaeche{animation:ku-flaeche 1.2s .5s ease-out both}@keyframes ku-flaeche{from{opacity:0}}
.ku-punkt circle{fill:var(--card-background-color,#1c1c1c);stroke:var(--farbe);stroke-width:3}.vf-wahl{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}.vf-wahl select{flex:1 1 160px;min-width:0}
.vf-hinweis{display:flex;gap:6px;align-items:flex-start;margin:6px 0 10px}.vf-hinweis ha-icon{--mdc-icon-size:18px;color:var(--success-color,#43a047);flex:none}.vf-hinweis.grob ha-icon{color:var(--warning-color,#ffa000)}
.vf-fuss{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}.vf-fuss ha-icon{--mdc-icon-size:18px}.vf-lauf{display:flex;gap:8px;align-items:center;margin:6px 0;font-weight:500}.vf-lauf ha-icon{color:var(--primary-color)}
.ku-punkt circle.nicht{stroke:var(--secondary-text-color);stroke-width:2;opacity:.8}.ku-punkt circle.aktiv{fill:var(--farbe);filter:drop-shadow(0 0 6px var(--farbe))}
main:not(.still) .ku-punkt{animation:auftauchen .4s both;animation-delay:calc(.25s + var(--n) * .2s)}
.kurve text{font-size:13px;fill:var(--primary-text-color);text-anchor:middle}.kurve text.ku-v{fill:var(--secondary-text-color);font-size:12px}
@media (prefers-reduced-motion:reduce){.kurve *{animation:none!important}}
/* Training: path of the spell and one live scene per step (1.0.36) */
.zauber{color:var(--farbe,var(--primary-color));margin:4px 0 6px}
.vz-duell{padding:12px 12px 10px;color:var(--primary-text-color)}.vz-oben{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center}
.vz-kopf{display:flex;flex-direction:column;align-items:center;gap:2px;padding:8px;border-radius:12px;background:rgba(var(--rgb-primary-text-color,0,0,0),.04);transition:box-shadow .4s}
.vz-kopf b{font-size:20px;color:var(--primary-text-color)}.vz-kopf.an{box-shadow:0 0 0 2px var(--farbe),0 0 18px color-mix(in srgb,var(--farbe) 45%,transparent)}
main:not(.still) .vz-kopf.an{animation:zp-puls 2.2s ease-in-out infinite}
.vz-mitte{display:flex;flex-direction:column;align-items:center;text-align:center}.vz-waage{width:140px;height:72px;overflow:visible}
.vz-waage .fuss,.vz-waage line,.vz-waage .schale path{stroke:var(--secondary-text-color);stroke-width:2.5;fill:none;stroke-linecap:round}
.vz-waage .schale path:last-of-type{fill:color-mix(in srgb,var(--farbe) 30%,transparent);stroke:var(--farbe)}.vz-waage text{font-size:12px;fill:var(--secondary-text-color);text-anchor:middle}
.vz-waage .achse{fill:var(--farbe)}.vz-waage .balken{transform-origin:80px 30px;transform:rotate(calc(var(--neig) * -1));transition:transform 1.2s cubic-bezier(.3,1.4,.5,1)}
main:not(.still) .vz-duell:not(.fertig) .vz-waage .balken{animation:vz-wippen 3s ease-in-out infinite}@keyframes vz-wippen{50%{transform:rotate(calc(var(--neig) * -1 + 2deg))}}
.vz-kette{display:flex;gap:6px;flex-wrap:wrap;justify-content:center;margin:10px 0 6px}
.vz-glied{position:relative;overflow:hidden;font-size:12px;padding:3px 10px;border-radius:999px;background:rgba(var(--rgb-primary-text-color,0,0,0),.05);color:var(--secondary-text-color)}
.vz-glied i{position:absolute;inset:0 auto 0 0;width:var(--f);background:color-mix(in srgb,var(--farbe) 30%,transparent);transition:width .8s}.vz-glied.durch{color:var(--primary-text-color);background:color-mix(in srgb,var(--farbe) 22%,transparent)}
.vz-glied.jetzt{color:var(--primary-text-color);box-shadow:inset 0 0 0 1.5px var(--farbe)}.vz-glied{isolation:isolate}.vz-glied i{z-index:-1}
.vz-tab{display:grid;gap:3px;margin-top:6px;align-content:start}.vz-z{display:grid;grid-template-columns:minmax(90px,1.3fr) 1fr 1fr;gap:10px;align-items:center;font-size:13px}
.vz-z.vz-zk{margin-top:8px;font-weight:500;color:var(--secondary-text-color);font-size:12px}.vz-z.vz-zk span:not(:first-child){text-align:center}
.vz-zelle{display:grid;grid-template-columns:1fr 46px;gap:6px;align-items:center}.vz-zelle i{display:block;height:8px;border-radius:4px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);position:relative;overflow:hidden}
.vz-zelle i::after{content:'';position:absolute;inset:0 auto 0 0;width:var(--w,0);background:var(--farbe);border-radius:4px;transition:width .9s cubic-bezier(.3,.7,.3,1)}
.vz-zelle span{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.vz-zelle.vz-leer span{color:var(--secondary-text-color)}
.vz-fehl{text-align:center;font-variant-numeric:tabular-nums}.vz-fehl.vz-leer{color:var(--secondary-text-color)}.vz-fehl.rot{color:var(--error-color,#db4437)}
.vz-fuss{margin-top:8px;text-align:center}
.vz-datei rect{fill:color-mix(in srgb,var(--farbe) 20%,transparent);stroke:var(--farbe);stroke-width:2}.vz-datei text{fill:var(--primary-text-color);font-size:18px;text-anchor:middle}
main:not(.still) .vz-datei{animation:vz-holen 2.4s ease-in-out infinite;animation-delay:calc(var(--d0) + var(--i) * .6s)}@keyframes vz-holen{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
.vz-ha rect{fill:rgba(var(--rgb-primary-text-color,0,0,0),.06);stroke:var(--secondary-text-color);stroke-width:2}.vz-ha path{fill:none;stroke:var(--farbe);stroke-width:3;stroke-linecap:round}
@media (max-width:520px){.vz-z{grid-template-columns:minmax(70px,1fr) 1fr 1fr;gap:6px;font-size:12px}.vz-zelle{grid-template-columns:1fr 40px}.vz-waage{width:100px;height:56px}}
.zp{display:flex;align-items:flex-start;gap:0;margin:2px 0 10px}
.zp-st{display:flex;flex-direction:column;align-items:center;gap:5px;flex:none;width:58px;text-align:center}
.zp-punkt{position:relative;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(var(--rgb-primary-text-color,0,0,0),.07);color:var(--secondary-text-color);transition:background .4s,color .4s}
.zp-punkt ha-icon{--mdc-icon-size:17px;position:relative}.zp-punkt svg{position:absolute;inset:-3px;width:38px;height:38px;transform:rotate(-90deg);overflow:visible}
.zp-punkt circle{fill:none;stroke-width:3;stroke-linecap:round}.zp-punkt .h{stroke:color-mix(in srgb,currentColor 20%,transparent)}.zp-punkt .v{stroke:currentColor;transition:stroke-dashoffset 1s cubic-bezier(.3,.8,.3,1);filter:drop-shadow(0 0 4px currentColor)}
.zp-st.durch .zp-punkt{background:color-mix(in srgb,var(--farbe) 85%,#000);color:#fff}
.zp-st.jetzt .zp-punkt{background:color-mix(in srgb,var(--farbe) 18%,transparent);color:var(--farbe);box-shadow:0 0 18px color-mix(in srgb,var(--farbe) 55%,transparent)}
main:not(.still) .zp-st.jetzt .zp-punkt{animation:zp-puls 2.2s ease-in-out infinite}@keyframes zp-puls{50%{box-shadow:0 0 26px color-mix(in srgb,var(--farbe) 80%,transparent)}}
.zp-name{font-size:11px;line-height:1.2;color:var(--secondary-text-color)}.zp-st.jetzt .zp-name{color:var(--primary-text-color);font-weight:500}
.zp-linie{flex:1;min-width:6px;height:3px;margin-top:15px;border-radius:2px;background:rgba(var(--rgb-primary-text-color,0,0,0),.1);overflow:hidden}.zp-linie i{display:block;height:100%;width:0;background:var(--farbe)}.zp-linie.durch i{width:100%}
main:not(.still) .zp-linie.durch i{animation:balken-wachsen .6s ease-out both;animation-delay:calc(var(--n,0) * .1s)}
.szene{border-radius:16px;background:radial-gradient(ellipse at 50% 120%,color-mix(in srgb,var(--farbe) 16%,transparent),transparent 70%),rgba(var(--rgb-primary-text-color,0,0,0),.035);padding:6px 8px 10px;overflow:hidden}
.szene svg{display:block;width:100%;height:110px;overflow:visible}.sz-text{text-align:center;font-size:13px;color:var(--secondary-text-color);font-variant-numeric:tabular-nums;min-height:18px}
.szene *{transform-box:fill-box}
.sz-kessel path{fill:color-mix(in srgb,var(--farbe) 35%,transparent);stroke:var(--farbe);stroke-width:2}.sz-kessel ellipse{fill:var(--farbe);opacity:.7;filter:drop-shadow(0 0 8px var(--farbe))}
.sz-dampf circle{fill:var(--farbe);opacity:0;animation:sz-dampf 2.4s ease-out infinite;animation-delay:calc(var(--d0) + var(--i,0) * .5s)}.sz-dampf circle:nth-child(2){--i:1}.sz-dampf circle:nth-child(3){--i:2}@keyframes sz-dampf{0%{opacity:.6;transform:translateY(0) scale(.6)}100%{opacity:0;transform:translateY(-34px) scale(1.4)}}
.sz-flieg{fill:var(--farbe);opacity:0;animation:sz-flieg 2.4s cubic-bezier(.45,0,.4,1) infinite;animation-delay:calc(var(--d0) + var(--i) * .6s)}@keyframes sz-flieg{0%{opacity:0;transform:none}20%{opacity:1}100%{opacity:0;transform:translate(calc(260px - var(--i) * 50px),40px) scale(.4) rotate(160deg)}}
.sz-aufn rect{fill:var(--farbe)}.sz-aufn{opacity:.35}.sz-aufn.drin{opacity:1}.sz-aufn.drin rect{filter:drop-shadow(0 0 4px var(--farbe))}
.sz-blase rect,.sz-blase path{fill:color-mix(in srgb,var(--farbe) 18%,transparent);stroke:color-mix(in srgb,var(--farbe) 55%,transparent);stroke-width:1.5}.sz-blase text{font-size:11px;text-anchor:middle;fill:var(--primary-text-color)}
.sz-blase{opacity:.15;transform-origin:center}.sz-blase.an{opacity:1}main:not(.still) .sz-blase.an{animation:sz-blase 3.6s ease-in-out infinite;animation-delay:calc(var(--d0) + var(--i) * .4s)}@keyframes sz-blase{0%,100%{transform:none}10%{transform:scale(1.12)}20%{transform:none}}
.sz-ohr path{fill:none;stroke:var(--farbe);stroke-width:3;stroke-linecap:round}.sz-ohr circle{fill:var(--farbe)}
.sz-wahl rect{fill:color-mix(in srgb,var(--farbe) 22%,transparent);stroke:var(--farbe)}.sz-wahl{opacity:0;animation:sz-rein 3s ease-in-out infinite;animation-delay:calc(var(--d0) + var(--i) * .5s)}
.sz-wahl.raus rect{fill:color-mix(in srgb,var(--error-color,#f44336) 25%,transparent);stroke:var(--error-color,#f44336)}.sz-wahl.raus{animation-name:sz-raus}
@keyframes sz-rein{0%{opacity:0;transform:none}25%{opacity:1;transform:translateX(150px)}60%{opacity:1;transform:translateX(150px)}100%{opacity:0;transform:translate(320px,0) scale(.6)}}
@keyframes sz-raus{0%{opacity:0;transform:none}25%{opacity:1;transform:translateX(150px)}60%{opacity:1;transform:translateX(150px)}100%{opacity:0;transform:translate(170px,60px) rotate(25deg)}}
.sz-welle rect{fill:var(--farbe);transform-origin:center;animation:m-welle 1.2s ease-in-out infinite;animation-delay:calc(var(--d0) - var(--i) * .09s)}.sz-pfeil path{fill:none;stroke:var(--secondary-text-color);stroke-width:2;stroke-linecap:round}
.sz-raster rect{fill:rgba(var(--rgb-primary-text-color,0,0,0),.07);transition:fill .6s}.sz-raster rect.an{fill:color-mix(in srgb,var(--farbe) calc(25% + var(--h) * 75%),transparent)}
.sz-netz line{stroke:var(--farbe);stroke-width:1;opacity:calc(var(--hell) * .55)}.sz-netz circle{fill:var(--farbe);opacity:var(--hell);filter:drop-shadow(0 0 calc(var(--hell) * 6px) var(--farbe))}
main:not(.still) .sz-netz circle{animation:m-feuern 2s ease-in-out infinite;animation-delay:calc(var(--d0) + var(--s) * .35s)}
.sz-kurve polyline{fill:none;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round;filter:drop-shadow(0 0 4px currentColor)}.sz-kurve .achse{stroke:var(--divider-color);stroke-width:1}.sz-kurve .ziel{stroke:var(--success-color,#4caf50);stroke-dasharray:4 5;opacity:.6}
.sz-kurve text{font-size:10px;fill:var(--secondary-text-color)}.sz-kopf{filter:drop-shadow(0 0 6px currentColor)}main:not(.still) .sz-kopf{animation:sz-kopf 1.6s ease-in-out infinite}@keyframes sz-kopf{50%{transform:scale(1.6)}}
.sz-lernt .h{fill:rgba(var(--rgb-primary-text-color,0,0,0),.08)}.sz-lernt .v{fill:var(--farbe);filter:drop-shadow(0 0 6px var(--farbe));transition:width 1s}
.sz-schild path{fill:rgba(var(--rgb-primary-text-color,0,0,0),.06);stroke:rgba(var(--rgb-primary-text-color,0,0,0),.2);stroke-width:2}.sz-schild .h{fill:none;stroke:transparent;stroke-width:3;stroke-linecap:round}
.sz-schild.an path:first-child{fill:color-mix(in srgb,var(--success-color,#4caf50) 25%,transparent);stroke:var(--success-color,#4caf50)}.sz-schild.an .h{stroke:var(--success-color,#4caf50)}
.sz-schild.jetzt path:first-child{stroke:var(--farbe);fill:color-mix(in srgb,var(--farbe) 15%,transparent)}main:not(.still) .sz-schild.jetzt path:first-child{animation:atmen 1.4s ease-in-out infinite}
.sz-ziel rect{fill:color-mix(in srgb,var(--farbe) 18%,transparent);stroke:var(--farbe);stroke-width:2}.sz-ziel circle{fill:var(--farbe)}
.sz-funke{fill:#fff;filter:drop-shadow(0 0 8px var(--farbe));animation:sz-funke 2.2s cubic-bezier(.45,0,.3,1) infinite;animation-delay:var(--d0)}@keyframes sz-funke{0%{transform:none;opacity:0}15%{opacity:1}100%{transform:translateX(380px);opacity:0}}
@media (max-width:600px){.zp-st{width:40px}.zp-name{display:none}.zp-st.jetzt{width:auto;min-width:40px}.zp-st.jetzt .zp-name{display:block;max-width:80px}.szene svg{height:90px}}
@media (prefers-reduced-motion:reduce){.zauber *,.szene *{animation:none!important}.sz-wahl,.sz-flieg{opacity:1}}
/* Figures as tiles, people as cards (1.0.36) */
.stat-raster{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:12px}.stat-raster.klein-stat{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0}
.stat{--sf:var(--primary-color);position:relative;padding:14px 16px;border-radius:18px;background:linear-gradient(145deg,color-mix(in srgb,var(--sf) 12%,var(--ha-card-background,var(--card-background-color))),var(--ha-card-background,var(--card-background-color)) 70%);border:1px solid color-mix(in srgb,var(--sf) 22%,var(--divider-color));overflow:hidden;transition:transform .2s,box-shadow .25s}
div.stat{background:linear-gradient(145deg,color-mix(in srgb,var(--sf) 10%,transparent),transparent 75%)}
.stat.kachel:hover{transform:translateY(-2px);box-shadow:0 8px 26px color-mix(in srgb,var(--sf) 25%,transparent)}
main:not(.still) .stat{animation:auftauchen .45s cubic-bezier(.2,.8,.3,1) both;animation-delay:calc(var(--n,0) * 70ms)}
.stat.ton-gruen{--sf:var(--success-color,#4caf50)}.stat.ton-gelb{--sf:var(--warning-color,#ff9800)}.stat.ton-rot{--sf:var(--error-color,#f44336)}.stat.ton-laeuft{--sf:#9c6bff}
.st-kopf{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--secondary-text-color)}.st-titel{min-width:0;overflow-wrap:anywhere;hyphens:auto}.st-ikon{width:28px;height:28px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex:none;color:var(--sf);background:color-mix(in srgb,var(--sf) 16%,transparent)}.st-ikon ha-icon{--mdc-icon-size:17px}
.st-mitte{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:8px 0 2px}.stat .wert{font-size:30px;font-weight:300;margin:0;font-variant-numeric:tabular-nums;color:var(--primary-text-color)}.klein-stat .stat .wert{font-size:24px}
.stat.ton-gelb .wert,.stat.ton-rot .wert{color:var(--sf)}
.st-ring{width:46px;height:46px;transform:rotate(-90deg);flex:none}.klein-stat .st-ring{width:38px;height:38px}.st-ring circle{fill:none;stroke-width:5;stroke-linecap:round}.st-ring .hinten{stroke:rgba(var(--rgb-primary-text-color,0,0,0),.08)}.st-ring .vorn{stroke:var(--sf);filter:drop-shadow(0 0 4px color-mix(in srgb,var(--sf) 60%,transparent))}
main:not(.still) .st-ring .vorn{animation:ring-fuellen 1.1s cubic-bezier(.3,.8,.3,1) both;animation-delay:calc(.15s + var(--n,0) * 70ms)}
.st-unter{font-size:12.5px;color:var(--secondary-text-color);line-height:1.4}
.stat.ton-laeuft .st-ikon ha-icon{animation:k-funke 2.4s ease-in-out infinite}
.personen{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin:6px 0}
.person{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:14px;background:rgba(var(--rgb-primary-text-color,0,0,0),.04)}main:not(.still) .person{animation:auftauchen .4s both;animation-delay:calc(var(--n) * 60ms)}
.p-kreis{width:32px;height:32px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-weight:600;color:#fff;background:radial-gradient(circle at 30% 25%,color-mix(in srgb,var(--pf) 70%,#fff),var(--pf))}
.p-mitte{flex:1;min-width:0}.p-mitte b{font-weight:500}.p-spur{height:6px;border-radius:3px;margin-top:5px;background:rgba(var(--rgb-primary-text-color,0,0,0),.08);overflow:hidden}.p-spur i{display:block;height:100%;width:var(--w);border-radius:3px;background:var(--pf)}main:not(.still) .p-spur i{animation:balken-wachsen .8s .2s cubic-bezier(.2,.8,.3,1) both}
@media (max-width:600px){.stat-raster{grid-template-columns:1fr 1fr;gap:8px}.stat{padding:12px}.stat .wert{font-size:24px}.st-ring{width:38px;height:38px}}
@media (prefers-reduced-motion:reduce){.stat,.st-ring .vorn,.person,.p-spur i,.st-ikon ha-icon{animation:none!important}}
.laeufe{position:relative;display:flex;flex-direction:column;gap:10px;margin-top:6px}
.laeufe::before{content:'';position:absolute;left:15px;top:8px;bottom:8px;width:2px;background:linear-gradient(var(--divider-color),transparent)}
.lauf{--lf:var(--secondary-text-color);position:relative;display:flex;gap:12px;align-items:flex-start}.lauf.gut{--lf:var(--success-color,#4caf50)}.lauf.gut2{--lf:var(--primary-color)}.lauf.rot{--lf:var(--error-color,#f44336)}
main:not(.still) .lauf{animation:auftauchen .4s both;animation-delay:calc(var(--n) * 60ms)}
.l-punkt{position:relative;z-index:1;width:32px;height:32px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;color:var(--lf);background:color-mix(in srgb,var(--lf) 18%,var(--ha-card-background,var(--card-background-color)));box-shadow:0 0 0 3px var(--ha-card-background,var(--card-background-color))}.l-punkt ha-icon{--mdc-icon-size:17px}
.lauf.gut .l-punkt{box-shadow:0 0 0 3px var(--ha-card-background,var(--card-background-color)),0 0 14px color-mix(in srgb,var(--lf) 50%,transparent)}
.l-inhalt{flex:1;min-width:0;padding:8px 12px;border-radius:14px;background:rgba(var(--rgb-primary-text-color,0,0,0),.035)}.l-titel{font-weight:500;color:var(--lf)}.l-v{font-size:12px;padding:1px 7px;border-radius:999px;background:color-mix(in srgb,var(--lf) 16%,transparent)}
.l-werte{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px;color:var(--secondary-text-color);margin:3px 0 1px}.l-werte b{color:var(--primary-text-color);font-weight:500}.l-werte ha-icon{--mdc-icon-size:15px;opacity:.6}
@media (prefers-reduced-motion:reduce){.lauf{animation:none!important}}
/* Prüfen: tiles 1.0.36 */
.pr-kopf{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:14px 16px;margin-bottom:12px;border-radius:18px;background:linear-gradient(120deg,color-mix(in srgb,var(--primary-color) 16%,transparent),color-mix(in srgb,var(--primary-color) 4%,transparent));border:1px solid color-mix(in srgb,var(--primary-color) 22%,transparent)}
.pr-ring .ziel-ring,.pr-ring .ziel-ring svg{width:54px;height:54px}.pr-ring .ziel-ring span{font-size:13px}.pr-ring.tick{animation:rd-pop .5s cubic-bezier(.2,.9,.3,1.5)}
.pr-text{display:flex;flex-direction:column;gap:2px;flex:1 1 220px;min-width:0}.pr-text b{font-size:17px;font-weight:500}
button.k.pr-alle{background:linear-gradient(120deg,var(--primary-color),color-mix(in srgb,var(--primary-color) 60%,#a855f7));box-shadow:0 4px 18px color-mix(in srgb,var(--primary-color) 40%,transparent);position:relative;overflow:hidden}
button.k.pr-alle::after{content:'';position:absolute;inset:0;background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.35) 50%,transparent 70%);background-size:250% 100%;animation:schimmer 3.5s linear infinite}
.pr-leiste{margin-bottom:6px}.pr-tasten{margin:0 0 12px;opacity:.75}
.pr-auto{display:inline-flex;align-items:center;gap:8px;cursor:pointer}.pr-auto input{position:absolute;opacity:0;width:1px;height:1px}
.pr-auto-s{width:34px;height:20px;border-radius:10px;background:rgba(var(--rgb-primary-text-color,0,0,0),.18);position:relative;transition:background .25s;flex:none}.pr-auto-s::after{content:'';position:absolute;left:3px;top:3px;width:14px;height:14px;border-radius:50%;background:#fff;transition:transform .25s cubic-bezier(.2,.9,.3,1.3);box-shadow:0 1px 3px rgba(0,0,0,.3)}
.pr-auto input:checked+.pr-auto-s{background:var(--primary-color)}.pr-auto input:checked+.pr-auto-s::after{transform:translateX(14px)}.pr-auto input:focus-visible+.pr-auto-s{outline:2px solid var(--primary-color);outline-offset:2px}
.liste{gap:12px}
.eintrag{display:block;padding:14px 16px 12px;border-radius:20px;border:1px solid color-mix(in srgb,var(--ef) 22%,var(--divider-color));background:linear-gradient(150deg,color-mix(in srgb,var(--ef) 9%,var(--ha-card-background,var(--card-background-color))) 0%,var(--ha-card-background,var(--card-background-color)) 55%);box-shadow:0 2px 14px rgba(0,0,0,.12);overflow:hidden;transition:border-color .25s,box-shadow .25s,transform .25s}
.eintrag::before{content:'';position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:0 3px 3px 0;background:var(--ef);box-shadow:0 0 12px var(--ef);opacity:.85}
main:not(.still) .eintrag{animation:auftauchen .45s cubic-bezier(.2,.8,.3,1) both;animation-delay:calc(var(--n,0) * 60ms)}
.eintrag.aktiv{border-color:color-mix(in srgb,var(--ef) 70%,transparent);box-shadow:0 0 0 1px color-mix(in srgb,var(--ef) 60%,transparent),0 8px 30px color-mix(in srgb,var(--ef) 22%,transparent);transform:translateY(-1px)}
.e-kopf{display:flex;align-items:center;gap:10px;min-width:0}
.e-ikon{width:34px;height:34px;border-radius:11px;display:flex;align-items:center;justify-content:center;flex:none;color:var(--ef);background:color-mix(in srgb,var(--ef) 16%,transparent)}.e-ikon ha-icon{--mdc-icon-size:19px}
.e-titel{display:flex;flex-direction:column;min-width:0;flex:1}.e-titel b{font-weight:500;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.e-titel .klein{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.e-meta{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.e-chip{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;font-size:12px;color:var(--secondary-text-color);background:rgba(var(--rgb-primary-text-color,0,0,0),.06);white-space:nowrap}.e-chip ha-icon{--mdc-icon-size:13px}.e-chip.e-test{color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 14%,transparent)}
.e-ton{display:flex;align-items:center;gap:12px;margin:12px 0 10px}
.eintrag .spielen{width:48px;height:48px;flex:none;color:#fff;background:radial-gradient(circle at 30% 25%,color-mix(in srgb,var(--ef) 70%,#fff),var(--ef));box-shadow:0 4px 16px color-mix(in srgb,var(--ef) 45%,transparent);transition:transform .2s}
.eintrag .spielen:hover{transform:scale(1.06)}.eintrag .spielen:active{transform:scale(.94)}.eintrag .spielen circle{stroke:#fff;stroke-width:2.5}
.eintrag .welle{flex:1;height:56px;margin:0;border-radius:14px;color:var(--ef);background:color-mix(in srgb,var(--ef) 7%,rgba(var(--rgb-primary-text-color,0,0,0),.03))}
.welle canvas{transform-origin:center;opacity:0}.welle.da canvas{opacity:1}main:not(.still) .welle.da canvas{animation:welle-auf .7s cubic-bezier(.2,.9,.3,1.2) both}@keyframes welle-auf{from{transform:scaleY(0);opacity:0}}
.welle .gespielt{position:absolute;left:0;top:0;bottom:0;width:0;background:linear-gradient(90deg,transparent,color-mix(in srgb,var(--ef) 22%,transparent));pointer-events:none;opacity:0;transition:opacity .25s}.welle .gespielt.an{opacity:1}
.eintrag .welle .spielkopf{background:#fff;width:2px;box-shadow:0 0 10px 2px var(--ef)}
.ki{border-radius:14px;padding:9px 12px;margin-bottom:8px;background:rgba(var(--rgb-primary-text-color,0,0,0),.04);display:flex;flex-direction:column;gap:5px}
.ki-zeile{display:flex;align-items:flex-start;gap:8px;font-size:13px;color:var(--secondary-text-color)}.ki-zeile strong{color:var(--primary-text-color);font-weight:500}.ki-zeile ha-icon{--mdc-icon-size:17px;flex:none;color:#b388ff;margin-top:-1px}.ki-ohr ha-icon{color:var(--secondary-text-color)}
main:not(.still) .ki-zeile:first-child ha-icon{animation:ki-funkeln 2.8s ease-in-out infinite}@keyframes ki-funkeln{0%,70%,100%{transform:none;filter:none}80%{transform:scale(1.25) rotate(12deg);filter:drop-shadow(0 0 4px #b388ff)}}
.e-mess{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.e-spur{position:relative;flex:1 1 140px;max-width:300px;height:8px;border-radius:4px;background:rgba(var(--rgb-primary-text-color,0,0,0),.1)}
.e-spur i{position:absolute;left:0;top:0;bottom:0;width:var(--w);border-radius:4px;background:linear-gradient(90deg,color-mix(in srgb,var(--ef) 45%,transparent),var(--ef))}.e-spur.drueber i{box-shadow:0 0 8px var(--ef)}
main:not(.still) .e-spur i{animation:balken-wachsen .9s .2s cubic-bezier(.2,.8,.3,1) both}
.e-spur b{position:absolute;top:-4px;bottom:-4px;width:2px;margin-left:-1px;border-radius:1px;background:var(--primary-text-color);opacity:.7}
.eintrag .gehoert{margin:0 0 8px}.marke ha-icon{--mdc-icon-size:12px;margin-right:3px}
.eintrag .knoepfe{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between}
.entscheid{display:flex;gap:8px;flex-wrap:wrap}.entscheid button.k{padding:10px 18px;font-weight:500;border-radius:14px;transition:transform .15s,box-shadow .25s,background .25s}.entscheid button.k:active{transform:scale(.95)}
.entscheid button.k.empfohlen{position:relative;box-shadow:0 0 0 1.5px currentColor}
.entscheid button.k.empfohlen::before{content:'✦';position:absolute;top:-7px;right:-5px;width:16px;height:16px;border-radius:50%;font-size:10px;line-height:16px;text-align:center;color:#fff;background:#9c6bff;box-shadow:0 0 8px #9c6bff}
main:not(.still) .entscheid button.k.empfohlen{animation:empfohlen 2.6s ease-in-out infinite}@keyframes empfohlen{50%{box-shadow:0 0 0 1.5px currentColor,0 0 16px -2px currentColor}}
.e-mehr{display:flex;gap:2px;align-items:center;flex-wrap:wrap}.e-mehr button.k.leise{padding:8px 10px;border-radius:12px}.e-mehr button.k.leise:hover{background:rgba(var(--rgb-primary-text-color,0,0,0),.07)}.e-mehr .rechts{margin-left:6px}
.e-mehr select{border-radius:12px}
@media (max-width:600px){.pr-tasten{display:none}.eintrag{padding:12px 12px 10px}.e-meta .e-chip:first-child{display:none}.e-ton{gap:10px}.eintrag .spielen{width:44px;height:44px}.entscheid{width:100%}.entscheid button.k{flex:1;justify-content:center;padding:11px 10px}.e-mehr{width:100%;justify-content:space-between}.e-mehr .txt{display:none}.e-mehr .rechts{margin-left:auto}}
@media (prefers-reduced-motion:reduce){.eintrag,.welle canvas,.e-spur i,.ki-zeile ha-icon,.entscheid button.k,button.k.pr-alle::after,.pr-ring{animation:none!important}}
`;

class SprachmodellPanel extends HTMLElement {
  constructor() {
    super();
    this._vglOffen = new Set();
    this._vglWahl = {};
    this.attachShadow({ mode: 'open' });
    this._daten = null;
    this._liste = null;
    this._filter = { echo: '', verlauf: 'bewertet', seite: 0, urteil: '', sort: '' };
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
  _schritt(x) { if (!x) return ''; const i = x.indexOf(':'), k = i < 0 ? x : x.slice(0, i), d = i < 0 ? '' : x.slice(i + 1); const tr = ((this._daten || {}).wort || {}).training || {}, v = tr.vergleich || tr.vergleich_fertig || {}; const s = this.t('s_' + k, { d, a: v.a ?? '?', b: v.b ?? '?' }); return s === 's_' + k ? x : (k === 'aufnahmen' && d ? s + ' (' + d + ')' : s); }
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
    if (erstes) { TEXTE_DA.then(() => { this._bereit = true; this._aufbauen(); this._laden(); }); return; }
    if (!this._bereit) return;
    const zust = Object.values(h.entities || {}).filter((e) => e.platform === 'sprachmodell').map((e) => h.states[e.entity_id]).filter(Boolean);
    // last_contact changes with every trainer report: it only refreshes the training page (live log), not lists you work in
    const st = zust.map((s) => s.state + JSON.stringify({ ...s.attributes, last_contact: undefined })).join('|');
    const live = zust.map((s) => s.attributes.last_contact || '').join('|');
    if (st !== this._stempel) { const war = this._stempel; this._stempel = st; this._liveStempel = live; if (war && !this._rec.an && !this._bearbeitet()) this._laden(); }
    else if (live !== this._liveStempel) { this._liveStempel = live; if (this._reiter === 'training' && !this._bearbeitet()) this._laden(); }
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
      if (this._bereit) { this._kopfZeichnen(); this._laden(); }
    }
  }
  set panel(p) { this._panel = p; }
  connectedCallback() {
    // values Home Assistant set before the element was defined would hide the setters: hand them over again
    for (const k of ['panel', 'narrow', 'route', 'hass']) {
      if (Object.prototype.hasOwnProperty.call(this, k)) { const v = this[k]; delete this[k]; this[k] = v; }
    }
    window.addEventListener('keydown', this._taste);
  }
  disconnectedCallback() { window.removeEventListener('keydown', this._taste); this._audio.pause(); this._recStopp(); if (this._raumD) this._raumSchliessen(); }

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
<div class="leisten"><nav class="woerter"></nav><nav class="reiter"></nav></div><main></main><div class="raum-wurzel"></div><input type="file" id="datei" accept=".zip,application/zip,.wav,audio/wav" hidden multiple>`;
    const m = this.shadowRoot.querySelector('ha-menu-button'); m.hass = this._hass; m.narrow = this._narrow;
    this._reiter = this._reiter || 'zentrale';
    this.shadowRoot.addEventListener('click', (e) => this._klick(e));
    this.shadowRoot.addEventListener('change', (e) => this._aenderung(e));
    this.shadowRoot.addEventListener('input', (e) => this._eingabe(e));
    // which trainer entries are open survives a redraw ("toggle" does not bubble, so listen while capturing)
    this.shadowRoot.addEventListener('toggle', (e) => {
      const d = e.target;
      if (d.dataset && d.dataset.abschnitt) { this._merk('abschnitt.' + d.dataset.abschnitt, d.open ? '1' : '0'); return; }
      if (!d.classList || !d.classList.contains('tr-eintrag')) return;
      this._trOffen = this._trOffen || new Set([...this.shadowRoot.querySelectorAll('details.tr-eintrag[open]')].map((x) => x.dataset.tid));
      if (d.open) this._trOffen.add(d.dataset.tid); else this._trOffen.delete(d.dataset.tid);
    }, true);
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
      if (this._daten.wort && this._reiter === 'verlauf') { const z = this._filter.zelle; this._liste = await this._api('GET', (z ? `liste?filter=alle&zeile=${z.zeile}&von=${z.von}&bis=${z.bis}&seite=${this._filter.seite}` : `liste?filter=${this._filter.verlauf}&seite=${this._filter.seite}${this._filter.verlauf === 'bewertet' ? (this._filter.urteil ? '&art=' + this._filter.urteil : '') + (this._filter.sort ? '&sort=' + this._filter.sort : '') : ''}`) + ew + (z ? (z.echo ? '&echo=' + encodeURIComponent(z.echo) : '') : ef)); }
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
    // Home Assistant may scroll the window or an element around the panel: keep every scroll position, and the
    // page's height while it is redrawn, so a refresh (the training page refreshes with every trainer report)
    // never jumps back to the top
    const positionen = this._scrollPositionen();
    main.style.minHeight = main.offsetHeight + 'px';
    const log = main.querySelector('.protokoll'), oben = !log || log.scrollTop < 30, logPos = log ? log.scrollTop : 0;
    // grow-in animations only when a page is opened, not each time its data refreshes
    const seite = this._reiter + '|' + this._wortId;
    main.classList.toggle('still', this._gezeigt === seite);
    this._gezeigt = seite;
    main.innerHTML = f.call(this);
    const logNeu = main.querySelector('.protokoll'); if (logNeu) logNeu.scrollTop = oben ? 0 : logPos;
    if (this._reiter === 'pruefen') this._markieren(false);
    if (main.querySelector('[data-welle]')) this._wellen(main);
    if (this._reiter === 'aufnehmen') this._recZeichnen();
    if (!main.classList.contains('still')) this._hochzaehlen(main);
    positionen.forEach(([el, y]) => { if (el.scrollTop !== y) el.scrollTop = y; });
    // cards fill in their content a moment later: let go of the height only once they have
    requestAnimationFrame(() => { main.style.minHeight = ''; });
  }

  // big numbers count up when a page opens (not when its data refreshes)
  _hochzaehlen(wurzel) {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    wurzel.querySelectorAll('.wert, .ring span, .rd-wert b').forEach((el) => {
      if (el.children.length) return;
      const m = /^(\D{0,2}?)(\d+(?:[.,]\d+)?)(.*)$/.exec(el.textContent.trim()); if (!m) return;
      const ziel = parseFloat(m[2].replace(',', '.')), stellen = (m[2].split(/[.,]/)[1] || '').length, komma = m[2].includes(',') ? ',' : '.';
      if (!(ziel > 0) || (m[1] && m[1] !== 'v')) return;
      const start = performance.now(), dauer = 900;
      const schritt = (jetzt) => {
        const f = Math.min(1, (jetzt - start) / dauer), x = ziel * (1 - Math.pow(1 - f, 3));
        el.textContent = m[1] + (stellen ? x.toFixed(stellen).replace('.', komma) : String(Math.round(x))) + m[3];
        if (f < 1 && el.isConnected) requestAnimationFrame(schritt);
      };
      requestAnimationFrame(schritt);
    });
  }

  _scrollPositionen() {
    const liste = [];
    for (let el = this; el; el = el.assignedSlot || el.parentNode || el.host) {
      if (el.nodeType === 1 && el.scrollTop > 0) liste.push([el, el.scrollTop]);
    }
    const se = document.scrollingElement;
    if (se && se.scrollTop > 0 && !liste.some(([el]) => el === se)) liste.push([se, se.scrollTop]);
    return liste;
  }

  // ---------- Zentrale ----------
  _fertigText(t, kurz) {
    if (t.restzeit_min == null) return '';
    const u = new Date(Date.now() + t.restzeit_min * 60000).toLocaleTimeString(this._loc, { hour: '2-digit', minute: '2-digit' });
    return this.t(kurz ? 't_fertig_kurz' : t.phase === 'training' ? 't_fertig_training' : 't_fertig', { u });
  }

  // a figure as a small glowing tile: icon, number that counts up, optional ring (0..1) and a line below
  _stat({ icon, titel, wert, unter = '', ton = '', ring = null, reiter = '', titelHilfe = '', n = 0 }) {
    const u = 2 * Math.PI * 19, a = ring == null ? null : Math.max(0, Math.min(1, ring));
    return `<${reiter ? 'ha-card' : 'div'} class="stat ${reiter ? 'kachel' : ''} ${ton ? 'ton-' + ton : ''}" ${reiter ? `data-reiter="${reiter}"` : ''} ${titelHilfe ? `title="${esc(titelHilfe)}"` : ''} style="--n:${n}">
<div class="st-kopf"><span class="st-ikon"><ha-icon icon="${icon}"></ha-icon></span><span class="st-titel">${esc(titel)}</span></div>
<div class="st-mitte"><div class="wert">${esc(wert)}</div>${a == null ? '' : `<svg class="st-ring" viewBox="0 0 46 46"><circle cx="23" cy="23" r="19" class="hinten"/><circle cx="23" cy="23" r="19" class="vorn" style="stroke-dasharray:${u.toFixed(1)};stroke-dashoffset:${(u * (1 - a)).toFixed(1)};--voll:${u.toFixed(1)}"/></svg>`}</div>
${unter ? `<div class="st-unter">${unter}</div>` : ''}</${reiter ? 'ha-card' : 'div'}>`;
  }

  _quoteRing(q, farbe) {
    const r = 25, u = 2 * Math.PI * r, a = q == null ? 0 : Math.max(0, Math.min(1, q));
    return `<div class="ring"><svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="${r}" class="hinten"></circle>${q == null ? '' : `<circle cx="32" cy="32" r="${r}" class="vorn" style="stroke:${farbe};stroke-dasharray:${u.toFixed(1)};stroke-dashoffset:${(u * (1 - a)).toFixed(1)};--voll:${u.toFixed(1)}"></circle>`}</svg><span>${q == null ? '–' : Math.round(a * 100) + '%'}</span><small>${esc(this.t('h_erkennt'))}</small></div>`;
  }

  _tage(tage, farbe) {
    const m = Math.max(1, ...tage);
    return `<div class="tage" title="${esc(this.t('h_tage_titel'))}">${tage.map((n) => `<i style="height:${n ? Math.round(14 + 86 * n / m) : 6}%;${n ? `background:${farbe}` : ''}" title="${n}"></i>`).join('')}</div>`;
  }

  _messer(name, wert, max, text, warn) {
    const p = max ? Math.max(0, Math.min(100, (wert / max) * 100)) : 0;
    const klasse = warn == null ? '' : p >= warn[1] ? 'rot' : p >= warn[0] ? 'gelb' : 'gruen';
    return `<div class="messer"><div class="zeile weit"><span>${esc(name)}</span><span class="klein">${esc(text)}</span></div><div class="spur ${klasse}"><i style="width:${p.toFixed(0)}%"></i></div></div>`;
  }

  _held() {
    const d = this._daten, ws = d.woerter, tr = d.trainer;
    const lauf = ws.find((w) => LAEUFT.includes((w.training || {}).phase));
    let icon, titel, text, knopf = '', farbe, art = '', balken = '';
    if (lauf) {
      const t = lauf.training;
      farbe = this._farbe(lauf); icon = 'mdi:school-outline'; art = 'laeuft';
      titel = this.t('h_lauf', { w: lauf.wort });
      text = [this._schritt(t.schritt) || this.t('p_' + t.phase), t.prozent != null ? Math.round(t.prozent) + ' %' : '', this._fertigText(t, true)].filter(Boolean).join(' · ');
      balken = `<div class="fortschritt"><i style="width:${t.prozent ?? 3}%;background-color:${farbe}"></i></div>`;
      knopf = `<button class="k haupt" data-reiter="training" data-wort="${esc(lauf.id)}"><ha-icon icon="mdi:chart-timeline-variant"></ha-icon>${esc(this.t('h_ansehen'))}</button>`;
    } else if ((d.nach_neustart || []).length) {
      const namen = d.nach_neustart.map((id) => (ws.find((w) => w.id === id) || {}).wort).filter(Boolean).join(', ');
      farbe = 'var(--primary-color)'; icon = 'mdi:restart';
      titel = this.t('h_neustart', { w: namen }); text = this.t('h_neustart_text');
      knopf = this._admin ? `<button class="k haupt" data-a="reparaturen"><ha-icon icon="mdi:restart"></ha-icon>${esc(this.t('h_neustart_knopf'))}</button>` : '';
    } else if (d.offen) {
      const w = ws.filter((x) => x.offen).sort((x, y) => y.offen - x.offen)[0];
      farbe = 'var(--warning-color,#ff9800)'; icon = 'mdi:playlist-check';
      titel = this.t(d.offen === 1 ? 'h_offen1' : 'h_offen', { n: d.offen });
      text = this.t('h_offen_text');
      knopf = `<button class="k haupt" data-reiter="pruefen" data-wort="${esc(w.id)}"><ha-icon icon="mdi:play"></ha-icon>${esc(this.t('h_pruefen'))}</button>`;
    } else if (!tr.online && (d.reihe.length || ws.some((w) => (w.training || {}).phase === 'wartet'))) {
      farbe = 'var(--error-color,#f44336)'; icon = 'mdi:lan-disconnect';
      titel = this.t('h_trainer_weg'); text = this.t('h_trainer_weg_text');
      knopf = `<button class="k" data-reiter="einstellungen"><ha-icon icon="mdi:cog-outline"></ha-icon>${esc(this.t('h_einrichten'))}</button>`;
    } else {
      farbe = 'var(--success-color,#4caf50)'; icon = 'mdi:check-circle-outline';
      titel = this.t('h_bereit'); text = this.t(ws.some((w) => Object.keys(w.geraete || {}).length) ? 'h_bereit_text' : 'h_bereit_ohne');
    }
    const summe = (k) => ws.reduce((n, w) => n + (w[k] || 0), 0);
    const pillen = [
      ['mdi:waveform', this.t(ws.length === 1 ? 'h_wort1' : 'h_woerter', { n: ws.length })],
      ['mdi:speaker-wireless', this.t(d.geraete.length === 1 ? 'z_geraet' : 'z_geraete', { n: d.geraete.length })],
      ['mdi:microphone-outline', this.t('h_aufnahmen', { n: summe('aufnahmen') })],
      ['mdi:check-all', this.t('h_bewertet', { n: summe('bewertet') })],
    ].map(([i, x]) => `<span class="pille"><ha-icon icon="${i}"></ha-icon>${esc(x)}</span>`).join('');
    return `<ha-card class="held ${art}" style="--hf:${farbe}"><div class="held-ikon"><ha-icon icon="${icon}"></ha-icon></div><div class="held-text"><div class="held-titel">${esc(titel)}</div><div class="klein">${esc(text)}</div>${balken}<div class="pillen">${pillen}</div></div>${knopf ? `<div class="held-knopf">${knopf}</div>` : ''}</ha-card>`;
  }

  _trainerKachel() {
    const tr = this._daten.trainer, i = tr.info || {}, l = tr.last || {};
    const laeuft = this._daten.woerter.some((w) => LAEUFT.includes((w.training || {}).phase));
    const n = (tr.liste || []).length;
    const status = n > 1 ? this._trainerStatus() : tr.online ? (laeuft ? this.t('h_tr_arbeitet') : this.t('z_trainer_an')) : tr.kontakt ? this.t('z_trainer_aus') : this.t('z_trainer_nie');
    let inhalt = '';
    if (tr.online) {
      const ram = l.ram_gb || i.ram_gb;
      const liste = tr.liste || [], haupt = liste.find((t) => t.laeuft.length) || liste.find((t) => t.id === tr.ziel) || liste.find((t) => t.online);
      inhalt = (n > 1 && haupt ? `<div class="klein" style="margin-top:4px">${esc(haupt.name)}</div>` : '') + '<div class="messer-liste">'
        + (l.cpu != null ? this._messer(this.t('h_tr_cpu'), l.cpu, 100, `${l.cpu} % · ${l.kerne || i.cpu || '?'} ${this.t('h_tr_kerne')}`) : i.cpu ? this._messer(this.t('h_tr_cpu'), 0, 100, `${i.cpu} ${this.t('h_tr_kerne')}`) : '')
        + (ram ? this._messer(this.t('h_tr_ram'), l.ram_belegt_gb ?? 0, ram, l.ram_belegt_gb != null ? `${this._zahl(l.ram_belegt_gb, 1)} / ${this._zahl(ram, 0)} GB` : `${this._zahl(ram, 0)} GB`, [70, 90]) : '')
        + (i.platz_gb ? this._messer(this.t('h_tr_platte'), i.platz_gb - (l.platz_frei_gb ?? i.platz_frei_gb), i.platz_gb, this.t('h_tr_frei', { n: this._zahl(l.platz_frei_gb ?? i.platz_frei_gb, 0) }), [75, 90]) : '')
        + '</div>';
      if (tr.engpass) inhalt += `<div class="hinweis" style="margin:10px 0 0">${esc(this.t('h_tr_engpass_' + tr.engpass))}</div>`;
    } else {
      inhalt = `<div class="klein" style="margin-top:6px;line-height:1.5">${esc(tr.kontakt ? this.t('h_tr_weg', { z: this._zeit(tr.kontakt) }) : this.t('h_tr_nie'))}</div>`;
    }
    return `<ha-card class="kachel" data-reiter="einstellungen"><div class="zeile weit"><div class="klein"><ha-icon icon="mdi:school-outline"></ha-icon> ${esc(this.t('z_trainer'))}</div><span class="status ${tr.online ? (laeuft ? 'arbeitet' : 'an') : ''}"><i></i>${esc(status)}</span></div>
<div class="tr-name">${esc(i.name || this.t('z_trainer'))}${i.version ? ` <span class="klein">v${esc(i.version)}</span>` : ''}</div>${inhalt}</ha-card>`;
  }

  _geraeteKachel() {
    const d = this._daten;
    const zeilen = d.geraete.map((g) => {
      const woerter = Object.values(g.plaetze).map((p) => d.woerter.find((w) => w.id === p.wort)).filter(Boolean);
      return `<div class="ger"><span class="punkt ${g.fehler ? '' : 'an'}" ${g.fehler ? 'style="background:var(--error-color,#f44336)"' : ''}></span><span class="ger-name">${esc(g.name)}</span><span class="ger-woerter">${woerter.map((w) => `<span class="mini" style="--wf:${this._farbe(w)}">${esc(w.wort)}</span>`).join('') || `<span class="klein">${esc(this.t('h_ger_frei'))}</span>`}</span></div>`;
    }).join('');
    return `<ha-card class="kachel" data-reiter="geraete"><div class="zeile weit"><div class="klein"><ha-icon icon="mdi:speaker-wireless"></ha-icon> ${esc(this.t('z_geraete_titel'))}</div><span class="klein">${d.geraete.length}</span></div>${zeilen ? `<div class="ger-liste">${zeilen}</div>` : `<div class="klein" style="margin-top:8px">${esc(this.t('z_geraete_leer'))}</div>`}</ha-card>`;
  }

  _reiheKachel() {
    const d = this._daten, reihe = d.reihe.map((id) => d.woerter.find((w) => w.id === id)).filter(Boolean);
    const nachts = d.woerter.some((w) => w.nachts);
    return `<ha-card class="kachel" data-reiter="einstellungen"><div class="zeile weit"><div class="klein"><ha-icon icon="mdi:format-list-numbered"></ha-icon> ${esc(this.t('z_reihe'))}</div><span class="klein">${reihe.length}</span></div>
${reihe.length ? `<ol class="reihe-liste">${reihe.map((w) => `<li><span class="punkt" style="background:${this._farbe(w)}"></span>${esc(w.wort)}</li>`).join('')}</ol>` : `<div class="leer-klein"><ha-icon icon="mdi:sleep"></ha-icon><span>${esc(this.t('z_reihe_leer'))}</span></div>`}
${nachts ? `<div class="klein" style="margin-top:8px"><ha-icon icon="mdi:weather-night" style="--mdc-icon-size:16px"></ha-icon> ${esc(this.t('h_nachts', { u: String(d.einstellungen.uhrzeit).slice(0, 5) }))}</div>` : ''}</ha-card>`;
  }

  _wortKarte(w, i) {
    const t = w.training || {}, laeuft = LAEUFT.includes(t.phase), n = Object.keys(w.geraete || {}).length, f = this._farbe(w, i);
    const tage = w.tage || [], summe = tage.reduce((a, b) => a + b, 0);
    const unten = laeuft
      ? `<div class="fortschritt" style="margin:4px 0 6px"><i style="width:${t.prozent ?? 3}%;background-color:${f}"></i></div><div class="zeile weit klein"><span>${esc(this._schritt(t.schritt) || this.t('p_' + t.phase))}${t.prozent != null ? ' · ' + Math.round(t.prozent) + ' %' : ''}</span><span>${esc(this._fertigText(t, true))}</span></div>${this._tage(tage, f)}<div class="klein">${esc(this.t('h_tage', { n: summe }))}</div>`
      : `${this._tage(tage, f)}<div class="zeile weit klein"><span>${esc(this.t('h_tage', { n: summe }))}</span><span>${w.fehlausloeser != null ? esc(this.t('z_fehl', { n: this._zahl(w.fehlausloeser, 1) })) : ''}</span></div>`;
    const status = t.phase === 'fehler' ? `<span class="mini rot-f">${esc(this.t('p_fehler'))}</span>` : t.phase === 'wartet' || w.in_reihe ? `<span class="mini">${esc(this.t('h_in_reihe'))}</span>` : '';
    return `<ha-card class="kachel wortkarte ${laeuft ? 'laeuft' : ''}" style="--wf:${f}" data-reiter="${laeuft ? 'training' : w.offen ? 'pruefen' : 'uebersicht'}" data-wort="${esc(w.id)}">
<div class="wk-kopf"><div style="min-width:0"><div class="klein">${esc(SPRACHNAMEN[this._spr][w.sprache] || this._sprachname(w.sprache))} · ${esc(n === 1 ? this.t('z_geraet') : n ? this.t('z_geraete', { n }) : this.t('z_kein_geraet'))}</div><div class="name">${esc(w.wort)}</div>
<div class="zeile" style="gap:6px"><span class="mini">${w.aktiv ? 'v' + w.aktiv : esc(this.t('z_keine_version'))}</span>${w.offen ? `<span class="mini gelb-f">${esc(this.t('h_offen_kurz', { n: w.offen }))}</span>` : ''}${status}</div></div>${this._quoteRing(w.trefferquote, f)}</div>
${unten}</ha-card>`;
  }

  // what "thorough" costs on this trainer: its hardware, the last run's duration and when a night run would end
  _gruendlichInfo(w, e) {
    const tr = this._daten.trainer, liste = tr.liste || [];
    // the trainer this card is about: the chosen one, else the one that gets the next run, else the main one
    const wahl = this._daten.einstellungen.trainer_wahl || 'auto';
    const haupt = liste.find((t) => t.id === wahl) || liste.find((t) => t.id === tr.ziel) || liste.find((t) => t.online) || liste[0];
    const i = haupt ? haupt.info || {} : tr.info || {}, karten = i.grafik || [], nvidia = karten.find((k) => k.art === 'nvidia');
    const cpu = i.prozessor ? i.prozessor.replace(/\((R|TM)\)/g, '').replace(/\s+CPU\b/, '').replace(/\s+/g, ' ').trim() : '';
    const hw = [cpu, i.cpu ? this.t('g_kerne', { n: i.cpu }) : '', i.ram_gb ? this._zahl(i.ram_gb, 0) + ' GB' : '',
      karten.length ? karten.map((k) => k.name).join(', ') : (i.prozessor ? this.t('g_keine_grafik') : '')].filter(Boolean).join(' · ');
    // graphics card: only the GPU image of the trainer tries it (start-up probe); "auto" uses it when it works
    const b = i.beschleuniger || {}, ziel = b.gpu && this._daten.einstellungen.geraet !== 'cpu' ? 'gpu' : 'cpu';
    // measured on this trainer, or estimated from another trainer's run with both speed tests (computed in HA)
    const da = haupt && w.dauer ? w.dauer[haupt.id] : null;
    const einfach = da ? da.einfach : null, gruendlich = da ? da.gruendlich : null;
    let stufe = 0, rat;
    const [hh, mm] = String(this._daten.einstellungen.uhrzeit || '02:00').split(':').map(Number);
    const ende = gruendlich != null ? new Date(2000, 0, 1, hh, mm + Math.round(gruendlich)) : null;
    const endeText = ende ? ende.toLocaleTimeString(this._loc, { hour: '2-digit', minute: '2-digit' }) : '';
    // a night run should be done by 7 in the morning (start before noon: the same day, otherwise the next one)
    const spaet = ende && e.nachts && hh * 60 + mm + gruendlich > (hh < 12 ? 7 * 60 : 31 * 60);
    if (ziel === 'cpu' && i.cpu && i.cpu < 4) { stufe = 2; rat = this.t('g_rat_wenig'); }
    else if (spaet) { stufe = 1; rat = this.t('g_rat_spaet', { z: endeText }); }
    else if (ende && e.nachts) rat = this.t('g_rat_nachts', { z: endeText });
    else rat = this.t(ziel === 'gpu' ? 'g_rat_gpu' : i.cpu >= 8 ? 'g_rat_gut' : 'g_rat_nacht_tipp');
    const zeilen = [
      hw ? `<div><span class="klein">${esc(this.t('g_hardware'))}</span> ${esc(hw)}</div>` : '',
      this._geraetZeile(b, nvidia),
      einfach != null ? `<div><span class="klein">${esc(this.t('g_dauer'))}</span> ${esc(this.t('g_dauer_wert', { a: this._dauer(einfach), b: this._dauer(gruendlich) }))}${da.quelle === 'geschaetzt' ? ` <span class="klein">${esc(this.t('g_geschaetzt'))}</span>` : ''}</div>` : `<div class="klein">${esc(this.t(ziel === 'gpu' ? 'g_dauer_allg_gpu' : 'g_dauer_allg'))}</div>`,
      `<div class="g-rat"><span class="punkt" style="background:var(--${['success', 'warning', 'error'][stufe]}-color)"></span>${esc(rat)}</div>`,
      !nvidia && b.bild !== 'gpu' && karten.length ? `<div class="klein">${esc(this.t('g_igpu'))}</div>` : '',
    ].join('');
    return `<div class="g-info ${e.gruendlich ? 'an' : ''}"><ha-icon icon="mdi:chip"></ha-icon><div><b>${esc(this.t('g_titel'))}</b>${liste.length > 1 ? this._trainerWahl(w, liste) : ''}${liste.length > 1 && haupt ? `<div class="klein" style="margin-top:6px">${esc(this.t('g_fuer', { n: haupt.name }))}</div>` : ''}${zeilen}</div></div>`;
  }

  // several trainers: which one gets the next run, and how long a run takes on each
  _trainerWahl(w, liste) {
    const tr = this._daten.trainer, wahl = this._daten.einstellungen.trainer_wahl || 'auto', dauer = w.dauer || {};
    const zeilen = liste.map((t) => {
      const d = dauer[t.id], an = t.online && !t.pause;
      const zustand = !t.online ? this.t('tr_aus') : t.pause ? this.t('tr_pause') : t.laeuft.length ? this.t('tr_arbeitet', { w: t.laeuft.join(', ') }) : this.t('tr_frei');
      const zeit = d ? this.t('tr_dauer', { a: this._dauer(d.einfach), b: this._dauer(d.gruendlich) }) + ' · ' + this.t(d.quelle === 'gemessen' ? 'tr_gemessen' : 'tr_geschaetzt') + (d.geraet === 'gpu' ? ' · ' + this.t('tr_karte') : '') : t.online ? this.t('tr_dauer_offen') : '';
      return `<div class="tr-zeile ${tr.ziel === t.id ? 'ziel' : ''}"><span class="punkt ${an ? 'an' : ''}"></span><div style="min-width:0"><div><b>${esc(this._trName(t))}</b> <span class="klein">${esc(zustand)}</span>${tr.ziel === t.id ? ` <span class="mini">${esc(this.t('tr_naechster'))}</span>` : ''}</div><div class="klein">${esc(zeit)}</div></div></div>`;
    }).join('');
    return `<div style="margin-top:6px"><span class="klein">${esc(this.t('tr_wer'))}</span> <select data-zopt="trainer_wahl" ${this._admin ? '' : 'disabled'}><option value="auto" ${liste.some((t) => t.id === wahl) ? '' : 'selected'}>${esc(this.t('tr_auto'))}</option>${liste.map((t) => `<option value="${esc(t.id)}" ${t.id === wahl ? 'selected' : ''}>${esc(this._trName(t))}</option>`).join('')}</select></div>
<div class="tr-liste">${zeilen}</div><div class="klein">${esc(this.t(wahl === 'auto' || !liste.some((t) => t.id === wahl) ? 'tr_auto_hilfe' : 'tr_fest_hilfe'))}</div>`;
  }

  // where the trainer computes, with a choice only when the graphics card really works
  _geraetZeile(b, nvidia) {
    const titel = `<span class="klein">${esc(this.t('g_geraet'))}</span> `;
    if (b.gpu) {
      const wahl = this._daten.einstellungen.geraet === 'cpu' ? 'cpu' : 'auto';
      return `<div>${titel}<select data-zopt="geraet" ${this._admin ? '' : 'disabled'}><option value="auto" ${wahl === 'auto' ? 'selected' : ''}>${esc(this.t('g_geraet_gpu', { n: b.name || nvidia?.name || 'GPU' }))}</option><option value="cpu" ${wahl === 'cpu' ? 'selected' : ''}>${esc(this.t('g_geraet_cpu'))}</option></select></div>`;
    }
    if (b.bild === 'gpu' && b.pruefe) return `<div>${titel}${esc(this.t('g_geraet_pruefe'))}</div>`;
    if (b.bild === 'gpu') {
      const grund = b.grund === 'nicht_geladen' ? 'g_gpu_geladen' : b.grund === 'keine_karte' || !nvidia ? 'g_gpu_keine' : 'g_gpu_nicht';
      return `<div>${titel}${esc(this.t('g_geraet_cpu'))}<div class="klein" ${b.fehler ? `title="${esc(b.fehler)}"` : ''}>${esc(this.t(grund, { n: nvidia ? nvidia.name : '' }))}</div></div>`;
    }
    return nvidia ? `<div>${titel}${esc(this.t('g_geraet_cpu'))}<div class="klein">${esc(this.t('g_nvidia', { n: nvidia.name }))}</div></div>` : '';
  }

  _gpuKurz(i) {
    const b = i.beschleuniger || {};
    if (b.gpu) return this.t(this._daten.einstellungen.geraet === 'cpu' ? 'g_kurz_aus' : 'g_kurz_an');
    if (b.bild === 'gpu') return this.t(b.pruefe ? 'g_geraet_pruefe' : 'g_kurz_nicht');
    return (i.grafik || []).some((k) => k.art === 'nvidia') ? this.t('g_nvidia_kurz') : '';
  }

  _steckbrief(t) {
    const tr = t ? { ...this._daten.trainer, info: t.info, bild_bereit: t.bild_bereit } : this._daten.trainer, i = tr.info || {};
    if (!Object.keys(i).length) return '';
    const ampel = (stufe) => `<span class="punkt" style="background:var(--${['success', 'warning', 'error'][stufe]}-color)"></span>`;
    const zeilen = [];
    const aelter = (a, b) => { const x = String(a).split('.').map(Number), y = String(b).split('.').map(Number); for (let k = 0; k < 3; k++) if ((x[k] || 0) !== (y[k] || 0)) return (x[k] || 0) < (y[k] || 0); return false; };
    if (i.version) { const alt = aelter(i.version, this._daten.version_trainer || VERSION); zeilen.push([this.t('sb_version'), 'v' + i.version + (i.art ? ' · ' + (i.art === 'app' ? this.t('sb_app') : 'Docker') : ''), alt ? 1 : 0, alt ? this.t(tr.bild_bereit === false ? 'sb_version_bild_fehlt' : (t ? t.neustart_taste : this._daten.einstellungen.trainer_neustart) ? 'sb_version_alt_knopf' : 'sb_version_alt', { v: this._daten.version_trainer || VERSION }) : '']); }
    if (i.prozessor) zeilen.push([this.t('sb_prozessor'), i.prozessor.replace(/\((R|TM)\)/g, '').replace(/\s+CPU\b/, '').replace(/\s+/g, ' ').trim(), 0, '']);
    if (i.grafik) zeilen.push([this.t('sb_grafik'), i.grafik.length ? i.grafik.map((k) => k.name).join(', ') : this.t('sb_grafik_keine'), 0, this._gpuKurz(i)]);
    if (i.cpu) zeilen.push([this.t('sb_kerne'), String(i.cpu) + (i.prozesse ? ' · ' + this.t('sb_prozesse', { n: i.prozesse }) : ''), i.cpu >= 4 ? 0 : i.cpu >= 2 ? 1 : 2, i.cpu >= 4 ? '' : this.t('sb_kerne_wenig')]);
    if (i.ram_gb) zeilen.push([this.t('sb_ram'), this._zahl(i.ram_gb, 1) + ' GB', i.ram_gb >= 6 ? 0 : i.ram_gb >= 4 ? 1 : 2, i.ram_gb >= 6 ? '' : this.t('sb_ram_wenig')]);
    if (i.swap_gb != null) { const q = i.swap_gb ? i.swap_belegt_gb / i.swap_gb : 0; zeilen.push([this.t('sb_swap'), i.swap_gb ? `${this._zahl(i.swap_belegt_gb, 1)} / ${this._zahl(i.swap_gb, 1)} GB` : this.t('sb_swap_kein'), q < 0.25 ? 0 : q < 0.6 ? 1 : 2, q < 0.25 ? '' : this.t('sb_swap_voll')]); }
    if (i.platz_frei_gb != null) zeilen.push([this.t('sb_platte'), this.t('sb_platte_wert', { f: this._zahl(i.platz_frei_gb, 0), g: this._zahl(i.platz_gb, 0) }), i.platz_frei_gb >= 40 ? 0 : i.platz_frei_gb >= 15 ? 1 : 2, i.platz_frei_gb >= 40 ? '' : this.t('sb_platte_wenig')]);
    if (i.art === 'docker' && i.version && !aelter(i.version, '1.0.31')) {
      // a Proxmox container fetches the newest version on every restart anyway; one command lets it update while running
      const proxmox = i.ort === 'proxmox' || (i.name_eigen && i.name === 'Proxmox');
      if (i.selbst_update) zeilen.push([this.t('sb_selbst'), this.t('sb_selbst_ja'), 0, '']);
      else if (proxmox) zeilen.push([this.t('sb_selbst'), this.t('sb_selbst_neustart'), 0, this.t('sb_selbst_proxmox'), `bash -c "$(curl -fsSL ${PROXMOX})" -- update`]);
      else zeilen.push([this.t('sb_selbst'), this.t('sb_selbst_nein'), 1, this.t('sb_selbst_tipp')]);
    }
    if (tr.engpass && (!t || t.laeuft.length)) zeilen.push([this.t('sb_lauf'), this.t('h_tr_engpass_' + tr.engpass), 2, '']);
    if (t) return `<table class="steckbrief">${zeilen.map(([k, v, st, tipp, befehl]) => `<tr><td>${esc(k)}</td><td>${ampel(st)}${esc(v)}${tipp ? `<div class="klein">${esc(tipp)}</div>` : ''}${befehl ? `<div class="schluessel" style="margin-top:4px"><code style="white-space:normal;word-break:break-all">${esc(befehl)}</code><button class="k leise" data-a="kopieren" data-text="${esc(befehl)}">${esc(this.t('es_kopieren'))}</button></div>` : ''}</td></tr>`).join('')}</table>`;
    return `<h3>${esc(this.t('sb_titel'))}</h3><table class="steckbrief">${zeilen.map(([k, v, st, tipp, befehl]) => `<tr><td>${esc(k)}</td><td>${ampel(st)}${esc(v)}${tipp ? `<div class="klein">${esc(tipp)}</div>` : ''}${befehl ? `<div class="schluessel" style="margin-top:4px"><code style="white-space:normal;word-break:break-all">${esc(befehl)}</code><button class="k leise" data-a="kopieren" data-text="${esc(befehl)}">${esc(this.t('es_kopieren'))}</button></div>` : ''}</td></tr>`).join('')}</table>`;
  }

  _trName(t) { return t.alt ? this.t('tr_alt_name') : t.name; }

  // "connected" for one trainer, "2 of 3 on" for several
  _trainerStatus() {
    const tr = this._daten.trainer, liste = tr.liste || [];
    if (liste.length > 1) return this.t('tr_an_von', { a: liste.filter((t) => t.online).length, n: liste.length });
    return tr.online ? this.t('t_trainer_an') : tr.kontakt ? this.t('t_trainer_zuletzt', { z: this._zeit(tr.kontakt) }) : this.t('t_trainer_nie');
  }

  // every trainer that ever connected: state, profile, take runs yes/no, remove when it is gone
  _trainerUebersicht() {
    const liste = this._daten.trainer.liste || [];
    if (!liste.length) return `<div class="leer-klein"><ha-icon icon="mdi:server-off"></ha-icon><span>${esc(this.t('tr_keiner'))}</span></div>`;
    return liste.map((t, k) => {
      const zustand = !t.online ? this.t('tr_aus_seit', { z: this._zeit(t.kontakt) }) : t.pause ? this.t('tr_pause') : t.laeuft.length ? this.t('tr_arbeitet', { w: t.laeuft.join(', ') }) : this.t('tr_frei');
      const offen = this._trOffen ? this._trOffen.has(t.id) : k === 0;
      return `<details class="tr-eintrag" data-tid="${esc(t.id)}" ${offen ? 'open' : ''}><summary><span class="punkt ${t.online && !t.pause ? 'an' : ''}"></span><b>${esc(this._trName(t))}</b><span class="klein">${esc(zustand)}</span></summary>
${t.alt ? `<div class="hinweis">${esc(this.t('tr_alt'))}</div>` : ''}${this._steckbrief(t)}
${this._neustartTeil(t)}
<label class="schalter-zeile"><input type="checkbox" data-tpause="${esc(t.id)}" ${t.pause ? '' : 'checked'}> ${esc(this.t('tr_nimmt'))}</label>
<div class="klein">${esc(this.t('tr_nimmt_hilfe'))}</div>
${t.online ? '' : `<button class="k leise" data-a="trainer_vergessen" data-tid="${esc(t.id)}"><ha-icon icon="mdi:delete-outline"></ha-icon>${esc(this.t('tr_vergessen'))}</button>`}</details>`;
    }).join('');
  }

  // setting up a trainer: where it runs, with one command to copy (the real key goes into the copy, not on screen)
  _einrichten(basis) {
    const ort = this._ort || 'windows', gpu = !!this._mitGpu;
    const tabs = ['app', 'proxmox', 'windows', 'linux'].map((o) => `<button class="k ${o === ort ? 'haupt' : 'leise'}" data-a="ort" data-ort="${o}">${esc(this.t('ei_' + o))}</button>`).join('');
    let inhalt;
    if (ort === 'app') inhalt = `<p class="klein" style="line-height:1.6">${this.t('es_app', { r: esc(REPO) })}</p>`;
    else {
      const befehl = this._befehl(ort, gpu, basis, false);
      const schritte = [1, 2, 3].map((n) => `<li>${esc(this.t(`ei_${ort}_${n}`))}</li>`).join('');
      inhalt = `${ort === 'proxmox' ? '' : `<label class="schalter-zeile"><input type="checkbox" data-a="gpu_wahl" ${gpu ? 'checked' : ''}> ${esc(this.t('ei_gpu'))}</label><div class="klein">${esc(this.t('ei_gpu_hilfe'))}</div>`}
<ol class="ei-schritte">${schritte}</ol>
<div class="befehl"><pre>${esc(befehl)}</pre><button class="k haupt" data-a="befehl_kopieren"><ha-icon icon="mdi:content-copy"></ha-icon>${esc(this.t('es_kopieren'))}</button></div>
<div class="klein" style="line-height:1.5">${esc(this.t(ort === 'proxmox' ? 'ei_proxmox_hilfe' : 'ei_docker_hilfe'))}</div>`;
    }
    return `<div class="ei-tabs">${tabs}</div>${inhalt}`;
  }

  // the command to paste: one line, so it works in PowerShell, cmd and any Linux shell alike
  _befehl(ort, gpu, basis, echt) {
    const tr = this._daten.trainer, schl = echt || this._zeigeSchl ? tr.schluessel || '' : '••••••';
    if (ort === 'proxmox') return `bash -c "$(curl -fsSL ${PROXMOX})" -- ${basis} ${schl}`;
    return `docker run -d --name wake-word-studio-trainer --restart unless-stopped${gpu ? ' --gpus all' : ''} -v wake-word-studio-trainer:/data -v /var/run/docker.sock:/var/run/docker.sock -e HA_URL=${basis} -e KEY=${schl} ${gpu ? BILD.replace(':latest', ':gpu') : BILD}`;
  }

  // restart a trainer from here: a button entity of Home Assistant that restarts it (Proxmox, Portainer, app ...), one per trainer
  _neustartTeil(t) {
    const wahl = t.neustart_taste || '', st = this._hass.states || {};
    const name = (id) => (st[id] && st[id].attributes.friendly_name) || id;
    const passt = (id) => /trainer|wake|sprachmodell/i.test(id + ' ' + name(id));
    const tasten = Object.keys(st).filter((id) => id.startsWith('button.'))
      .sort((a, b) => (passt(b) - passt(a)) || name(a).localeCompare(name(b)));
    if (wahl && !tasten.includes(wahl)) tasten.unshift(wahl);
    return `<div class="neustart"><select data-ttaste="${esc(t.id)}" title="${esc(this.t('es_neustart_taste'))}"><option value="">${esc(this.t('es_neustart_keine'))}</option>${tasten.map((id) => `<option value="${esc(id)}" ${id === wahl ? 'selected' : ''}>${esc(name(id))}${name(id) !== id ? ' · ' + esc(id) : ''}</option>`).join('')}</select>
${this._neustartKnopf(t)}</div>
<p class="klein" style="line-height:1.5">${esc(this.t(wahl && !st[wahl] ? 'es_neustart_fehlt' : 'es_neustart_hilfe'))}</p>`;
  }

  // the restart button of one trainer: while it restarts it says so and cannot be pressed again
  _neustartKnopf(t, klein) {
    const st = this._hass.states || {}, wahl = t.neustart_taste, n = t.neustart;
    if (n && !n.zu_lange) return `<button class="k leise startet" disabled><span class="dreher"></span>${esc(this.t('nst_startet', { z: this._uhrzeit(n.seit) }))}</button>`;
    const da = wahl && st[wahl] && st[wahl].state !== 'unavailable';
    return `<button class="k ${da ? 'haupt' : 'leise'}" data-a="trainer_neustart" data-tid="${esc(t.id)}" ${da ? '' : 'disabled'}><ha-icon icon="mdi:restart"></ha-icon>${esc(this.t(klein ? 'nst_jetzt' : 'es_neustart'))}</button>${n && n.zu_lange ? `<div class="klein warn">${esc(this.t('nst_zu_lange'))}</div>` : ''}`;
  }

  _uhrzeit(iso) { try { return new Date(iso).toLocaleTimeString(this._loc, { hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; } }

  _aelter(a, b) { const x = String(a).replace(/^v/, '').split('.').map(Number), y = String(b).replace(/^v/, '').split('.').map(Number); for (let k = 0; k < 3; k++) if ((x[k] || 0) !== (y[k] || 0)) return (x[k] || 0) < (y[k] || 0); return false; }

  // main page: a newer version of the studio or of a trainer is there - say what to do, with the button right here
  _versionHinweise() {
    if (!this._admin) return '';
    const d = this._daten, st = this._hass.states || {}, aus = [];
    const zeile = (icon, text, knopf, art) => `<div class="v-hinweis ${art || ''}"><ha-icon icon="${icon}"></ha-icon><div class="v-text">${esc(text)}</div>${knopf || ''}</div>`;
    // the studio itself (Marketplace/HACS update entity): update, then Home Assistant has to restart
    const upd = Object.keys(st).filter((id) => id.startsWith('update.') && /wake.?word.?studio/i.test(id + ' ' + (st[id].attributes.friendly_name || st[id].attributes.title || ''))).map((id) => st[id])[0];
    const neuste = upd && upd.attributes.latest_version, drin = upd && upd.attributes.installed_version;
    if (upd && upd.state === 'on' && neuste) {
      aus.push(zeile('mdi:package-up', this.t(upd.attributes.in_progress ? 'vh_studio_laedt' : 'vh_studio_neu', { v: neuste }), upd.attributes.in_progress ? '<span class="dreher"></span>' : `<button class="k haupt" data-a="studio_update" data-ent="${esc(upd.entity_id)}"><ha-icon icon="mdi:download"></ha-icon>${esc(this.t('vh_aktualisieren'))}</button>`));
    } else if (drin && this._aelter(d.version_integration, drin)) {
      aus.push(zeile('mdi:restart-alert', this.t('vh_ha_neustart', { v: drin }), `<button class="k haupt" data-a="ha_neustart"><ha-icon icon="mdi:restart"></ha-icon>${esc(this.t('vh_ha_knopf'))}</button>`, 'warn'));
    }
    // trainers that are on and older than the trainer version this studio works with
    for (const t of d.trainer.liste || []) {
      const i = t.info || {};
      if (!t.online || t.alt || !i.version || !this._aelter(i.version, d.version_trainer || d.version_integration)) continue;
      const name = this._trName(t), v = d.version_trainer || d.version_integration;
      if (t.neustart && !t.neustart.zu_lange) { aus.push(zeile('mdi:restart', this.t('vh_tr_startet', { n: name, v, z: this._uhrzeit(t.neustart.seit) }), '<span class="dreher"></span>')); continue; }
      if (t.bild_bereit === false) { aus.push(zeile('mdi:timer-sand', this.t('vh_tr_bild', { n: name, v }))); continue; }
      const text = this.t(i.selbst_update && !t.laeuft.length ? 'vh_tr_selbst' : 'vh_tr_alt', { n: name, a: i.version, v });
      const knopf = t.neustart_taste ? this._neustartKnopf(t, true) : `<button class="k leise" data-reiter="einstellungen"><ha-icon icon="mdi:cog-outline"></ha-icon>${esc(this.t('vh_taste_waehlen'))}</button>`;
      aus.push(zeile('mdi:update', text, knopf, 'info'));
    }
    return aus.length ? `<ha-card class="v-karte">${aus.join('')}</ha-card>` : '';
  }

  _zentrale() {
    const d = this._daten;
    if (!d.woerter.length) {
      return `${this._versionHinweise()}<ha-card><div class="leer" style="padding:28px 12px"><ha-icon icon="mdi:waveform"></ha-icon><h2 style="margin-top:12px;color:var(--primary-text-color)">${esc(this.t('z_leer_titel'))}</h2><p style="max-width:560px;margin:0 auto 16px;line-height:1.5">${esc(this.t('z_leer_text'))}</p>${this._admin ? `<button class="k haupt" data-reiter="neu"><ha-icon icon="mdi:plus"></ha-icon>${esc(this.t('z_wort_anlegen'))}</button>` : `<p class="klein">${esc(this.t('nur_admin_hinweis'))}</p>`}</div></ha-card>
<div class="raster">${this._trainerKachel()}${this._geraeteKachel()}</div>`;
    }
    const karten = d.woerter.map((w, i) => this._wortKarte(w, i)).join('');
    return `${this._versionHinweise()}${this._held()}
<h3 class="abschnitt">${esc(this.t('h_deine_woerter'))}</h3>
<div class="raster">${karten}${this._admin ? `<ha-card class="kachel neu-karte" data-reiter="neu"><ha-icon icon="mdi:plus"></ha-icon><div>${esc(this.t('neues_wort'))}</div></ha-card>` : ''}</div>
<h3 class="abschnitt">${esc(this.t('h_studio'))}</h3>
<div class="raster">${this._trainerKachel()}${this._reiheKachel()}${this._geraeteKachel()}</div>`;
  }

  // ---------- Übersicht eines Worts ----------
  _uebersicht() {
    const d = this._daten, w = d.wort, s = w.statistik, t = w.training, v = w.versionen.find((x) => x.nr === w.aktiv), b = (v && v.bericht && v.bericht.neu) || {};
    const e = w.einstellungen, laeuft = LAEUFT.includes(t.phase);
    const namen = Object.fromEntries(d.geraete.map((g) => [g.knoten, g.name]));
    const geraete = Object.entries(e.geraete || {}).map(([k, p]) => (namen[k] || k) + ' · ' + this.t('w_platz', { n: p }));
    return `
<div class="stat-raster">
${this._stat({ icon: 'mdi:playlist-check', titel: this.t('ue_warten'), wert: String(s.offen), ton: s.offen ? 'gelb' : 'gruen', reiter: 'pruefen', n: 0,
    unter: esc(s.offen ? this.t('ue_aelteste', { z: this._zeit(s.aeltestes_offen) }) : this.t('ue_alles')) })}
${this._stat({ icon: 'mdi:bullseye-arrow', titel: this.t('ue_aktiv'), wert: v ? 'v' + v.nr : '–', ring: b.trefferquote != null ? b.trefferquote : null, reiter: 'qualitaet', n: 1,
    unter: esc(b.trefferquote != null ? this.t('z_erkennt', { q: this._pct(b.trefferquote) }) + ' · ' + this.t('z_fehl', { n: this._zahl(b.fehlausloeser_pro_stunde, 1) }) : v ? this.t('ue_eingespielt', { z: this._zeit(v.eingespielt) }) : this.t('q_keine')) })}
${this._stat({ icon: laeuft ? 'mdi:auto-fix' : 'mdi:school-outline', titel: this.t('r_training'), wert: laeuft && t.prozent != null ? Math.round(t.prozent) + ' %' : this.t('p_' + t.phase), ring: laeuft && t.prozent != null ? t.prozent / 100 : null, ton: laeuft ? 'laeuft' : '', reiter: 'training', n: 2,
    unter: laeuft ? esc(this._schritt(t.schritt)) : `<span class="punkt ${d.trainer.online ? 'an' : ''}"></span>${esc(d.trainer.online ? this.t('t_trainer_an') : this.t('t_kein_trainer'))}${w.neu_seit_lauf > 0 ? ' · ' + esc(this.t('ue_neue_bew', { n: w.neu_seit_lauf })) : ''}` })}
${this._stat({ icon: 'mdi:speaker-wireless', titel: this.t('ue_geraete'), wert: String(geraete.length), reiter: this._admin ? 'wort' : 'geraete', n: 3, unter: esc(geraete.join(', ') || this.t('z_kein_geraet')) })}
</div>
<ha-card><h2>${esc(this.t('ue_alltag'))}</h2>${this._alltag()}</ha-card>
${this._weg(w, v)}`;
  }

  // the way of a wake word as four stations; the one that needs you now glows, the ones behind are done
  _weg(w, v) {
    const d = this._daten, s = w.statistik, t = w.training, e = w.einstellungen, laeuft = LAEUFT.includes(t.phase);
    const n = Object.keys(e.geraete || {}).length;
    const jetzt = s.offen ? 1 : (laeuft || t.phase === 'wartet') ? 2 : !v ? 2 : 3;
    const stationen = [
      ['pruefen', 'mdi:microphone-message', 'ws_sammeln', this.t('ws_sammeln_wert', { n: s.aufnahmen })],
      ['pruefen', 'mdi:playlist-check', 'ws_pruefen', s.offen ? this.t('ws_pruefen_offen', { n: s.offen }) : this.t('ws_pruefen_fertig')],
      ['training', 'mdi:auto-fix', 'ws_training', laeuft ? this.t('p_' + t.phase) + (t.prozent != null ? ` · ${Math.round(t.prozent)} %` : '')
        : e.nachts ? this.t('ws_training_nachts', { u: String(d.einstellungen.uhrzeit).slice(0, 5) }) : this.t('ws_training_hand')],
      ['qualitaet', 'mdi:speaker-wireless', 'ws_geraet', v ? this.t('ws_geraet_wert', { v: v.nr, n }) : this.t('ws_geraet_noch')],
    ];
    const erklaerung = [this.t('ue_so_1'), esc(this.t('ue_so_2', { w: e.wort })), this.t('ue_so_3'),
      esc(e.nachts ? this.t('ue_so_4n', { u: String(d.einstellungen.uhrzeit).slice(0, 5) }) : this.t('ue_so_4h')) + ' ' + esc(this.t('ue_so_4b')) + ' ' + esc(e.automatisch_einspielen ? this.t('ue_so_5a') : this.t('ue_so_5h'))];
    return `<ha-card><h2>${esc(this.t('ue_so'))}</h2><div class="weg ${laeuft ? 'laeuft' : ''}">${stationen.map(([reiter, icon, titel, wert], i) => `${i ? `<div class="weg-linie ${i <= jetzt ? 'durch' : ''}"><i></i></div>` : ''}<a class="weg-station ${i < jetzt ? 'erledigt' : i === jetzt ? 'jetzt' : ''}" data-reiter="${reiter}" style="--n:${i}">
<span class="weg-punkt"><ha-icon icon="${i < jetzt ? 'mdi:check' : icon}"></ha-icon></span><b>${esc(this.t(titel))}</b><span class="klein">${esc(wert)}</span></a>`).join('')}</div>
<details class="weg-mehr"><summary class="klein">${esc(this.t('ws_mehr'))}</summary><ol class="klein">${erklaerung.map((x) => `<li>${x}</li>`).join('')}</ol></details></ha-card>`;
  }

  // how the word developed: hit rate of the newest trained versions (old ones drop out), versions that were not rolled out as small grey points
  _kurve(w) {
    const vs = [...w.versionen].filter((v) => v.bericht && v.bericht.neu && v.bericht.neu.trefferquote != null).sort((a, b) => a.nr - b.nr).slice(-KURVE_VERSIONEN);
    if (vs.length < 2) return '';
    const q = vs.map((v) => v.bericht.neu.trefferquote), lo = Math.max(0, Math.min(...q) - 0.05), hi = Math.min(1, Math.max(...q) + 0.02);
    const B = 600, H = 120, x = (i) => 30 + (i / (vs.length - 1)) * (B - 60), y = (v) => 14 + (1 - (v - lo) / ((hi - lo) || 1)) * (H - 44);
    const pkt = q.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
    const farbe = this._farbe(this._wortKurz() || {});
    return `<svg class="kurve" viewBox="0 0 ${B} ${H}" style="--farbe:${esc(farbe)}" aria-label="${esc(this.t('ku_titel'))}">
<polygon class="ku-flaeche" points="${x(0).toFixed(1)},${H - 24} ${pkt} ${x(vs.length - 1).toFixed(1)},${H - 24}"/><polyline class="ku-linie" points="${pkt}"/>
${vs.map((v, i) => `<g class="ku-punkt" style="--n:${i}"><circle cx="${x(i).toFixed(1)}" cy="${y(q[i]).toFixed(1)}" r="${v.nr === w.aktiv ? 6 : v.status === 'verworfen' ? 3 : 4}" class="${v.nr === w.aktiv ? 'aktiv' : v.status === 'verworfen' ? 'nicht' : ''}"/><text x="${x(i).toFixed(1)}" y="${(y(q[i]) - 11).toFixed(1)}">${esc(this._pct(q[i]))}</text><text class="ku-v" x="${x(i).toFixed(1)}" y="${H - 6}">v${v.nr}</text></g>`).join('')}</svg>`;
  }

  _alltag() {
    const a = this._daten.wort.statistik.alltag;
    if (!a.aufgewacht && !a.verpasst) return `<div class="klein">${esc(this.t('al_leer'))}</div>`;
    const quote = a.aufgewacht ? a.richtig / a.aufgewacht : null;
    return `<div class="stat-raster klein-stat">
${this._stat({ icon: 'mdi:check-circle-outline', titel: this.t('al_richtig'), wert: String(a.richtig), ton: 'gruen', n: 0 })}
${this._stat({ icon: 'mdi:alert-circle-outline', titel: this.t('al_falsch'), wert: String(a.falsch), ton: a.falsch ? 'rot' : '', n: 1 })}
${this._stat({ icon: 'mdi:ear-hearing-off', titel: this.t('al_verpasst'), wert: String(a.verpasst), ton: a.verpasst ? 'gelb' : '', n: 2 })}
${this._stat({ icon: 'mdi:target', titel: this.t('al_genau'), wert: quote == null ? '–' : this._pct(quote), ring: quote, n: 3 })}</div>`;
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
    const fertig = (this._prGemacht || {})[this._wortId] || 0, alle = fertig + s.offen;
    this._prBasis = { offen: s.offen, fertig };
    return `
<div class="pr-kopf"><div class="pr-ring">${this._zielRing(fertig, Math.max(1, alle))}</div>
<div class="pr-text"><b>${esc(this.t('pr_kopf_offen', { n: s.offen }))}</b><span class="klein">${esc(fertig ? this.t('pr_kopf_fertig', { n: fertig }) : this.t('pr_kopf_los'))}</span></div>
${mitVorschlag ? `<button class="k haupt pr-alle" data-a="alle_vorschlaege"><ha-icon icon="mdi:creation"></ha-icon>${esc(this.t('pr_vorschlaege', { n: mitVorschlag }))}</button>` : ''}</div>
<div class="zeile weit pr-leiste"><div class="zeile"><button class="chip ${!this._filter.echo ? 'an' : ''}" data-echo="">${esc(this.t('pr_alle'))} · ${s.offen}</button>${echoChips}</div>
<label class="pr-auto klein"><input type="checkbox" id="autoplay" ${this._autoplay ? 'checked' : ''}><span class="pr-auto-s"></span>${esc(this.t('pr_autoplay'))}</label></div>
<div class="klein pr-tasten">${this._andere().length ? this.t('pr_tasten') : this.t('pr_tasten').replace(/ · <b>3<\/b>[^·]*/, '')}</div>
<div class="liste">${l.eintraege.map((a, i) => this._eintrag(a, i, true)).join('')}</div>
${l.gesamt > l.eintraege.length ? `<div class="leer klein">${esc(this.t('pr_weitere', { n: l.gesamt - l.eintraege.length }))}</div>` : ''}`;
  }

  // one recording as a tile: what it is, its sound, what the studio thinks about it, and the decision
  _eintrag(a, i, pruefen) {
    const art = a.quelle === 'browser' ? 'browser' : a.art;
    const sc = typeof a.score === 'number' ? a.score : null, cu = typeof a.cutoff === 'number' ? a.cutoff : null;
    const wort = this._daten.wort.einstellungen.wort;
    const grund = a.grund ? this.t('g_' + a.grund) : '';
    const farbe = { wake: this._farbe(this._wortKurz() || {}), mistake: 'var(--error-color,#f44336)', nearmiss: 'var(--warning-color,#ff9800)', noise: 'var(--secondary-text-color)' }[art] || 'var(--primary-color)';
    const empf = pruefen ? a.vorschlag : null, k = (u) => !pruefen && a.urteil === u ? 'gewaehlt' : '';
    const marken = `${a.auto ? `<span class="marke">${esc(this.t('pr_auto'))}</span>` : ''}${a.schnitt ? `<span class="marke"><ha-icon icon="mdi:content-cut"></ha-icon>${esc(this.t('pr_geschnitten', { a: this._zahl(a.schnitt[0], 1), b: this._zahl(a.schnitt[1], 1) }))}</span>` : ''}${this._wortMarke(a, pruefen)}`;
    const ki = (pruefen && a.vorschlag) || a.gehoert != null || sc != null;
    const zweifel = !pruefen && sc != null && ((a.urteil === 'wort' && sc < 0.2) || (a.urteil === 'kein_wort' && sc >= (cu != null ? cu : 0.9)));
    return `<div class="eintrag" tabindex="-1" data-id="${esc(a.id)}" data-i="${i}" style="--ef:${farbe};--n:${Math.min(i, 8)}">
<div class="e-kopf"><span class="e-ikon"><ha-icon icon="${ART_ICON[art] || 'mdi:waveform'}"></ha-icon></span><div class="e-titel"><b>${esc(this.t('a_' + art))}</b>${a.echo ? `<span class="klein">${esc(a.echo)}</span>` : ''}</div>
<div class="e-meta"><span class="e-chip"><ha-icon icon="mdi:clock-outline"></ha-icon>${this._zeit(a.zeit)}</span>${a.dauer ? `<span class="e-chip">${this._zahl(a.dauer, 1)} s</span>` : ''}${a.test ? `<span class="e-chip e-test"><ha-icon icon="mdi:flask-outline"></ha-icon>${esc(this.t('pr_test'))}</span>` : ''}</div></div>
<div class="e-ton"><button class="spielen" data-spielen="${esc(a.id)}" title="${esc(this.t('pr_abspielen'))}"><svg viewBox="0 0 52 52"><circle cx="26" cy="26" r="25"></circle></svg><ha-icon icon="mdi:play"></ha-icon></button>
<div class="welle" data-welle="${esc(a.id)}" ${Array.isArray(a.schnitt) ? `data-von="${a.schnitt[0]}" data-bis="${a.schnitt[1]}"` : ''} title="${esc(this.t('pr_welle_t'))}"><canvas></canvas><div class="gespielt"></div><div class="spielkopf"></div></div></div>
${ki ? `<div class="ki">${pruefen && a.vorschlag ? `<div class="ki-zeile"><ha-icon icon="mdi:creation"></ha-icon><span>${esc(this.t('pr_vorschlag'))}: <strong>${esc(a.vorschlag === 'wort' ? this.t('pr_gesagt', { w: wort }) : this.t('pr_nicht'))}</strong>${grund ? `<span class="klein"> – ${esc(grund)}</span>` : ''}</span></div>` : ''}
${a.gehoert != null ? `<div class="ki-zeile ki-ohr"><ha-icon icon="mdi:ear-hearing"></ha-icon><span>${a.gehoert ? esc(this.t('pr_gehoert', { t: a.gehoert })) : esc(this.t('pr_nichts_gehoert'))}</span></div>` : ''}
${sc != null ? `<div class="e-mess"><div class="e-spur ${cu != null && sc >= cu ? 'drueber' : ''}"><i style="--w:${Math.min(100, sc * 100).toFixed(1)}%"></i>${cu != null ? `<b style="left:${(cu * 100).toFixed(1)}%"></b>` : ''}</div><span class="klein">${esc(this.t('pr_wert', { w: this._zahl(sc) }))}${cu != null ? ' · ' + esc(this.t('pr_schwelle', { w: this._zahl(cu) })) : ''}</span></div>` : ''}</div>`
    : a.notiz ? `<div class="klein">${esc(a.notiz)}</div>` : ''}
${zweifel ? `<div class="e-zweifel"><ha-icon icon="mdi:alert-circle-outline"></ha-icon>${esc(this.t(a.urteil === 'wort' ? 'v_zweifel_wort' : 'v_zweifel_nicht', { w: this._zahl(sc) }))}</div>` : ''}${marken ? `<div class="gehoert">${marken}</div>` : ''}
${!pruefen && (a.person || a.quelle === 'hochgeladen' || a.quelle === 'browser') ? `<div class="vorschlag">${[a.person ? esc(a.person) : '', a.quelle === 'hochgeladen' ? esc(this.t('pr_hochgeladen')) : a.quelle === 'browser' ? esc(this.t('pr_aufgenommen')) : ''].filter(Boolean).join(' · ')}</div>` : ''}
<div class="knoepfe">
<div class="entscheid"><button class="k gut ${k('wort')} ${empf === 'wort' ? 'empfohlen' : ''}" data-urteil="wort" data-id="${esc(a.id)}"><ha-icon icon="mdi:check"></ha-icon><span>${esc(pruefen ? this.t('pr_gesagt', { w: wort }) : this.t('pr_wort_k'))}</span> <kbd>1</kbd></button>
<button class="k schlecht ${k('kein_wort')} ${empf === 'kein_wort' ? 'empfohlen' : ''}" data-urteil="kein_wort" data-id="${esc(a.id)}"><ha-icon icon="mdi:close"></ha-icon><span>${esc(this.t('pr_nicht_k'))}</span> <kbd>2</kbd></button></div>
<div class="e-mehr"><button class="k leise ${k('verworfen')}" data-urteil="verworfen" data-id="${esc(a.id)}" title="${esc(this.t('pr_unbrauchbar_t'))}"><ha-icon icon="mdi:delete-outline"></ha-icon><span class="txt">${esc(this.t('u_verworfen'))}</span> <kbd>0</kbd></button>
${this._andere().length && !a.zu_wort && !a.von_wort ? `<button class="k leise" data-umzug="${esc(a.id)}" title="${esc(this.t('pr_anderes_t'))}" aria-expanded="false"><ha-icon icon="mdi:swap-horizontal"></ha-icon><span class="txt">${esc(this.t('pr_anderes'))}</span> <kbd>3</kbd></button>` : ''}
<button class="k leise" data-schnitt="${esc(a.id)}" title="${esc(this.t('pr_schneiden_t'))}"><ha-icon icon="mdi:content-cut"></ha-icon><span class="txt">${esc(this.t('pr_schneiden'))}</span></button>
<span class="rechts">${this._personWahl(a.person || (pruefen ? this._person : ''), a.id)}</span></div>
</div><div class="umzug" data-umzugbox="${esc(a.id)}"></div><div class="schnitt" data-schnittbox="${esc(a.id)}"></div></div>`;
  }

  // ---------- Recording of another word ----------
  _vglUmschalten(nr, zeile) {
    const det = this.shadowRoot.querySelector(`[data-vgldetail="${nr}"]`);
    if (!det) return;
    const auf = det.hidden;
    if (auf) this._vglOffen.add(nr); else this._vglOffen.delete(nr);
    zeile.classList.toggle('offen', auf);
    det.hidden = !auf;
    const box = det.querySelector('.vgl');
    if (box) { box.classList.remove('auf'); if (auf) { void box.offsetWidth; box.classList.add('auf'); } }
  }

  _andere() { const d = this._daten; return d && d.woerter ? d.woerter.filter((w) => w.id !== this._wortId) : []; }

  _wortMarke(a, pruefen) {
    const name = (x) => { const w = this._daten.woerter.find((v) => v.id === x.id); return w ? w.wort : x.wort; };
    if (a.zu_wort) return ` <span class="marke wortmarke" style="--wf:${this._farbe(this._daten.woerter.find((v) => v.id === a.zu_wort.id))}"><i></i>${esc(this.t('pr_zu_wort_marke', { w: name(a.zu_wort) }))}${pruefen ? '' : ` <button class="link" data-zurueck="${esc(a.id)}" data-ziel="${esc(a.zu_wort.id)}">${esc(this.t('pr_rueckgaengig'))}</button>`}</span>`;
    if (a.von_wort) return ` <span class="marke wortmarke" style="--wf:${this._farbe(this._daten.woerter.find((v) => v.id === a.von_wort.id))}"><i></i>${esc(this.t('pr_von_wort', { w: name(a.von_wort) }))}</span>`;
    return '';
  }

  _umzugOeffnen(id) {
    const box = this.shadowRoot.querySelector(`[data-umzugbox="${CSS.escape(id)}"]`);
    if (!box) return;
    const knopf = this.shadowRoot.querySelector(`[data-umzug="${CSS.escape(id)}"]`);
    const offen = !!box.innerHTML;
    this.shadowRoot.querySelectorAll('[data-umzugbox]').forEach((b) => { b.innerHTML = ''; });
    this.shadowRoot.querySelectorAll('[data-umzug]').forEach((b) => b.setAttribute('aria-expanded', 'false'));
    if (offen) return;
    const alle = this._daten.woerter;
    box.innerHTML = `<div class="klein umzug-frage">${esc(this.t('pr_welches'))}</div>
<div class="umzug-woerter">${this._andere().map((w) => `<button class="chip wortwahl" data-ziel="${esc(w.id)}" data-id="${esc(id)}" style="--wf:${this._farbe(w, alle.indexOf(w))}"><span class="farbe"></span>${esc(w.wort)}</button>`).join('')}</div>
<div class="klein umzug-hilfe">${esc(this.t('pr_anderes_hilfe', { w: this._wortName() }))}</div>`;
    if (knopf) knopf.setAttribute('aria-expanded', 'true');
    const erst = box.querySelector('[data-ziel]');
    if (erst) erst.focus({ preventScroll: true });
    box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  async _umziehen(id, ziel) {
    const w = this._daten.woerter.find((v) => v.id === ziel);
    if (!w) return;
    const zeile = this.shadowRoot.querySelector(`.eintrag[data-id="${CSS.escape(id)}"]`);
    const sel = zeile && zeile.querySelector('select[data-person]');
    const person = sel ? sel.value : this._person;
    const von = this._wortId;
    if (zeile) zeile.querySelectorAll('[data-ziel]').forEach((b) => { b.disabled = true; b.classList.toggle('an', b.dataset.ziel === ziel); });
    try { if (navigator.vibrate) navigator.vibrate(12); } catch (e) { /* not supported */ }
    try { await this._api('POST', 'aktion', { aktion: 'anderes_wort', wort: von, id, ziel, person }); }
    catch (e) { this._meldung(this.t('ging_nicht', { f: this._fehlerText(e) })); if (zeile) zeile.querySelectorAll('[data-ziel]').forEach((b) => { b.disabled = false; }); return; }
    this._meldung(this.t('pr_zu_wort_ok', { w: w.wort }), { text: this.t('pr_rueckgaengig'), action: () => this._zurueckholen(von, id, ziel) });
    if (this._reiter === 'pruefen' && zeile) {
      const farbe = this._farbe(w, this._daten.woerter.indexOf(w));
      this._wegGleiten(zeile, id, `<div class="stempel u-umzug" style="--wf:${farbe}"><ha-icon icon="mdi:swap-horizontal"></ha-icon>${esc(this.t('pr_zu_wort', { w: w.wort }))}</div>`);
    } else this._laden();
  }

  async _zurueckholen(wort, id, ziel) {
    try { await this._api('POST', 'aktion', { aktion: 'anderes_wort_zurueck', wort, id, ziel }); this._meldung(this.t('pr_zurueck_ok')); }
    catch (e) { this._meldung(this.t('ging_nicht', { f: this._fehlerText(e) })); }
    this._laden();
  }

  // ---------- Zuschneiden ----------
  async _schnittOeffnen(id) {
    const box = this.shadowRoot.querySelector(`[data-schnittbox="${CSS.escape(id)}"]`);
    if (!box) return;
    if (this._schnitt && this._schnitt.id === id) { this._schnitt = null; box.innerHTML = ''; return; }
    this.shadowRoot.querySelectorAll('[data-schnittbox]').forEach((b) => { b.innerHTML = ''; });
    const a = ((this._liste && this._liste.eintraege) || []).find((x) => x.id === id) || {};
    try {
      const url = await this._blob(id);
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const puffer = await ctx.decodeAudioData(await (await fetch(url)).arrayBuffer());
      ctx.close();
      const dauer = puffer.duration, s = a.schnitt || [0, dauer];
      this._schnitt = { id, url, dauer, daten: puffer.getChannelData(0), von: s[0], bis: Math.min(s[1], dauer) };
    } catch (e) { this._meldung(this.t('ging_nicht', { f: e.message })); return; }
    const z = this._schnitt;
    box.innerHTML = `<div class="studio"><canvas></canvas><div class="wahl"></div><div class="aus links"></div><div class="aus rechts"></div>
<div class="griff" data-griff="von" tabindex="0" role="slider" aria-label="${esc(this.t('pr_anfang'))}"><span></span></div><div class="griff" data-griff="bis" tabindex="0" role="slider" aria-label="${esc(this.t('pr_ende'))}"><span></span></div><div class="spielkopf"></div></div>
<div class="zeile weit studio-leiste"><span class="zeile" style="gap:8px"><button class="k rund haupt" data-sa="spielen" title="${esc(this.t('pr_spielen_t'))}"><ha-icon icon="mdi:play"></ha-icon></button><button class="k" data-sa="hoeren"><ha-icon icon="mdi:play-box-outline"></ha-icon>${esc(this.t('pr_auswahl_hoeren'))}</button><button class="k leise" data-sa="auto" title="${esc(this.t('pr_auto_schnitt_t'))}"><ha-icon icon="mdi:auto-fix"></ha-icon>${esc(this.t('pr_auto_schnitt'))}</button></span><span class="klein zeitanzeige" data-sinfo></span></div>
<div class="zeile weit" style="margin-top:8px;flex-wrap:wrap;gap:8px"><span class="klein">${esc(this.t('pr_studio_hilfe'))}</span><span class="zeile" style="gap:8px"><button class="k leise" data-sa="ganz">${esc(this.t('pr_ganz'))}</button><button class="k haupt" data-sa="speichern"><ha-icon icon="mdi:content-save-outline"></ha-icon>${esc(this.t('pr_schnitt_speichern'))}</button></span></div>`;
    const st = box.querySelector('.studio');
    const zeit = (ev) => { const r = st.getBoundingClientRect(); return Math.min(z.dauer, Math.max(0, ((ev.clientX - r.left) / r.width) * z.dauer)); };
    const MIN = 0.2;
    let zug = null;
    st.addEventListener('pointerdown', (ev) => {
      if (ev.button > 0) return;
      const g = ev.target.closest('[data-griff]'), t = zeit(ev);
      zug = { art: g ? g.dataset.griff : t > z.von && t < z.bis ? 'feld' : 'neu', t, von: z.von, bis: z.bis, x: ev.clientX, bewegt: false, g };
      st.setPointerCapture(ev.pointerId); ev.preventDefault();
      if (g) { g.classList.add('zieht'); g.focus({ preventScroll: true }); }
    });
    st.addEventListener('pointermove', (ev) => {
      if (!zug) return;
      if (!zug.bewegt && Math.abs(ev.clientX - zug.x) < 4) return;
      zug.bewegt = true; st.classList.add('zieht');
      const t = zeit(ev);
      if (zug.art === 'von') z.von = Math.max(0, Math.min(t, z.bis - MIN));
      else if (zug.art === 'bis') z.bis = Math.min(z.dauer, Math.max(t, z.von + MIN));
      else if (zug.art === 'feld') { const l = zug.bis - zug.von; z.von = Math.min(Math.max(0, zug.von + t - zug.t), z.dauer - l); z.bis = z.von + l; }
      else { z.von = Math.min(zug.t, t); z.bis = Math.min(z.dauer, Math.max(Math.max(zug.t, t), z.von + MIN)); }
      this._schnittLage(box);
    });
    const los = (ev) => {
      if (!zug) return;
      st.classList.remove('zieht'); if (zug.g) zug.g.classList.remove('zieht');
      if (!zug.bewegt && !zug.g) this._abspielen(z.url, zeit(ev), z.dauer);  // tap: play from here, like in a studio
      else if (zug.bewegt && zug.art !== 'neu' && zug.art !== 'feld' && ev.type === 'pointerup') this._abspielen(z.url, zug.art === 'von' ? z.von : Math.max(z.von, z.bis - 0.8), z.bis);
      zug = null;
    };
    st.addEventListener('pointerup', los); st.addEventListener('pointercancel', los);
    st.addEventListener('keydown', (ev) => {
      const g = ev.target.closest && ev.target.closest('[data-griff]');
      if (!g || !['ArrowLeft', 'ArrowRight'].includes(ev.key)) return;
      const d = (ev.key === 'ArrowLeft' ? -1 : 1) * (ev.shiftKey ? 0.1 : 0.01);
      if (g.dataset.griff === 'von') z.von = Math.max(0, Math.min(z.von + d, z.bis - MIN)); else z.bis = Math.min(z.dauer, Math.max(z.bis + d, z.von + MIN));
      this._schnittLage(box); ev.preventDefault(); ev.stopPropagation();
    });
    if (this._schnittRO) this._schnittRO.disconnect();
    this._schnittRO = new ResizeObserver(() => this._schnittZeichnen(box));
    this._schnittRO.observe(st);
    this._schnittZeichnen(box);
    this._schnittLage(box);
  }

  // waveform with time ruler, drawn once (and on resize); selection, handles and play head are elements on top
  _schnittZeichnen(box) {
    const z = this._schnitt, c = box.querySelector('canvas');
    if (!z || !c || !c.clientWidth) return;
    const dpr = window.devicePixelRatio || 1, b = c.clientWidth, h = c.clientHeight, lineal = 18, wh = h - lineal;
    c.width = Math.round(b * dpr); c.height = Math.round(h * dpr);
    const g = c.getContext('2d'), farbe = (getComputedStyle(this).getPropertyValue('--primary-color') || '#03a9f4').trim();
    g.scale(dpr, dpr); g.clearRect(0, 0, b, h);
    const schritt = z.dauer > 3 ? 0.5 : z.dauer > 1.2 ? 0.25 : 0.1;
    g.font = '10px ui-monospace,Menlo,Consolas,monospace'; g.textBaseline = 'middle';
    for (let t = 0; t <= z.dauer + 1e-6; t += schritt) {
      const x = Math.round((t / z.dauer) * b) + 0.5, gross = Math.abs(t / (schritt * 2) - Math.round(t / (schritt * 2))) < 1e-6;
      g.fillStyle = 'rgba(255,255,255,.05)'; g.fillRect(x, 0, 1, wh);
      g.fillStyle = 'rgba(255,255,255,.35)'; g.fillRect(x, wh, 1, gross ? 6 : 3);
      if (gross && x < b - 24) { g.fillStyle = 'rgba(255,255,255,.55)'; g.fillText(this._zahl(t, schritt < 0.25 ? 1 : 1) + 's', x + 3, wh + 11); }
    }
    g.fillStyle = 'rgba(255,255,255,.08)'; g.fillRect(0, wh / 2, b, 1);
    const verlauf = g.createLinearGradient(0, 0, 0, wh);
    verlauf.addColorStop(0, farbe); verlauf.addColorStop(0.5, '#ffffff'); verlauf.addColorStop(1, farbe);
    g.fillStyle = verlauf;
    const balken = 3, luecke = 1, n = Math.floor(b / (balken + luecke)), proBalken = z.daten.length / n;
    let spitze = 1e-4;
    for (let i = 0; i < z.daten.length; i += 7) spitze = Math.max(spitze, Math.abs(z.daten[i]));
    for (let k = 0; k < n; k++) {
      let m = 0;
      for (let i = Math.floor(k * proBalken), e = Math.min(z.daten.length, Math.floor((k + 1) * proBalken)); i < e; i++) { const v = Math.abs(z.daten[i]); if (v > m) m = v; }
      const y = Math.max(2, Math.min(1, m / spitze) * (wh - 8));
      g.beginPath(); if (g.roundRect) g.roundRect(k * (balken + luecke), (wh - y) / 2, balken, y, 1.5); else g.rect(k * (balken + luecke), (wh - y) / 2, balken, y); g.fill();
    }
  }

  _schnittLage(box) {
    const z = this._schnitt;
    if (!z) return;
    const p = (t) => (t / z.dauer) * 100 + '%', q = (s) => box.querySelector(s);
    q('.aus.links').style.width = p(z.von); q('.aus.rechts').style.width = p(z.dauer - z.bis);
    q('.wahl').style.left = p(z.von); q('.wahl').style.width = p(z.bis - z.von);
    q('[data-griff="von"]').style.left = p(z.von); q('[data-griff="bis"]').style.left = p(z.bis);
    q('[data-griff="von"]').setAttribute('aria-valuetext', this._zahl(z.von, 2) + ' s'); q('[data-griff="bis"]').setAttribute('aria-valuetext', this._zahl(z.bis, 2) + ' s');
    this._schnittInfo(box);
  }

  _schnittInfo(box) {
    const z = this._schnitt, info = box.querySelector('[data-sinfo]');
    if (!z || !info) return;
    const hier = this._audio.src === z.url, t = hier ? this._audio.currentTime : null;
    info.textContent = (t != null ? '▸ ' + this._zahl(t, 2) + ' s · ' : '') + this.t('pr_auswahl', { a: this._zahl(z.von, 2), b: this._zahl(z.bis, 2), d: this._zahl(z.bis - z.von, 2) });
  }

  // loudest stretch of the recording, with a little air on both sides
  _schnittAuto() {
    const z = this._schnitt, d = z.daten, fenster = Math.max(1, Math.round(d.length / z.dauer / 100)), werte = [];
    for (let i = 0; i < d.length; i += fenster) { let s = 0; const e = Math.min(d.length, i + fenster); for (let k = i; k < e; k++) s += d[k] * d[k]; werte.push(Math.sqrt(s / (e - i))); }
    const sortiert = [...werte].sort((a, b) => a - b), boden = sortiert[Math.floor(sortiert.length * 0.2)] || 0, spitze = sortiert[sortiert.length - 1] || 0;
    const grenze = boden + (spitze - boden) * 0.12;
    const an = werte.findIndex((v) => v > grenze);
    let aus = werte.length - 1; while (aus > an && werte[aus] <= grenze) aus--;
    if (an < 0) return;
    const sek = z.dauer / werte.length;
    z.von = Math.max(0, an * sek - 0.12); z.bis = Math.min(z.dauer, Math.max((aus + 1) * sek + 0.15, z.von + 0.2));
  }

  async _schnittAktion(was) {
    const z = this._schnitt;
    if (!z) return;
    const box = this.shadowRoot.querySelector(`[data-schnittbox="${CSS.escape(z.id)}"]`);
    if (was === 'hoeren') { this._abspielen(z.url, z.von, z.bis); return; }
    if (was === 'spielen') {
      if (this._audio.src === z.url && !this._audio.paused) { this._audio.pause(); return; }
      const t = this._audio.src === z.url && this._audio.currentTime < z.dauer - 0.05 ? this._audio.currentTime : 0;
      this._abspielen(z.url, t, z.dauer); return;
    }
    if (was === 'auto') { this._schnittAuto(); if (box) this._schnittLage(box); this._abspielen(z.url, z.von, z.bis); return; }
    const ganz = was === 'ganz' || (z.von <= 0.01 && z.bis >= z.dauer - 0.01);
    try {
      await this._api('POST', 'aktion', { aktion: 'schnitt', wort: this._wortId, id: z.id, von: ganz ? null : z.von, bis: ganz ? null : z.bis });
      this._meldung(this.t(ganz ? 'pr_schnitt_weg' : 'pr_schnitt_ok'));
      this._schnitt = null; this._laden();
    } catch (e) { this._meldung(this.t('ging_nicht', { f: this._fehlerText(e) })); }
  }

  _markieren(fokus = true) {
    const alle = [...this.shadowRoot.querySelectorAll('.eintrag:not(.weg)')];
    alle.forEach((e, i) => e.classList.toggle('aktiv', i === this._aktiv));
    const e = alle[this._aktiv];
    if (e && fokus) e.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    return e;
  }

  _tastatur(e) {
    if (this._raumD && e.key === 'Escape') { this._raumSchliessen(); return; }
    if (this._raumD) return;
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
    else if (e.key === '3' && akt.querySelector('[data-umzug]')) { this._umzugOeffnen(akt.dataset.id); e.preventDefault(); }
  }

  // small waveform per recording: decoded once when it comes into view, cached as 160 peaks
  _wellen(wurzel) {
    if (!this._wellenCache) this._wellenCache = new Map();
    if (this._wellenIO) this._wellenIO.disconnect();
    this._wellenIO = new IntersectionObserver((eintraege) => eintraege.forEach((e) => { if (e.isIntersecting) { this._wellenIO.unobserve(e.target); this._welleLaden(e.target); } }), { rootMargin: '200px' });
    wurzel.querySelectorAll('[data-welle]').forEach((el) => {
      const s = this._wellenCache.get(this._wortId + '/' + el.dataset.welle);
      if (s) this._welleMalen(el, s); else this._wellenIO.observe(el);
      if (!el._klick) { el._klick = true; el.addEventListener('click', (ev) => this._welleKlick(el, ev)); }
    });
  }

  async _welleLaden(el) {
    const id = el.dataset.welle, schl = this._wortId + '/' + id;
    try {
      const url = await this._blob(id);
      if (!this._dekoder) this._dekoder = new (window.AudioContext || window.webkitAudioContext)();
      const p = await this._dekoder.decodeAudioData(await (await fetch(url)).arrayBuffer());
      const d = p.getChannelData(0), n = 160, je = d.length / n, spitzen = new Float32Array(n);
      let max = 1e-4;
      for (let k = 0; k < n; k++) { let m = 0; for (let i = Math.floor(k * je), e = Math.floor((k + 1) * je); i < e; i++) { const v = Math.abs(d[i]); if (v > m) m = v; } spitzen[k] = m; if (m > max) max = m; }
      const s = { spitzen: spitzen.map((v) => v / max), dauer: p.duration };
      this._wellenCache.set(schl, s);
      if (this._wellenCache.size > 300) this._wellenCache.delete(this._wellenCache.keys().next().value);
      if (el.isConnected) this._welleMalen(el, s);
    } catch (e) { /* no waveform for this one, the tile works without it */ }
  }

  _welleMalen(el, s) {
    const c = el.querySelector('canvas');
    if (!c || !c.clientWidth) return;
    const dpr = window.devicePixelRatio || 1, b = c.clientWidth, h = c.clientHeight;
    c.width = Math.round(b * dpr); c.height = Math.round(h * dpr);
    const g = c.getContext('2d'); g.scale(dpr, dpr);
    // the tile colour (.welle has color: var(--ef)) as a real colour for the canvas, lighter towards the middle
    const rgb = (getComputedStyle(el).color.match(/[\d.]+/g) || [3, 169, 244]).slice(0, 3).map(Number);
    const echt = `rgb(${rgb.join(',')})`, hell = `rgb(${rgb.map((x) => Math.round(x + (255 - x) * 0.45)).join(',')})`;
    const verlauf = g.createLinearGradient(0, 0, 0, h); verlauf.addColorStop(0, echt); verlauf.addColorStop(0.5, hell); verlauf.addColorStop(1, echt);
    g.fillStyle = verlauf;
    const n = Math.min(s.spitzen.length, Math.max(40, Math.floor(b / 4))), schritt = s.spitzen.length / n, w = b / n, bw = Math.max(1.5, w * 0.62);
    const von = el.dataset.von != null ? Number(el.dataset.von) : null, bis = el.dataset.bis != null ? Number(el.dataset.bis) : null;
    for (let k = 0; k < n; k++) {
      let m = 0; for (let j = Math.floor(k * schritt), e = Math.floor((k + 1) * schritt); j < e; j++) m = Math.max(m, s.spitzen[j]);
      const t = ((k + 0.5) / n) * s.dauer, drin = von == null || (t >= von && t <= bis);
      g.globalAlpha = drin ? 0.95 : 0.2;  // a trimmed recording: only the trained part in full colour
      const y = Math.max(3, Math.pow(m, 0.8) * (h - 10)), x = k * w + (w - bw) / 2, r = Math.min(bw / 2, y / 2);
      g.beginPath(); if (g.roundRect) g.roundRect(x, (h - y) / 2, bw, y, r); else g.rect(x, (h - y) / 2, bw, y); g.fill();
    }
    g.globalAlpha = 1;
    el._dauer = s.dauer;
    el.classList.add('da');
  }

  // tap the waveform: play from there (a trimmed recording stops at its trim end)
  async _welleKlick(el, ev) {
    const id = el.dataset.welle, a = ((this._liste && this._liste.eintraege) || []).find((x) => x.id === id) || {};
    const r = el.getBoundingClientRect(), dauer = el._dauer || a.dauer;
    if (!dauer) { this._spielen(id); return; }
    const t = Math.max(0, Math.min(dauer, ((ev.clientX - r.left) / r.width) * dauer));
    const s = Array.isArray(a.schnitt) && a.schnitt.length === 2 ? a.schnitt : null;
    try { await this._abspielen(await this._blob(id), s ? Math.min(Math.max(t, s[0]), s[1] - 0.05) : t, s ? s[1] : null, id); } catch (e) { this._meldung(this.t('ging_nicht', { f: e.message })); }
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
      // a trimmed recording plays only its trimmed part, so reviewing later hears exactly what is trained
      const a = url ? null : ((this._liste && this._liste.eintraege) || []).find((x) => x.id === id);
      const s = a && Array.isArray(a.schnitt) && a.schnitt.length === 2 ? a.schnitt : null;
      await this._abspielen(url || await this._blob(id), s ? s[0] : 0, s ? s[1] : null, id);
    } catch (e) { this._meldung(this.t('ging_nicht', { f: e.message })); }
  }

  // play src from von to bis (null = to the end); one frame loop moves the play head, the ring and stops at bis
  async _abspielen(src, von = 0, bis = null, id = null) {
    const au = this._audio;
    au.pause();
    if (au.src !== src) { au.src = src; await new Promise((r) => { if (au.readyState >= 1) r(); else { au.addEventListener('loadedmetadata', r, { once: true }); au.addEventListener('error', r, { once: true }); } }); }
    this._bereich = [von || 0, bis];
    this._spielt = id; if (!id) this._ring(true);
    try { au.currentTime = von || 0; await au.play(); } catch (e) { this._meldung(this.t('ging_nicht', { f: e.message })); return; }
    cancelAnimationFrame(this._lauf);
    const schritt = () => {
      const [a, b] = this._bereich || [0, null];
      if (b != null && au.currentTime >= b) au.pause();
      const z = this._schnitt, box = z && this.shadowRoot.querySelector(`[data-schnittbox="${CSS.escape(z.id)}"]`);
      if (box && au.src === z.url) {
        const k = box.querySelector('.spielkopf'), knopf = box.querySelector('[data-sa="spielen"] ha-icon');
        if (k) { k.style.left = (au.currentTime / z.dauer) * 100 + '%'; k.classList.add('an'); }
        if (knopf) knopf.setAttribute('icon', au.paused ? 'mdi:play' : 'mdi:pause');
        this._schnittInfo(box);
      }
      if (this._spielt) {
        this._ring(au.paused, a, b);
        const w = this.shadowRoot.querySelector(`[data-welle="${CSS.escape(this._spielt)}"]`), k = w && w.querySelector('.spielkopf'), d = w && (w._dauer || au.duration);
        if (k && d) { const x = Math.min(100, (au.currentTime / d) * 100) + '%', g = w.querySelector('.gespielt'); k.style.left = x; k.classList.toggle('an', !au.paused); if (g) { g.style.width = x; g.classList.toggle('an', !au.paused); } }
      }
      if (!au.paused) this._lauf = requestAnimationFrame(schritt);
      else if (this._spielt && b != null) { this._spielt = null; this._ring(true); }
    };
    this._lauf = requestAnimationFrame(schritt);
  }

  _ring(aus, von = null, bis = null) {
    const [a, e] = von == null ? (this._bereich || [0, null]) : [von, bis];
    this.shadowRoot.querySelectorAll('.spielen').forEach((b) => {
      const an = !aus && b.dataset.spielen === this._spielt;
      const c = b.querySelector('circle'), ende = e != null ? e : this._audio.duration || 1, anteil = Math.min(1, Math.max(0, (this._audio.currentTime - a) / Math.max(0.01, ende - a)));
      c.style.strokeDashoffset = an ? 157 - 157 * anteil : 157;
      b.querySelector('ha-icon').setAttribute('icon', an && !this._audio.paused ? 'mdi:pause' : 'mdi:play');
    });
  }

  async _urteilen(id, urteil) {
    const zeile = this.shadowRoot.querySelector(`.eintrag[data-id="${CSS.escape(id)}"]`);
    const sel = zeile && zeile.querySelector('select[data-person]');
    const person = urteil === 'wort' ? (sel ? sel.value : this._person) : '';
    // feedback right away: the pressed button lights up (and the phone ticks), before the answer from HA
    const knopf = zeile && zeile.querySelector(`[data-urteil="${urteil}"]`);
    if (knopf) { knopf.classList.remove('drueck'); void knopf.offsetWidth; knopf.classList.add('drueck'); }
    try { if (navigator.vibrate) navigator.vibrate(12); } catch (e) { /* not supported */ }
    if (zeile) zeile.querySelectorAll('[data-urteil]').forEach((b) => b.classList.toggle('gewaehlt', b.dataset.urteil === urteil));
    try { await this._api('POST', 'urteil', { wort: this._wortId, ids: [id], urteil, person }); }
    catch (e) { this._meldung(this.t('ging_nicht', { f: this._fehlerText(e) })); return; }
    if (this._reiter === 'pruefen') { this._prGemacht = this._prGemacht || {}; this._prGemacht[this._wortId] = (this._prGemacht[this._wortId] || 0) + 1; this._prRing(); }
    if (this._reiter === 'pruefen' && zeile) {
      // stamp with the answer, then the tile slides away and the list closes the gap
      const icon = { wort: 'mdi:check-circle', kein_wort: 'mdi:close-circle', verworfen: 'mdi:delete' }[urteil] || 'mdi:check';
      this._wegGleiten(zeile, id, `<div class="stempel u-${esc(urteil)}"><ha-icon icon="${icon}"></ha-icon>${esc(this.t('u_' + urteil))}${urteil === 'wort' && person ? ' · ' + esc(person) : ''}</div>`);
    } else this._laden();
  }

  // the ring at the top fills with every decision, without drawing the page again
  _prRing() {
    const box = this.shadowRoot.querySelector('.pr-ring'), s = this._daten && this._daten.wort && this._daten.wort.statistik;
    if (!box || !s) return;
    const fertig = this._prGemacht[this._wortId] || 0, b0 = this._prBasis || { offen: s.offen, fertig }, offen = Math.max(0, b0.offen - (fertig - b0.fertig));
    const ring = box.querySelector('.ziel-ring'), vorn = box.querySelector('.vorn'), a = fertig / Math.max(1, fertig + offen), u = 2 * Math.PI * 16;
    if (vorn) { vorn.style.animation = 'none'; vorn.style.strokeDashoffset = (u * (1 - a)).toFixed(1); }
    const zahl = ring && ring.querySelector('span'); if (zahl) zahl.textContent = Math.round(a * 100) + '%';
    if (ring && a >= 1 && !ring.classList.contains('voll')) { ring.classList.add('voll'); if (zahl) zahl.outerHTML = '<ha-icon icon="mdi:check"></ha-icon>'; }
    box.classList.remove('tick'); void box.offsetWidth; box.classList.add('tick');
    const b = this.shadowRoot.querySelector('.pr-text b'); if (b) b.textContent = this.t('pr_kopf_offen', { n: offen });
  }

  _wegGleiten(zeile, id, stempel) {
    zeile.classList.add('weg');
    zeile.insertAdjacentHTML('beforeend', stempel);
    const ruhig = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (zeile.animate && !ruhig) {
      const h = zeile.offsetHeight;
      zeile.animate([{ opacity: 1, transform: 'none', height: h + 'px', marginBottom: '0px' }, { opacity: 1, transform: 'none', height: h + 'px', offset: 0.45 },
        { opacity: 0, transform: 'translateX(48px) scale(.97)', height: '0px', paddingTop: '0px', paddingBottom: '0px', marginBottom: '-10px', borderWidth: '0px' }],
      { duration: 900, easing: 'cubic-bezier(.4,0,.2,1)', fill: 'forwards' });
    } else setTimeout(() => { zeile.style.display = 'none'; }, 600);
    if (this._spielt === id) this._audio.pause();
    const rest = [...this.shadowRoot.querySelectorAll('.eintrag:not(.weg)')];
    this._aktiv = Math.min(this._aktiv, rest.length - 1);
    const naechste = this._markieren();
    if (naechste && this._autoplay) this._spielen(naechste.dataset.id);
    clearTimeout(this._nachladen); this._nachladen = setTimeout(() => this._laden(), rest.length ? 4000 : 300);
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
<div class="rec"><button class="gross ${r.an ? 'an' : ''}" data-a="rec" ${sicher ? '' : 'disabled'}><ha-icon icon="${r.an ? 'mdi:stop' : 'mdi:microphone'}"></ha-icon></button><div class="rec-welle ${r.an ? 'an' : ''}"><canvas id="recwelle" height="72"></canvas></div><div class="pegel" title="${esc(this.t('au_pegel'))}"><i id="pegel"></i></div><div class="klein" id="recinfo">${esc(this.t(r.an ? 'au_stopp' : 'au_start'))}</div></div>
<div id="takes"></div>
<div class="rec-ziel">${this._zielRing(bisher, 50 * Math.max(1, Object.entries(s.personen || {}).filter(([n, p]) => n !== 'Unbekannt' && (r.modus === 'wort' ? p.wort : p.kein_wort)).length))}<div class="klein">${esc(this.t('au_wieviel', { n: bisher }))}</div></div></ha-card>`;
  }

  _recZeichnen() {
    const box = this.shadowRoot.getElementById('takes'); if (!box) return;
    const r = this._rec;
    box.innerHTML = r.takes.length ? `<div class="takes">${r.takes.map((t, i) => `<span class="take ${t.modus === 'kein_wort' ? 'gegen' : ''} ${Date.now() - (t.zeit || 0) < 1500 ? 'neu' : ''}">${this._miniForm(t.form)}${this._zahl(t.dauer, 1)} s<button data-takespielen="${i}" title="${esc(this.t('pr_abspielen'))}"><ha-icon icon="mdi:play"></ha-icon></button><button data-takeweg="${i}"><ha-icon icon="mdi:close"></ha-icon></button></span>`).join('')}</div>
<div class="zeile" style="margin-top:12px"><button class="k haupt" data-a="recspeichern"><ha-icon icon="mdi:content-save-outline"></ha-icon>${esc(this.t('au_speichern', { n: r.takes.length }))}</button><button class="k leise" data-a="recverwerfen">${esc(this.t('au_verwerfen'))}</button></div>` : `<div class="klein" style="text-align:center">${esc(this.t('au_leer'))}</div>`;
    const knopf = this.shadowRoot.querySelector('[data-a="rec"]');
    if (knopf) { knopf.classList.toggle('an', r.an); knopf.querySelector('ha-icon').setAttribute('icon', r.an ? 'mdi:stop' : 'mdi:microphone'); }
    const welle = this.shadowRoot.querySelector('.rec-welle'); if (welle) welle.classList.toggle('an', r.an);
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
    r.spitzen = [];
    // Einfache Trennung nach Lautstärke: Sprache = deutlich über dem Grundrauschen
    let rauschen = 0.004, imWort = false, still = 0, puffer = [], vorlauf = [];
    const VOR = Math.ceil(0.3 / block), NACH = Math.ceil(0.35 / block), LANG = Math.ceil(3.0 / block);
    proz.onaudioprocess = (ev) => {
      const x = new Float32Array(ev.inputBuffer.getChannelData(0));
      let s = 0; for (let i = 0; i < x.length; i++) s += x[i] * x[i];
      const rms = Math.sqrt(s / x.length);
      const p = this.shadowRoot.getElementById('pegel'); if (p) p.style.width = Math.min(100, Math.sqrt(rms) * 300) + '%';
      let spitze = 0; for (let i = 0; i < x.length; i++) spitze = Math.max(spitze, Math.abs(x[i]));
      r.spitzen.push({ p: spitze, wort: imWort }); if (r.spitzen.length > 400) r.spitzen.shift();
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
    this._recWelle();
  }

  // live wave while recording: speech that becomes a take glows in the colour of the word
  _recWelle() {
    const r = this._rec;
    const malen = () => {
      const c = this.shadowRoot.getElementById('recwelle');
      if (!r.an || !c) { r.welle = null; return; }
      const b = c.clientWidth || 300, h = c.height; if (c.width !== b) c.width = b;
      const g = c.getContext('2d'), st = getComputedStyle(this);
      const farbe = r.modus === 'kein_wort' ? (st.getPropertyValue('--error-color').trim() || '#f44336') : (st.getPropertyValue('--primary-color').trim() || '#03a9f4');
      g.clearRect(0, 0, b, h);
      const n = Math.floor(b / 4), sp = r.spitzen.slice(-n), v = n - sp.length;
      sp.forEach((x, i) => {
        const y = Math.max(2, Math.min(h - 2, Math.sqrt(x.p) * h * 1.2));
        g.globalAlpha = (x.wort ? 0.55 : 0.18) + 0.45 * (i / n);
        g.fillStyle = x.wort ? farbe : st.getPropertyValue('--secondary-text-color').trim() || '#888';
        g.fillRect((v + i) * 4, (h - y) / 2, 2.5, y);
      });
      g.globalAlpha = 1;
      r.welle = requestAnimationFrame(malen);
    };
    if (!r.welle) r.welle = requestAnimationFrame(malen);
  }

  _miniForm(form) {
    if (!form) return '';
    return `<svg class="mini-form" viewBox="0 0 48 16" aria-hidden="true">${form.map((x, i) => { const y = Math.max(1.5, Math.min(16, Math.sqrt(x) * 18)); return `<rect x="${i * 2}" y="${((16 - y) / 2).toFixed(1)}" width="1.3" height="${y.toFixed(1)}" rx=".6"/>`; }).join('')}</svg>`;
  }

  _zielRing(wert, ziel) {
    const a = Math.min(1, wert / ziel), u = 2 * Math.PI * 16;
    return `<div class="ziel-ring ${a >= 1 ? 'voll' : ''}"><svg viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" class="hinten"/><circle cx="20" cy="20" r="16" class="vorn" style="stroke-dasharray:${u.toFixed(1)};stroke-dashoffset:${(u * (1 - a)).toFixed(1)};--voll:${u.toFixed(1)}"/></svg>${a >= 1 ? '<ha-icon icon="mdi:check"></ha-icon>' : `<span>${Math.round(a * 100)}%</span>`}</div>`;
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
    const form = Array.from({ length: 24 }, (_, k) => { let x = 0; for (let i = Math.floor((k * m) / 24); i < Math.floor(((k + 1) * m) / 24); i++) x = Math.max(x, Math.abs(aus[i])); return x / 32768; });
    this._rec.takes.push({ blob, url: URL.createObjectURL(blob), dauer: m / 16000, modus: this._rec.modus, form, zeit: Date.now() });
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
    const filter = ['bewertet', 'auto', 'hochgeladen', 'test', 'alle'];
    const z = this._filter.zelle;
    return `<div class="zeile" style="margin-bottom:10px">${z ? `<button class="chip an" data-a="zelle_weg"><ha-icon icon="mdi:table" style="--mdc-icon-size:16px"></ha-icon>${esc(this.t('tb_zeile_' + z.zeile))} · ${this._zahl(z.von)}–${this._zahl(Math.min(1, z.bis))}${z.echo ? ' · ' + esc(z.echo) : ''} ✕</button>` : filter.map((k) => `<button class="chip ${this._filter.verlauf === k ? 'an' : ''}" data-verlauf="${k}">${esc(this.t('v_' + k))}</button>`).join('')}<span class="klein">${esc(this.t('v_anzahl', { n: l.gesamt }))}</span></div>
${!z && this._filter.verlauf === 'bewertet' ? this._entscheidZeile(l) : `<div class="klein" style="margin-bottom:10px">${esc(this.t('v_hilfe'))}</div>`}
${l.gesamt ? `<div class="liste">${l.eintraege.map((a, i) => this._eintrag(a, i, false)).join('')}</div>` : `<ha-card><div class="leer">${esc(this.t('v_leer'))}</div></ha-card>`}
${l.seiten > 1 ? `<div class="zeile" style="justify-content:center;margin-top:12px"><button class="k" data-seite="-1" ${l.seite ? '' : 'disabled'}>${esc(this.t('zurueck'))}</button><span class="klein">${esc(this.t('seite', { a: l.seite + 1, b: l.seiten }))}</span><button class="k" data-seite="1" ${l.seite + 1 < l.seiten ? '' : 'disabled'}>${esc(this.t('weiter'))}</button></div>` : ''}`;
  }

  // your answers at a glance: said / not said with their counts, and the ones the device disagreed with first
  _entscheidZeile(l) {
    const n = l.anzahl || {}, f = this._filter, w = n.wort || 0, k = n.kein_wort || 0;
    const chip = (attr, wert, an, text) => `<button class="chip ${an ? 'an' : ''}" ${attr}="${wert}">${esc(text)}</button>`;
    return `<div class="zeile v-entscheid">${chip('data-vurteil', '', !f.urteil, this.t('v_alle_urteile', { n: w + k }))}${chip('data-vurteil', 'wort', f.urteil === 'wort', this.t('v_gesagt', { n: w }))}${chip('data-vurteil', 'kein_wort', f.urteil === 'kein_wort', this.t('v_nicht', { n: k }))}
<span class="v-trenn"></span>${chip('data-vsort', '', !f.sort, this.t('v_sort_neu'))}${chip('data-vsort', 'zweifel', f.sort === 'zweifel', this.t('v_sort_zweifel'))}</div>
<div class="klein" style="margin-bottom:10px">${esc(this.t(f.sort === 'zweifel' ? 'v_zweifel_hilfe' : 'v_hilfe'))}</div>`;
  }

  // ---------- Hochladen ----------
  _hochladenSeite() {
    const s = this._daten.wort.statistik;
    return `<ha-card><h2>${esc(this.t('h_titel'))}</h2>
<div class="zeile" style="margin-bottom:12px"><span class="klein">${esc(this.t('h_wer'))}</span>${this._personWahl(this._person, 'hoch')}</div>
<div class="abwurf" data-a="datei"><span class="ab-ikon"><ha-icon icon="mdi:folder-zip-outline"></ha-icon><i></i><i></i></span><p>${this.t('h_ziehen')}</p><p class="klein">${this.t('h_ordner')}</p></div>
<div id="hochergebnis" style="margin-top:12px">${this._hochErgebnis || ''}</div></ha-card>
<ha-card><h2>${esc(this.t('h_woher'))}</h2><div class="klein" style="line-height:1.6">${this.t('h_woher_text')}</div></ha-card>
<ha-card><h2>${esc(this.t('h_bisher'))}</h2>${(() => { const l = Object.entries(s.personen), max = Math.max(1, ...l.map(([, n]) => n.wort + n.kein_wort));
  return l.length ? this._personen(l.map(([p, n]) => [p === 'Unbekannt' ? this.t('unbekannt') : p, (n.wort + n.kein_wort) / max, this.t('hl_person_info', { a: n.wort, b: n.kein_wort })])) : `<div class="klein">${esc(this.t('h_nichts'))}</div>`; })()}</ha-card>`;
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
  _ergebnisText(e) { return this.t({ eingespielt: 'e_eingespielt', besser: 'e_besser', nicht_besser: 'e_nicht_besser', 'nicht besser': 'e_nicht_besser', gleich: 'e_gleich', laeuft_nicht: 'e_laeuft_nicht', fehler: 'e_fehler' }[e] || e); }

  _uhr(sek) { return new Date(sek * 1000).toLocaleTimeString(this._loc, { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  _spanne(sek) { sek = Math.max(0, Math.round(sek)); const h = Math.floor(sek / 3600), m = Math.floor(sek / 60) % 60, s = sek % 60; return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`; }

  // Everything the trainer reports about the current (or last) run: steps with times, load, live log
  _details(w, laeuft) {
    const l = w.live;
    if (!l || !(l.protokoll || []).length && !(l.schritte || []).length) return '';
    const jetzt = Date.now() / 1000, fehler = w.training.phase === 'fehler', schritte = l.schritte || [];
    const aktuell = schritte.length ? schritte[schritte.length - 1] : null;
    const phasen = w.training.vergleich ? ['vorbereiten', 'daten', 'test'] : LAEUFT;
    const reihe = phasen.slice(phasen.indexOf(aktuell ? aktuell.phase : 'vorbereiten') + 1);
    const zeilen = schritte.map((x, i) => {
      const letzte = i === schritte.length - 1, offen = letzte && laeuft && !x.ende;
      const icon = offen ? '<ha-icon class="drehen" icon="mdi:loading"></ha-icon>' : letzte && fehler ? '<ha-icon class="rot" icon="mdi:close-circle"></ha-icon>' : '<ha-icon class="gruen" icon="mdi:check-circle"></ha-icon>';
      const ende = x.ende || (offen ? jetzt : x.start);
      return `${icon}<span>${esc(this._schritt(x.detail || x.schritt))}</span><span class="klein">${this._uhr(x.start)} · ${this._spanne(ende - x.start)}</span>`;
    }).join('') + (laeuft ? reihe.map((p) => `<ha-icon class="spaeter" icon="mdi:circle-outline"></ha-icon><span class="spaeter">${esc(this.t('p_' + p))}</span><span></span>`).join('') : '');
    const s = l.system || {};
    const balken = (wert, max) => `<div class="fortschritt"><i style="width:${Math.min(100, Math.max(0, (wert / max) * 100))}%"></i></div>`;
    const last = laeuft && (s.cpu != null || s.ram_gb) ? `<ha-card><h2>${esc(this.t('t_last'))}</h2><div class="last">
${s.cpu != null ? `<span>${esc(this.t('t_cpu'))}</span>${balken(s.cpu, 100)}<span class="klein">${s.cpu} % · ${esc(this.t('t_kerne', { n: s.kerne }))}</span>` : ''}
${s.ram_gb ? `<span>${esc(this.t('t_ram'))}</span>${balken(s.ram_belegt_gb || 0, s.ram_gb)}<span class="klein">${this._zahl(s.ram_belegt_gb, 1)} / ${this._zahl(s.ram_gb, 1)} GB</span>` : ''}
${[['platte_warten', 't_platte'], ['speicher_warten', 't_speicher_warten'], ['cpu_warten', 't_cpu_warten']].map(([k, t]) => s[k] != null ? `<span>${esc(this.t(t))}</span>${balken(s[k], 100)}<span class="klein">${Math.round(s[k])} %</span>` : '').join('')}
${s.platz_frei_gb != null ? `<span>${esc(this.t('t_platz_frei'))}</span><span></span><span class="klein">${this._zahl(s.platz_frei_gb, 1)} GB</span>` : ''}
</div>${Math.max(s.platte_warten || 0, s.speicher_warten || 0) >= 50 && (s.cpu ?? 100) < 50 ? `<div class="klein" style="margin-top:8px">${esc(this.t('t_platte_hinweis'))}</div>` : ''}</ha-card>` : '';
    const fl = this._logFilter || 'alle', arten = { wichtig: ['info', 'warnung', 'fehler'], ausgabe: ['aus', 'warnung_aus', 'balken', 'schritt'] };
    const alle = l.protokoll || [], gezeigt = fl === 'alle' ? alle : alle.filter(([, art]) => arten[fl].includes(art));
    const log = gezeigt.slice().reverse().map(([z, art, text]) => `<div class="l-${esc(art)}"><span class="z">${this._uhr(z)}</span>${esc(text)}</div>`).join('');
    const chips = ['alle', 'wichtig', 'ausgabe'].map((k) => `<button class="chip ${fl === k ? 'an' : ''}" data-logfilter="${k}">${esc(this.t('t_log_' + k))}</button>`).join('');
    const bs = laeuft ? (l.balken || []) : [];
    const aktiv = bs.length ? `<ha-card class="laeuft"><h2><span class="lebt"></span>${esc(this.t('t_aktiv'))}</h2><div class="aktiv">${bs.map((b) => {
      const name = b.name === '·' ? this.t('t_teilschritt') : this._schritt(b.name);
      const rest = b.rest && b.rest !== '00:00' && b.rest !== '?' ? b.rest : b.rest_min ? this.t('t_rest_min', { n: b.rest_min }) : '';
      const info = [b.n != null && b.gesamt != null ? `${b.n} / ${b.gesamt}` : '', b.tempo || '', rest ? this.t('t_noch', { z: rest }) : ''].filter(Boolean).join(' · ');
      const icon = /^omni|omnivoice/i.test(b.name) ? 'mdi:account-voice' : b.name === '·' ? 'mdi:cog-sync-outline' : /lade|download/i.test(b.name) ? 'mdi:download' : 'mdi:progress-clock';
      return `<div class="aktiv-z"><ha-icon icon="${icon}"></ha-icon><div><div class="zeile weit"><b>${esc(name)}</b><span class="proz">${this._zahl(b.prozent, b.prozent < 10 ? 1 : 0)} %</span></div><div class="fortschritt"><i style="width:${Math.min(100, Math.max(0, b.prozent))}%"></i></div>${info ? `<div class="klein">${esc(info)}</div>` : ''}</div></div>`;
    }).join('')}</div></ha-card>` : '';
    return `<ha-card><div class="zeile weit"><h2 style="margin:0">${esc(this.t('t_ablauf'))}</h2><span class="klein">${l.start ? esc(this.t('t_laeuft_seit', { z: this._spanne((aktuell && !laeuft && aktuell.ende ? aktuell.ende : jetzt) - l.start) })) : ''}</span></div><div class="ablauf" style="margin-top:10px">${zeilen}</div></ha-card>
${aktiv}${last}
${this._klapp('k_protokoll', 'mdi:text-box-outline', this.t('t_protokoll'), [this.t('t_log_zeilen', { n: gezeigt.length, g: alle.length }), l.zeit ? this.t('t_stand', { z: this._zeit(l.zeit) }) : ''].filter(Boolean).join(' · '), `<div class="zeile weit" style="flex-wrap:wrap;gap:6px"><div class="zeile" style="gap:6px">${chips}</div><span class="klein">${esc(this.t('t_log_zeilen', { n: gezeigt.length, g: alle.length }))} <button class="k leise" data-a="log_kopieren">${esc(this.t('es_kopieren'))}</button></span></div>
<div class="protokoll" style="margin-top:8px">${log || esc(this.t('t_protokoll_leer'))}</div>`)}`;
  }

  // training at work: sound flows into a small network that fires layer by layer, the result lights up.
  // Pure CSS; the shared start offset keeps the loop running smoothly when the page refreshes its data.
  _magie(phase, farbe) {
    const d0 = `-${((Date.now() % 12000) / 1000).toFixed(2)}s`;
    const schichten = [[250, [18, 39, 60, 81]], [370, [10, 29, 48, 67, 86]], [490, [26, 48, 70]], [600, [48]]];
    let linien = '', knoten = '', teile = '', k = 0;
    const kante = (x1, y1, x2, y2, s) => {
      linien += `<line class="m-linie" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
      if ((k++ % 2) === 0) teile += `<circle cx="${x1}" cy="${y1}" r="2.6" style="--dx:${x2 - x1}px;--dy:${y2 - y1}px;--s:${s}"/>`;
    };
    schichten[0][1].forEach((y) => kante(160, 48, 250, y, 0));
    for (let l = 0; l < schichten.length - 1; l++) {
      const [xa, ya] = schichten[l], [xb, yb] = schichten[l + 1];
      ya.forEach((y1) => yb.forEach((y2) => kante(xa, y1, xb, y2, l + 1)));
    }
    schichten.forEach(([x, ys], l) => ys.forEach((y) => { knoten += `<circle cx="${x}" cy="${y}" r="${l === 3 ? 9 : 6}" style="--s:${l + 1}"/>`; }));
    const welle = Array.from({ length: 16 }, (_, i) => `<rect x="${10 + i * 9}" y="${48 - 6 - (i % 5) * 7}" width="5" height="${12 + (i % 5) * 14}" rx="2.5" style="--i:${i}"/>`).join('');
    const stern = (x, y, s) => `<path class="m-stern" style="--s:${s}" d="M${x} ${y - 7}L${x + 2} ${y - 2}L${x + 7} ${y}L${x + 2} ${y + 2}L${x} ${y + 7}L${x - 2} ${y + 2}L${x - 7} ${y}L${x - 2} ${y - 2}Z"/>`;
    return `<svg class="magie st-${esc(phase)}" viewBox="0 0 640 96" preserveAspectRatio="xMidYMid meet" style="--d0:${d0};${farbe ? `--farbe:${esc(farbe)}` : ''}" aria-hidden="true">
<g class="m-welle">${welle}</g><g class="m-netz">${linien}<g class="m-teil">${teile}</g><g class="m-knoten">${knoten}</g></g>
<circle class="m-ziel" cx="600" cy="48" r="9"/>${stern(626, 18, 0)}${stern(578, 84, 1)}${stern(630, 76, 2)}</svg>`;
  }

  // Training as a spell that you can follow: a path with one station per real step of the trainer, and below it a
  // scene for the step running now, driven by its real numbers (recordings, voices, training steps, learning curve).
  _zauber(w) {
    if (w.training.vergleich) return this._zauberVgl(w);
    const t = w.training, l = w.live || {}, bs = l.balken || [], schl = (x) => String(x || '').split(':')[0];
    const jetzt = schl(t.schritt), b = bs.find((x) => schl(x.name) === jetzt) || bs[0] || null;
    const stationen = [['vorbereiten', 'mdi:package-variant'], ['aufnahmen', 'mdi:microphone-message'], ['stimmen', 'mdi:account-voice'],
      ['merkmale', 'mdi:blur'], ['training', 'mdi:brain'], ['test', 'mdi:shield-check-outline'], ['senden', 'mdi:send']];
    const zu = { grunddaten: 0, laden: 0, aufnahmen: 1, stimmen: 2, aehnlich_pruefen: 2, stimmen_omni: 2, omni_wort: 2, omni_gerede: 2,
      merkmale: 3, merkmale_gerede: 3, auswahl: 4, training: 4, weitertrainieren: 4, kandidat: 4, kandidat_pruefen: 4, mitteln: 4,
      test_neu: 5, test_alt: 5, senden: 6 };
    const phaseZu = { vorbereiten: 0, daten: 1, merkmale: 3, training: 4, test: 5 };
    const nr = zu[jetzt] ?? phaseZu[t.phase] ?? 0;
    // progress inside the step: its own bar, else what the detail says (recordings i/n), else the share of the phase
    let anteil = b ? b.prozent / 100 : null, n = b && b.n, g = b && b.gesamt;
    const det = String(t.schritt || '').split(':')[1] || '';
    if (anteil == null && /^\d+\/\d+$/.test(det)) { [n, g] = det.split('/'); anteil = Number(n) / Math.max(1, Number(g)); }
    if (anteil == null) anteil = 0;
    anteil = Math.max(0, Math.min(1, anteil));
    const u = 2 * Math.PI * 15;
    const pfad = stationen.map(([k, icon], i) => {
      const art = i < nr ? 'durch' : i === nr ? 'jetzt' : '';
      return `${i ? `<div class="zp-linie ${i <= nr ? 'durch' : ''}"><i></i></div>` : ''}<div class="zp-st ${art}" style="--n:${i}"><span class="zp-punkt">${i === nr
        ? `<svg viewBox="0 0 36 36"><circle cx="18" cy="18" r="15" class="h"/><circle cx="18" cy="18" r="15" class="v" style="stroke-dasharray:${u.toFixed(1)};stroke-dashoffset:${(u * (1 - anteil)).toFixed(1)}"/></svg>` : ''}<ha-icon icon="${i < nr ? 'mdi:check' : icon}"></ha-icon></span><span class="zp-name">${esc(this.t('zp_' + k))}</span></div>`;
    }).join('');
    return `<div class="zauber" style="--farbe:${esc(w.farbe || this._farbe(this._wortKurz() || {}))}"><div class="zp">${pfad}</div>${this._szene(stationen[nr][0], jetzt, det, anteil, n, g, w)}</div>`;
  }

  // the path as a row of stations: done ones ticked, the running one with a ring that fills with its progress
  _pfad(stationen, nr, anteil, name) {
    const u = 2 * Math.PI * 15;
    return stationen.map(([k, icon], i) => {
      const art = i < nr ? 'durch' : i === nr ? 'jetzt' : '';
      return `${i ? `<div class="zp-linie ${i <= nr ? 'durch' : ''}"><i></i></div>` : ''}<div class="zp-st ${art}" style="--n:${i}"><span class="zp-punkt">${i === nr
        ? `<svg viewBox="0 0 36 36"><circle cx="18" cy="18" r="15" class="h"/><circle cx="18" cy="18" r="15" class="v" style="stroke-dasharray:${u.toFixed(1)};stroke-dashoffset:${(u * (1 - anteil)).toFixed(1)}"/></svg>` : ''}<ha-icon icon="${i < nr ? 'mdi:check' : icon}"></ha-icon></span><span class="zp-name">${esc(name(k))}</span></div>`;
    }).join('');
  }

  // A fair test of two stored versions: no training, its own path (data, both models, test A, test B, verdict) and a
  // live duel board fed by the interim figures of both tests (what each version hears so far, false wakes so far)
  _zauberVgl(w) {
    const t = w.training, v = t.vergleich, l = w.live || {}, bs = l.balken || [], schl = (x) => String(x || '').split(':')[0];
    const jetzt = schl(t.schritt), b = bs.find((x) => schl(x.name) === jetzt) || null;
    const stationen = [['vorbereiten', 'mdi:package-variant'], ['aufnahmen', 'mdi:microphone-message'], ['pruefdaten', 'mdi:database-check-outline'],
      ['modelle', 'mdi:download'], ['a', 'mdi:alpha-a-circle-outline'], ['b', 'mdi:alpha-b-circle-outline'], ['urteil', 'mdi:scale-balance']];
    const zu = { grunddaten: 0, laden: 0, aufnahmen: 1, stimmen: 2, aehnlich_pruefen: 2, stimmen_omni: 2, omni_wort: 2, omni_gerede: 2,
      vgl_modelle: 3, vgl_a: 4, vgl_b: 5, vgl_urteil: 6 };
    const nr = zu[jetzt] ?? (t.phase === 'test' ? 4 : t.phase === 'daten' ? 1 : 0);
    const det = String(t.schritt || '').split(':')[1] || '';
    let anteil = b ? b.prozent / 100 : null;
    if (anteil == null && /^\d+\/\d+$/.test(det)) { const [n, g] = det.split('/'); anteil = Number(n) / Math.max(1, Number(g)); }
    anteil = Math.max(0, Math.min(1, anteil ?? 0));
    const name = (k) => k === 'a' ? `v${v.a}` : k === 'b' ? `v${v.b}` : this.t('vz_' + k);
    const pfad = this._pfad(stationen, nr, anteil, name);
    const st = stationen[nr][0];
    let szene;
    if (st === 'a' || st === 'b' || st === 'urteil') szene = this._vglDuell(w, v, st, l.pruefen || {});
    else if (st === 'modelle') {
      const d0 = `-${((Date.now() % 12000) / 1000).toFixed(2)}s`;
      szene = `<div class="szene sz-modelle" style="--d0:${d0}"><svg viewBox="0 0 640 110" aria-hidden="true">${[v.a, v.b].map((x, i) => `<g class="vz-datei" style="--i:${i}"><rect x="${150 + i * 260}" y="22" width="80" height="64" rx="10"/><text x="${190 + i * 260}" y="62">v${x}</text></g>`).join('')}<g class="vz-ha"><rect x="296" y="36" width="48" height="36" rx="8"/><path d="M308 60 l12 -12 l12 12"/></g></svg><div class="sz-text">${esc(this.t('vz_s_modelle', { a: v.a, b: v.b }))}</div></div>`;
    } else {
      const station = st === 'pruefdaten' ? 'stimmen' : st;
      const n = b && b.n, g = b && b.gesamt;
      szene = this._szene(station, jetzt, det, anteil, n, g, w);
      if (st === 'pruefdaten') szene = szene.replace(/<div class="sz-text">[\s\S]*?<\/div>/, `<div class="sz-text">${esc(this.t('vz_s_pruefdaten'))}</div>`);
    }
    return `<div class="zauber vz" style="--farbe:${esc(w.farbe || this._farbe(this._wortKurz() || {}))}"><div class="zp">${pfad}</div>${szene}</div>`;
  }

  // live duel: both versions on the same recordings, A first, then B; the scale leans towards the one ahead so far
  _vglDuell(w, v, st, pr) {
    const A = pr.vgl_a || null, B = pr.vgl_b || null, BED = ['ruhig', 'leise', 'hall', 'musik', 'gerede', 'alltag'], SCHW = ['weit', 'laut_tv', 'laut_musik', 'chaos'];
    const quote = (x, ks) => x && x.n ? ks.reduce((s, k) => s + ((x.hoert || {})[k] || 0), 0) / (ks.length * x.n) : null;
    const qa = quote(A, BED), qb = quote(B, BED);
    const neigung = qa != null && qb != null ? Math.max(-14, Math.min(14, (qa - qb) * 140)) : 0;
    const vorn = qa == null || qb == null ? this.t(st === 'a' ? 'vz_a_laeuft' : 'vz_b_wartet', { a: v.a, b: v.b })
      : Math.abs(qa - qb) < 0.01 ? this.t('vz_gleichauf') : this.t('vz_vorn', { v: qa > qb ? v.a : v.b });
    const teile = ['lagen', 'aehnlich', 'gerede', 'geraeusch', 'stille'];
    const lauf = st === 'a' ? A : st === 'b' ? B : null, teil = lauf ? lauf.teil : '';
    const kette = st === 'urteil' ? '' : `<div class="vz-kette">${teile.map((k, i) => {
      const idx = teile.indexOf(teil), art = i < idx ? 'durch' : i === idx ? 'jetzt' : '';
      const fort = lauf && k === teil ? (k === 'lagen' ? lauf.n / Math.max(1, lauf.gesamt) : k === 'aehnlich' ? (lauf.aehnlich_n || 0) / Math.max(1, lauf.aehnlich_gesamt || 1)
        : ((lauf.min || {})[k] || 0) / Math.max(0.1, (lauf.max_min || {})[k] || 1)) : 0;
      return `<span class="vz-glied ${art}" style="--f:${Math.round(Math.min(1, fort) * 100)}%"><i></i>${esc(this.t('vz_t_' + k))}</span>`;
    }).join('')}</div>`;
    const spalte = (x, nr, aktiv) => `<div class="vz-kopf ${aktiv ? 'an' : ''}"><b>v${nr}</b><span class="klein">${esc(x ? (x.n >= x.gesamt && x.teil === 'stille' && !aktiv ? this.t('vz_fertig') : this.t('vz_gehoert', { n: x.n, g: x.gesamt })) : this.t('vz_wartet'))}</span></div>`;
    const zelle = (x, k) => {
      if (!x || !x.n) return '<div class="vz-zelle vz-leer"><i></i><span>–</span></div>';
      const q = ((x.hoert || {})[k] || 0) / x.n;
      return `<div class="vz-zelle"><i style="--w:${(q * 100).toFixed(1)}%"></i><span>${this._pct(q)}</span></div>`;
    };
    const fehl = (x, k) => {
      if (!x || !(x.min || {})[k]) return '<div class="vz-fehl vz-leer">–</div>';
      return `<div class="vz-fehl ${(x.fehl || {})[k] ? 'rot' : ''}">${esc(this.t('vz_fehl_wert', { n: (x.fehl || {})[k] || 0, m: this._zahl((x.min || {})[k], 0) }))}</div>`;
    };
    const zeilen = (ks) => ks.map((k) => `<div class="vz-z"><span>${esc(this.t('b_' + k))}</span>${zelle(A, k)}${zelle(B, k)}</div>`).join('');
    const waage = `<svg class="vz-waage" viewBox="0 0 160 80" aria-hidden="true"><path class="fuss" d="M80 30 V72 M60 74 H100"/><g class="balken" style="--neig:${neigung.toFixed(1)}deg"><line x1="22" y1="30" x2="138" y2="30"/><g class="schale"><path d="M22 30 L10 52 M22 30 L34 52"/><path d="M6 52 Q22 62 38 52 Z"/><text x="22" y="74">v${v.a}</text></g><g class="schale"><path d="M138 30 L126 52 M138 30 L150 52"/><path d="M122 52 Q138 62 154 52 Z"/><text x="138" y="74">v${v.b}</text></g></g><circle cx="80" cy="30" r="5" class="achse"/></svg>`;
    return `<div class="szene vz-duell ${st === 'urteil' ? 'fertig' : ''}">
<div class="vz-oben">${spalte(A, v.a, st === 'a')}<div class="vz-mitte">${waage}<div class="klein">${esc(vorn)}</div></div>${spalte(B, v.b, st === 'b')}</div>${kette}
<div class="vz-tab"><div class="vz-z vz-zk"><span>${esc(this.t('vz_hoert'))}</span><span>v${v.a}</span><span>v${v.b}</span></div>${zeilen(BED)}
<div class="vz-z vz-zk"><span>${esc(this.t('vz_hart'))}</span><span></span><span></span></div>${zeilen(SCHW)}
<div class="vz-z vz-zk"><span>${esc(this.t('vz_springt'))}</span><span></span><span></span></div>${['gerede', 'geraeusch', 'stille'].map((k) => `<div class="vz-z"><span>${esc(this.t('vz_f_' + k))}</span>${fehl(A, k)}${fehl(B, k)}</div>`).join('')}</div>
<div class="klein vz-fuss">${esc(this.t(st === 'urteil' ? 'vz_s_urteil' : 'vz_vorlaeufig'))}</div></div>`;
  }

  _szene(station, schritt, det, anteil, n, g, w) {
    const wort = w.einstellungen.wort, d0 = `-${((Date.now() % 12000) / 1000).toFixed(2)}s`, zahl = (x) => Number(x).toLocaleString(this._loc);
    const zaehler = n != null && g != null ? `${zahl(n)} / ${zahl(g)}` : `${Math.round(anteil * 100)} %`;
    let bild = '', text = '';
    const kessel = `<g class="sz-kessel"><path d="M282 70 Q320 108 358 70 Z"/><ellipse cx="320" cy="70" rx="38" ry="7"/><g class="sz-dampf"><circle cx="306" cy="58" r="4"/><circle cx="322" cy="50" r="5"/><circle cx="336" cy="60" r="3.5"/></g></g>`;
    if (station === 'vorbereiten') {
      bild = `${kessel}${[0, 1, 2, 3].map((i) => `<rect class="sz-flieg" x="${60 + i * 50}" y="30" width="18" height="16" rx="3" style="--i:${i}"/>`).join('')}`;
      text = this.t('zs_vorbereiten');
    } else if (station === 'aufnahmen') {
      const k = 8, an = Math.round(anteil * k);
      bild = `${kessel}${Array.from({ length: k }, (_, i) => `<g class="sz-aufn ${i < an ? 'drin' : ''}" style="--i:${i};transform:translate(${40 + i * 26}px,0)"><rect x="0" y="34" width="3" height="12" rx="1.5"/><rect x="5" y="28" width="3" height="24" rx="1.5"/><rect x="10" y="32" width="3" height="16" rx="1.5"/></g>`).join('')}`;
      text = this.t('zs_aufnahmen', { z: zaehler });
    } else if (station === 'stimmen') {
      if (schritt === 'aehnlich_pruefen') {
        bild = `<g class="sz-ohr"><path d="M300 30 q24 -6 30 18 q2 14 -12 22 q-6 4 -6 12" /><circle cx="314" cy="48" r="5"/></g>${[0, 1, 2, 3, 4, 5].map((i) => `<g class="sz-wahl ${i % 3 === 1 ? 'raus' : 'rein'}" style="--i:${i}"><rect x="120" y="40" width="64" height="18" rx="9"/></g>`).join('')}`;
        text = this.t('zs_aehnlich');
      } else {
        const k = 9, an = Math.max(1, Math.round(anteil * k));
        bild = Array.from({ length: k }, (_, i) => { const x = 20 + i * 66, y = i % 2 ? 58 : 24; return `<g class="sz-blase ${i < an ? 'an' : ''}" style="--i:${i}"><rect x="${x}" y="${y}" width="62" height="24" rx="12"/><path d="M${x + 12} ${y + 24} l-4 8 l10 -8z"/><text x="${x + 31}" y="${y + 16}">${esc(wort.length > 9 ? wort.slice(0, 8) + '…' : wort)}</text></g>`; }).join('');
        text = this.t(schritt === 'stimmen_omni' || /^omni/.test(schritt) ? 'zs_stimmen_omni' : 'zs_stimmen', { z: zaehler, w: wort });
      }
    } else if (station === 'merkmale') {
      const sp = 40, zei = 6, an = Math.round(anteil * sp);
      let zellen = '';
      for (let c = 0; c < sp; c++) for (let r = 0; r < zei; r++) zellen += `<rect x="${150 + c * 11}" y="${18 + r * 12}" width="9" height="10" rx="2" class="${c < an ? 'an' : ''}" style="--h:${((c * 7 + r * 13) % 10) / 10}"/>`;
      const welle = Array.from({ length: 12 }, (_, i) => `<rect x="${20 + i * 9}" y="${54 - 6 - (i % 4) * 8}" width="5" height="${12 + (i % 4) * 16}" rx="2.5" style="--i:${i}"/>`).join('');
      bild = `<g class="sz-welle">${welle}</g><g class="sz-pfeil"><path d="M132 54 h10 m-4 -4 l4 4 l-4 4"/></g><g class="sz-raster">${zellen}</g>`;
      text = this.t('zs_merkmale', { z: zaehler });
    } else if (station === 'training') {
      const kurven = (w.live && w.live.kurven) || {}, namen = Object.keys(kurven), kand = schritt === 'kandidat' ? det : '';
      const pkt = kurven[String(this._daten.wort.training.schritt || '')] || kurven[namen[namen.length - 1]] || [];
      bild = this._lernkurve(kurven, anteil, Number(g) || 0);
      const letzt = pkt[pkt.length - 1];
      text = schritt === 'mitteln' ? this.t('zs_mitteln') : schritt === 'kandidat_pruefen' ? this.t('zs_vergleich') : schritt === 'auswahl' ? this.t('zs_auswahl')
        : this.t(kand ? 'zs_kandidat' : 'zs_training', { k: kand, z: zaehler, w: wort }) + (letzt ? ' · ' + this.t('zs_kurve', { q: this._zahl(letzt[1], 0) + ' %', f: letzt[2] != null ? this._zahl(letzt[2], 1) : '–' }) : '');
    } else if (station === 'test') {
      const k = 7, an = Math.round(anteil * k);
      bild = Array.from({ length: k }, (_, i) => `<g class="sz-schild ${i < an ? 'an' : ''} ${i === an ? 'jetzt' : ''}" style="--i:${i};transform:translate(${70 + i * 76}px,20px)"><path d="M20 0 L38 7 V22 Q38 38 20 46 Q2 38 2 22 V7 Z"/><path class="h" d="M12 23 l6 6 l11 -12"/></g>`).join('');
      text = this.t(schritt === 'test_alt' ? 'zs_test_alt' : 'zs_test_neu', { z: `${Math.round(anteil * 100)} %` });
    } else {
      bild = `<g class="sz-ziel">${[0, 1, 2].map((i) => `<g style="transform:translate(${470 + i * 50}px,30px)"><rect x="0" y="0" width="26" height="36" rx="8"/><circle cx="13" cy="24" r="5"/></g>`).join('')}</g><circle class="sz-funke" cx="120" cy="48" r="6"/>`;
      text = this.t('zs_senden');
    }
    return `<div class="szene sz-${station}" style="--d0:${d0}"><svg viewBox="0 0 640 110" preserveAspectRatio="xMidYMid meet" aria-hidden="true">${bild}</svg><div class="sz-text">${esc(text)}</div></div>`;
  }

  // the real learning curve of the training running now: hit rate after each evaluation, one line per candidate
  _lernkurve(kurven, anteil, gesamt) {
    const namen = Object.keys(kurven).filter((k) => (kurven[k] || []).length);
    const netz = `<g class="sz-netz" style="--hell:${(0.25 + 0.75 * anteil).toFixed(2)}">${[[40, [30, 55, 80]], [90, [22, 44, 66, 88]], [140, [40, 70]]].map(([x, ys], li, alle) =>
      ys.map((y) => (alle[li + 1] ? alle[li + 1][1].map((y2) => `<line x1="${x}" y1="${y}" x2="${alle[li + 1][0]}" y2="${y2}"/>`).join('') : '') + `<circle cx="${x}" cy="${y}" r="5" style="--s:${li}"/>`).join('')).join('')}</g>`;
    if (!namen.length) return `${netz}<g class="sz-lernt"><rect x="200" y="50" width="400" height="8" rx="4" class="h"/><rect x="200" y="50" width="${(400 * anteil).toFixed(1)}" height="8" rx="4" class="v"/></g>`;
    const maxS = Math.max(gesamt, ...namen.flatMap((k) => kurven[k].map((p) => p[0])), 1);
    const X = (st) => 200 + (st / maxS) * 400, Y = (q) => 98 - (q / 100) * 84;
    const farben = ['var(--farbe)', '#b388ff', '#ffb74d', '#4dd0e1'];
    const linien = namen.map((k, i) => { const p = kurven[k], pts = p.map((x) => `${X(x[0]).toFixed(1)},${Y(x[1]).toFixed(1)}`).join(' '), e = p[p.length - 1];
      return `<polyline points="${pts}" style="stroke:${farben[i % 4]}"/><circle class="sz-kopf" cx="${X(e[0]).toFixed(1)}" cy="${Y(e[1]).toFixed(1)}" r="4.5" style="fill:${farben[i % 4]}"/>`; }).join('');
    return `${netz}<g class="sz-kurve"><line x1="200" y1="98" x2="600" y2="98" class="achse"/><line x1="200" y1="14" x2="600" y2="14" class="ziel"/><text x="604" y="18">100 %</text>${linien}</g>`;
  }

  _konfetti() {
    const farben = ['#4caf50', '#03a9f4', '#ffc107', '#e91e63', '#9c27b0', '#ffffff'];
    const teile = Array.from({ length: 28 }, (_, i) => {
      const w = (i / 28) * Math.PI * 2 + (i % 3) * 0.2, r = 70 + (i * 37) % 90;
      return `<i style="--x:${30 + (i * 13) % 40}%;--c:${farben[i % farben.length]};--dx:${Math.round(Math.cos(w) * r)}px;--dy:${Math.round(Math.sin(w) * r * 0.7 - 30)}px;--rot:${(i * 47) % 360}deg;--v:${(i % 4) * 40}ms"></i>`;
    }).join('');
    return `<div class="feier" aria-hidden="true">${teile}</div>`;
  }

  _training() {
    const d = this._daten, w = d.wort, t = w.training, e = w.einstellungen, tr = d.trainer;
    const laeuft = LAEUFT.includes(t.phase);
    const kurz = (b) => (b ? `${this._pct(b.trefferquote)} · ${this._zahl(b.fehlausloeser_pro_stunde, 1)}/${this.t('std')}` : '–');
    const platz = d.reihe.indexOf(w.id);
    // a better version: a short burst of confetti, once per version (not on every refresh)
    const feierKey = t.phase === 'fertig' && t.besser && t.version ? w.id + '|' + t.version : '';
    const feier = feierKey && !(this._gefeiert || (this._gefeiert = new Set())).has(feierKey);
    if (feier) this._gefeiert.add(feierKey);
    return `${!tr.online && !tr.kontakt ? `<div class="hinweis"><b>${esc(this.t('t_kein_trainer'))}</b><br>${this.t('t_kein_trainer_text')}</div>` : ''}
<ha-card class="${laeuft ? 'laeuft' : ''} ${feier ? 'gefeiert' : ''}"><div class="zeile weit"><h2 style="margin:0">${esc(this.t('p_' + t.phase))}</h2><span class="klein"><span class="punkt ${tr.online ? 'an' : ''}"></span>${esc(tr.online ? this.t('t_trainer_an') : tr.kontakt ? this.t('t_trainer_zuletzt', { z: this._zeit(tr.kontakt) }) : this.t('t_trainer_nie'))}</span></div>
${laeuft ? `${this._zauber(w)}<div class="fortschritt"><i style="width:${t.prozent ?? 3}%"></i></div><div class="zeile weit klein"><span>${esc(this._schritt(t.schritt))}</span><span>${t.prozent != null ? Math.round(t.prozent) + ' %' : ''}${t.restzeit_min != null ? ' · ' + esc(this.t('t_noch', { z: this._dauer(t.restzeit_min) })) : ''}</span></div>${t.restzeit_min != null ? `<div class="klein" style="text-align:right">${esc(this._fertigText(t))}</div>` : ''}${t.start ? `<div class="klein">${esc(this.t('t_gestartet', { z: this._zeit(t.start) }))}</div>` : ''}` : ''}
${t.vergleich && (laeuft || t.phase === 'wartet') ? `<p class="vf-lauf"><ha-icon icon="mdi:scale-balance"></ha-icon>${esc(this.t('vf_titel_lauf', { a: t.vergleich.a, b: t.vergleich.b }))}</p>` : ''}
${t.phase === 'bereit' && t.vergleich_fertig ? `<p class="klein"><ha-icon icon="mdi:scale-balance" style="--mdc-icon-size:16px;vertical-align:-3px"></ha-icon> ${esc(this.t('vf_fertig', { a: t.vergleich_fertig.a, b: t.vergleich_fertig.b }))} <button class="link" data-reiter="qualitaet">${esc(this.t('vf_ansehen'))}</button></p>` : ''}
${t.phase === 'wartet' ? `<p class="klein">${esc(this.t('t_auftrag', { g: this.t('grund_' + (t.grund || 'von_hand')) }))} ${esc(tr.online ? this.t('t_holt') : this.t('t_holt_nicht'))} ${platz > 0 ? esc(this.t('t_platz', { n: platz + 1 })) : ''}</p>` : ''}
${feier ? this._konfetti() : ''}${t.phase === 'fertig' && t.version ? `<p>v${t.version}: ${t.besser ? `<span class="gruen">${esc(this.t('t_besser'))}</span>` : `<span class="gelb">${esc(this.t(t.gleich ? 't_gleich' : 't_nicht_besser'))}</span>`}.</p>` : ''}
${t.phase === 'fehler' ? `<p class="rot">${esc(this._schritt(t.schritt || t.hinweis) || this.t('p_fehler'))}</p>` : ''}
<div class="zeile" style="margin-top:12px">${laeuft || t.phase === 'wartet' ? `<button class="k schlecht" data-a="abbrechen"><ha-icon icon="mdi:stop"></ha-icon>${esc(this.t('t_abbrechen'))}</button>` : `<button class="k haupt" data-a="trainieren"><ha-icon icon="mdi:play"></ha-icon>${esc(this.t('t_jetzt'))}</button><span class="klein">${esc(w.neu_seit_lauf > 0 ? this.t('t_neue', { n: w.neu_seit_lauf }) : this.t('t_keine_neuen'))}</span>`}</div></ha-card>
${this._details(w, laeuft)}
${this._klapp('k_auto', 'mdi:robot-outline', this.t('t_auto'), this._autoKurz(e, d), `<div class="schalter-raster">
${this._kachelSchalter('nachts', 'mdi:weather-night', 'sw_nachts', 'sw_nachts_text', e.nachts, { zusatz: String(d.einstellungen.uhrzeit).slice(0, 5) })}
${this._kachelSchalter('automatisch_einspielen', 'mdi:rocket-launch-outline', 'sw_einspielen', 'sw_einspielen_text', e.automatisch_einspielen)}
${this._kachelSchalter('schwelle_automatisch', 'mdi:tune-vertical', 'sw_schwelle', 'sw_schwelle_text', e.schwelle_automatisch)}
${this._kachelSchalter('vorpruefen', 'mdi:ear-hearing', 'sw_vorpruefen', 'sw_vorpruefen_text', e.vorpruefen)}
${this._kachelSchalter('gruendlich', 'mdi:podium-gold', 'sw_gruendlich', 'sw_gruendlich_text', e.gruendlich, { unter: `<label class="unter-schalter ${e.gruendlich ? '' : 'aus'}"><input type="checkbox" class="schieber" data-wopt="mitteln" ${e.mitteln ? 'checked' : ''} ${this._admin && e.gruendlich ? '' : 'disabled'}><span><b>${esc(this.t('sw_mitteln'))}</b><span class="klein">${esc(this.t('sw_mitteln_text'))}</span></span></label>` })}
${this._raumSchalter(e)}
</div>
${this._gruendlichInfo(w, e)}
<p class="klein">${esc(this.t('t_besser_heisst'))}</p>`)}
${this._klapp('k_laeufe', 'mdi:history', this.t('t_laeufe'), this._laeufeKurz(w), `${this._kurve(w)}${w.laeufe.length ? `<div class="laeufe">${w.laeufe.map((l, i) => {
  const art = l.ergebnis === 'eingespielt' ? 'gut' : l.ergebnis === 'fehler' ? 'rot' : l.ergebnis === 'besser' ? 'gut2' : '';
  const icon = { eingespielt: 'mdi:rocket-launch', besser: 'mdi:trending-up', fehler: 'mdi:alert-circle', gleich: 'mdi:approximately-equal' }[l.ergebnis] || 'mdi:minus-circle-outline';
  const wert = (b) => b ? `<b>${this._pct(b.trefferquote)}</b> <span class="klein">· ${this._zahl(b.fehlausloeser_pro_stunde, 1)}/${esc(this.t('std'))}</span>` : '<span class="klein">–</span>';
  const extra = [l.dauer_min != null ? this._dauer(l.dauer_min) : '', l.geraet === 'gpu' || l.geraet_rueckfall ? this.t(l.geraet_rueckfall ? 'l_rueckfall' : 'l_gpu') : '', l.trainer_name && (this._daten.trainer.liste || []).length > 1 ? l.trainer_name : ''].filter(Boolean);
  return `<div class="lauf ${art}" style="--n:${Math.min(i, 8)}"><span class="l-punkt"><ha-icon icon="${icon}"></ha-icon></span><div class="l-inhalt"><div class="zeile weit"><span class="l-titel">${esc(this._ergebnisText(l.ergebnis))}${l.version ? ` <span class="l-v">v${esc(String(l.version))}</span>` : ''}</span><span class="klein">${this._datum(l.ende)}</span></div>
<div class="l-werte"><span>${esc(this.t('t_vorher'))} ${wert(l.alt)}</span><ha-icon icon="mdi:arrow-right"></ha-icon><span>${esc(this.t('t_nachher'))} ${wert(l.neu)}</span></div>
${l.hinweis || extra.length ? `<div class="klein">${esc([l.hinweis, ...extra].filter(Boolean).join(' · '))}</div>` : ''}</div></div>`;
}).join('')}</div>` : `<div class="klein">${esc(this.t('t_kein_lauf'))}</div>`}`)}`;
  }

  _autoKurz(e, d) {
    const an = [['nachts', 'sw_nachts'], ['automatisch_einspielen', 'sw_einspielen'], ['schwelle_automatisch', 'sw_schwelle'], ['vorpruefen', 'sw_vorpruefen'], ['gruendlich', 'sw_gruendlich']]
      .filter(([k]) => e[k]).map(([k, t]) => this.t(t) + (k === 'nachts' ? ' ' + String(d.einstellungen.uhrzeit).slice(0, 5) : ''));
    return an.length ? this.t('kl_an', { l: an.join(' · ') }) : this.t('kl_alles_aus');
  }

  _laeufeKurz(w) {
    const l = w.laeufe[0];
    if (!l) return this.t('t_kein_lauf');
    return this.t('kl_laeufe', { n: w.laeufe.length, e: this._ergebnisText(l.ergebnis) + (l.version ? ' v' + l.version : ''), z: this._datum(l.ende) });
  }

  // ---------- Qualität ----------
  _tabelle() {
    const w = this._daten.wort, tb = (w.statistik || {}).tabelle;
    if (!tb) return '';
    const echo = this._tbEcho && tb.zeilen[this._tbEcho] ? this._tbEcho : '';
    const z = tb.zeilen[echo], g = tb.grenzen, n = g.length - 1;
    const summe = Object.values(z).reduce((a, r) => a + r.reduce((x, y) => x + y, 0), 0);
    const schwellen = Object.values(w.schwellen || {}), sw = schwellen.length ? schwellen[0] : null;
    const kopf = Array.from({ length: n }, (_, i) => `<th class="tb-k ${sw != null && sw >= g[i] && sw < g[i + 1] ? 'tb-sw' : ''}">${i === 0 ? '&lt;' + this._zahl(g[1]) : i === n - 1 ? '≥' + this._zahl(g[i]) : this._zahl(g[i])}</th>`).join('');
    const auffaellig = (zeile, i) => (zeile === 'kein_wort' && g[i] >= 0.95) || (zeile === 'wort' && g[i + 1] <= 0.7);
    const reihen = ['wort', 'verpasst', 'kein_wort', 'offen'].map((zeile) => {
      const r = z[zeile] || [], ges = r.reduce((x, y) => x + y, 0);
      const zellen = r.map((anz, i) => {
        if (!anz) return '<td class="tb-z leer"></td>';
        const anteil = anz / ges, auff = auffaellig(zeile, i);
        const farbe = auff ? 'var(--warning-color,#ff9800)' : zeile === 'kein_wort' ? 'var(--error-color,#f44336)' : zeile === 'offen' ? 'var(--secondary-text-color)' : 'var(--success-color,#4caf50)';
        return `<td class="tb-z ${auff ? 'auff' : ''}" style="--tf:${farbe};--ta:${Math.round(12 + 70 * anteil)}%" data-zelle="${zeile}|${g[i]}|${g[i + 1]}" title="${esc(this.t('tb_titel_zelle', { n: anz }))}">${anz}</td>`;
      }).join('');
      return `<tr><th class="tb-r">${esc(this.t('tb_zeile_' + zeile))}<span class="klein"> · ${ges}</span></th>${zellen}</tr>`;
    }).join('');
    const echos = Object.keys(tb.zeilen).filter((k) => k);
    const auffAnz = ['wort', 'kein_wort'].reduce((a, zeile) => a + (z[zeile] || []).reduce((x, anz, i) => x + (auffaellig(zeile, i) ? anz : 0), 0), 0);
    return this._klapp('k_tabelle', 'mdi:table-eye', this.t('tb_titel'), summe ? (auffAnz ? this.t('tb_auff', { n: auffAnz }) : this.t('tb_keine_auff')) : this.t('tb_leer'), `<div class="zeile weit">${echos.length > 1 ? `<div class="zeile"><button class="chip ${!echo ? 'an' : ''}" data-tbecho="">${esc(this.t('pr_alle'))}</button>${echos.map((e) => `<button class="chip ${echo === e ? 'an' : ''}" data-tbecho="${esc(e)}">${esc(e)}</button>`).join('')}</div>` : ''}</div>
<p class="klein" style="line-height:1.5">${esc(this.t('tb_hilfe'))}</p>
${summe ? `<div class="tb-rahmen"><table class="tb"><tr><th class="tb-r klein">${esc(this.t('tb_ecke'))}</th>${kopf}</tr>${reihen}</table></div>
<div class="zeile klein" style="margin-top:8px;gap:14px">${auffAnz ? `<span><span class="tb-muster auff"></span>${esc(this.t('tb_auff', { n: auffAnz }))}</span>` : `<span class="gruen">${esc(this.t('tb_keine_auff'))}</span>`}${sw != null ? `<span><span class="tb-muster sw"></span>${esc(this.t('tb_schwelle', { w: this._zahl(sw) }))}</span>` : ''}</div>` : `<div class="klein">${esc(this.t('tb_leer'))}</div>`}`);
  }

  _lagen(bed, schwer) {
    return `<h3>${esc(this.t(schwer ? 'q_schwer_lagen' : 'q_lagen'))}</h3>${schwer ? `<div class="klein" style="margin:-4px 0 8px">${esc(this.t('q_schwer_hilfe'))}</div>` : ''}<div class="lagen">${(schwer ? ['weit', 'laut_tv', 'laut_musik', 'chaos'] : ['ruhig', 'leise', 'hall', 'musik', 'gerede', 'alltag']).filter((k) => bed[k] != null).map((k, i) => `<div class="lage"><span>${esc(this.t('b_' + k))}</span><div class="lage-balken"><i style="--w:${Math.round(bed[k] * 100)}%;animation-delay:${i * 60}ms" class="${schwer ? 'hart' : bed[k] >= 0.85 ? 'gut' : bed[k] >= 0.65 ? 'mittel' : 'schwach'}"></i></div><b>${this._pct(bed[k])}</b></div>`).join('')}</div>`;
  }

  _versionen(w) {
    const zeilen = w.versionen.map((x) => {
      const b = x.bericht || {}, n = b.neu || {}, vg = b.vergleich, offen = this._vglOffen.has(x.nr);
      const stand = x.status === 'verworfen' && vg && vg.urteil === 'gleich' ? 'gleich' : x.status;
      const details = vg || b.alt !== undefined;
      return `<tr class="vrow ${details ? 'klickbar' : ''} ${offen ? 'offen' : ''}" ${details ? `data-vgl="${x.nr}" title="${esc(this.t('q_details'))}"` : ''}><td>${details ? '<ha-icon class="pfeil" icon="mdi:chevron-right"></ha-icon>' : ''}v${x.nr}<div class="klein">${this._datum(x.zeit)}</div></td><td>${this._pct(n.trefferquote)}</td><td>${this._pct(n.trefferquote_alltag)}</td><td>${this._pct(n.trefferquote_schwer)}</td><td>${this._zahl(n.fehlausloeser_pro_stunde, 1)}/${esc(this.t('std'))}</td><td class="${x.status === 'aktiv' ? 'gruen' : ''}">${esc(this.t('s_' + stand))}</td><td class="z">${x.status !== 'aktiv' && this._admin ? `<button class="k" data-a="einspielen" data-nr="${x.nr}">${esc(this.t('q_einspielen'))}</button>` : ''}</td></tr>
${details ? `<tr class="vdetail" data-vgldetail="${x.nr}" ${offen ? '' : 'hidden'}><td colspan="7"><div class="vgl">${this._vergleich(x)}</div></td></tr>` : ''}`;
    }).join('');
    return `<div class="tabelle-scroll"><table class="versionen"><tr><th>${esc(this.t('q_version'))}</th><th>${esc(this.t('q_erkannt_ruhig'))}</th><th title="${esc(this.t('q_alltag_t'))}">${esc(this.t('q_alltag_k'))}</th><th title="${esc(this.t('q_schwer_t'))}">${esc(this.t('q_schwer_k'))}</th><th>${esc(this.t('q_fehl'))}</th><th>${esc(this.t('q_stand'))}</th><th></th></tr>${zeilen}</table></div>`;
  }

  _vergleich(x) {
    const b = x.bericht || {}, vg = b.vergleich;
    const wert = (k, v) => v == null ? '–' : k.startsWith('fehlausloeser') ? this._zahl(v, 1) : this._pct(v);
    const name = (z) => z.kennzahl.endsWith('_bei_fa') ? this.t('k_' + z.kennzahl, { fa: this._zahl(z.fa, 1) })
      : z.kennzahl.startsWith('erkannt_') ? this.t('k_erkannt', { b: this.t('b_' + z.kennzahl.slice(8)) })
        : z.kennzahl === 'schwaechste_person' ? this.t('k_schwaechste_person', { p: z.person || '' }) : this.t('k_' + z.kennzahl);
    const icon = { besser: 'mdi:check-circle', schlechter: 'mdi:close-circle', gleich: 'mdi:approximately-equal' };
    const kopf = this._urteilZeile(b);
    const tab = vg ? `<table class="vgl-tab"><tr><th>${esc(this.t(b.alt_nr ? 'q_vgl' : 'q_vgl_vorher', { v: b.alt_nr }))}</th><th class="z">${esc(this.t('q_vgl_neu', { v: x.nr }))}</th><th class="z">${esc(b.alt_nr ? 'v' + b.alt_nr : this.t('q_vgl_alt'))}</th><th class="z"></th></tr>${vg.zeilen.map((z) => `<tr class="${z.wichtig ? 'wichtig' : ''}"><td>${esc(name(z))}</td><td class="z">${z.kennzahl.endsWith('_bei_fa') && z.neu == null ? esc(this.t('q_nicht_erreicht')) : wert(z.kennzahl, z.neu)}</td><td class="z">${z.kennzahl.endsWith('_bei_fa') && z.alt == null ? esc(this.t('q_nicht_erreicht')) : wert(z.kennzahl, z.alt)}</td><td class="z"><ha-icon class="u-${z.urteil}" icon="${icon[z.urteil]}" title="${esc(this.t('u_' + z.urteil))}"></ha-icon></td></tr>`).join('')}</table>
<div class="klein" style="margin-top:6px">${esc(this.t('q_vgl_basis', { n: vg.testaufnahmen, h: this._zahl(vg.stunden_rede, 1), g: this._zahl(vg.stunden_geraeusch, 1) }))}</div>` : '';
    const kand = b.kandidaten ? `<div class="klein" style="margin-top:8px">${esc(this._kandidatText(b.kandidaten))}</div>` : '';
    const raum = b.raumklang ? `<div class="klein" style="margin-top:6px"><ha-icon icon="mdi:home-sound-out" style="--mdc-icon-size:16px;vertical-align:-3px"></ha-icon> ${esc(this.t('rk_bericht', { n: b.raumklang }))}</div>` : '';
    return kopf + this._duell(b, x.nr) + tab + kand + raum;
  }

  _kandidatText(k) {
    const w = (k.werte || [])[k.gewaehlt - 1] || {};
    const auf = k.grundlage === 'echt' ? this.t('g_auf_echt', { a: k.wahl_aufnahmen }) : this.t('g_auf_eigen');
    const was = w.rezept === 'gemittelt' ? this.t('g_gewaehlt_mittel', { n: k.anzahl })
      : this.t('g_gewaehlt', { n: k.anzahl, k: k.gewaehlt }) + (w.rezept === 'abgebrochen' ? ' ' + this.t('g_rezept_abgebrochen') : w.rezept === 'sanft' ? ' ' + this.t('g_rezept_sanft') : '');
    return `${was} ${auf}`;
  }

  _urteilZeile(b) {
    const vg = b.vergleich, icon = { besser: 'mdi:check-circle', schlechter: 'mdi:close-circle', gleich: 'mdi:approximately-equal' };
    const zeile = (cls, ic, text) => `<div class="vgl-urteil ${cls}"><ha-icon icon="${ic}"></ha-icon><span>${esc(text)}</span></div>`;
    if (vg) {
      const liste = (ks) => [...new Set(ks)].map((k) => this.t(k === 'alltag_bei_fa' ? 'k_alltag_kurz' : k === 'schwer_bei_fa' ? 'k_schwer_kurz' : 'k_' + k)).join(', ');
      return zeile('u-' + vg.urteil, icon[vg.urteil] || 'mdi:information', this.t('g_' + vg.grund, { k: liste(vg.grund === 'besser_in' ? vg.besser_in : vg.schlechter_in) }));
    }
    if (b.alt === null) return zeile('', 'mdi:information-outline', this.t('g_erste'));
    return b.alt && b.besser != null ? zeile('', 'mdi:information-outline', this.t(b.besser ? 'g_alt_besser' : 'g_alt_nicht')) : '';
  }

  // two bars per question, this version against the one before: the three things that matter in daily life
  _duell(b, nr, hinweis = true) {
    const n = b.neu || {}, a = b.alt;
    if (!a) return '';
    const vg = b.vergleich, urteil = (k, fa) => { const z = vg && vg.zeilen.find((r) => r.kennzahl === k && (fa == null || r.fa === fa)); return z ? z.urteil : null; };
    const alltag = n.trefferquote_alltag != null && a.trefferquote_alltag != null;
    const fragen = [
      { titel: alltag ? 'd_hoert_alltag' : 'd_hoert', hin: 'd_mehr', neu: alltag ? n.trefferquote_alltag : n.trefferquote, alt: alltag ? a.trefferquote_alltag : a.trefferquote, pct: true, u: urteil('alltag_bei_fa', 1) },
      { titel: 'd_hoert_schwer', hin: 'd_mehr', neu: n.trefferquote_schwer, alt: a.trefferquote_schwer, pct: true, u: urteil('schwer_bei_fa', 1) },
      { titel: 'd_fehl_rede', hin: 'd_weniger', neu: n.fehlausloeser_pro_stunde, alt: a.fehlausloeser_pro_stunde, u: urteil('fehlausloeser_rede') },
      { titel: 'd_fehl_geraeusch', hin: 'd_weniger', neu: n.fehlausloeser_geraeusch_pro_stunde, alt: a.fehlausloeser_geraeusch_pro_stunde, u: urteil('fehlausloeser_geraeusch') },
      { titel: 'd_fehl_stille', hin: 'd_weniger', neu: n.fehlausloeser_stille_pro_stunde, alt: a.fehlausloeser_stille_pro_stunde, u: urteil('fehlausloeser_stille') },
      { titel: 'd_fehl_echt', hin: 'd_weniger', neu: n.echte_fehlausloeser, alt: a.echte_fehlausloeser, pct: true, skala: true, u: urteil('echte_fehlausloeser') },
      { titel: 'd_gegen', hin: 'd_weniger', neu: n.gegenbeispiele, alt: a.gegenbeispiele, pct: true, skala: true, u: urteil('aehnliche_woerter') },
    ].filter((f) => f.neu != null && f.alt != null);
    if (!fragen.length) return '';
    const altName = b.alt_nr ? 'v' + b.alt_nr : this.t('q_vgl_alt');
    const icon = { besser: 'mdi:check-circle', schlechter: 'mdi:close-circle', gleich: 'mdi:approximately-equal' };
    let k = 0;
    const balken = (name, wert, f, max, klasse) => `<div class="d-zeile"><span class="d-name">${esc(name)}</span><div class="d-spur"><i class="${klasse}" style="--w:${Math.max(1.5, Math.min(100, (wert / max) * 100)).toFixed(1)}%;animation-delay:${(k++) * 70}ms"></i></div><b>${f.pct ? this._pct(wert) : this._zahl(wert, 1)}</b></div>`;
    return `<div class="duell">${fragen.map((f) => {
      const max = f.pct && !f.skala ? 1 : Math.max(f.pct ? 0.05 : 1, f.neu, f.alt) * 1.1;
      const marke = f.u ? `<div class="d-fuss"><span class="d-urteil u-${f.u}"><ha-icon icon="${icon[f.u]}"></ha-icon>${esc(this.t('d_u_' + f.u))}</span></div>` : '';
      return `<div class="d-frage"><div class="d-kopf"><span>${esc(this.t(f.titel))}</span><span class="klein">${esc(this.t(f.hin))}</span></div>${balken('v' + nr, f.neu, f, max, 'neu')}${balken(altName, f.alt, f, max, 'alt')}${marke}</div>`;
    }).join('')}${vg || !hinweis ? '' : `<div class="klein">${esc(this.t('d_alter_test'))}</div>`}</div>`;
  }

  // the active version at a glance: how it hears in every condition and, next to it, the duel against the version before
  _aktivBlick(v, b, gemessen) {
    const neu = gemessen || b.neu || {}, duell = this._duell(b, v.nr);
    const rechts = duell ? `<div class="blick-duell"><h3>${esc(this.t(b.alt_nr ? 'd_titel' : 'd_titel_vorher', { a: v.nr, b: b.alt_nr }))}</h3>${this._urteilZeile(b)}${duell}${b.vergleich ? `<button class="link" data-a="vgl_zeigen" data-nr="${v.nr}">${esc(this.t('q_alle_werte'))}<ha-icon icon="mdi:chevron-right"></ha-icon></button>` : ''}</div>` : '';
    const links = neu.bedingungen ? `<div>${this._lagen(neu.bedingungen)}${neu.schwer ? this._lagen(neu.schwer, true) : ''}</div>` : '';
    return links || rechts ? `<div class="blick ${links && rechts ? 'zwei' : ''}">${links}${rechts}</div>` : '';
  }

  _vglZeigen(nr) {
    const karte = this.shadowRoot.querySelector('details[data-abschnitt="k_versionen"]');
    if (karte && !karte.open) karte.open = true;
    const zeile = this.shadowRoot.querySelector(`tr[data-vgl="${nr}"]`), det = this.shadowRoot.querySelector(`[data-vgldetail="${nr}"]`);
    if (!zeile || !det) return;
    if (det.hidden) this._vglUmschalten(nr, zeile);
    zeile.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  }

  _qualitaet() {
    const w = this._daten.wort, s = w.statistik, v = w.versionen.find((x) => x.nr === w.aktiv), b = (v && v.bericht) || {};
    // a later run measured the active version again in its test (it always tests the active one too): newest figures
    const frisch = v && w.versionen.find((x) => x.nr > v.nr && x.bericht && x.bericht.alt_nr === v.nr && x.bericht.alt && x.bericht.alt.bedingungen);
    const neu = frisch ? frisch.bericht.alt : b.neu || {}, personen = neu.je_person || {};
    const sjl = Object.values(w.schwellen || {}), sj = sjl.length ? sjl[0] : null;
    const herkunft = b.herkunft === 'vor der Integration eingespielt' ? this.t('q_herkunft') : b.herkunft;
    return `<ha-card><h2>${esc(this.t('q_aktiv'))} ${v ? 'v' + v.nr : ''}</h2>${v ? `
<div class="stat-raster klein-stat">
${neu.trefferquote_alltag != null ? this._stat({ icon: 'mdi:home-sound-in-outline', titel: this.t('q_alltag_k'), wert: this._pct(neu.trefferquote_alltag), ring: neu.trefferquote_alltag, titelHilfe: this.t('q_alltag_t'), n: 0 }) : ''}
${neu.trefferquote_schwer != null ? this._stat({ icon: 'mdi:weight-lifter', titel: this.t('q_schwer_k'), wert: this._pct(neu.trefferquote_schwer), ring: neu.trefferquote_schwer, titelHilfe: this.t('q_schwer_t'), n: 1 }) : ''}
${this._stat({ icon: 'mdi:check-decagram-outline', titel: this.t('q_erkennt'), wert: this._pct(neu.trefferquote), ring: neu.trefferquote, n: 2 })}
${neu.bedingungen ? '' : this._stat({ icon: 'mdi:music', titel: this.t('q_musik'), wert: this._pct(neu.trefferquote_musik), ring: neu.trefferquote_musik, n: 3 })}
${this._stat({ icon: 'mdi:account-voice-off', titel: this.t('q_fehl'), wert: this._zahl(neu.fehlausloeser_pro_stunde, 1), ton: neu.fehlausloeser_pro_stunde > 0.5 ? 'gelb' : 'gruen', n: 4 })}
${neu.fehlausloeser_geraeusch_pro_stunde != null ? this._stat({ icon: 'mdi:music-note-off-outline', titel: this.t('q_fehl_geraeusch'), wert: this._zahl(neu.fehlausloeser_geraeusch_pro_stunde, 1), ton: neu.fehlausloeser_geraeusch_pro_stunde > 0.5 ? 'gelb' : 'gruen', n: 5 }) : ''}
${this._stat({ icon: 'mdi:shield-off-outline', titel: this.t('q_gegen'), wert: this._pct(neu.gegenbeispiele), ton: neu.gegenbeispiele > 0.05 ? 'gelb' : '', n: 6 })}</div>
${frisch ? `<div class="klein" style="margin-top:8px"><ha-icon icon="mdi:refresh" style="--mdc-icon-size:16px"></ha-icon> ${esc(this.t('q_frisch', { z: this._zeit(frisch.zeit), n: frisch.nr }))}</div>` : ''}
<details class="inklapp" data-abschnitt="k_aktiv_mehr" ${this._merk('abschnitt.k_aktiv_mehr') === '1' ? 'open' : ''}><summary><ha-icon icon="mdi:chevron-down"></ha-icon>${esc(this.t('kl_einzelwerte'))}</summary>${this._aktivBlick(v, b, frisch ? neu : null)}
${Object.keys(personen).length ? `<h3>${esc(this.t('q_je_person'))}</h3>${this._personen(Object.entries(personen).map(([p, x]) => [p, x.trefferquote, this.t('q_person_info', { q: this._pct(x.trefferquote), n: x.anzahl })]))}` : ''}</details>
<div class="klein" style="margin-top:10px">${esc(this.t('ue_eingespielt', { z: this._zeit(v.eingespielt) }))}${b.cutoff ? ' · ' + esc(this.t('q_modell_schwelle', { w: this._zahl(b.cutoff) })) : ''}${herkunft ? ' · ' + esc(herkunft) : ''}</div>` : `<div class="klein">${esc(this.t('q_keine'))}</div>`}</ha-card>
${this._tabelle()}
<ha-card><h2>${esc(this.t('q_alltag'))}</h2>${this._alltag()}</ha-card>
${this._klapp('k_schwelle', 'mdi:tune-vertical', this.t('q_schwelle'), [sj != null ? this.t('kl_jetzt', { w: this._zahl(sj) }) : '', s.schwelle_vorschlag != null ? this.t('kl_vorschlag', { w: this._zahl(s.schwelle_vorschlag) }) : '', this.t((w.einstellungen || {}).schwelle_automatisch ? 'kl_auto' : s.schwelle_hand ? 'kl_hand' : 'kl_fest')].filter(Boolean).join(' · '), `${this._verteilung(sj, s.schwelle_vorschlag)}
${(w.einstellungen || {}).schwelle_automatisch ? this._schwelleAuto(s, sj) : s.schwelle_vorschlag != null ? `<div class="zeile weit" style="margin-top:10px"><span>${this.t('q_vorschlag', { w: this._zahl(s.schwelle_vorschlag) })} ${sj != null ? esc(this.t('q_jetzt', { w: this._zahl(sj) })) : ''}</span><button class="k haupt" data-a="schwelle" data-wert="${s.schwelle_vorschlag}" ${!this._admin || (sj != null && Math.abs(sj - s.schwelle_vorschlag) < 0.005) ? 'disabled' : ''}>${esc(this.t('q_uebernehmen'))}</button></div>` : `<div class="klein">${esc(this.t('q_vorschlag_spaeter'))}</div>`}
<div class="klein" style="margin-top:8px">${esc(this.t('q_legende'))}${(w.einstellungen || {}).schwelle_automatisch ? '' : ' ' + esc(this.t('q_legende_hand'))}</div>
${this._admin && Object.keys(w.schwellen || {}).length ? this._schwelleHand(s, sj, (w.einstellungen || {}).schwelle_automatisch) : ''}`)}
${this._klapp('k_versionen', 'mdi:source-branch', this.t('q_versionen'), w.versionen.length ? this.t('kl_versionen', { n: w.versionen.length, a: w.aktiv ? 'v' + w.aktiv : '–', z: 'v' + Math.max(...w.versionen.map((x) => x.nr)) }) : this.t('q_keine'), `${this._kurve(w)}${w.versionen.length ? this._versionen(w) : `<div class="klein">${esc(this.t('q_keine'))}</div>`}`)}
${this._vglFrei(w)}`;
  }

  // compare any two versions: pick both, see the questions side by side
  _vglKandidaten(w) {
    return [...w.versionen].filter((v) => v.bericht && v.bericht.neu).sort((a, b) => b.nr - a.nr);
  }

  _vglPaar(w) {
    const vs = this._vglKandidaten(w), nrs = vs.map((v) => v.nr), wahl = this._vglWahl[this._wortId] || {};
    let a = nrs.includes(wahl.a) ? wahl.a : nrs[0];
    let b = nrs.includes(wahl.b) ? wahl.b : (nrs.includes(w.aktiv) && w.aktiv !== a ? w.aktiv : nrs.find((n) => n !== a));
    if (a === b) b = nrs.find((n) => n !== a);
    return { vs, a: vs.find((v) => v.nr === a), b: vs.find((v) => v.nr === b) };
  }

  _vglFrei(w) {
    const { vs, a, b } = this._vglPaar(w);
    if (vs.length < 2 || !a || !b) return '';
    const wahl = (seite, nr) => `<select data-vglwahl="${seite}" aria-label="${esc(this.t('vf_version'))}">${vs.map((v) => `<option value="${v.nr}" ${v.nr === nr ? 'selected' : ''}>v${v.nr}${v.nr === w.aktiv ? ' · ' + esc(this.t('vf_aktiv')) : ''} · ${esc(this._datum(v.zeit))}</option>`).join('')}</select>`;
    const t = w.training || {}, laeuft = t.vergleich && (LAEUFT.includes(t.phase) || t.phase === 'wartet');
    const kurz = laeuft ? this.t(t.phase === 'wartet' ? 'vf_wartet' : 'vf_laeuft_jetzt', { a: t.vergleich.a, b: t.vergleich.b })
      : (w.vergleiche || []).length ? this.t('kl_fair', { n: w.vergleiche.length }) : this.t('vf_hilfe');
    return this._klapp('k_vergleich', 'mdi:scale-balance', this.t('vf_titel'), kurz, `<div class="vf-wahl">${wahl('a', a.nr)}<button class="k rund" data-a="vgl_tauschen" title="${esc(this.t('vf_tauschen'))}"><ha-icon icon="mdi:swap-horizontal"></ha-icon></button>${wahl('b', b.nr)}</div>
<div class="vf-inhalt">${this._vglFreiInhalt(w, a, b)}</div>`);
  }

  // a measurement of y against x turned around, so that x stays on top; the verdicts turn with it
  _vglUmdrehen(neu, alt, vg, altNr) {
    const um = { besser: 'schlechter', schlechter: 'besser', gleich: 'gleich' };
    const liste = (ks) => ks || [];
    return { neu: alt, alt: neu, alt_nr: altNr, vergleich: vg ? { ...vg, urteil: um[vg.urteil] || vg.urteil, besser_in: liste(vg.schlechter_in), schlechter_in: liste(vg.besser_in), grund: vg.grund === 'besser_in' ? 'schlechter_in' : vg.grund === 'schlechter_in' ? 'besser_in' : vg.grund, zeilen: vg.zeilen.map((z) => ({ ...z, neu: z.alt, alt: z.neu, urteil: um[z.urteil] || z.urteil })) } : undefined };
  }

  _vglFreiInhalt(w, a, b) {
    // best first: a fair test of exactly this pair, then a run that measured both on the same audio, else the stored figures
    const fair = (w.vergleiche || []).find((f) => (f.a === a.nr && f.b === b.nr) || (f.a === b.nr && f.b === a.nr));
    const gleicherLauf = (x, y) => x.bericht.alt_nr === y.nr && x.bericht.alt;
    let bericht, hinweis, sicher = true;
    if (fair) {
      bericht = fair.a === a.nr ? { neu: fair.neu, alt: fair.alt, alt_nr: b.nr, vergleich: fair.vergleich } : this._vglUmdrehen(fair.neu, fair.alt, fair.vergleich, b.nr);
      hinweis = this.t('vf_fair', { z: this._zeit(fair.zeit), n: fair.test_positiv ?? '–' });
    } else if (gleicherLauf(a, b)) { bericht = a.bericht; hinweis = this.t('vf_gleich_lauf', { v: a.nr }); }
    else if (gleicherLauf(b, a)) { bericht = this._vglUmdrehen(b.bericht.neu, b.bericht.alt, b.bericht.vergleich, b.nr); hinweis = this.t('vf_gleich_lauf', { v: b.nr }); }
    else { bericht = { neu: a.bericht.neu, alt: b.bericht.neu, alt_nr: b.nr }; hinweis = this.t('vf_getrennt', { a: a.nr, b: b.nr }); sicher = false; }
    const nr = a.nr, duell = this._duell(bericht, nr, false);
    const na = bericht.neu || {}, nb = bericht.alt || {};
    const zeile = (titel, ka, kb, f) => `<tr><td>${esc(titel)}</td><td class="z">${f(ka)}</td><td class="z">${f(kb)}</td></tr>`;
    const pct = (x) => this._pct(x);
    const tab = `<table class="vgl-tab"><tr><th></th><th class="z">v${a.nr}</th><th class="z">v${b.nr}</th></tr>
${zeile(this.t('vf_ruhig'), na.trefferquote, nb.trefferquote, pct)}
${fair ? '' : zeile(this.t('vf_schwelle'), a.bericht.cutoff, b.bericht.cutoff, (x) => x == null ? '–' : this._zahl(x))}${fair ? '' : zeile(this.t('vf_testaufnahmen'), a.bericht.test_positiv, b.bericht.test_positiv, (x) => x == null ? '–' : String(x))}</table>`;
    return `${bericht.vergleich ? this._vglUrteil(bericht.vergleich, a.nr, b.nr) : ''}<div class="klein vf-hinweis ${sicher ? '' : 'grob'}"><ha-icon icon="${sicher ? 'mdi:check-decagram-outline' : 'mdi:information-outline'}"></ha-icon><span>${esc(hinweis)}</span></div>${duell}${tab}${this._vglFairKnopf(w, a, b, fair)}`;
  }

  // the verdict in plain words for any pair (the run's own line speaks of taking a version over)
  _vglUrteil(vg, a, b) {
    const icon = { besser: 'mdi:check-circle', schlechter: 'mdi:close-circle', gleich: 'mdi:approximately-equal' };
    const liste = (ks) => [...new Set(ks || [])].map((k) => this.t(k === 'alltag_bei_fa' ? 'k_alltag_kurz' : k === 'schwer_bei_fa' ? 'k_schwer_kurz' : 'k_' + k)).join(', ');
    const text = vg.urteil === 'besser' ? this.t('vf_u_besser', { a, k: liste(vg.besser_in) })
      : vg.urteil === 'schlechter' ? this.t('vf_u_schlechter', { a, k: liste(vg.schlechter_in) }) : this.t('vf_u_gleich', { a, b });
    return `<div class="vgl-urteil u-${vg.urteil}"><ha-icon icon="${icon[vg.urteil] || 'mdi:information'}"></ha-icon><span>${esc(text)}</span></div>`;
  }

  _vglFairKnopf(w, a, b, fair) {
    if (!this._admin) return '';
    const t = w.training || {}, v = t.vergleich, aktiv = LAEUFT.includes(t.phase) || t.phase === 'wartet';
    if (aktiv && v && ((v.a === a.nr && v.b === b.nr) || (v.a === b.nr && v.b === a.nr))) {
      return `<div class="vf-fuss"><span class="klein"><ha-icon icon="mdi:timer-sand"></ha-icon> ${esc(this.t(t.phase === 'wartet' ? 'vf_wartet' : 'vf_laeuft_jetzt', { a: v.a, b: v.b }))}</span><button class="link" data-reiter="training">${esc(this.t('vf_zum_training'))}<ha-icon icon="mdi:chevron-right"></ha-icon></button></div>`;
    }
    const grund = !w.kann_vergleichen ? this.t('vf_trainer_alt') : aktiv ? this.t('vf_belegt') : '';
    return `<div class="vf-fuss"><button class="k ${fair ? '' : 'haupt'}" data-a="vgl_fair" ${grund ? 'disabled' : ''}><ha-icon icon="mdi:scale-balance"></ha-icon>${esc(this.t(fair ? 'vf_neu_testen' : 'vf_fair_testen'))}</button><span class="klein">${esc(grund || this.t('vf_fair_hilfe'))}</span></div>`;
  }

  _vglFreiNeu() {
    const w = this._daten.wort, box = this.shadowRoot.querySelector('.vf-inhalt');
    if (!box) return;
    const { a, b } = this._vglPaar(w);
    this.shadowRoot.querySelectorAll('select[data-vglwahl]').forEach((s) => { s.value = String(s.dataset.vglwahl === 'a' ? a.nr : b.nr); });
    box.innerHTML = this._vglFreiInhalt(w, a, b);
  }

  // people as small cards: initial in a coloured circle, a bar and a line (shares 0..1)
  _personen(liste) {
    return `<div class="personen">${liste.map(([name, anteil, text], i) => `<div class="person" style="--pf:${FARBEN[(i + 2) % FARBEN.length]};--n:${i}"><span class="p-kreis">${esc((name || '?').slice(0, 1).toUpperCase())}</span><div class="p-mitte"><div class="zeile weit"><b>${esc(name)}</b><span class="klein">${esc(text)}</span></div><div class="p-spur"><i style="--w:${(Math.max(0, Math.min(1, anteil || 0)) * 100).toFixed(1)}%"></i></div></div></div>`).join('')}</div>`;
  }

  // your own threshold, in addition to the suggestion: steps of 0.01, setting it switches the automatic adjustment off
  _schwelleHand(s, sj, auto) {
    const h = s.schwelle_hand, start = sj != null ? sj : (s.schwelle_vorschlag != null ? s.schwelle_vorschlag : 0.95);
    const info = auto ? this.t('q_hand_auto') : h ? this.t('q_hand_info', { w: this._zahl(h.wert), z: this._datum(h.zeit) }) : this.t('q_hand_hilfe');
    return `<div class="sw-hand"><div class="zeile weit" style="gap:10px;flex-wrap:wrap"><span class="zeile" style="gap:8px"><ha-icon icon="mdi:hand-back-right-outline" style="--mdc-icon-size:18px;color:var(--primary-color)"></ha-icon><b>${esc(this.t('q_hand_titel'))}</b></span>
<span class="zeile" style="gap:6px"><button class="k rund" data-a="sw_schritt" data-d="-1" aria-label="-0.01">−</button><input type="number" class="sw-wert" min="0.5" max="0.99" step="0.01" value="${start.toFixed(2)}" aria-label="${esc(this.t('q_hand_titel'))}"><button class="k rund" data-a="sw_schritt" data-d="1" aria-label="+0.01">+</button><button class="k haupt" data-a="schwelle_hand">${esc(this.t('q_hand_setzen'))}</button></span></div>
<div class="klein" style="margin-top:6px;line-height:1.5">${esc(info)}</div></div>`;
  }

  _schwelleAuto(s, sj) {
    const a = s.schwelle_auto, b = s.schwelle_basis || { wort: 0, kein_wort: 0 };
    const woher = a ? this.t(a.quelle === 'antworten' ? 'q_auto_antworten' : 'q_auto_test', { z: this._datum(a.zeit) }) : '';
    const weiter = s.schwelle_vorschlag != null ? this.t('q_auto_folgt') : this.t('q_auto_spaeter', { a: b.wort, b: b.kein_wort });
    return `<div style="margin-top:10px"><div class="zeile" style="gap:8px"><ha-icon icon="mdi:tune-variant" style="--mdc-icon-size:18px;color:var(--primary-color)"></ha-icon><span>${this.t('q_auto_jetzt', { w: sj != null ? this._zahl(sj) : '–' })}</span></div>
<div class="klein" style="margin-top:4px;line-height:1.5">${esc([woher, weiter].filter(Boolean).join(' '))}</div></div>`;
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
  _sprachname(code) {
    try {
      return new Intl.DisplayNames([this._spr], { type: 'language' }).of(code) || code;
    } catch (e) {
      return code;
    }
  }

  _sprachWahl(wert) {
    const name = (s) => SPRACHNAMEN[this._spr][s] || this._sprachname(s);
    const liste = [...this._daten.sprachen].sort((a, b) => name(a).localeCompare(name(b), this._spr));
    return `<select data-feld="sprache">${liste.map((s) => `<option value="${s}" ${s === wert ? 'selected' : ''}>${esc(name(s))}</option>`).join('')}</select>`;
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
      return `<div class="platz ${jetzt ? 'an' : ''}" data-knoten="${esc(g.knoten)}"><span class="pl-ikon"><ha-icon icon="mdi:speaker-wireless"></ha-icon></span><div class="pl-text"><div class="pl-name">${esc(g.name)}</div><div class="klein">${esc(g.knoten)}${gewaehlt ? ' · ' + esc(this.t('w_auswahl', { w: gewaehlt })) : ''}${g.fehler ? ' · <span class="rot">' + esc(this.t('ge_nicht_gefunden')) + '</span>' : ''}${g.clips ? '' : ' · ' + esc(this.t('ge_ohne_clips'))}</div></div>
<select data-platz="${esc(g.knoten)}"><option value="">${esc(this.t('w_platz_aus'))}</option>${plaetze.map((p, i) => `<option value="${p}" ${jetzt === p ? 'selected' : ''}>${esc(this.t('w_platz', { n: p }) + belegt[i])}</option>`).join('')}</select></div>`;
    }).join('');
  }

  _farbWahl(wert) {
    return `<div class="farbwahl">${FARBEN.map((f) => `<button data-farbe="${f}" class="${f === wert ? 'an' : ''}" style="background:${f}" aria-label="${f}"></button>`).join('')}</div>`;
  }

  // live preview of the word being created: it appears big in its colour as you type
  _neuVorschau(e) {
    const spr = SPRACHNAMEN[this._spr][e.sprache] || this._sprachname(e.sprache);
    return `<div class="neu-vorschau ${e.wort ? 'da' : ''}" style="--farbe:${esc(e.farbe || FARBEN[0])}"><div class="nv-funken" aria-hidden="true">${Array.from({ length: 10 }, (_, i) => `<i style="--i:${i}"></i>`).join('')}</div>
<div class="klein nv-sprache">${esc(spr)}</div><div class="nv-wort">${esc(e.wort || this.t('nv_leer'))}</div><div class="klein nv-text">${esc(e.id ? this._nvGeraet(e) : this.t(e.wort ? 'nv_da' : 'nv_hilfe'))}</div></div>`;
  }

  // under the preview of an existing word: how the devices list it
  _nvGeraet(e) {
    const anzeige = String(e.anzeige || '').trim() || (String(e.wort || '').trim() + ' (custom)');
    return this.t('nv_geraet', { a: anzeige, n: Object.values(e.geraete || {}).filter(Boolean).length });
  }

  _neuStand() {
    const e = this._entwurf, sr = this.shadowRoot; if (!e) return;
    const v = sr.querySelector('.neu-vorschau'); if (!v) return;
    const war = v.classList.contains('da');
    v.classList.toggle('da', !!String(e.wort || '').trim());
    v.style.setProperty('--farbe', e.farbe || (e.id ? this._farbe(this._wortKurz()) : FARBEN[0]));
    v.querySelector('.nv-wort').textContent = String(e.wort || '').trim() || this.t('nv_leer');
    v.querySelector('.nv-text').textContent = e.id ? this._nvGeraet(e) : this.t(String(e.wort || '').trim() ? 'nv_da' : 'nv_hilfe');
    sr.querySelectorAll('.platz[data-knoten]').forEach((k) => k.classList.toggle('an', !!(e.geraete || {})[k.dataset.knoten]));
    const spr = sr.querySelector('select[data-feld="sprache"]');
    if (spr) v.querySelector('.nv-sprache').textContent = spr.options[spr.selectedIndex] ? spr.options[spr.selectedIndex].text : '';
    if (!war && v.classList.contains('da')) { v.classList.remove('funkt'); void v.offsetWidth; v.classList.add('funkt'); }
    const schritt = (n, ok) => { const el = sr.querySelector(`.neu-schritt[data-schritt="${n}"]`); if (el) el.classList.toggle('fertig', ok); };
    schritt('wort', !!String(e.wort || '').trim());
    schritt('geraete', Object.keys(e.geraete || {}).length > 0);
  }

  // creating a word: a short moment of magic, then its page
  async _erschaffen(name, farbe) {
    const box = this.shadowRoot.querySelector('.raum-wurzel'); if (!box || this._raumD) return;
    box.innerHTML = `<div class="rd-hinter"></div><div class="rd erschaffen" style="--farbe:${esc(farbe)}">${this._magie('training', farbe)}<div class="er-wort">${esc(name)}</div><p class="rd-mitte klein">${esc(this.t('nv_erschaffen'))}</p>${this._konfetti()}</div>`;
    await new Promise((r) => setTimeout(r, 1900));
    const dlg = box.querySelector('.rd'); if (dlg) dlg.classList.add('geht');
    setTimeout(() => { if (!this._raumD) box.innerHTML = ''; }, 260);
  }

  _neu() {
    const d = this._daten;
    if (!this._entwurf || this._entwurf.id) {
      const spr = String((this._hass.config && this._hass.config.language) || 'en').slice(0, 2);
      this._entwurf = { wort: '', anzeige: '', sprache: d.sprachen.includes(spr) ? spr : 'en', geraete: {}, modell_id: '', farbe: FARBEN[d.woerter.length % FARBEN.length], automatisch_einspielen: true, nachts: true };
    }
    const e = this._entwurf;
    const modelle = (d.vorhandene_modelle || []).filter((m) => !d.woerter.some((w) => w.modell_id === m.modell_id));
    return `${this._neuVorschau(e)}<ha-card><h2>${esc(this.t('w_neu_titel'))}</h2><div class="klein" style="line-height:1.5">${this.t('w_neu_text')}</div>
<div class="neu-schritt" data-schritt="wort"><span class="neu-nr">1</span><div><label class="feld">${esc(this.t('w_text'))}</label><input type="text" data-feld="wort" value="${esc(e.wort)}" placeholder="${esc(this.t('w_text_bsp'))}"></div></div>
<div class="neu-schritt fertig" data-schritt="sprache"><span class="neu-nr">2</span><div><label class="feld">${esc(this.t('w_sprache'))}</label>${this._sprachWahl(e.sprache)}<div class="klein" style="margin-top:4px">${esc(this.t('w_sprache_hilfe'))}</div></div></div>
<div class="neu-schritt fertig" data-schritt="aussehen"><span class="neu-nr">3</span><div>
${modelle.length ? `<label class="feld">${esc(this.t('w_vorhanden'))}</label><select data-feld="modell_id"><option value="">${esc(this.t('w_vorhanden_keins'))}</option>${modelle.map((m) => `<option value="${esc(m.modell_id)}" ${m.modell_id === e.modell_id ? 'selected' : ''}>${esc(m.anzeige || m.modell_id)} (${esc(m.modell_id)}.tflite)</option>`).join('')}</select><div class="klein" style="margin-top:4px">${esc(this.t('w_modell_hilfe'))}</div>` : ''}
<label class="feld">${esc(this.t('w_anzeige'))}</label><input type="text" data-feld="anzeige" value="${esc(e.anzeige)}" placeholder="${esc(this.t('w_anzeige_hilfe', { w: e.wort || '…' }))}">
<label class="feld">${esc(this.t('w_farbe'))}</label>${this._farbWahl(e.farbe)}</div></div>
<div class="neu-schritt" data-schritt="geraete"><span class="neu-nr">4</span><div><h3>${esc(this.t('w_geraete'))}</h3><div class="klein">${esc(this.t('w_geraete_hilfe'))}</div>${this._plaetze(e, null)}</div></div>
<div class="zeile" style="margin-top:16px"><button class="k haupt gross-k" data-a="anlegen"><ha-icon icon="mdi:auto-fix"></ha-icon>${esc(this.t('w_anlegen'))}</button></div></ha-card>`;
  }

  _wortSeite() {
    const d = this._daten, w = d.wort;
    if (!this._entwurf || this._entwurf.id !== w.id) this._entwurf = { ...w.einstellungen, id: w.id, geraete: { ...(w.einstellungen.geraete || {}) } };
    const e = this._entwurf;
    return `<ha-card><h2>${esc(this.t('w_titel'))}</h2>${this._neuVorschau({ ...e, farbe: e.farbe || this._farbe(this._wortKurz()) })}
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
${Object.keys(g.plaetze).map((p) => { const pl = g.plaetze[p], w = wort(pl.wort); return `<tr><td>${esc(this.t('ge_platz', { n: p }))}</td><td>${w ? `<a class="chip" data-reiter="${this._admin ? 'wort' : 'uebersicht'}" data-wort="${esc(w.id)}"><span class="punkt" style="background:${this._farbe(w)}"></span>${esc(w.wort)}</a>` : `<span class="klein">${esc(this.t('ge_nicht'))}</span>`}</td><td>${esc(pl.auswahl || '–')}</td><td class="z">${pl.schwelle != null ? this._zahl(pl.schwelle) : '–'}</td></tr>`; }).join('')}</table>${this._raumTeil(g)}</ha-card>`).join('') + `<div class="klein">${esc(this.t('ge_hilfe'))}</div>`;
  }

  // ---------- Raumklang (claps next to a device = how its room sounds) ----------
  _raumTeil(g) {
    const r = g.raum, art = r && r.hall != null ? this._hallArt(r.hall) : '';
    const status = r ? this.t(r.stellen === 1 ? 'rk_angelernt_1' : 'rk_angelernt', { n: r.n, s: r.stellen }) : this.t('rk_nicht');
    const wellen = Array.from({ length: 5 }, (_, i) => `<i style="--i:${i}"></i>`).join('');
    return `<div class="raum ${r ? 'an' : ''}"><div class="raum-ikon" aria-hidden="true">${wellen}<ha-icon icon="mdi:home-sound-out"></ha-icon></div>
<div class="raum-text"><b>${esc(this.t('rk_titel'))}</b><div class="klein">${esc(status)}${r && r.hall != null ? ` · ${esc(this.t('rk_hall_kurz', { h: this._zahl(r.hall, 2), a: this.t('rk_art_' + art) }))}` : ''}</div>
${r ? '' : `<div class="klein raum-warum">${esc(this.t('rk_warum'))}</div>`}</div>
<div class="raum-knoepfe">${r ? `<button class="k leise" data-raum="hoeren" data-knoten="${esc(g.knoten)}" title="${esc(this.t('rk_hoeren_titel'))}"><ha-icon icon="mdi:ear-hearing"></ha-icon>${esc(this.t('rk_hoeren'))}</button>` : ''}
${this._admin ? `<button class="k ${r ? '' : 'haupt'}" data-raum="start" data-knoten="${esc(g.knoten)}"><ha-icon icon="mdi:hand-clap"></ha-icon>${esc(this.t(r ? 'rk_weitere' : 'rk_anlernen'))}</button>` : ''}
${r && this._admin ? `<button class="k leise" data-raum="loeschen" data-knoten="${esc(g.knoten)}" title="${esc(this.t('rk_loeschen'))}"><ha-icon icon="mdi:delete-outline"></ha-icon></button>` : ''}</div></div>`;
  }

  _raumSchalter(e) {
    const n = (this._daten.geraete || []).filter((g) => g.raum).length;
    const info = n ? `<span class="klein kachel-info"><ha-icon icon="mdi:check-circle"></ha-icon>${esc(this.t('rk_wort_an', { n }))}</span>`
      : `<span class="klein kachel-info">${esc(this.t('rk_wort_keins'))} <a class="chip" data-reiter="geraete"><ha-icon icon="mdi:hand-clap"></ha-icon>${esc(this.t('rk_zu_geraeten'))}</a></span>`;
    return this._kachelSchalter('raumklang', 'mdi:home-sound-out', 'sw_raumklang', 'sw_raumklang_text', e.raumklang !== false, { unter: info });
  }

  // one setting as a tile: icon, short title, one line on what it does, a switch; on = tinted and the icon glows
  _kachelSchalter(opt, icon, titel, text, an, x = {}) {
    return `<div class="kschalter ${an ? 'an' : ''}"><label class="kschalter-kopf"><span class="kschalter-ikon"><ha-icon icon="${icon}"></ha-icon></span>
<span class="kschalter-text"><b>${esc(this.t(titel))}${x.zusatz ? ` <span class="klein">· ${esc(x.zusatz)}</span>` : ''}</b><span class="klein">${esc(this.t(text))}</span></span>
<input type="checkbox" class="schieber" data-wopt="${opt}" ${an ? 'checked' : ''} ${this._admin ? '' : 'disabled'}></label>${x.unter || ''}</div>`;
  }

  _hallArt(h) { return h < 0.3 ? 'trocken' : h < 0.6 ? 'normal' : 'hallig'; }

  async _raumAktion(was, knoten) {
    const g = ((this._daten && this._daten.geraete) || []).find((x) => x.knoten === knoten);
    if (was === 'start' && g) { this._raumOeffnen(g); return; }
    if (was === 'hoeren' && g && g.raum) { this._raumHoeren(null, g); return; }
    if (was === 'loeschen' && g) {
      if (!confirm(this.t('rk_loeschen_frage', { g: g.name }))) return;
      try { await this._hass.fetchWithAuth('/api/sprachmodell/raum?knoten=' + encodeURIComponent(knoten), { method: 'DELETE' }); } catch (e) { this._meldung(this.t('ging_nicht', { f: e.message })); }
      this._laden(); return;
    }
    const d = this._raumD; if (!d) return;
    if (was === 'los') this._raumLos();
    else if (was === 'nochmal') { this._raumAufraeumen(); d.schritt = 'start'; d.ergebnis = null; this._raumZeichnen(); }
    else if (was === 'probe') this._raumHoeren(d.ergebnis ? d.ergebnis.impulse : null, d.geraet);
    else if (was === 'speichern') this._raumSpeichern();
    else if (was === 'zu') this._raumSchliessen();
  }

  _raumOeffnen(g) {
    if (!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) { this._meldung(this.t('au_kein_mikro')); return; }
    this._raumD = { geraet: g, schritt: 'start', klatscher: [], ergebnis: null };
    this._raumZeichnen();
  }

  _raumSchliessen() {
    this._raumAufraeumen();
    const box = this.shadowRoot.querySelector('.raum-wurzel');
    const dlg = box && box.querySelector('.rd');
    this._raumD = null;
    if (dlg) { dlg.classList.add('geht'); setTimeout(() => { if (!this._raumD) box.innerHTML = ''; }, 260); } else if (box) box.innerHTML = '';
  }

  _raumAufraeumen() {
    const d = this._raumD; if (!d) return;
    clearInterval(d.uhr); cancelAnimationFrame(d.bild);
    try { if (d.proz) d.proz.disconnect(); if (d.quelle) d.quelle.disconnect(); if (d.strom) d.strom.getTracks().forEach((t) => t.stop()); if (d.ctx) d.ctx.close(); } catch (e) { /* schon zu */ }
    Object.assign(d, { proz: null, quelle: null, strom: null, ctx: null });
  }

  _raumZeichnen() {
    const box = this.shadowRoot.querySelector('.raum-wurzel'), d = this._raumD; if (!box || !d) return;
    const name = esc(d.geraet.name), s = d.schritt;
    let inhalt = '';
    if (s === 'start') {
      inhalt = `<div class="rd-bild">${this._raumSzene()}</div>
<ol class="rd-schritte"><li>${esc(this.t('rk_s1', { g: d.geraet.name }))}</li><li>${esc(this.t('rk_s2'))}</li><li>${esc(this.t('rk_s3'))}</li></ol>
<div class="klein rd-tipp">${esc(this.t('rk_tipp'))}</div>
<div class="rd-knoepfe"><button class="k leise" data-raum="zu">${esc(this.t('rk_abbrechen'))}</button><button class="k haupt" data-raum="los"><ha-icon icon="mdi:microphone"></ha-icon>${esc(this.t('rk_los'))}</button></div>`;
    } else if (s === 'zaehlen') {
      inhalt = `<div class="rd-zaehler"><svg viewBox="0 0 120 120"><circle class="rd-ring-grund" cx="60" cy="60" r="52"/><circle class="rd-ring" cx="60" cy="60" r="52" style="--dauer:${d.zaehlen}s"/></svg><b id="rdzahl">${d.rest}</b></div>
<p class="rd-mitte">${esc(this.t('rk_hingehen'))}</p><div class="rd-knoepfe"><button class="k leise" data-raum="zu">${esc(this.t('rk_abbrechen'))}</button></div>`;
    } else if (s === 'hoeren') {
      const punkte = Array.from({ length: 4 }, (_, i) => `<span class="rd-punkt" data-n="${i}"><ha-icon icon="mdi:hand-clap"></ha-icon></span>`).join('');
      inhalt = `<div class="rd-live"><canvas id="rdwelle" height="120"></canvas><div class="rd-aufnahme"><span class="lebt"></span>${esc(this.t('rk_lauscht'))}</div></div>
<div class="rd-punkte">${punkte}</div><p class="rd-mitte" id="rdhinweis">${esc(this.t('rk_klatschen'))}</p>
<div class="fortschritt rd-zeit"><i id="rdzeit" style="width:0"></i></div>
<div class="rd-knoepfe"><button class="k leise" data-raum="zu">${esc(this.t('rk_abbrechen'))}</button></div>`;
    } else if (s === 'denken') {
      inhalt = `${this._magie('merkmale')}<p class="rd-mitte rd-denkt" id="rddenkt">${esc(this.t('rk_denkt_1'))}</p>`;
    } else if (s === 'fertig') {
      const e = d.ergebnis, art = e.hall != null ? this._hallArt(e.hall) : 'normal';
      inhalt = `<div class="rd-ergebnis">${this._raumKurven(e.impulse)}
<div class="rd-wert"><span class="klein">${esc(this.t('rk_nachhall'))}</span><b>${e.hall != null ? esc(this._zahl(e.hall, 2)) + ' s' : '–'}</b><span class="chip rd-art rd-${art}">${esc(this.t('rk_art_' + art))}</span></div></div>
<p class="klein rd-mitte">${esc(this.t('rk_gefunden', { n: e.impulse.length }))} ${esc(this.t('rk_erklaerung_' + art))}</p>
${e.laut ? `<div class="hinweis">${esc(this.t('rk_zu_laut'))}</div>` : ''}
<div class="rd-knoepfe"><button class="k leise" data-raum="nochmal"><ha-icon icon="mdi:restart"></ha-icon>${esc(this.t('rk_nochmal'))}</button><button class="k" data-raum="probe"><ha-icon icon="mdi:ear-hearing"></ha-icon>${esc(this.t('rk_hoeren'))}</button><button class="k haupt" data-raum="speichern" ${d.speichert ? 'disabled' : ''}><ha-icon icon="mdi:auto-fix"></ha-icon>${esc(this.t('rk_speichern'))}</button></div>`;
    } else if (s === 'gespeichert') {
      inhalt = `${this._konfetti()}<div class="rd-fertig"><ha-icon icon="mdi:check-circle"></ha-icon></div><p class="rd-mitte"><b>${esc(this.t('rk_gespeichert', { g: d.geraet.name }))}</b></p><p class="klein rd-mitte">${esc(this.t('rk_gespeichert_text'))}</p>
<div class="rd-knoepfe"><button class="k haupt" data-raum="zu">${esc(this.t('rk_fertig'))}</button></div>`;
    } else if (s === 'fehler') {
      inhalt = `<div class="rd-fertig rd-nein"><ha-icon icon="mdi:hand-clap"></ha-icon></div><p class="rd-mitte"><b>${esc(this.t('rk_zu_wenig_titel'))}</b></p><p class="klein rd-mitte">${esc(this.t(d.fehler || 'rk_zu_wenig'))}</p>
<div class="rd-knoepfe"><button class="k leise" data-raum="zu">${esc(this.t('rk_abbrechen'))}</button><button class="k haupt" data-raum="nochmal"><ha-icon icon="mdi:restart"></ha-icon>${esc(this.t('rk_nochmal'))}</button></div>`;
    }
    const neu = !box.querySelector('.rd');
    if (neu) box.innerHTML = `<div class="rd-hinter" data-raum="zu"></div><div class="rd" role="dialog" aria-modal="true"><div class="rd-kopf"><ha-icon icon="mdi:home-sound-out"></ha-icon><div><div class="klein">${esc(this.t('rk_titel'))}</div><b>${name}</b></div><button class="ikon" data-raum="zu" title="${esc(this.t('rk_abbrechen'))}"><ha-icon icon="mdi:close"></ha-icon></button></div><div class="rd-inhalt"></div></div>`;
    const ziel = box.querySelector('.rd-inhalt');
    ziel.innerHTML = `<div class="rd-schritt">${inhalt}</div>`;
  }

  // little scene for the start: phone next to the device, a person clapping a few steps away, sound rings
  _raumSzene() {
    return `<svg class="rd-szene" viewBox="0 0 320 120" aria-hidden="true">
<rect class="sz-boden" x="10" y="104" width="300" height="2" rx="1"/>
<g class="sz-geraet"><rect x="40" y="70" width="38" height="34" rx="10"/><circle cx="59" cy="80" r="3"/></g>
<g class="sz-handy"><rect x="84" y="84" width="14" height="20" rx="3"/><rect class="sz-schirm" x="86" y="87" width="10" height="13" rx="1"/></g>
<g class="sz-ringe"><circle cx="230" cy="56" r="10"/><circle cx="230" cy="56" r="10"/><circle cx="230" cy="56" r="10"/></g>
<g class="sz-person"><circle cx="250" cy="34" r="9"/><path d="M250 44v34M250 78l-10 26M250 78l10 26"/><g class="sz-haende"><path class="sz-l" d="M250 52l-18 2"/><path class="sz-r" d="M250 56l-18 0"/></g></g>
<path class="sz-weg" d="M224 70 C 180 50, 140 58, 104 84"/></svg>`;
  }

  // decay of every clap (level in dB over time): steep = dry room, long = echoey room
  _raumKurven(impulse) {
    const farben = ['var(--primary-color)', '#8bc34a', '#ff9800', '#e91e63', '#9c27b0', '#009688'];
    const B = 300, H = 110, rahmen = 160, T = Math.max(0.3, ...impulse.map((x) => x.length / 16000));
    const pfade = impulse.map((x, k) => {
      const n = Math.floor(x.length / rahmen);
      let spitze = 1e-9; for (let i = 0; i < x.length; i++) spitze = Math.max(spitze, Math.abs(x[i]));
      const pkt = [];
      for (let i = 0; i < n; i++) {
        let s = 0; for (let j = i * rahmen; j < (i + 1) * rahmen; j++) s += x[j] * x[j];
        const db = Math.max(-60, 20 * Math.log10(Math.sqrt(s / rahmen) / spitze + 1e-9));
        pkt.push(`${((i * rahmen) / 16000 / T * B).toFixed(1)},${(8 + (-db / 60) * (H - 16)).toFixed(1)}`);
      }
      if (!pkt.length) return '';
      const letzt = pkt[pkt.length - 1].split(',')[0];
      return `<polygon points="0,${H - 8} ${pkt.join(' ')} ${letzt},${H - 8}" style="--c:${farben[k % farben.length]};--v:${k * 120 + 500}ms"/><polyline points="${pkt.join(' ')}" style="--c:${farben[k % farben.length]};--v:${k * 120}ms"/>`;
    }).join('');
    return `<svg class="rd-kurven" viewBox="0 0 ${B} ${H}" preserveAspectRatio="none" aria-hidden="true"><line x1="0" y1="${H - 8}" x2="${B}" y2="${H - 8}"/>${pfade}</svg>`;
  }

  _ton(ctx, frequenz, dauer, wann = 0, laut = 0.25) {
    const o = ctx.createOscillator(), v = ctx.createGain(), t = ctx.currentTime + wann;
    o.frequency.value = frequenz; o.type = 'sine';
    v.gain.setValueAtTime(0, t); v.gain.linearRampToValueAtTime(laut, t + 0.01); v.gain.exponentialRampToValueAtTime(0.0001, t + dauer);
    o.connect(v); v.connect(ctx.destination); o.start(t); o.stop(t + dauer + 0.02);
  }

  async _raumLos() {
    const d = this._raumD; if (!d) return;
    try {
      d.strom = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } });
    } catch (e) { this._meldung(this.t('au_erlaubnis', { f: e.message })); return; }
    if (this._raumD !== d) { d.strom.getTracks().forEach((t) => t.stop()); return; }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const quelle = ctx.createMediaStreamSource(d.strom), proz = ctx.createScriptProcessor(1024, 1, 1);
    const rate = ctx.sampleRate, block = 1024 / rate;
    Object.assign(d, { ctx, quelle, proz, rate, stuecke: [], spitzen: [], klatscher: [], rauschen: 0.002, laeuft: false, zaehlen: 5, rest: 5 });
    let letzte = -9, vorher = [0, 0, 0], t = 0;
    const DAUER = 12;
    proz.onaudioprocess = (ev) => {
      const x = new Float32Array(ev.inputBuffer.getChannelData(0));
      let s = 0, p = 0; for (let i = 0; i < x.length; i++) { s += x[i] * x[i]; p = Math.max(p, Math.abs(x[i])); }
      const rms = Math.sqrt(s / x.length);
      if (!d.laeuft) { d.rauschen = d.rauschen * 0.9 + rms * 0.1; return; }
      d.stuecke.push(x); d.spitzen.push(p); t += block;
      const davor = Math.max(...vorher);
      // a clap: a sudden, loud peak well above the room's noise and the blocks before it
      if (p > Math.max(0.05, d.rauschen * 10) && p > davor * 3 && t - letzte > 0.35) {
        letzte = t; d.klatscher.push(t - block); this._raumKlatsch(d.klatscher.length);
      } else if (t - letzte > 0.6) d.rauschen = d.rauschen * 0.98 + rms * 0.02;
      vorher = [vorher[1], vorher[2], p];
      const fertig = t >= DAUER || d.klatscher.length >= 6 || (d.klatscher.length >= 4 && t - letzte > 1.3);
      if (fertig && d.laeuft) { d.laeuft = false; setTimeout(() => this._raumAuswerten(), 0); }
    };
    quelle.connect(proz); proz.connect(ctx.destination);
    d.schritt = 'zaehlen'; this._raumZeichnen();
    this._ton(ctx, 660, 0.12);
    d.uhr = setInterval(() => {
      if (this._raumD !== d) { clearInterval(d.uhr); return; }
      d.rest -= 1;
      const z = this.shadowRoot.getElementById('rdzahl');
      if (d.rest > 0) { if (z) { z.textContent = d.rest; z.classList.remove('tick'); void z.offsetWidth; z.classList.add('tick'); } this._ton(ctx, 660, 0.12); return; }
      clearInterval(d.uhr);
      this._ton(ctx, 1320, 0.25, 0, 0.35);
      // start listening once the signal tone has died away, so it is never taken for a clap
      setTimeout(() => {
        if (this._raumD !== d) return;
        d.schritt = 'hoeren'; this._raumZeichnen(); d.laeuft = true; this._raumWelle();
        const start = performance.now();
        d.uhr = setInterval(() => { const b = this.shadowRoot.getElementById('rdzeit'); if (b) b.style.width = Math.min(100, (performance.now() - start) / (DAUER * 10)) + '%'; }, 200);
      }, 450);
    }, 1000);
  }

  _raumKlatsch(n) {
    const p = this.shadowRoot.querySelector(`.rd-punkt[data-n="${n - 1}"]`);
    if (p) p.classList.add('an');
    const h = this.shadowRoot.getElementById('rdhinweis');
    if (h) h.textContent = this.t(n >= 4 ? 'rk_genug' : 'rk_weiter', { n });
    const live = this.shadowRoot.querySelector('.rd-live');
    if (live) { const r = document.createElement('i'); r.className = 'rd-blitz'; live.appendChild(r); setTimeout(() => r.remove(), 700); }
  }

  // live wave: the peaks scroll from right to left, claps glow
  _raumWelle() {
    const d = this._raumD, c = this.shadowRoot.getElementById('rdwelle'); if (!d || !c) return;
    const farbe = getComputedStyle(this).getPropertyValue('--primary-color').trim() || '#03a9f4';
    const malen = () => {
      if (this._raumD !== d || d.schritt !== 'hoeren') return;
      const b = c.clientWidth || 300, h = c.height; if (c.width !== b) c.width = b;
      const g = c.getContext('2d'); g.clearRect(0, 0, b, h);
      const n = Math.floor(b / 4), sp = d.spitzen.slice(-n), versatz = n - sp.length;
      g.fillStyle = farbe;
      sp.forEach((p, i) => {
        const y = Math.max(2, Math.min(h - 4, Math.sqrt(p) * h * 1.1));
        g.globalAlpha = 0.35 + 0.65 * (i / n);
        g.fillRect((versatz + i) * 4, (h - y) / 2, 2.5, y);
      });
      g.globalAlpha = 1;
      const block = 1024 / d.rate, jetzt = d.spitzen.length * block;
      d.klatscher.forEach((k) => {
        const x = b - ((jetzt - k) / block) * 4; if (x < 0) return;
        const verlauf = g.createLinearGradient(x - 10, 0, x + 10, 0);
        verlauf.addColorStop(0, 'rgba(255,255,255,0)'); verlauf.addColorStop(0.5, 'rgba(255,255,255,.75)'); verlauf.addColorStop(1, 'rgba(255,255,255,0)');
        g.fillStyle = verlauf; g.fillRect(x - 10, 0, 20, h); g.fillStyle = farbe;
      });
      d.bild = requestAnimationFrame(malen);
    };
    malen();
  }

  _auf16k(roh, rate) {
    const faktor = rate / 16000, m = Math.floor(roh.length / faktor), aus = new Float32Array(m);
    for (let i = 0; i < m; i++) {
      const a = Math.floor(i * faktor), b = Math.max(a + 1, Math.min(roh.length, Math.floor((i + 1) * faktor)));
      let s = 0; for (let j = a; j < b; j++) s += roh[j];
      aus[i] = s / (b - a);
    }
    return aus;
  }

  _wavBlob(x) {
    const m = x.length, kopf = new DataView(new ArrayBuffer(44)), daten = new Int16Array(m);
    for (let i = 0; i < m; i++) daten[i] = Math.max(-32768, Math.min(32767, Math.round(x[i] * 32767)));
    const schreib = (p, t) => { for (let i = 0; i < t.length; i++) kopf.setUint8(p + i, t.charCodeAt(i)); };
    schreib(0, 'RIFF'); kopf.setUint32(4, 36 + m * 2, true); schreib(8, 'WAVE'); schreib(12, 'fmt ');
    kopf.setUint32(16, 16, true); kopf.setUint16(20, 1, true); kopf.setUint16(22, 1, true); kopf.setUint32(24, 16000, true);
    kopf.setUint32(28, 32000, true); kopf.setUint16(32, 2, true); kopf.setUint16(34, 16, true); schreib(36, 'data'); kopf.setUint32(40, m * 2, true);
    return new Blob([kopf, daten.buffer], { type: 'audio/wav' });
  }

  // reverb time from the decay (Schroeder): -5 to -25 dB, else -5 to -15 dB, extrapolated to 60 dB
  _hallzeit(x) {
    const e = new Float64Array(x.length + 1);
    for (let i = x.length - 1; i >= 0; i--) e[i] = e[i + 1] + x[i] * x[i];
    if (!(e[0] > 0)) return null;
    const zeit = (db) => { const grenze = e[0] * Math.pow(10, db / 10); for (let i = 0; i < x.length; i++) if (e[i] <= grenze) return i / 16000; return null; };
    const t5 = zeit(-5), t25 = zeit(-25), t15 = zeit(-15);
    if (t5 != null && t25 != null && t25 > t5) return 3 * (t25 - t5);
    if (t5 != null && t15 != null && t15 > t5) return 6 * (t15 - t5);
    return null;
  }

  // cut every clap with its echo out of the recording: from just before the peak until it sinks into the noise
  _raumImpulse(x, zeiten) {
    const rahmen = 160, n = Math.floor(x.length / rahmen), pegel = new Float32Array(n);
    for (let i = 0; i < n; i++) { let s = 0; for (let j = i * rahmen; j < (i + 1) * rahmen; j++) s += x[j] * x[j]; pegel[i] = Math.sqrt(s / rahmen); }
    const sortiert = [...pegel].sort((a, b) => a - b), rauschen = Math.max(1e-5, sortiert[Math.floor(n * 0.2)] || 1e-5);
    const spitzen = zeiten.map((t) => {
      const a = Math.max(0, Math.floor((t - 0.12) * 16000)), b = Math.min(x.length, Math.floor((t + 0.2) * 16000));
      let p = a; for (let i = a; i < b; i++) if (Math.abs(x[i]) > Math.abs(x[p])) p = i;
      return p;
    });
    const aus = []; let laut = 0;
    spitzen.forEach((p, k) => {
      const start = Math.max(0, p - 16), grenze = Math.min(x.length, k + 1 < spitzen.length ? spitzen[k + 1] - 320 : x.length, p + Math.floor(1.2 * 16000));
      const spitze = Math.abs(x[p]);
      if (20 * Math.log10(spitze / rauschen) < 25) return;  // too quiet against the room noise
      let ende = grenze, still = 0;
      for (let f = Math.ceil(p / rahmen) + 2; f < Math.floor(grenze / rahmen); f++) {
        still = pegel[f] < rauschen * 2 ? still + 1 : 0;
        if (still >= 3) { ende = Math.min(grenze, (f + 2) * rahmen); break; }
      }
      if (ende - start < 0.06 * 16000) return;
      let geclippt = 0; for (let i = start; i < ende; i++) if (Math.abs(x[i]) > 0.98) geclippt++;
      if (geclippt > 8) laut++;
      const h = x.slice(start, ende), faktor = 0.9 / spitze, aus_n = Math.min(320, h.length >> 2);
      for (let i = 0; i < h.length; i++) h[i] *= faktor;
      for (let i = 0; i < aus_n; i++) h[h.length - 1 - i] *= 0.5 - 0.5 * Math.cos((Math.PI * i) / aus_n);
      aus.push(h);
    });
    return { impulse: aus.slice(0, 6), laut: laut > 0 && laut >= aus.length / 2 };
  }

  async _raumAuswerten() {
    const d = this._raumD; if (!d) return;
    const stuecke = d.stuecke, rate = d.rate, zeiten = [...d.klatscher];
    this._raumAufraeumen();
    if (this._raumD !== d) return;
    d.schritt = 'denken'; this._raumZeichnen();
    const n = stuecke.reduce((a, b) => a + b.length, 0), roh = new Float32Array(n);
    let o = 0; for (const s of stuecke) { roh.set(s, o); o += s.length; }
    const e = this._raumImpulse(this._auf16k(roh, rate), zeiten);
    const hall = e.impulse.map((h) => this._hallzeit(h)).filter((h) => h != null && h > 0.05 && h < 4);
    hall.sort((a, b) => a - b);
    e.hall = hall.length ? hall[Math.floor(hall.length / 2)] : null;
    e.hallJe = e.impulse.map((h) => this._hallzeit(h));
    // a short moment of "thinking" with changing words: the analysis itself takes milliseconds
    const worte = ['rk_denkt_1', 'rk_denkt_2', 'rk_denkt_3'];
    for (let i = 1; i < worte.length; i++) {
      await new Promise((r) => setTimeout(r, 650));
      const p = this.shadowRoot.getElementById('rddenkt'); if (p) { p.textContent = this.t(worte[i]); p.classList.remove('neu'); void p.offsetWidth; p.classList.add('neu'); }
    }
    await new Promise((r) => setTimeout(r, 600));
    if (this._raumD !== d) return;
    if (e.impulse.length < 2) { d.schritt = 'fehler'; d.fehler = zeiten.length >= 2 ? 'rk_zu_leise' : 'rk_zu_wenig'; this._raumZeichnen(); return; }
    d.ergebnis = e; d.schritt = 'fertig'; this._raumZeichnen();
  }

  async _raumSpeichern() {
    const d = this._raumD; if (!d || !d.ergebnis || d.speichert) return;
    d.speichert = true; this._raumZeichnen();
    const stelle = Date.now().toString(36);
    let ok = 0;
    for (let i = 0; i < d.ergebnis.impulse.length; i++) {
      const fd = new FormData();
      fd.append('knoten', d.geraet.knoten); fd.append('stelle', stelle);
      const h = d.ergebnis.hallJe[i]; if (h != null) fd.append('hall', String(h));
      fd.append('datei', this._wavBlob(d.ergebnis.impulse[i]), 'klatsch.wav');
      try { const r = await this._hass.fetchWithAuth('/api/sprachmodell/raum', { method: 'POST', body: fd }); if (r.ok) ok++; } catch (e) { /* zählt als nicht gespeichert */ }
    }
    d.speichert = false;
    if (this._raumD !== d) return;
    if (!ok) { this._meldung(this.t('ging_nicht', { f: '' })); this._raumZeichnen(); return; }
    d.schritt = 'gespeichert'; this._raumZeichnen(); this._laden();
  }

  // hear it: one of your own recordings of the word, first as recorded, then as in this room
  async _raumHoeren(impulse, g) {
    try {
      const ctx = this._hoerCtx || (this._hoerCtx = new (window.AudioContext || window.webkitAudioContext)());
      if (ctx.state === 'suspended') await ctx.resume();
      let h = impulse;
      if (!h) {
        h = await Promise.all((g.raum.ids || []).slice(-3).map(async (id) => {
          const r = await this._hass.fetchWithAuth('/api/sprachmodell/raum/' + encodeURIComponent(g.knoten) + '/' + encodeURIComponent(id));
          return (await ctx.decodeAudioData(await r.arrayBuffer())).getChannelData(0);
        }));
      }
      const wid = (Object.values(g.plaetze || {}).find((p) => p.wort) || {}).wort || (this._daten.woerter[0] || {}).id;
      let trocken = null;
      if (wid) {
        const l = await this._api('GET', `liste?filter=bewertet&art=wort&wort=${encodeURIComponent(wid)}`);
        const a = (l.eintraege || [])[0];
        if (a) { const r = await this._hass.fetchWithAuth('/api/sprachmodell/audio/' + encodeURIComponent(wid) + '/' + encodeURIComponent(a.id)); trocken = await ctx.decodeAudioData(await r.arrayBuffer()); }
      }
      const imp = h[0], buf = ctx.createBuffer(1, imp.length, 16000); buf.copyToChannel(imp instanceof Float32Array ? imp : new Float32Array(imp), 0);
      if (!trocken) { const q = ctx.createBufferSource(); q.buffer = buf; q.connect(ctx.destination); q.start(); this._meldung(this.t('rk_hoeren_klatsch')); return; }
      const nass = ctx.createConvolver(); nass.normalize = true; nass.buffer = buf;
      const a = ctx.createBufferSource(); a.buffer = trocken; a.connect(ctx.destination); a.start();
      const b = ctx.createBufferSource(); b.buffer = trocken; const v = ctx.createGain(); v.gain.value = 1.4;
      b.connect(nass); nass.connect(v); v.connect(ctx.destination); b.start(ctx.currentTime + trocken.duration + 0.5);
      this._meldung(this.t('rk_hoeren_info'));
    } catch (e) { this._meldung(this.t('ging_nicht', { f: e.message })); }
  }

  // ---------- Einstellungen ----------
  _einstellungen() {
    const d = this._daten, e = d.einstellungen, tr = d.trainer;
    const basis = tr.adresse || location.origin;
    if (!this._admin) return `<ha-card><div class="zeile weit"><h2 style="margin:0">${esc(this.t('es_trainer'))}</h2><span class="klein"><span class="punkt ${tr.online ? 'an' : ''}"></span>${esc(tr.online ? this.t('t_trainer_an') : tr.kontakt ? this.t('t_trainer_zuletzt', { z: this._zeit(tr.kontakt) }) : this.t('t_trainer_nie'))}</span></div><p class="klein">${esc(this.t('nur_admin_hinweis'))}</p></ha-card>
<div class="klein">${esc(this.t('es_info', { v: d.version_integration, a: d.ablage }))}</div>`;
    return `${this._abschnitt('allgemein', 'mdi:clock-outline', 'es_allgemein', 'es_allgemein_kurz', `<label class="feld">${esc(this.t('es_zeit'))}</label><input type="time" data-zopt="uhrzeit" value="${esc(String(e.uhrzeit).slice(0, 5))}">
<label class="feld">${esc(this.t('es_min_neu'))}</label><input type="number" min="1" max="500" data-zopt="nachts_min_neu" value="${e.nachts_min_neu}">
<label class="feld">${esc(this.t('es_erinnerung'))}</label><input type="number" min="0" max="60" data-zopt="erinnerung_tage" value="${e.erinnerung_tage}">
<label class="feld">${esc(this.t('es_aufbewahren'))}</label><input type="number" min="7" max="365" data-zopt="unbewertet_tage" value="${e.unbewertet_tage}">
<label class="feld">${esc(this.t('es_personen'))}</label><input type="text" data-zopt="personen" value="${esc((e.personen || []).join(', '))}" placeholder="${esc(d.personen.join(', '))}">`)}
${this._abschnitt('trainer', 'mdi:school-outline', 'es_trainer', '', `<p class="klein" style="line-height:1.5">${esc(this.t('es_trainer_text'))}</p>
<h3>${esc(this.t('tr_deine'))}</h3>${this._trainerUebersicht()}
<h3>${esc(this.t('ei_titel'))}</h3>${this._einrichten(basis)}
<table><tr><td>${esc(this.t('es_adresse'))}</td><td><code>${esc(basis)}</code></td></tr><tr><td>${esc(this.t('es_schluessel'))}</td><td><div class="schluessel"><code>${this._zeigeSchl ? esc(tr.schluessel) : '••••••••••••'}</code><button class="k leise" data-a="schluessel">${esc(this.t(this._zeigeSchl ? 'es_verbergen' : 'es_zeigen'))}</button><button class="k leise" data-a="schluessel_neu">${esc(this.t('es_neu_schluessel'))}</button></div></td></tr></table>`, `<span class="klein"><span class="punkt ${tr.online ? 'an' : ''}"></span>${esc(this._trainerStatus())}</span>`)}
${this._sendenKarte(tr, basis)}
${this._abschnitt('ablage', 'mdi:folder-outline', 'es_ablage', 'es_ablage_kurz', `<p class="klein" style="line-height:1.6">${this.t('es_ablage_text', { a: esc(d.ablage) })}</p>`)}
<div class="klein">${esc(this.t('es_info', { v: d.version_integration, a: d.ablage }))}</div>`;
  }

  // a large card that folds open and closed, closed by default; a short line says what is inside, and which ones are
  // open is remembered in this browser
  _klapp(id, icon, titel, kurz, inhalt, rechts = '') {
    const auf = this._merk('abschnitt.' + id) === '1';
    return `<ha-card class="abschnitt klapp"><details data-abschnitt="${id}" ${auf ? 'open' : ''}><summary><span class="ab-ikon"><ha-icon icon="${icon}"></ha-icon></span><span class="ab-titel"><h2>${esc(titel)}</h2>${kurz ? `<span class="klein">${esc(kurz)}</span>` : ''}</span>${rechts}<ha-icon class="ab-pfeil" icon="mdi:chevron-down"></ha-icon></summary><div class="ab-inhalt">${inhalt}</div></details></ha-card>`;
  }

  // a settings section that folds open and closed; which ones are open is remembered in this browser
  _abschnitt(id, icon, titel, kurz, inhalt, rechts = '') {
    const offen = this._merk('abschnitt.' + id);
    const auf = offen == null ? id === 'trainer' : offen === '1';
    return `<ha-card class="abschnitt"><details data-abschnitt="${id}" ${auf ? 'open' : ''}><summary><span class="ab-ikon"><ha-icon icon="${icon}"></ha-icon></span><span class="ab-titel"><h2>${esc(this.t(titel))}</h2>${kurz ? `<span class="klein">${esc(this.t(kurz))}</span>` : ''}</span>${rechts}<ha-icon class="ab-pfeil" icon="mdi:chevron-down"></ha-icon></summary><div class="ab-inhalt">${inhalt}</div></details></ha-card>`;
  }

  _sendenKarte(tr, basis) {
    const d = this._daten, adresse = basis.replace(/\/+$/, '') + '/api/wake_word_studio';
    const geraete = (d.geraete || []).filter((g) => g.senden);
    const schritte = [1, 2, 3, 4].map((n) => `<li>${esc(this.t('es_senden_s' + n))}</li>`).join('');
    // live from Home Assistant where possible, so a switch flips at once; the studio's own snapshot otherwise
    const live = (ent, sonst) => { const st = ent && this._hass && this._hass.states[ent]; return st ? st.state : sonst; };
    const zeilen = geraete.map((g) => {
      const s = g.senden, ziel = live(s.ziel_entitaet, s.ziel), behalten = live(s.behalten_entitaet, s.behalten), seite = live(s.seite_entitaet, s.seite);
      const status = live(s.status_entitaet, s.status), offen = live(s.offen_entitaet, s.offen);
      const an = ziel === 'Custom' && behalten !== 'off';
      const art = behalten === 'off' ? 'rot' : an ? 'gruen' : 'gelb';
      const pille = behalten === 'off' ? this.t('es_senden_behalten_aus_kurz') : an ? this.t('es_senden_an') : ziel && ziel !== 'Off' ? this.t('es_senden_anders', { z: ziel }) : this.t('es_senden_aus');
      const extra = [status && !['unknown', 'unavailable'].includes(status) ? status : '', offen && !['unknown', 'unavailable', '0'].includes(String(offen)) ? this.t('es_senden_offen', { n: offen }) : ''].filter(Boolean).join(' · ');
      const schalter = (ent, wert, text, warn) => ent ? `<label class="schalter"><input type="checkbox" data-gschalter="${esc(ent)}" ${warn ? 'data-warn="1"' : ''} ${wert === 'on' ? 'checked' : ''} ${['unknown', 'unavailable'].includes(wert) ? 'disabled' : ''}><i></i><span>${esc(text)}</span></label>` : '';
      const optionen = (s.ziel_optionen && s.ziel_optionen.length ? s.ziel_optionen : [ziel]).filter(Boolean);
      const auswahl = s.ziel_entitaet ? `<label class="klein zeile" style="gap:6px">${esc(this.t('es_senden_an_wahl'))}<select data-gziel="${esc(s.ziel_entitaet)}">${optionen.map((o) => `<option value="${esc(o)}" ${o === ziel ? 'selected' : ''}>${esc(o === 'Off' ? this.t('es_senden_ziel_aus') : o === 'Custom' ? 'Custom · Wake Word Studio' : o)}</option>`).join('')}</select></label>` : '';
      const einrichten = s.ip && s.seite_entitaet ? `<button class="k ${an ? 'leise' : 'haupt'}" data-a="seite" data-ent="${esc(s.seite_entitaet)}" data-behalten="${esc(s.behalten_entitaet || '')}" data-ip="${esc(s.ip)}"><ha-icon icon="mdi:open-in-new"></ha-icon>${esc(this.t(an ? 'es_senden_seite' : 'es_senden_einrichten'))}</button>` : '';
      return `<div class="sgeraet"><div class="zeile weit"><span class="titel"><span class="punkt ${an ? 'an' : ''}"></span>${esc(g.name)}</span><span class="pille ${art}">${esc(pille)}</span></div>
<div class="zeile sgeraet-regler">${schalter(s.behalten_entitaet, behalten, this.t('es_schalter_behalten'), true)}${schalter(s.seite_entitaet, seite, this.t('es_schalter_seite'))}${auswahl}</div>
<div class="zeile weit"><span class="klein">${esc(extra || (s.ip ? 'IP ' + s.ip : ''))}</span>${einrichten}</div></div>`;
    }).join('');
    return this._abschnitt('senden', 'mdi:send-outline', 'es_senden', 'es_senden_kurz', `<p class="klein" style="line-height:1.6">${esc(this.t('es_senden_text'))}</p>
<ol class="klein" style="line-height:1.6;padding-left:20px">${schritte}</ol>
<table><tr><td>${esc(this.t('es_senden_ziel'))}</td><td><code>Custom</code></td></tr><tr><td>${esc(this.t('es_adresse'))}</td><td><div class="schluessel"><code>${esc(adresse)}</code><button class="k leise" data-a="kopieren" data-text="${esc(adresse)}">${esc(this.t('es_kopieren'))}</button></div></td></tr><tr><td>${esc(this.t('es_senden_token'))}</td><td><div class="schluessel"><code>${this._zeigeSchl ? esc(tr.schluessel) : '••••••••••••'}</code><button class="k leise" data-a="kopieren" data-schl="1">${esc(this.t('es_kopieren'))}</button></div></td></tr></table>
${geraete.length ? `<h3 style="margin:16px 0 8px">${esc(this.t('es_senden_geraete'))}</h3><div class="sgeraete">${zeilen}</div>` : `<p class="klein">${esc(this.t('es_senden_keine'))}</p>`}
<p class="klein" style="line-height:1.6">${esc(this.t('es_senden_hinweis'))}</p>`);
  }

  async _kopieren(text) {
    try { await navigator.clipboard.writeText(text); }
    catch (e) {
      const f = document.createElement('textarea'); f.value = text; f.style.position = 'fixed'; f.style.opacity = '0';
      this.shadowRoot.appendChild(f); f.select(); document.execCommand('copy'); f.remove();
    }
    this._meldung(this.t('es_kopiert'));
  }

  // ---------- Ereignisse ----------
  async _klick(e) {
    const t = e.target.closest('[data-reiter],[data-a],[data-spielen],[data-urteil],[data-echo],[data-verlauf],[data-seite],[data-recmodus],[data-takespielen],[data-takeweg],[data-farbe],[data-zelle],[data-tbecho],[data-schnitt],[data-sa],[data-logfilter],[data-umzug],[data-ziel],[data-zurueck],[data-vgl],[data-raum],[data-vurteil],[data-vsort]');
    if (!t) return;
    if (t.dataset.raum) { this._raumAktion(t.dataset.raum, t.dataset.knoten); return; }
    if (t.dataset.reiter) { if (t.dataset.reiter === 'neu') this._entwurf = null; this._gehe(t.dataset.reiter, t.dataset.wort); return; }
    if (t.dataset.spielen) { const zeile = t.closest('.eintrag'); if (zeile) { const alle = [...this.shadowRoot.querySelectorAll('.eintrag:not(.weg)')]; this._aktiv = Math.max(0, alle.indexOf(zeile)); this._markieren(false); } this._spielen(t.dataset.spielen); return; }
    if (t.dataset.urteil) { this._urteilen(t.dataset.id, t.dataset.urteil); return; }
    if (t.dataset.schnitt) { this._schnittOeffnen(t.dataset.schnitt); return; }
    if (t.dataset.umzug) { this._umzugOeffnen(t.dataset.umzug); return; }
    if (t.dataset.vgl && !e.target.closest('button')) { this._vglUmschalten(Number(t.dataset.vgl), t); return; }
    if (t.dataset.zurueck) { this._zurueckholen(this._wortId, t.dataset.zurueck, t.dataset.ziel); return; }
    if (t.dataset.ziel && t.dataset.id) { this._umziehen(t.dataset.id, t.dataset.ziel); return; }
    if (t.dataset.sa) { this._schnittAktion(t.dataset.sa); return; }
    if (t.dataset.echo !== undefined) { this._filter.echo = t.dataset.echo; this._filter.seite = 0; this._aktiv = 0; this._laden(); return; }
    if (t.dataset.zelle) { const [zeile, von, bis] = t.dataset.zelle.split('|'); this._filter.zelle = { zeile, von: Number(von), bis: Number(bis), echo: this._tbEcho || '' }; this._filter.seite = 0; this._gehe('verlauf', this._wortId); return; }
    if (t.dataset.logfilter) { this._logFilter = t.dataset.logfilter; this._zeichnen(); return; }
    if (t.dataset.tbecho !== undefined) { this._tbEcho = t.dataset.tbecho; this._zeichnen(); return; }
    if (t.dataset.vurteil !== undefined) { this._filter.urteil = t.dataset.vurteil; this._filter.seite = 0; this._laden(); return; }
    if (t.dataset.vsort !== undefined) { this._filter.sort = t.dataset.vsort; this._filter.seite = 0; this._laden(); return; }
    if (t.dataset.verlauf) { this._filter.zelle = null; this._filter.verlauf = t.dataset.verlauf; this._filter.seite = 0; this._laden(); return; }
    if (t.dataset.seite) { this._filter.seite = Math.max(0, this._filter.seite + Number(t.dataset.seite)); this._laden(); window.scrollTo(0, 0); return; }
    if (t.dataset.recmodus) { this._rec.modus = t.dataset.recmodus; this._zeichnen(); return; }
    if (t.dataset.takespielen) { const tk = this._rec.takes[Number(t.dataset.takespielen)]; if (tk) this._spielen('take' + t.dataset.takespielen, tk.url); return; }
    if (t.dataset.takeweg) { const [tk] = this._rec.takes.splice(Number(t.dataset.takeweg), 1); if (tk) URL.revokeObjectURL(tk.url); this._recZeichnen(); return; }
    if (t.dataset.farbe) { if (this._entwurf) { this._entwurf.farbe = t.dataset.farbe; this._entwurf._geaendert = true; } this.shadowRoot.querySelectorAll('[data-farbe]').forEach((b) => b.classList.toggle('an', b === t)); this._neuStand(); return; }
    const a = t.dataset.a;
    try {
      if (a === 'neu') this._laden();
      else if (a === 'datei') this.shadowRoot.getElementById('datei').click();
      else if (a === 'zelle_weg') { this._filter.zelle = null; this._filter.seite = 0; this._laden(); }
      else if (a === 'reparaturen') { history.pushState(null, '', '/config/repairs'); window.dispatchEvent(new CustomEvent('location-changed')); }
      else if (a === 'holen') { t.disabled = true; await this._api('POST', 'aktion', { aktion: 'jetzt_holen' }); this._laden(); }
      else if (a === 'trainieren') { await this._api('POST', 'aktion', { aktion: 'training_starten', wort: this._wortId }); this._laden(); }
      else if (a === 'abbrechen') { if (confirm(this.t('t_abbrechen_frage'))) { await this._api('POST', 'aktion', { aktion: 'training_abbrechen', wort: this._wortId }); this._laden(); } }
      else if (a === 'alle_vorschlaege') {
        const ids = ((this._liste && this._liste.eintraege) || []).filter((x) => x.vorschlag).map((x) => x.id);
        if (confirm(this.t('pr_alle_frage', { n: ids.length }))) { await this._api('POST', 'aktion', { aktion: 'vorschlaege_uebernehmen', wort: this._wortId, ids, person: this._person }); this._laden(); }
      } else if (a === 'schwelle') {
        const w = Number(t.dataset.wert);
        if (confirm(this.t('q_schwelle_frage', { w: this._zahl(w) }))) { await this._api('POST', 'aktion', { aktion: 'schwelle', wort: this._wortId, wert: w }); this._meldung(this.t('q_schwelle_ok')); this._laden(); }
      } else if (a === 'sw_schritt') {
        const f = this.shadowRoot.querySelector('.sw-wert');
        if (f) f.value = Math.min(0.99, Math.max(0.5, (Number(f.value) || 0.95) + 0.01 * Number(t.dataset.d))).toFixed(2);
      } else if (a === 'schwelle_hand') {
        const f = this.shadowRoot.querySelector('.sw-wert'), w = Math.round(Number(f && f.value) * 100) / 100;
        if (!(w >= 0.5 && w <= 0.99)) { this._meldung(this.t('q_hand_bereich')); return; }
        const auto = (this._daten.wort.einstellungen || {}).schwelle_automatisch;
        if (confirm(this.t(auto ? 'q_hand_frage_auto' : 'q_schwelle_frage', { w: this._zahl(w) }))) { await this._api('POST', 'aktion', { aktion: 'schwelle', wort: this._wortId, wert: w, hand: true }); this._meldung(this.t('q_schwelle_ok')); this._laden(); }
      } else if (a === 'vgl_tauschen') {
        const { a: x, b: y } = this._vglPaar(this._daten.wort);
        this._vglWahl[this._wortId] = { a: y.nr, b: x.nr }; this._vglFreiNeu();
      } else if (a === 'vgl_fair') {
        const { a: x, b: y } = this._vglPaar(this._daten.wort);
        if (confirm(this.t('vf_frage', { a: x.nr, b: y.nr }))) { t.disabled = true; await this._api('POST', 'aktion', { aktion: 'vergleich_starten', wort: this._wortId, a: x.nr, b: y.nr }); this._meldung(this.t('vf_gestartet')); this._laden(); }
      } else if (a === 'vgl_zeigen') {
        this._vglZeigen(Number(t.dataset.nr));
      } else if (a === 'einspielen') {
        const nr = Number(t.dataset.nr);
        if (confirm(this.t('q_einspielen_frage', { n: nr }))) { await this._api('POST', 'aktion', { aktion: 'einspielen', wort: this._wortId, nr }); this._meldung(this.t('q_wird', { n: nr })); this._laden(); }
      } else if (a === 'trainer_neustart') {
        const tr = (this._daten.trainer.liste || []).find((x) => x.id === t.dataset.tid);
        if (tr && confirm(this.t(tr.laeuft.length ? 'es_neustart_frage_lauf' : 'es_neustart_frage'))) {
          t.disabled = true;
          await this._api('POST', 'aktion', { aktion: 'trainer', trainer: tr.id, neustarten: true });
          this._meldung(this.t('es_neustart_ok'));
          this._laden();
        }
      } else if (a === 'studio_update') {
        if (confirm(this.t('vh_update_frage'))) { t.disabled = true; await this._hass.callService('update', 'install', { entity_id: t.dataset.ent }); }
      } else if (a === 'ha_neustart') {
        if (confirm(this.t('vh_ha_frage'))) { t.disabled = true; await this._hass.callService('homeassistant', 'restart', {}); }
      } else if (a === 'schluessel') { this._zeigeSchl = !this._zeigeSchl; this._zeichnen(); }
      else if (a === 'schluessel_neu') { if (confirm(this.t('es_neu_frage'))) { await this._api('POST', 'aktion', { aktion: 'schluessel_neu' }); this._zeigeSchl = true; this._laden(); } }
      else if (a === 'log_kopieren') { const w = this._daten.wort, l = (w && w.live) || {}; await this._kopieren((l.protokoll || []).map(([z, art, text]) => `${new Date(z * 1000).toLocaleString()} [${art}] ${text}`).join('\n')); }
      else if (a === 'ort') { this._ort = t.dataset.ort; this._zeichnen(); }
      else if (a === 'gpu_wahl') { this._mitGpu = t.checked; this._zeichnen(); }
      else if (a === 'befehl_kopieren') await this._kopieren(this._befehl(this._ort || 'windows', !!this._mitGpu, this._daten.trainer.adresse || location.origin, true));
      else if (a === 'trainer_vergessen') {
        const tn = (this._daten.trainer.liste || []).find((x) => x.id === t.dataset.tid);
        if (tn && confirm(this.t('tr_vergessen_frage', { n: this._trName(tn) }))) { await this._api('POST', 'aktion', { aktion: 'trainer', trainer: tn.id, vergessen: true }); this._laden(); }
      }
      else if (a === 'kopieren') await this._kopieren(t.dataset.schl ? (this._daten.trainer || {}).schluessel || '' : t.dataset.text);
      else if (a === 'behalten') { await this._hass.callService('switch', 'turn_on', { entity_id: t.dataset.ent }); this._meldung(this.t('es_senden_behalten_ok')); setTimeout(() => this._laden(), 1500); }
      else if (a === 'seite') {
        // the page is off until switched on; give the device a moment, within the click's permission to open a tab.
        // Sending needs "Keep wake clips", so that goes on too.
        const fenster = window.open('about:blank', '_blank');
        if (t.dataset.behalten) await this._hass.callService('switch', 'turn_on', { entity_id: t.dataset.behalten });
        await this._hass.callService('switch', 'turn_on', { entity_id: t.dataset.ent });
        await new Promise((r) => setTimeout(r, 800));
        const ziel = 'http://' + t.dataset.ip + ':8181/setup';
        if (fenster) { try { fenster.opener = null; } catch (e2) { /* ignore */ } fenster.location.href = ziel; } else window.open(ziel, '_blank', 'noopener');
        this._meldung(this.t('es_senden_seite_ok')); setTimeout(() => this._zeichnen(), 1500);
      }
      else if (a === 'rec') { if (this._rec.an) this._recStopp(); else await this._recStart(); }
      else if (a === 'recspeichern') { t.disabled = true; await this._recSpeichern(); }
      else if (a === 'recverwerfen') { this._rec.takes.forEach((x) => URL.revokeObjectURL(x.url)); this._rec.takes = []; this._recZeichnen(); }
      else if (a === 'anlegen') {
        const e2 = this._entwurfDaten();
        if (!String(e2.wort || '').trim()) { this._meldung(this.t('w_fehlt')); return; }
        t.disabled = true;
        const r = await this._api('POST', 'aktion', { aktion: 'wort_neu', einstellungen: e2 });
        const zauber = this._erschaffen(String(e2.wort).trim(), e2.farbe || FARBEN[0]);
        this._entwurf = null; this._gehe('uebersicht', r.id);
        await zauber;
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
      this._neuStand();
    }
  }

  async _aenderung(e) {
    const t = e.target;
    if (t.id === 'datei') { this._hochladen([...t.files]); t.value = ''; return; }
    if (t.id === 'autoplay') { this._autoplay = t.checked; this._merk('autoplay', t.checked ? '1' : '0'); return; }
    if (t.id === 'recnotiz') { this._rec.notiz = t.value; return; }
    if (t.dataset.vglwahl) {
      const { a, b } = this._vglPaar(this._daten.wort), nr = Number(t.value);
      const neu = { a: a.nr, b: b.nr, [t.dataset.vglwahl]: nr }, andere = t.dataset.vglwahl === 'a' ? 'b' : 'a';
      if (neu[andere] === nr) neu[andere] = t.dataset.vglwahl === 'a' ? b.nr === nr ? a.nr : b.nr : a.nr === nr ? b.nr : a.nr;
      this._vglWahl[this._wortId] = neu; this._vglFreiNeu(); return;
    }
    if (t.dataset.feld && this._entwurf) { this._entwurf[t.dataset.feld] = t.value; this._entwurf._geaendert = true; this._neuStand(); return; }
    if (t.dataset.platz !== undefined && this._entwurf) {
      const g = { ...(this._entwurf.geraete || {}) };
      if (t.value) g[t.dataset.platz] = t.value; else delete g[t.dataset.platz];
      this._entwurf.geraete = g; this._entwurf._geaendert = true; this._neuStand(); return;
    }
    if (t.dataset.gschalter) {
      // "Keep wake clips" off deletes the clips on the device, so that one asks first
      if (!t.checked && t.dataset.warn && !confirm(this.t('es_behalten_aus_frage'))) { t.checked = true; return; }
      try { await this._hass.callService('switch', t.checked ? 'turn_on' : 'turn_off', { entity_id: t.dataset.gschalter }); this._meldung(this.t(t.checked ? 'es_ein' : 'es_aus')); }
      catch (e2) { t.checked = !t.checked; this._meldung(this.t('ging_nicht', { f: e2.message })); }
      setTimeout(() => this._zeichnen(), 900); return;
    }
    if (t.dataset.gziel) {
      try { await this._hass.callService('select', 'select_option', { entity_id: t.dataset.gziel, option: t.value }); this._meldung(t.value === 'Custom' ? this.t('es_ziel_custom') : this.t('gespeichert')); }
      catch (e2) { this._meldung(this.t('ging_nicht', { f: e2.message })); }
      setTimeout(() => this._zeichnen(), 900); return;
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
        const kachel = t.closest('.kschalter-kopf') && t.closest('.kschalter');
        if (kachel) { kachel.classList.toggle('an', t.checked); kachel.classList.toggle('neu', t.checked); }
        if (t.dataset.wopt === 'gruendlich' && kachel) {
          const u = kachel.querySelector('.unter-schalter'), m = u && u.querySelector('input');
          if (u) u.classList.toggle('aus', !t.checked); if (m) m.disabled = !t.checked || !this._admin;
        }
        await this._api('POST', 'aktion', { aktion: 'wort_aendern', wort: this._wortId, einstellungen: { [t.dataset.wopt]: t.checked } });
        this._meldung(this.t('gespeichert'));
      } else if (t.dataset.ttaste) {
        await this._api('POST', 'aktion', { aktion: 'trainer', trainer: t.dataset.ttaste, taste: t.value });
        this._meldung(this.t('gespeichert'));
        this._laden();
      } else if (t.dataset.tpause) {
        await this._api('POST', 'aktion', { aktion: 'trainer', trainer: t.dataset.tpause, pause: !t.checked });
        this._meldung(this.t('gespeichert'));
        this._laden();
      } else if (t.dataset.zopt) {
        let wert = t.type === 'number' ? Number(t.value) : t.value;
        if (t.dataset.zopt === 'personen') wert = t.value.split(',').map((x) => x.trim()).filter(Boolean);
        await this._api('POST', 'aktion', { aktion: 'einstellungen', einstellungen: { [t.dataset.zopt]: wert } });
        this._meldung(this.t('gespeichert'));
        if (t.dataset.zopt === 'trainer_wahl') this._laden();
      }
    } catch (err) { this._meldung(this.t('ging_nicht', { f: this._fehlerText(err) })); }
  }

  _meldung(text, aktion) {
    const detail = aktion ? { message: text, action: aktion, duration: 8000 } : { message: text };
    this.dispatchEvent(new CustomEvent('hass-notification', { detail, bubbles: true, composed: true }));
  }
}

if (!customElements.get('sprachmodell-panel')) customElements.define('sprachmodell-panel', SprachmodellPanel);
console.info('%c Wake Word Studio ' + VERSION + ' ', 'background:#6d5dfc;color:#fff;border-radius:3px');
