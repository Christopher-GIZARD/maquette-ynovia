'use strict';

// ── Global state ──────────────────────────────────────────
const A = {};           // { questionId: value }
let FORM_DATA = null;
let PAPPERS_ENABLED = false;
let CATEGORIE_PAPPERS = null;

// ── Entry point ───────────────────────────────────────────
(async function init() {
  // Vérifie si l'API Pappers est activée côté serveur
  try {
    const cfg = await fetch('/api/config');
    if (cfg.ok) {
      const cfgData = await cfg.json();
      PAPPERS_ENABLED = Boolean(cfgData.pappers_enabled);
    }
  } catch (_) { /* serveur non dispo, PAPPERS_ENABLED reste false */ }

  try {
    const r = await fetch('./decision_tree.json');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    buildForm(data);
  } catch (e) {
    document.getElementById('spinner').style.display = 'none';
    document.getElementById('load-msg').textContent =
      'Impossible de charger le fichier automatiquement. Veuillez le sélectionner manuellement.';
    document.getElementById('load-manual').style.display = 'block';
  }
})();

function handleFile(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result);
      buildForm(data);
    } catch (err) {
      alert('Fichier JSON invalide : ' + err.message);
    }
  };
  reader.readAsText(file);
}

// ── Build entire form ─────────────────────────────────────
function buildForm(data) {
  FORM_DATA = data;
  const root = document.getElementById('form-root');
  let html = '';

  html += buildPappersSection(data.pappers_fields);
  html += buildQuestionsSection(data.questions);

  root.innerHTML = html;

  data.questions.forEach(q => applyDefaults(q));
  wireEvents();
  wireSirenInput();

  document.getElementById('load-screen').style.display = 'none';
  document.getElementById('app').style.display = 'block';
  updateProgress();
}

// ── Pappers fields ────────────────────────────────────────
function buildPappersSection(fields) {
  const inputs = fields.map(f => {
    const isFullWidth = f.id === 'adresse';
    const inputEl = f.type === 'number'
      ? `<input type="number" class="pf-input" id="pf-${esc(f.id)}" placeholder="…">`
      : f.type === 'date'
      ? `<input type="date" class="pf-input" id="pf-${esc(f.id)}">`
      : `<input type="text" class="pf-input" id="pf-${esc(f.id)}" placeholder="…">`;
    return `<div class="pf-group${isFullWidth ? ' pf-full' : ''}">
      <div class="pf-label${f.required ? ' req' : ''}">${esc(f.label)}</div>
      ${inputEl}
    </div>`;
  }).join('');

  return `<div class="form-section">
    <div class="sec-hdr">
      <div class="sec-ico">🏢</div>
      <div>
        <div class="sec-ttl">Identification de la société</div>
        <div class="sec-stl">Informations légales et de contact</div>
      </div>
    </div>
    <div class="pf-grid">${inputs}</div>
    <div class="pappers-enrich-row" id="pappers-enrich-row" style="display:none">
      <button class="btn-pappers" id="btn-pappers" onclick="enrichWithPappers()">
        <span class="btn-pappers-ico">🔍</span> Enrichir avec Pappers
      </button>
      <span class="pappers-hint">Préremplir les champs depuis les données légales</span>
    </div>
    <div id="pappers-categorie-card"></div>
  </div>`;
}

// ── Questions section ─────────────────────────────────────
function buildQuestionsSection(questions) {
  const general = [];
  const modules = [];

  questions.forEach(q => {
    if (q.uo_base_module !== undefined || (q.id && q.id.startsWith('has_'))) {
      modules.push(q);
    } else {
      general.push(q);
    }
  });

  let html = '';

  if (general.length) {
    html += `<div class="form-section">
      <div class="sec-hdr">
        <div class="sec-ico">⚙️</div>
        <div>
          <div class="sec-ttl">Paramètres généraux du projet</div>
          <div class="sec-stl">Structure, utilisateurs, contraintes et migration</div>
        </div>
      </div>
      <div>${general.map(q => renderQ(q, 0, null, null, null)).join('')}</div>
    </div>`;
  }

  if (modules.length) {
    html += `<div class="form-section">
      <div class="sec-hdr">
        <div class="sec-ico">🧩</div>
        <div>
          <div class="sec-ttl">Modules Odoo</div>
          <div class="sec-stl">Périmètre fonctionnel et besoins métier</div>
        </div>
      </div>
      <div>${modules.map(q => renderQ(q, 0, null, null, null)).join('')}</div>
    </div>`;
  }

  return html;
}

// ── Render single question ────────────────────────────────
function renderQ(q, depth, inheritedVP, inheritedVM, inheritedVV) {
  let vpId   = inheritedVP;
  let vmMode = inheritedVM;
  let vmVal  = (inheritedVV !== undefined) ? inheritedVV : null;

  if (q.show_if) {
    const si = q.show_if;
    if (si.parent_id) vpId = si.parent_id;
    if      (si.gt  !== undefined) { vmMode = 'gt';  vmVal = si.gt; }
    else if (si.gte !== undefined) { vmMode = 'gte'; vmVal = si.gte; }
    else if (si.lt  !== undefined) { vmMode = 'lt';  vmVal = si.lt; }
    else if (si.lte !== undefined) { vmMode = 'lte'; vmVal = si.lte; }
  }

  const hidden   = vpId !== null ? ' style="display:none"' : '';
  const isModule = q.uo_base_module !== undefined || (q.id && q.id.startsWith('has_'));

  const vpA = vpId   ? ` data-vp="${esc(vpId)}"`                : '';
  const vmA = vmMode ? ` data-vm="${esc(vmMode)}"`               : '';
  const vvA = vmVal !== null ? ` data-vv="${esc(String(vmVal))}"` : '';

  const inputHTML = renderInput(q);

  let childrenHTML = '';

  if (q.children) {
    q.children.forEach(c => {
      if (c.show_if && !c.show_if.parent_id) {
        childrenHTML += renderQ(c, depth + 1, q.id, null, null);
      } else {
        childrenHTML += renderQ(c, depth + 1, q.id, 'true', null);
      }
    });
  }

  if (q.children_map) {
    Object.entries(q.children_map).forEach(([val, children]) => {
      children.forEach(c => {
        childrenHTML += renderQ(c, depth + 1, q.id, 'value', val);
      });
    });
  }

  if (q.children_if_contains) {
    Object.entries(q.children_if_contains).forEach(([opt, children]) => {
      children.forEach(c => {
        childrenHTML += renderQ(c, depth + 1, q.id, 'contains', opt);
      });
    });
  }

  return `<div class="qi${isModule ? ' qmod' : ''}"
    id="qi-${esc(q.id)}"
    data-qid="${esc(q.id)}"
    data-t="${esc(q.type)}"
    data-d="${depth}"${vpA}${vmA}${vvA}${hidden}>
    <div class="qcard" id="qc-${esc(q.id)}">
      <div class="qlr">
        <div>
          <div class="qlbl">${esc(q.label)}</div>
          ${q.note ? `<div class="qnote">${esc(q.note)}</div>` : ''}
        </div>
      </div>
      ${inputHTML}
    </div>
    ${childrenHTML ? `<div class="qch">${childrenHTML}</div>` : ''}
  </div>`;
}

// ── Render input by type ──────────────────────────────────
function renderInput(q) {
  switch (q.type) {
    case 'boolean':
      return `<div class="bbrow">
        <button class="bbn" data-action="bool" data-qid="${esc(q.id)}" data-val="true">Oui</button>
        <button class="bbn" data-action="bool" data-qid="${esc(q.id)}" data-val="false">Non</button>
      </div>`;

    case 'select':
      return `<div class="sopts">${(q.options || []).map(o =>
        `<button class="sopt" data-action="select" data-qid="${esc(q.id)}" data-val="${esc(o)}">${esc(o)}</button>`
      ).join('')}</div>`;

    case 'multi_select':
      return `<div class="mlist" id="ml-${esc(q.id)}">${(q.options || []).map(o =>
        `<div class="mitem" data-action="multi" data-qid="${esc(q.id)}" data-val="${esc(o)}">
          <div class="mchk"></div>
          <span>${esc(o)}</span>
        </div>`
      ).join('')}</div>`;

    case 'number': {
      const def = q.default !== undefined ? q.default : 0;
      return `<div class="numrow">
        <button class="nadj" data-action="adjnum" data-qid="${esc(q.id)}" data-val="-1">−</button>
        <input class="nin" type="number" id="nin-${esc(q.id)}"
          value="${esc(String(def))}"
          data-action="number" data-qid="${esc(q.id)}">
        <button class="nadj" data-action="adjnum" data-qid="${esc(q.id)}" data-val="1">+</button>
      </div>`;
    }

    case 'text':
      return `<input class="txin" type="text" id="txin-${esc(q.id)}"
        data-action="text" data-qid="${esc(q.id)}" placeholder="Saisir…">`;

    case 'date':
      return `<input class="dtin" type="date" id="dtin-${esc(q.id)}"
        data-action="date" data-qid="${esc(q.id)}">`;

    default:
      return '';
  }
}

// ── Apply defaults (number) ───────────────────────────────
function applyDefaults(q) {
  if (q.type === 'number' && q.default !== undefined) {
    A[q.id] = q.default;
  }
  const all = [
    ...(q.children || []),
    ...Object.values(q.children_map || {}).flat(),
    ...Object.values(q.children_if_contains || {}).flat()
  ];
  all.forEach(c => applyDefaults(c));
}

// ── Catégorie Pappers ─────────────────────────────────────
const SANTE_COLORS  = { FRAGILE: 'red', STABLE: 'gray', DYNAMIQUE: 'green', PREMIUM: 'teal', INCONNU: 'gray' };
const TAILLE_COLORS = { MICRO: 'gray', TPE: 'blue', PME: 'green', ETI: 'orange', GE: 'red' };

function renderCategorieCard(cat) {
  const el = document.getElementById('pappers-categorie-card');
  if (!el) return;

  if (!cat) { el.innerHTML = ''; return; }

  const tailleCls  = TAILLE_COLORS[cat.taille?.code]  || 'gray';
  const santeCls   = SANTE_COLORS[cat.sante?.code]    || 'gray';
  const coeff      = cat.coefficient_combine ?? '';
  const coeffColor = coeff > 1 ? 'var(--A)' : coeff < 1 ? '#E85D5D' : 'var(--T2)';

  el.innerHTML = `
    <div class="pap-cat-card">
      <div class="pap-cat-row">
        <div class="pap-badge pap-badge--${tailleCls}">
          <span class="pap-badge-label">${esc(cat.taille?.label ?? '')}</span>
          <span class="pap-badge-detail">${esc(cat.taille?.detail ?? '')}</span>
        </div>
        <div class="pap-badge pap-badge--${santeCls}">
          <span class="pap-badge-label">${esc(cat.sante?.label ?? '')}</span>
          <span class="pap-badge-detail">${esc(cat.sante?.detail ?? '')}</span>
        </div>
        <div class="pap-coeff" style="color:${coeffColor}">
          ×&thinsp;${coeff}
        </div>
      </div>
      ${cat.resume ? `<div class="pap-resume">${esc(cat.resume)}</div>` : ''}
    </div>`;
}

// ── Pappers enrichment ────────────────────────────────────
function wireSirenInput() {
  const sirenInput = document.getElementById('pf-siren');
  if (!sirenInput || !PAPPERS_ENABLED) return;

  sirenInput.addEventListener('input', () => {
    const siren = sirenInput.value.replace(/\s/g, '');
    const row = document.getElementById('pappers-enrich-row');
    if (row) row.style.display = /^\d{9}$/.test(siren) ? 'flex' : 'none';
  });
}

async function enrichWithPappers() {
  const sirenInput = document.getElementById('pf-siren');
  if (!sirenInput) return;

  const siren = sirenInput.value.replace(/\s/g, '');
  if (!/^\d{9}$/.test(siren)) return;

  const btn = document.getElementById('btn-pappers');
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-pappers-ico">⏳</span> Enrichissement…';

  try {
    const resp = await fetch(`/api/pappers/${siren}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Erreur ${resp.status}`);
    }
    const data = await resp.json();

    // Mapping champs Pappers → champs formulaire
    const mapping = {
      raison_sociale:      data.raison_sociale,
      forme_juridique:     data.forme_juridique,
      code_naf:            data.code_naf,
      activite_principale: data.activite_principale,
      secteur_activite:    data.secteur_activite,
      ca_annuel:           data.ca_annuel,
      resultat_net:        data.resultat_net,
      effectif:            data.effectif,
      dirigeant_principal: data.dirigeant_principal,
      date_creation:       data.date_creation,
      adresse:             data.adresse,
      site_web:            data.site_web,
    };

    let filled = 0;
    Object.entries(mapping).forEach(([fieldId, value]) => {
      if (value === undefined || value === null || value === '') return;
      const el = document.getElementById('pf-' + fieldId);
      if (!el) return;
      el.value = value;
      el.classList.add('pf-enriched');
      filled++;
    });

    CATEGORIE_PAPPERS = data.categorie || null;
    renderCategorieCard(CATEGORIE_PAPPERS);

    showToast(`Enrichissement Pappers : ${filled} champ${filled > 1 ? 's' : ''} rempli${filled > 1 ? 's' : ''}`);

  } catch (err) {
    showToast('Pappers : ' + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-pappers-ico">🔍</span> Enrichir avec Pappers';
  }
}

// ── Event wiring (delegation) ─────────────────────────────
function wireEvents() {
  const root = document.getElementById('form-root');

  root.addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    const qid    = btn.dataset.qid;
    const val    = btn.dataset.val;

    if (action === 'bool')   setB(qid, val === 'true');
    if (action === 'select') setS(qid, val);
    if (action === 'multi')  toggleM(qid, val);
    if (action === 'adjnum') {
      const input = document.getElementById('nin-' + qid);
      if (input) {
        const cur  = Number(input.value) || 0;
        const next = Math.max(0, cur + Number(val));
        input.value = next;
        setN(qid, next);
      }
    }
  });

  root.addEventListener('input', e => {
    const el     = e.target;
    const action = el.dataset.action;
    const qid    = el.dataset.qid;
    if (!action || !qid) return;

    if (action === 'number') setN(qid, Number(el.value));
    if (action === 'text')   setT(qid, el.value);
    if (action === 'date')   setT(qid, el.value);
  });
}

// ── Answer setters ────────────────────────────────────────
function setB(qid, val) {
  A[qid] = val;
  const qi = document.getElementById('qi-' + qid);
  if (!qi) return;
  const btns = qi.querySelector('.bbrow')
    ? qi.querySelector('.bbrow').querySelectorAll('.bbn')
    : [];
  btns.forEach((b, i) => {
    b.classList.toggle('y', i === 0 &&  val);
    b.classList.toggle('n', i === 1 && !val);
  });
  markOk(qid);
  if (qi.classList.contains('qmod')) {
    qi.classList.toggle('yan', val === true);
    qi.classList.toggle('non', val === false);
  }
  updateVis(qid);
  updateProgress();
}

function setS(qid, val) {
  A[qid] = val;
  const ml = document.getElementById('qi-' + qid);
  if (!ml) return;
  ml.querySelectorAll('.sopt').forEach(b => {
    b.classList.toggle('on', b.dataset.val === val);
  });
  markOk(qid);
  updateVis(qid);
  updateProgress();
}

function toggleM(qid, val) {
  if (!Array.isArray(A[qid])) A[qid] = [];
  const idx = A[qid].indexOf(val);
  if (idx >= 0) {
    A[qid].splice(idx, 1);
  } else {
    A[qid].push(val);
  }
  const ml = document.getElementById('ml-' + qid);
  if (ml) {
    ml.querySelectorAll('.mitem').forEach(item => {
      item.classList.toggle('on', A[qid].includes(item.dataset.val));
    });
  }
  markOk(qid);
  updateVis(qid);
  updateProgress();
}

function setN(qid, val) {
  A[qid] = Number(val);
  markOk(qid);
  updateVis(qid);
  updateProgress();
}

function setT(qid, val) {
  A[qid] = val;
  if (val) markOk(qid);
  updateProgress();
}

function markOk(qid) {
  const qc = document.getElementById('qc-' + qid);
  if (qc) qc.classList.add('ok');
}

// ── Visibility update ─────────────────────────────────────
function updateVis(parentQid) {
  const ans = A[parentQid];
  document.querySelectorAll(`[data-vp="${CSS.escape(parentQid)}"]`).forEach(el => {
    const mode = el.dataset.vm;
    const vv   = el.dataset.vv;
    let show = false;

    if      (!mode || mode === 'true') show = ans === true;
    else if (mode === 'false')         show = ans === false;
    else if (mode === 'value')         show = String(ans) === String(vv);
    else if (mode === 'contains')      show = Array.isArray(ans) && ans.includes(vv);
    else if (mode === 'gt')            show = Number(ans) > Number(vv);
    else if (mode === 'gte')           show = Number(ans) >= Number(vv);
    else if (mode === 'lt')            show = Number(ans) < Number(vv);
    else if (mode === 'lte')           show = Number(ans) <= Number(vv);

    el.style.display = show ? '' : 'none';
    if (!show) clearDescendants(el);
  });
}

function clearDescendants(parentEl) {
  parentEl.querySelectorAll('.qi').forEach(el => {
    const qid = el.dataset.qid;
    if (qid) {
      delete A[qid];
      const qc = document.getElementById('qc-' + qid);
      if (qc) qc.classList.remove('ok');
      el.querySelectorAll('.bbn').forEach(b => b.classList.remove('y', 'n'));
      el.querySelectorAll('.sopt').forEach(b => b.classList.remove('on'));
      el.querySelectorAll('.mitem').forEach(b => b.classList.remove('on'));
      el.classList.remove('yan', 'non');
    }
  });
}

// ── Progress counter ──────────────────────────────────────
function updateProgress() {
  let visible = 0, answered = 0;
  document.querySelectorAll('.qi').forEach(el => {
    const qid = el.dataset.qid;
    if (!qid || isHidden(el)) return;
    visible++;
    const v = A[qid];
    if (v !== undefined && v !== null && v !== '' &&
        !(Array.isArray(v) && v.length === 0)) {
      answered++;
    }
  });
  const txt = document.getElementById('progress-txt');
  if (txt) txt.textContent = `${answered} / ${visible} questions répondues`;
}

// ── Build output payload ──────────────────────────────────
function buildOutput() {
  const societe = {};
  if (FORM_DATA && FORM_DATA.pappers_fields) {
    FORM_DATA.pappers_fields.forEach(f => {
      const el = document.getElementById('pf-' + f.id);
      if (el && el.value !== '') {
        societe[f.id] = f.type === 'number' ? Number(el.value) : el.value;
      }
    });
  }

  const reponses = {};
  const reponses_detail = [];

  document.querySelectorAll('.qi').forEach(el => {
    if (isHidden(el)) return;
    const qid = el.dataset.qid;
    if (!qid || A[qid] === undefined) return;

    reponses[qid] = A[qid];

    const lblEl = el.querySelector('.qlbl');
    const label = lblEl ? lblEl.textContent.trim() : qid;
    reponses_detail.push({ id: qid, label, valeur: A[qid] });
  });

  if (CATEGORIE_PAPPERS) societe.categorie = CATEGORIE_PAPPERS;

  return {
    meta: {
      genere_le: new Date().toISOString(),
      version_questionnaire: FORM_DATA?.meta?.version || '5.0',
      outil: "Formulaire Avant-Vente Ynov'iT Odoo"
    },
    societe,
    reponses,
    reponses_detail
  };
}

// ── Submit form → API ─────────────────────────────────────
async function submitForm() {
  const btn    = document.getElementById('btn-submit');
  const output = buildOutput();

  if (!output.societe.siren && !output.societe.raison_sociale) {
    showToast('Veuillez renseigner au moins le SIREN ou la raison sociale.');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '⏳ Envoi en cours…';

  try {
    const resp = await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(output)
    });

    if (!resp.ok) throw new Error(`Erreur serveur (${resp.status})`);

    const result = await resp.json();
    showToast('Formulaire envoyé — génération lancée');
    showStatus();
    startPolling(result.project_id);

  } catch (err) {
    showToast('Erreur : ' + err.message);
    btn.disabled = false;
    btn.innerHTML = '&#9654; Lancer la génération';
  }
}

// ── Status overlay ────────────────────────────────────────
function showStatus() {
  document.getElementById('status-overlay').classList.add('show');
  document.getElementById('status-icon').textContent  = '⏳';
  document.getElementById('status-title').textContent = 'Génération en cours…';
  document.getElementById('status-msg').textContent   = 'Préparation du pipeline';
  document.getElementById('status-bar').style.width   = '0%';
  document.getElementById('status-pct').textContent   = '0 %';
  document.getElementById('status-files').style.display      = 'none';
  document.getElementById('btn-close-status').style.display  = 'none';
}

function closeStatus() {
  document.getElementById('status-overlay').classList.remove('show');
  const btn = document.getElementById('btn-submit');
  btn.disabled  = false;
  btn.innerHTML = '&#9654; Lancer la génération';
}

const FILE_ICONS = {
  '.docx': '📄', '.xlsx': '📊', '.pdf': '📑',
  '.zip': '📦', '.json': '🔧', '.md': '📝', '.mmd': '📐'
};

function fileIcon(name) {
  const ext = name.substring(name.lastIndexOf('.'));
  return FILE_ICONS[ext] || '📎';
}

function startPolling(projectId) {
  const interval = setInterval(async () => {
    try {
      const resp = await fetch(`/api/status/${projectId}`);
      if (!resp.ok) return;
      const status = await resp.json();

      document.getElementById('status-bar').style.width  = status.progress + '%';
      document.getElementById('status-pct').textContent  = status.progress + ' %';
      document.getElementById('status-msg').textContent  = status.message;

      if (status.state === 'done') {
        clearInterval(interval);
        document.getElementById('status-icon').textContent  = '✅';
        document.getElementById('status-title').textContent = 'Génération terminée';
        document.getElementById('btn-close-status').style.display = '';

        if (status.files && status.files.length > 0) {
          const list = document.getElementById('status-files-list');
          list.innerHTML = status.files.map(f =>
            `<a class="status-file-link" href="/api/download/${projectId}/${encodeURIComponent(f)}" download>
              <span class="status-file-ico">${fileIcon(f)}</span>
              <span>${esc(f)}</span>
            </a>`
          ).join('');
          document.getElementById('status-files').style.display = '';
        }
      }

      if (status.state === 'error') {
        clearInterval(interval);
        document.getElementById('status-icon').textContent  = '❌';
        document.getElementById('status-title').textContent = 'Erreur lors de la génération';
        document.getElementById('btn-close-status').style.display = '';
      }

    } catch (err) {
      // Silently retry on network error
    }
  }, 5000);
}

// ── Helpers ───────────────────────────────────────────────
function isHidden(el) {
  let cur = el;
  while (cur) {
    if (cur.id === 'form-root') break;
    if (cur.style && cur.style.display === 'none') return true;
    cur = cur.parentElement;
  }
  return false;
}

function showToast(msg) {
  const t = document.getElementById('toast');
  document.getElementById('toast-msg').textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3500);
}

function esc(str) {
  return String(str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
}