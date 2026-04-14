/* ── State ── */
const jobs = new Map(); // id -> job object

/* ── DOM refs ── */
const urlInput    = document.getElementById('urlInput');
const formatSel   = document.getElementById('formatSelect');
const qualitySel  = document.getElementById('qualitySelect');
const qualityGrp  = document.getElementById('qualityGroup');
const addBtn      = document.getElementById('addBtn');
const startAllBtn = document.getElementById('startAllBtn');
const jobList     = document.getElementById('jobList');
const emptyState  = document.getElementById('emptyState');
const addError    = document.getElementById('addError');
const queueStats  = document.getElementById('queueStats');
const clearDoneBtn= document.getElementById('clearDoneBtn');

/* ── Format selector hides quality when not mp4 ── */
formatSel.addEventListener('change', () => {
  qualityGrp.style.display = formatSel.value === 'mp4' ? '' : 'none';
});

/* ── SSE connection ── */
function connectSSE() {
  const es = new EventSource('/api/events');

  es.onmessage = (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }

    if (msg.type === 'ping') return;

    if (msg.type === 'update') {
      jobs.set(msg.job.id, msg.job);
      renderJob(msg.job.id);
      updateStats();
    }
    if (msg.type === 'remove') {
      jobs.delete(msg.id);
      const el = document.getElementById(`job-${msg.id}`);
      if (el) el.remove();
      updateStats();
      checkEmpty();
    }
  };

  es.onerror = () => {
    setTimeout(connectSSE, 3000); // reconnect
    es.close();
  };
}
connectSSE();

/* ── Add jobs ── */
addBtn.addEventListener('click', addJobs);
urlInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.ctrlKey) addJobs();
});

async function addJobs() {
  const raw = urlInput.value.trim();
  if (!raw) { showError('Please paste at least one URL.'); return; }

  const urls = raw.split('\n').map(s => s.trim()).filter(Boolean);
  if (!urls.length) { showError('No valid URLs found.'); return; }

  clearError();
  addBtn.disabled = true;

  try {
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        urls,
        format: formatSel.value,
        quality: qualitySel.value,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    urlInput.value = '';
  } catch (err) {
    showError('Failed to add jobs: ' + err.message);
  } finally {
    addBtn.disabled = false;
  }
}

/* ── Start all ── */
startAllBtn.addEventListener('click', async () => {
  startAllBtn.disabled = true;
  try {
    await fetch('/api/start-all', { method: 'POST' });
  } finally {
    startAllBtn.disabled = false;
  }
});

/* ── Clear completed ── */
clearDoneBtn.addEventListener('click', async () => {
  const doneIds = [...jobs.values()]
    .filter(j => j.status === 'done')
    .map(j => j.id);
  await Promise.all(doneIds.map(id =>
    fetch(`/api/jobs/${id}`, { method: 'DELETE' })
  ));
});

/* ── Render ── */
function renderJob(id) {
  const job = jobs.get(id);
  if (!job) return;

  let el = document.getElementById(`job-${id}`);
  const isNew = !el;

  if (isNew) {
    el = document.createElement('div');
    el.id = `job-${id}`;
  }

  el.className = `job-card status-${job.status}`;

  const titleDisplay = job.title === job.url
    ? truncate(job.url, 72)
    : job.title;

  const progressHTML = (job.status === 'downloading' || job.status === 'done')
    ? `<div class="progress-wrap">
        <div class="progress-bar"><div class="progress-fill" style="width:${job.progress}%"></div></div>
        <span class="progress-pct">${job.progress}%</span>
       </div>`
    : '';

  const metaHTML = job.status === 'downloading' && (job.speed || job.eta)
    ? `<span class="job-meta">${[job.speed, job.eta].filter(Boolean).join(' · ')}</span>`
    : '';

  const errorHTML = job.status === 'error' && job.error
    ? `<div class="job-error">${escHtml(job.error)}</div>`
    : '';

  const downloadBtn = job.status === 'done' && job.filename
    ? `<a class="btn btn-primary btn-sm" href="/api/download/${encodeURIComponent(job.filename)}" download>&#8595; Save</a>`
    : '';

  const startBtn = job.status === 'pending' || job.status === 'error'
    ? `<button class="btn btn-secondary btn-sm" onclick="startJob('${id}')">&#9654; Start</button>`
    : '';

  const spinner = job.status === 'downloading'
    ? `<span class="job-meta">&#8987;</span>`
    : '';

  el.innerHTML = `
    <div class="job-main">
      <div class="job-title">${escHtml(titleDisplay)}</div>
      <div class="job-url">${escHtml(job.url)}</div>
      <div class="job-status-row">
        <span class="badge badge-${job.status}">${job.status}</span>
        <span class="job-meta">${job.format.toUpperCase()}${job.quality !== 'best' && job.format === 'mp4' ? ' · ' + job.quality + 'p' : ''}</span>
        ${metaHTML}
        ${spinner}
      </div>
      ${progressHTML}
      ${errorHTML}
    </div>
    <div class="job-actions">
      ${downloadBtn}
      ${startBtn}
      <button class="btn btn-ghost btn-icon" onclick="removeJob('${id}')" title="Remove">&#x2715;</button>
    </div>
  `;

  if (isNew) {
    if (emptyState) emptyState.style.display = 'none';
    jobList.prepend(el);
  }

  checkEmpty();
}

async function startJob(id) {
  await fetch(`/api/jobs/${id}/start`, { method: 'POST' });
}

async function removeJob(id) {
  await fetch(`/api/jobs/${id}`, { method: 'DELETE' });
}

function checkEmpty() {
  const hasJobs = jobs.size > 0;
  if (emptyState) emptyState.style.display = hasJobs ? 'none' : '';
}

function updateStats() {
  const all   = [...jobs.values()];
  const done  = all.filter(j => j.status === 'done').length;
  const dl    = all.filter(j => j.status === 'downloading').length;
  const pend  = all.filter(j => j.status === 'pending').length;
  const err   = all.filter(j => j.status === 'error').length;

  const parts = [];
  if (dl)   parts.push(`${dl} downloading`);
  if (pend) parts.push(`${pend} pending`);
  if (done) parts.push(`${done} done`);
  if (err)  parts.push(`${err} error`);
  queueStats.textContent = parts.join(' · ');
}

/* ── Helpers ── */
function showError(msg) {
  addError.textContent = msg;
  addError.classList.remove('hidden');
}
function clearError() {
  addError.textContent = '';
  addError.classList.add('hidden');
}
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function truncate(s, n) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}
