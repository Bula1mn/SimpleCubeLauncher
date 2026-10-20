'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const S = {
  config: {}, instances: [], javas: [], running: {}, tasks: [], version: '',
  freeGb: null, latest: {},
  page: 'home', tab: 'versions',
  versions: [], versionsLoaded: false, versionsLoading: false,
  versionType: 'release', versionLimit: 120, versionSearch: '', filterSig: '',
  search: { kind: 'mod', hits: [], total: 0, offset: 0, loading: false, q: '', gv: '', loader: 'fabric' },
  activeId: localStorage.getItem('activeInstance') || '',
  initialized: false, seenTasks: new Set(), logs: {},
  modalProject: null, pendingInstalls: new Set(), homeSig: '',
  sourceDraft: null, loaderTouched: false,
};

const PAGE_META = {
  home: ['主页', '选择一个实例，开始你的世界'],
  download: ['下载', '原版、Mod、光影与整合包，都在这里'],
  settings: ['设置', '调整 Java、内存与下载源'],
};

const LOADER_NAMES = { fabric: 'Fabric', forge: 'Forge', neoforge: 'NeoForge', quilt: 'Quilt', vanilla: '原版' };

function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function fmtBytes(n) {
  n = Number(n) || 0;
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
  return (n / 1024 / 1024 / 1024).toFixed(2) + ' GB';
}

function fmtSpeed(n) {
  return fmtBytes(n) + '/s';
}

function fmtNum(n) {
  n = Number(n) || 0;
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function fmtAgo(seconds) {
  const ts = Number(seconds) || 0;
  if (!ts) return '从未启动';
  const diff = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (diff < 60) return '刚刚';
  if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
  if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
  return Math.floor(diff / 86400) + ' 天前';
}

function fmtDuration(startedAt) {
  const start = Number(startedAt) || (Date.now() / 1000);
  const diff = Math.max(0, Math.floor(Date.now() / 1000 - start));
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  const s = diff % 60;
  if (h) return h + ' 小时 ' + m + ' 分';
  if (m) return m + ' 分 ' + s + ' 秒';
  return s + ' 秒';
}

function loaderName(loader) {
  if (!loader) return '原版';
  const type = typeof loader === 'string' ? loader : loader.type;
  return LOADER_NAMES[type] || type || '原版';
}

function activeInstance() {
  return S.instances.find((item) => item.id === S.activeId) || S.instances[0] || null;
}

function setActive(id) {
  S.activeId = id;
  S.homeSig = '';
  try { localStorage.setItem('activeInstance', id); } catch (e) {}
  renderInstances();
}

async function api(path, options = {}) {
  const opts = Object.assign({}, options);
  if (opts.body !== undefined && typeof opts.body !== 'string') {
    opts.body = JSON.stringify(opts.body);
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
  }
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch (err) { data = { error: text }; }
  if (!res.ok) throw new Error(data.error || ('请求失败（' + res.status + '）'));
  return data;
}

// ---------------- 状态 ----------------
async function refreshState(first) {
  const st = await api('/api/state');
  applyState(st, first);
}

function applyState(st, first) {
  S.config = st.config || {};
  S.instances = st.instances || [];
  S.javas = st.javas || [];
  S.running = st.running || {};
  S.tasks = st.tasks || [];
  S.version = st.version || '';
  S.freeGb = st.free_gb;
  S.baseDir = st.base_dir;
  if (S.sourceDraft == null) S.sourceDraft = S.config.download_source || 'auto';
  if (!S.activeId || !S.instances.some((item) => item.id === S.activeId)) {
    S.activeId = S.instances.length ? S.instances[0].id : '';
    try { localStorage.setItem('activeInstance', S.activeId); } catch (e) {}
  }
  if (first) {
    S.initialized = true;
    (st.tasks || []).forEach((task) => S.seenTasks.add(task.id));
  } else {
    handleTasks(st.tasks || []);
  }
  renderHeader();
  renderTasks();
  if (S.page === 'home') {
    renderInstances();
    renderRunning();
  }
}

async function poll() {
  try {
    const st = await api('/api/state');
    applyState(st, false);
  } catch (err) {
    // 本地服务短暂不可用时忽略
  }
}

function renderHeader() {
  const javaPill = $('#pill-java');
  if (S.javas.length) {
    const best = S.javas[0];
    javaPill.textContent = 'Java ' + best.major + ' · ' + S.javas.length + ' 个运行时';
  } else {
    javaPill.textContent = '未检测到 Java';
  }
  $('#pill-disk').textContent = S.freeGb == null ? '磁盘 —' : '剩余 ' + S.freeGb + ' GB';
  const runningCount = Object.values(S.running).filter((item) => item.alive).length;
  $('#side-status-text').textContent = runningCount ? runningCount + ' 个实例运行中' : '就绪';
  const dot = $('#side-dot');
  dot.className = 'dot ' + (runningCount ? 'live' : 'ok');
  $('#side-version').textContent = 'v' + (S.version || '0.1.0');
}

// ---------------- 主页 ----------------
function renderInstances() {
  const grid = $('#instance-grid');
  const count = $('#instance-count');
  count.textContent = S.instances.length ? (S.instances.length + ' 个实例') : '还没有实例';
  const sig = JSON.stringify(S.instances.map((item) => [
    item.id, item.name, item.version_id, item.mc_version,
    item.loader && item.loader.version, item.installing, item.java_ok,
    !!(S.running[item.id] && S.running[item.id].alive),
  ]));
  if (sig === S.homeSig) return;
  S.homeSig = sig;
  if (!S.instances.length) {
    grid.innerHTML =
      '<div class="empty" style="grid-column:1/-1">' +
        '<div class="empty-icon"><svg class="ic"><use href="#i-cube"/></svg></div>' +
        '<h3>还没有任何实例</h3>' +
        '<p>先下载一个游戏版本，或者直接安装一个整合包。</p>' +
        '<div class="empty-actions">' +
          '<button class="btn primary" data-action="go-download" data-tab="versions">安装原版</button>' +
          '<button class="btn" data-action="go-download" data-tab="modpack">浏览整合包</button>' +
        '</div>' +
      '</div>';
    return;
  }
  grid.innerHTML = S.instances.map(instanceCard).join('');
}

function instanceCard(inst) {
  const selected = inst.id === S.activeId;
  const runningInfo = S.running[inst.id] || {};
  const running = !!runningInfo.alive;
  const loader = inst.loader ? loaderName(inst.loader) : '原版';
  const letter = esc(String(inst.name || 'M').trim().charAt(0).toUpperCase() || 'M');
  const icon = inst.icon
    ? '<span>' + letter + '</span><img src="' + esc(inst.icon) + '" alt="" onerror="this.remove()">'
    : '<span>' + letter + '</span>';
  const javaWarn = inst.java_ok === false
    ? '<span class="chip warn">需要 Java ' + esc(inst.required_java) + '</span>'
    : '';
  const sub = inst.installing
    ? '<span class="spinner" style="width:12px;height:12px;border-width:2px"></span> 正在安装…'
    : '上次启动：' + fmtAgo(inst.last_played);
  const launchBtn = running
    ? '<button class="btn small" disabled>运行中</button>'
    : '<button class="btn small primary" data-action="launch" data-id="' + esc(inst.id) + '"' +
      (inst.installing ? ' disabled' : '') + '><svg class="ic"><use href="#i-play"/></svg>启动</button>';
  return '<article class="instance-card' + (selected ? ' selected' : '') + (running ? ' running' : '') +
    '" data-action="select-instance" data-id="' + esc(inst.id) + '">' +
    '<div class="instance-icon">' + icon + '</div>' +
    '<div class="instance-main">' +
      '<div class="instance-name">' + esc(inst.name) + '</div>' +
      '<div class="instance-meta"><span class="chip">' + esc(inst.mc_version || '') + '</span>' +
      '<span class="chip loader">' + esc(loader) + '</span>' + javaWarn + '</div>' +
      '<div class="instance-sub">' + sub + '</div>' +
    '</div>' +
    '<div class="instance-actions">' + launchBtn +
      '<button class="icon-btn" data-action="instance-menu" data-id="' + esc(inst.id) + '" title="更多">' +
      '<svg class="ic"><use href="#i-more"/></svg></button>' +
    '</div>' +
  '</article>';
}

function renderRunning() {
  const panel = $('#running-panel');
  const entries = Object.entries(S.running).filter(([, info]) => info.alive);
  if (!entries.length) {
    panel.innerHTML = '';
    return;
  }
  panel.innerHTML = entries.map(([id, info]) => {
    const inst = S.instances.find((item) => item.id === id);
    const name = inst ? inst.name : id;
    const log = S.logs[id] || '正在等待游戏输出…';
    return '<div class="running-card">' +
      '<div class="running-head"><span class="dot live"></span><strong>' + esc(name) + '</strong>' +
        '<span class="muted">PID ' + esc(info.pid || '—') + ' · 已运行 ' + fmtDuration(info.started_at) + '</span>' +
        '<button class="btn small" data-action="view-full-log" data-id="' + esc(id) + '">完整日志</button>' +
        '<button class="btn small" data-action="kill-game" data-id="' + esc(id) + '">结束游戏</button>' +
      '</div>' +
      '<pre class="log-view">' + esc(log) + '</pre>' +
    '</div>';
  }).join('');
  $$('.log-view', panel).forEach((el) => { el.scrollTop = el.scrollHeight; });
}

async function fetchLogs() {
  const entries = Object.entries(S.running).filter(([, info]) => info.alive);
  if (!entries.length) return;
  for (const [id] of entries) {
    try {
      const data = await api('/api/logs?instance_id=' + encodeURIComponent(id));
      S.logs[id] = data.log || '';
    } catch (err) {}
  }
  if (S.page === 'home') renderRunning();
}

// ---------------- 任务 ----------------
function renderTasks() {
  const dock = $('#task-dock');
  const active = S.tasks.filter((task) => task.status === 'running');
  if (!active.length) {
    dock.innerHTML = '';
    dock.classList.add('hidden');
    return;
  }
  dock.classList.remove('hidden');
  dock.innerHTML = active.map((task) => {
    const hasTotal = task.total > 0;
    const pct = hasTotal ? Math.min(100, Math.round((task.current / task.total) * 100)) : 0;
    const stage = task.stage + (task.message ? ' · ' + task.message : '');
    return '<div class="task">' +
      '<div class="task-head"><span>' + esc(task.title) + '</span>' +
        '<button data-action="cancel-task" data-id="' + esc(task.id) + '" title="取消">×</button></div>' +
      '<div class="task-stage">' + esc(stage) + '</div>' +
      '<div class="bar' + (hasTotal ? '' : ' indeterminate') + '"><i style="width:' + (hasTotal ? pct : 34) + '%"></i></div>' +
      '<div class="task-foot"><span>' + (hasTotal ? fmtBytes(task.current) + ' / ' + fmtBytes(task.total) : fmtBytes(task.current)) +
        '</span><span>' + (task.speed ? fmtSpeed(task.speed) : '') + '</span></div>' +
    '</div>';
  }).join('');
}

function handleTasks(tasks) {
  for (const task of tasks) {
    if (task.status === 'running' || S.seenTasks.has(task.id)) continue;
    S.seenTasks.add(task.id);
    if (task.status === 'error') {
      S.pendingInstalls.clear();
      toast('任务失败：' + task.title + '\n' + (task.error || ''), 'error', 8000);
    } else if (task.status === 'success') {
      if (task.kind === 'install') {
        S.pendingInstalls.clear();
        if (S.page === 'download') loadVersions(true);
      }
      if (task.kind === 'launch') toast('游戏已启动', 'ok');
      else if (task.kind === 'modpack') toast('整合包安装完成，已创建实例', 'ok', 6000);
      else toast('完成：' + task.title, 'ok');
    } else if (task.status === 'canceled') {
      S.pendingInstalls.clear();
      toast('已取消：' + task.title, 'error');
    }
  }
}

// ---------------- 页面 ----------------
function setPage(page) {
  S.page = page;
  $$('.nav-item[data-page]').forEach((btn) => btn.classList.toggle('active', btn.dataset.page === page));
  $$('.page').forEach((el) => el.classList.toggle('hidden', el.id !== 'page-' + page));
  const meta = PAGE_META[page] || PAGE_META.home;
  $('#page-title').textContent = meta[0];
  $('#page-subtitle').textContent = meta[1];
  if (page === 'home') {
    S.homeSig = '';
    renderInstances();
    renderRunning();
  } else if (page === 'download') {
    if (!S.versionsLoaded) loadVersions(false);
    ensureFilters();
    if (S.tab === 'versions') renderVersionList();
    else runSearch(true);
  } else if (page === 'settings') {
    fillSettings();
  }
}

function setTab(tab) {
  S.tab = tab;
  $$('#download-tabs .tab').forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === tab));
  $('#tab-versions').classList.toggle('hidden', tab !== 'versions');
  $('#tab-content').classList.toggle('hidden', tab === 'versions');
  if (tab === 'versions') {
    renderVersionList();
    return;
  }
  const loaderSel = $('#search-loader');
  loaderSel.style.display = tab === 'shader' ? 'none' : '';
  if (tab === 'shader') {
    loaderSel.value = 'all';
  } else if (!S.loaderTouched) {
    loaderSel.value = tab === 'modpack' ? 'all' : ((activeInstance() && activeInstance().loader && activeInstance().loader.type) || 'fabric');
  }
  S.search.kind = tab;
  runSearch(true);
}

// ---------------- 版本下载 ----------------
async function loadVersions(force) {
  if (S.versionsLoading) return;
  S.versionsLoading = true;
  try {
    const data = await api('/api/versions?type=' + S.versionType + (force ? '&refresh=1' : ''));
    S.versions = data.versions || [];
    S.latest = data.latest || {};
    S.versionsLoaded = true;
    if (force) S.pendingInstalls.clear();
    renderVersionList();
    ensureFilters();
  } catch (err) {
    toast('获取版本列表失败：' + err.message, 'error', 6000);
  } finally {
    S.versionsLoading = false;
  }
}

function renderVersionList() {
  const container = $('#version-list');
  if (!S.versionsLoaded) {
    container.innerHTML = '<div class="version-row"><div class="muted">正在获取版本清单…</div></div>';
    return;
  }
  const keyword = S.versionSearch.trim().toLowerCase();
  const matched = S.versions.filter((item) => !keyword || String(item.id).toLowerCase().includes(keyword));
  const shown = matched.slice(0, S.versionLimit);
  if (!shown.length) {
    container.innerHTML = '<div class="version-row"><div class="muted">没有匹配的版本</div></div>';
    $('#version-more').classList.add('hidden');
    return;
  }
  container.innerHTML = shown.map((item) => {
    const hasInstance = S.instances.some((inst) => inst.version_id === item.id && !inst.loader);
    const pending = S.pendingInstalls.has(item.id);
    const tagClass = item.type === 'release' ? 'release' : 'snapshot';
    const tagText = item.type === 'release' ? '正式版' : '快照';
    const side = hasInstance
      ? '<span class="badge"><svg class="ic"><use href="#i-check"/></svg>已安装</span>'
      : '<button class="btn small primary" data-action="install-version" data-id="' + esc(item.id) + '"' +
        (pending ? ' disabled' : '') + '>' + (pending ? '安装中…' : '安装') + '</button>';
    return '<div class="version-row">' +
      '<div class="version-name">' + esc(item.id) + '<span class="tag ' + tagClass + '">' + tagText + '</span></div>' +
      '<div class="version-date">' + fmtDate(item.releaseTime) + '</div>' +
      '<div class="version-side">' + side + '</div>' +
    '</div>';
  }).join('');
  $('#version-more').classList.toggle('hidden', matched.length <= S.versionLimit);
}

async function installVersion(versionId) {
  S.pendingInstalls.add(versionId);
  renderVersionList();
  try {
    const data = await api('/api/install/vanilla', { method: 'POST', body: { version_id: versionId } });
    if (data.existing) {
      toast('这个版本已经有原版实例了', 'ok');
      S.pendingInstalls.delete(versionId);
    } else {
      toast('已开始安装 Minecraft ' + versionId + '，进度见右下角', 'ok');
    }
    poll();
  } catch (err) {
    S.pendingInstalls.delete(versionId);
    toast('安装失败：' + err.message, 'error', 6000);
  }
  renderVersionList();
}

// ---------------- 搜索 ----------------
function ensureFilters(force) {
  const select = $('#search-game-version');
  if (!select) return;
  const options = [];
  const push = (value) => { if (value && options.indexOf(value) < 0) options.push(value); };
  S.instances.forEach((inst) => push(inst.mc_version));
  S.versions.filter((item) => item.type === 'release').slice(0, 60).forEach((item) => push(item.id));
  if (S.latest && S.latest.release) push(S.latest.release);
  const sig = options.join('|');
  if (force || sig !== S.filterSig) {
    S.filterSig = sig;
    const previous = select.value || S.search.gv;
    select.innerHTML = options.map((value) => '<option value="' + esc(value) + '">' + esc(value) + '</option>').join('');
    const inst = activeInstance();
    const preferred = previous || (inst && inst.mc_version) || options[0] || '';
    if (options.indexOf(preferred) >= 0) select.value = preferred;
    S.search.gv = select.value;
  }
  const loader = $('#search-loader');
  if (!S.loaderTouched) {
    if (S.tab === 'modpack' || S.tab === 'shader') loader.value = 'all';
    else {
      const inst = activeInstance();
      loader.value = (inst && inst.loader && inst.loader.type) || 'fabric';
    }
  }
}

async function runSearch(reset) {
  if (S.tab === 'versions') return;
  if (S.search.loading) return;
  if (reset) {
    S.search.offset = 0;
    S.search.hits = [];
  }
  const gameVersion = $('#search-game-version').value || '';
  const loaderSel = $('#search-loader');
  const loader = S.tab === 'shader' ? '' : loaderSel.value;
  const query = $('#content-search').value.trim();
  S.search.q = query;
  S.search.gv = gameVersion;
  S.search.loader = loader;
  S.search.loading = true;
  $('#search-meta').textContent = '正在搜索…';
  if (reset) {
    $('#search-results').innerHTML = Array.from({ length: 4 }, () => '<div class="result-skeleton"></div>').join('');
  }
  try {
    const url = '/api/search?kind=' + encodeURIComponent(S.tab) +
      '&q=' + encodeURIComponent(query) +
      '&game_version=' + encodeURIComponent(gameVersion) +
      '&loader=' + encodeURIComponent(loader) +
      '&limit=20&offset=' + S.search.offset;
    const data = await api(url);
    S.search.hits = reset ? (data.hits || []) : S.search.hits.concat(data.hits || []);
    S.search.total = data.total || 0;
    S.search.offset += (data.hits || []).length;
    renderSearchResults();
  } catch (err) {
    $('#search-meta').textContent = '搜索失败';
    $('#search-results').innerHTML = '<div class="empty" style="grid-column:1/-1"><h3>搜索失败</h3><p>' + esc(err.message) + '</p></div>';
  } finally {
    S.search.loading = false;
  }
}

function renderSearchResults() {
  const results = $('#search-results');
  const meta = $('#search-meta');
  const hits = S.search.hits;
  if (!hits.length) {
    meta.textContent = '没有找到内容';
    results.innerHTML = '<div class="empty" style="grid-column:1/-1"><h3>没有找到内容</h3><p>换个关键词，或放宽版本 / 加载器筛选。</p></div>';
    $('#search-more').classList.add('hidden');
    return;
  }
  meta.textContent = '找到 ' + S.search.total + ' 个结果，已显示 ' + hits.length + ' 个';
  results.innerHTML = hits.map((hit) => {
    const letter = esc(String(hit.title || '?').charAt(0).toUpperCase());
    const icon = hit.icon_url
      ? '<span>' + letter + '</span><img src="' + esc(hit.icon_url) + '" alt="" loading="lazy" onerror="this.remove()">'
      : '<span>' + letter + '</span>';
    return '<article class="result-card" data-action="open-project" data-id="' + esc(hit.project_id) + '">' +
      '<div class="result-icon">' + icon + '</div>' +
      '<div class="result-body">' +
        '<div class="result-title">' + esc(hit.title) + '</div>' +
        '<div class="result-desc">' + esc(hit.description) + '</div>' +
        '<div class="result-meta"><span>' + fmtNum(hit.downloads) + ' 次下载</span>' +
          '<span>' + esc(hit.author || '') + '</span></div>' +
      '</div>' +
      '<button class="btn small primary" data-action="open-project" data-id="' + esc(hit.project_id) + '">安装</button>' +
    '</article>';
  }).join('');
  $('#search-more').classList.toggle('hidden', hits.length >= S.search.total);
}

// ---------------- 项目详情 ----------------
async function openProject(projectId) {
  const kind = S.tab;
  const gv = $('#search-game-version').value || '';
  const loaderSel = $('#search-loader');
  const loader = (kind === 'shader' || kind === 'modpack') ? '' : loaderSel.value;
  showModal('<div class="modal-head" style="align-items:center"><div class="spinner"></div><div><div class="modal-title">正在加载项目…</div><div class="modal-sub">从 Modrinth 获取详情</div></div></div>');
  try {
    let url = '/api/project?id=' + encodeURIComponent(projectId);
    if (kind !== 'modpack') {
      url += '&game_version=' + encodeURIComponent(gv) + '&loader=' + encodeURIComponent(loader);
    }
    const data = await api(url);
    S.modalProject = { kind, project: data.project, versions: data.versions || [] };
    renderProjectModal();
  } catch (err) {
    showModal('<div class="modal-head"><div><div class="modal-title">加载失败</div><div class="modal-sub">' + esc(err.message) + '</div></div>' +
      '<button class="modal-close" data-action="close-modal"><svg class="ic"><use href="#i-close"/></svg></button></div>' +
      '<div class="modal-actions"><button class="btn" data-action="close-modal">关闭</button></div>');
  }
}

function mdLite(text, limit) {
  let value = String(text || '');
  value = value.replace(/!\[[^\]]*\]\([^)]*\)/g, '');
  value = value.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  value = value.replace(/[\x60]{3}[\s\S]*?[\x60]{3}/g, '');
  value = value.replace(/[#>*\x60_~]/g, '');
  value = value.replace(/\r/g, '');
  if (value.length > limit) value = value.slice(0, limit) + '…';
  return esc(value);
}

function renderProjectModal() {
  const ctx = S.modalProject;
  if (!ctx) return;
  const kind = ctx.kind;
  const project = ctx.project;
  const versions = ctx.versions;
  const letter = esc(String(project.title || '?').charAt(0));
  const icon = project.icon_url
    ? '<span>' + letter + '</span><img src="' + esc(project.icon_url) + '" alt="" onerror="this.remove()">'
    : '<span>' + letter + '</span>';
  const typeName = kind === 'shader' ? '光影' : (kind === 'modpack' ? '整合包' : 'Mod');
  const versionOptions = versions.map((item) => {
    const gvs = (item.game_versions || []).slice(-3).join(' / ');
    const loaders = (item.loaders || []).slice(0, 3).join(' / ');
    return '<option value="' + esc(item.id) + '">' + esc(item.version_number) + ' · ' + esc(gvs) +
      (loaders ? ' · ' + esc(loaders) : '') + '</option>';
  }).join('');
  let extra = '';
  if (kind === 'mod' || kind === 'shader') {
    if (!S.instances.length) {
      extra = '<div class="note warn">还没有实例。请先在主页新建一个实例，再安装内容。</div>';
    } else {
      const selected = S.instances.some((inst) => inst.id === S.activeId) ? S.activeId : S.instances[0].id;
      const options = S.instances.map((inst) =>
        '<option value="' + esc(inst.id) + '"' + (inst.id === selected ? ' selected' : '') + '>' +
          esc(inst.name) + '（' + esc(inst.mc_version) + ' · ' + esc(loaderName(inst.loader)) + '）</option>'
      ).join('');
      extra = '<div class="field"><label>安装到实例</label><select class="input" id="modal-instance">' + options + '</select></div>';
      if (kind === 'shader') {
        extra += '<div class="note">光影需要 Iris 或 OptiFine 才能生效。建议在 Fabric 实例中先安装 Iris Mod。</div>';
      }
      extra += '<div id="modal-hint"></div>';
    }
  } else {
    extra = '<div class="field"><label>新实例名称</label>' +
      '<input class="input" id="modal-pack-name" value="' + esc(project.title || '整合包') + '" maxlength="48"></div>' +
      '<div class="note">将自动创建独立实例，并安装整合包声明的游戏版本与加载器。</div>';
  }
  const html =
    '<div class="modal-head">' +
      '<div class="result-icon">' + icon + '</div>' +
      '<div><div class="modal-title">' + esc(project.title) + '</div>' +
        '<div class="modal-sub">' + typeName + ' · ' + fmtNum(project.downloads) + ' 次下载 · ' + esc(project.author || '') + '</div></div>' +
      '<button class="modal-close" data-action="close-modal"><svg class="ic"><use href="#i-close"/></svg></button>' +
    '</div>' +
    '<div class="modal-body">' +
      '<p class="project-desc">' + mdLite(project.body || project.description || '暂无简介', 1500) + '</p>' +
      '<div class="field"><label>选择版本</label><select class="input" id="modal-version"' + (versions.length ? '' : ' disabled') + '>' +
        (versionOptions || '<option>没有兼容的版本</option>') + '</select></div>' +
      extra +
    '</div>' +
    '<div class="modal-actions">' +
      '<button class="btn" data-action="close-modal">取消</button>' +
      '<button class="btn primary" id="modal-install-btn" data-action="modal-install"' + (versions.length ? '' : ' disabled') + '>开始安装</button>' +
    '</div>';
  showModal(html);
  const instanceSelect = $('#modal-instance');
  if (instanceSelect) {
    instanceSelect.addEventListener('change', updateModalHint);
    updateModalHint();
  }
}

function updateModalHint() {
  if (!S.modalProject) return;
  const select = $('#modal-instance');
  const button = $('#modal-install-btn');
  const hint = $('#modal-hint');
  if (!select || !button) return;
  const inst = S.instances.find((item) => item.id === select.value);
  if (inst && S.modalProject.kind === 'mod' && !inst.loader) {
    button.disabled = true;
    if (hint) hint.innerHTML = '<div class="note warn">该实例是原版，无法加载 Mod。请选择带有 Fabric / Forge / NeoForge 的实例。</div>';
  } else {
    button.disabled = false;
    if (hint) hint.innerHTML = '';
  }
}

async function modalInstall() {
  const ctx = S.modalProject;
  if (!ctx) return;
  const versionId = $('#modal-version') ? $('#modal-version').value : '';
  const button = $('#modal-install-btn');
  if (button) button.disabled = true;
  try {
    if (ctx.kind === 'modpack') {
      const name = $('#modal-pack-name') ? $('#modal-pack-name').value.trim() : '';
      await api('/api/install/modpack', { method: 'POST', body: { project_id: ctx.project.id, version_id: versionId, name } });
      toast('已开始安装整合包，安装完成后会自动创建实例', 'ok', 6000);
    } else {
      const instanceId = $('#modal-instance') ? $('#modal-instance').value : '';
      if (!instanceId) throw new Error('请先创建实例');
      const endpoint = ctx.kind === 'shader' ? '/api/install/shader' : '/api/install/mod';
      await api(endpoint, { method: 'POST', body: { project_id: ctx.project.id, version_id: versionId, instance_id: instanceId } });
      toast('已开始下载，进度见右下角', 'ok');
    }
    closeModal();
    poll();
  } catch (err) {
    toast('安装失败：' + err.message, 'error', 6000);
    if (button) button.disabled = false;
  }
}

// ---------------- 弹窗 ----------------
function showModal(html) {
  const root = $('#modal-root');
  root.innerHTML = '<div class="modal-backdrop" data-action="close-modal"></div><div class="modal">' + html + '</div>';
  root.classList.remove('hidden');
}

function closeModal() {
  const root = $('#modal-root');
  root.classList.add('hidden');
  root.innerHTML = '';
  S.modalProject = null;
}

function newInstanceModal() {
  const versions = S.versions.filter((item) => item.type === 'release').slice(0, 100);
  const selected = (S.latest && S.latest.release) || (versions[0] && versions[0].id) || '';
  const options = versions.map((item) => '<option value="' + esc(item.id) + '"' + (item.id === selected ? ' selected' : '') + '>' + esc(item.id) + '</option>').join('');
  const html =
    '<div class="modal-head"><div><div class="modal-title">新建实例</div><div class="modal-sub">选择游戏版本与加载器</div></div>' +
      '<button class="modal-close" data-action="close-modal"><svg class="ic"><use href="#i-close"/></svg></button></div>' +
    '<div class="modal-body">' +
      '<div class="field"><label>实例名称</label><input class="input" id="new-instance-name" maxlength="48" value="我的世界"></div>' +
      '<div class="field"><label>游戏版本</label><select class="input" id="new-instance-version">' + (options || '<option>请先加载版本列表</option>') + '</select></div>' +
      '<div class="field"><label>加载器</label><select class="input" id="new-instance-loader">' +
        '<option value="vanilla">原版</option><option value="fabric" selected>Fabric</option>' +
        '<option value="forge">Forge</option><option value="neoforge">NeoForge</option>' +
      '</select></div>' +
      '<div class="note">加载器会自动选择最新稳定版本。Forge / NeoForge 需要较长时间下载安装器。</div>' +
    '</div>' +
    '<div class="modal-actions"><button class="btn" data-action="close-modal">取消</button>' +
      '<button class="btn primary" data-action="create-instance">创建并安装</button></div>';
  showModal(html);
}

async function createInstance() {
  const version = $('#new-instance-version').value;
  const loader = $('#new-instance-loader').value;
  const name = $('#new-instance-name').value.trim() || version;
  if (!version) { toast('请选择一个游戏版本', 'error'); return; }
  try {
    await api('/api/instance/create', { method: 'POST', body: { mc_version: version, loader, name } });
    closeModal();
    setPage('home');
    toast('已开始创建实例，安装进度见右下角', 'ok', 5000);
    poll();
  } catch (err) {
    toast('创建失败：' + err.message, 'error', 6000);
  }
}

function instanceMenu(id) {
  const inst = S.instances.find((item) => item.id === id);
  if (!inst) return;
  const html =
    '<div class="modal-head"><div><div class="modal-title">' + esc(inst.name) + '</div>' +
      '<div class="modal-sub">' + esc(inst.mc_version) + ' · ' + esc(loaderName(inst.loader)) + '</div></div>' +
      '<button class="modal-close" data-action="close-modal"><svg class="ic"><use href="#i-close"/></svg></button></div>' +
    '<div class="modal-body"><div class="menu-list">' +
      '<button class="btn" data-action="open-folder" data-id="' + esc(id) + '"><svg class="ic"><use href="#i-folder"/></svg>打开游戏文件夹</button>' +
      '<button class="btn" data-action="view-full-log" data-id="' + esc(id) + '"><svg class="ic"><use href="#i-cube"/></svg>查看启动日志</button>' +
      '<button class="btn danger" data-action="delete-instance" data-id="' + esc(id) + '"><svg class="ic"><use href="#i-trash"/></svg>删除这个实例</button>' +
    '</div></div>';
  showModal(html);
}

function deleteInstanceModal(id) {
  const inst = S.instances.find((item) => item.id === id);
  if (!inst) return;
  const html =
    '<div class="modal-head"><div><div class="modal-title">删除实例</div>' +
      '<div class="modal-sub">' + esc(inst.name) + '</div></div>' +
      '<button class="modal-close" data-action="close-modal"><svg class="ic"><use href="#i-close"/></svg></button></div>' +
    '<div class="modal-body"><p class="project-desc">只会删除这个实例的 Mod、光影与存档，不会删除已下载的游戏本体和资源库。此操作无法撤销。</p></div>' +
    '<div class="modal-actions"><button class="btn" data-action="close-modal">取消</button>' +
      '<button class="btn danger" data-action="confirm-delete" data-id="' + esc(id) + '">确认删除</button></div>';
  showModal(html);
}

async function confirmDelete(id) {
  try {
    await api('/api/instance/delete', { method: 'POST', body: { id } });
    closeModal();
    toast('实例已删除', 'ok');
    poll();
  } catch (err) {
    toast('删除失败：' + err.message, 'error');
  }
}

async function openFolder(id) {
  const inst = S.instances.find((item) => item.id === id);
  if (!inst) return;
  try {
    await api('/api/open-folder', { method: 'POST', body: { path: inst.dir } });
  } catch (err) {
    toast('打开失败：' + err.message, 'error');
  }
}

async function viewFullLog(id) {
  try {
    const data = await api('/api/logs?instance_id=' + encodeURIComponent(id));
    showModal('<div class="modal-head"><div><div class="modal-title">启动日志</div><div class="modal-sub">最近一次启动</div></div>' +
      '<button class="modal-close" data-action="close-modal"><svg class="ic"><use href="#i-close"/></svg></button></div>' +
      '<div class="modal-body"><pre class="log-view" style="max-height:60vh">' + esc(data.log || '（暂无日志）') + '</pre></div>' +
      '<div class="modal-actions"><button class="btn" data-action="close-modal">关闭</button></div>');
  } catch (err) {
    toast('读取日志失败：' + err.message, 'error');
  }
}

async function launchGame(id) {
  setActive(id);
  try {
    await api('/api/launch', { method: 'POST', body: { instance_id: id } });
    toast('正在启动游戏…', 'ok');
    poll();
  } catch (err) {
    toast('启动失败：' + err.message, 'error', 8000);
  }
}

// ---------------- 设置 ----------------
function fillSettings() {
  const config = S.config;
  if (!config || !config.game_root) return;
  $('#set-game-root').value = config.game_root || '';
  const select = $('#set-java-select');
  const options = ['<option value="">自动选择（推荐）</option>'];
  S.javas.forEach((java) => {
    options.push('<option value="' + esc(java.path) + '">Java ' + java.major + ' · ' + esc(java.path) + '</option>');
  });
  select.innerHTML = options.join('');
  const configured = String(config.java_path || '');
  const known = S.javas.some((java) => java.path.toLowerCase() === configured.toLowerCase());
  select.value = known ? configured : '';
  $('#set-java-custom').value = known ? '' : configured;
  const memory = Number(config.memory_mb) || 4096;
  $('#set-memory').value = memory;
  $('#set-memory-out').value = memory + ' MB';
  $('#set-player').value = config.player_name || 'Steve';
  $('#set-width').value = config.width || 960;
  $('#set-height').value = config.height || 540;
  const source = S.sourceDraft || config.download_source || 'auto';
  $$('#set-source .seg').forEach((btn) => btn.classList.toggle('active', btn.dataset.source === source));
}

async function saveSettings() {
  const javaSelect = $('#set-java-select').value;
  const custom = $('#set-java-custom').value.trim();
  const body = {
    game_root: $('#set-game-root').value.trim(),
    java_path: javaSelect || custom,
    memory_mb: Number($('#set-memory').value) || 4096,
    download_source: S.sourceDraft || 'auto',
    player_name: $('#set-player').value.trim() || 'Steve',
    width: Number($('#set-width').value) || 960,
    height: Number($('#set-height').value) || 540,
  };
  try {
    const data = await api('/api/config', { method: 'POST', body });
    S.config = data.config;
    S.sourceDraft = data.config.download_source;
    fillSettings();
    $('#settings-hint').textContent = '已保存';
    setTimeout(() => { $('#settings-hint').textContent = ''; }, 2500);
    toast('设置已保存', 'ok');
    poll();
  } catch (err) {
    toast('保存失败：' + err.message, 'error', 6000);
  }
}

// ---------------- 交互 ----------------
function bindEvents() {
  document.addEventListener('click', onClick);
  document.addEventListener('change', onChange);
  document.addEventListener('input', onInput);
}

async function onClick(event) {
  const nav = event.target.closest('.nav-item[data-page]');
  if (nav) {
    setPage(nav.dataset.page);
    return;
  }
  const tab = event.target.closest('#download-tabs .tab');
  if (tab) {
    setTab(tab.dataset.tab);
    return;
  }
  const typeSeg = event.target.closest('#version-type .seg');
  if (typeSeg) {
    S.versionType = typeSeg.dataset.type;
    $$('#version-type .seg').forEach((btn) => btn.classList.toggle('active', btn === typeSeg));
    S.versionsLoaded = false;
    S.versionLimit = 120;
    loadVersions(false);
    return;
  }
  const sourceSeg = event.target.closest('#set-source .seg');
  if (sourceSeg) {
    S.sourceDraft = sourceSeg.dataset.source;
    $$('#set-source .seg').forEach((btn) => btn.classList.toggle('active', btn === sourceSeg));
    return;
  }
  const target = event.target.closest('[data-action]');
  if (!target) return;
  const action = target.dataset.action;
  const id = target.dataset.id;
  switch (action) {
    case 'select-instance':
      setActive(id);
      break;
    case 'launch':
      launchGame(id);
      break;
    case 'kill-game':
      try {
        await api('/api/kill', { method: 'POST', body: { instance_id: id } });
        toast('已结束游戏', 'ok');
      } catch (err) {
        toast('结束失败：' + err.message, 'error');
      }
      poll();
      break;
    case 'new-instance':
      newInstanceModal();
      break;
    case 'go-download':
      setPage('download');
      setTab(target.dataset.tab || 'versions');
      break;
    case 'refresh':
      await refreshState(false);
      if (S.page === 'download') loadVersions(true);
      toast('已刷新', 'ok');
      break;
    case 'shutdown':
      shutdown();
      break;
    case 'install-version':
      installVersion(id);
      break;
    case 'reload-versions':
      toast('正在刷新版本清单…', 'ok');
      loadVersions(true);
      break;
    case 'version-more':
      S.versionLimit += 120;
      renderVersionList();
      break;
    case 'search-more':
      runSearch(false);
      break;
    case 'open-project':
      openProject(id);
      break;
    case 'modal-install':
      modalInstall();
      break;
    case 'create-instance':
      createInstance();
      break;
    case 'instance-menu':
      instanceMenu(id);
      break;
    case 'open-folder':
      openFolder(id);
      break;
    case 'delete-instance':
      deleteInstanceModal(id);
      break;
    case 'confirm-delete':
      confirmDelete(id);
      break;
    case 'view-full-log':
      viewFullLog(id);
      break;
    case 'cancel-task':
      try { await api('/api/task/cancel', { method: 'POST', body: { task_id: id } }); } catch (err) {}
      poll();
      break;
    case 'save-settings':
      saveSettings();
      break;
    case 'open-game-root':
      try { await api('/api/open-folder', { method: 'POST', body: { path: S.config.game_root } }); }
      catch (err) { toast('打开失败：' + err.message, 'error'); }
      break;
    case 'close-modal':
      closeModal();
      break;
    default:
      break;
  }
}

function onChange(event) {
  const el = event.target;
  if (el.id === 'search-game-version') {
    S.search.gv = el.value;
    runSearch(true);
  } else if (el.id === 'search-loader') {
    S.loaderTouched = true;
    S.search.loader = el.value;
    runSearch(true);
  } else if (el.id === 'set-java-select') {
    if (el.value) $('#set-java-custom').value = '';
  }
}

let searchTimer = null;
function onInput(event) {
  const el = event.target;
  if (el.id === 'content-search') {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => runSearch(true), 450);
  } else if (el.id === 'version-search') {
    S.versionSearch = el.value;
    S.versionLimit = 120;
    renderVersionList();
  } else if (el.id === 'set-memory') {
    $('#set-memory-out').value = el.value + ' MB';
  } else if (el.id === 'set-java-custom') {
    if (el.value.trim()) $('#set-java-select').value = '';
  }
}

async function shutdown() {
  if (!window.confirm('确定要退出方块启动器吗？正在运行的游戏不会受到影响。')) return;
  try { await api('/api/shutdown', { method: 'POST', body: {} }); } catch (err) {}
  document.body.innerHTML = '<div style="height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;background:#f4f6f2;color:#4c5b51;font-family:Microsoft YaHei UI,sans-serif">' +
    '<div style="font-size:18px;font-weight:600">启动器已退出</div><div style="font-size:13px;color:#7b877f">可以关闭这个窗口了</div></div>';
}

// ---------------- Toast ----------------
function toast(message, type, duration) {
  const root = $('#toast-root');
  if (!root) return;
  const el = document.createElement('div');
  el.className = 'toast ' + (type || '');
  el.textContent = message;
  root.appendChild(el);
  const ms = duration || 4200;
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(-6px)';
    el.style.transition = 'all .2s ease';
    setTimeout(() => el.remove(), 220);
  }, ms);
}

// ---------------- 启动 ----------------
async function init() {
  bindEvents();
  try {
    await refreshState(true);
  } catch (err) {
    toast('无法连接本地服务：' + err.message, 'error', 8000);
  }
  setPage('home');
  loadVersions(false);
  setInterval(poll, 900);
  setInterval(fetchLogs, 2200);
}

init();
