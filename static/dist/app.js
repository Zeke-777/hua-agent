// ===========================================================================
// State
// ===========================================================================
const S = {
  mode: 'auth',        // 'auth' | 'welcome' | 'chat'
  isRegister: false,
  token: localStorage.getItem('token') || '',
  username: localStorage.getItem('username') || '',
  sessions: [],
  currentSessionId: null,
  messages: [],        // current session messages
  busy: false,
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// ===========================================================================
// API
// ===========================================================================
function headers(hasBody = true) {
  const h = { Authorization: `Bearer ${S.token}` };
  if (hasBody) h['Content-Type'] = 'application/json';
  return h;
}

async function api(method, path, body) {
  const opts = { method, headers: headers(!!body) };
  if (body) {
    opts.body = (body instanceof FormData) ? body : JSON.stringify(body);
    if (body instanceof FormData) delete opts.headers['Content-Type'];
  }
  try {
    const res = await fetch(path, opts);
    const data = await res.json();
    return { status: res.status, ...data };
  } catch (e) {
    return { status: 0, ok: false, detail: '网络错误，请稍后重试' };
  }
}

async function loadSessions() {
  const r = await api('GET', '/api/sessions');
  if (r.ok) S.sessions = r.sessions;
  renderSidebar();
}

// ===========================================================================
// Render
// ===========================================================================
function render() {
  if (S.mode === 'auth') {
    $('#auth-panel').style.display = 'flex';
    $('#main-panel').style.display = 'none';
    $('#auth-error').style.display = 'none';
    $('#auth-submit').textContent = S.isRegister ? '注册' : '登录';
    $('#auth-toggle').textContent = S.isRegister ? '已有账号？去登录' : '还没有账号？去注册';
  } else {
    $('#auth-panel').style.display = 'none';
    $('#main-panel').style.display = 'flex';
    $('#sidebar-user').textContent = S.username;
    renderSidebar();

    if (S.currentSessionId) {
      $('#welcome-screen').style.display = 'none';
      $('#messages').style.display = '';
      $('#input-area').style.display = 'flex';
      renderMessages();
    } else {
      $('#welcome-screen').style.display = 'flex';
      $('#messages').style.display = 'none';
      $('#input-area').style.display = 'none';
      $('#welcome-input').value = '';
    }
  }
}

function renderSidebar() {
  const el = $('#session-list');
  el.innerHTML = S.sessions.map(s => `
    <div class="session-item${s.session_id === S.currentSessionId ? ' active' : ''}"
         data-sid="${escHtml(s.session_id)}" data-name="${escHtml(s.name)}">
      <span class="icon">${s.image_url ? '🖼' : '🌺'}</span>
      <span>${escHtml(s.name)}</span>
    </div>
  `).join('') || '<div style="padding:16px;text-align:center;color:#888;font-size:13px">暂无会话</div>';

  el.querySelectorAll('.session-item').forEach(item => {
    item.addEventListener('click', () => switchSession(item.dataset.sid));
  });
}

function renderMessages() {
  const el = $('#messages');
  el.innerHTML = S.messages.map(m => {
    if (m.type === 'user') return `<div class="msg user">${escHtml(m.content)}</div>`;
    if (m.type === 'flower_card') return renderFlowerCard(m.data);
    if (m.type === 'system') return `<div class="msg system${m.error ? ' error' : ''}">${escHtml(m.content)}</div>`;
    return `<div class="msg ai">${DOMPurify.sanitize(marked.parse(m.content, {breaks: true}))}</div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

function renderFlowerCard(d) {
  const fields = ['形态结构','植物分类','生长习性','花期规律','气味与特征','繁殖方式','使用价值','文化寓意'];
  const hasContent = fields.some(f => d[f] && d[f].trim());
  const grid = fields.map(f => {
    const val = hasContent ? (d[f] || '—') : '暂时搜索不到资料';
    return `<div class="field"><span class="label">${f}：</span><span class="value">${escHtml(val)}</span></div>`;
  }).join('');
  const sources = d['参考来源'] ? `<div class="sources">${escHtml(d['参考来源'])}</div>` : '';
  const img = d._image_url ? `<img src="${escHtml(d._image_url)}" alt="${escHtml(d['名称'] || '')}">` : '';
  return `
    <div class="flower-card">
      <h3>${escHtml(d['名称'] || '')} — 研究报告</h3>
      ${img}
      <div class="grid">${grid}</div>
      ${sources}
    </div>
  `;
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ===========================================================================
// Actions
// ===========================================================================

// Auth
async function handleAuth() {
  const username = $('#auth-username').value.trim();
  const password = $('#auth-password').value.trim();
  if (!username || !password) {
    showAuthError('请填写用户名和密码');
    return;
  }
  if (!/^[a-zA-Z0-9_\-\.@]+$/.test(username)) {
    showAuthError('用户名只能包含英文字母、数字或 _ - . @');
    return;
  }
  if (username.length > 32) {
    showAuthError('用户名最多32位');
    return;
  }
  if (password.length < 6) {
    showAuthError('密码至少6位');
    return;
  }
  setBusy(true);
  const path = S.isRegister ? '/api/auth/register' : '/api/auth/login';
  const r = await api('POST', path, { username, password });

  if (S.isRegister && r.ok) {
    $('#auth-error').style.display = 'block';
    $('#auth-error').className = 'success';
    $('#auth-error').textContent = r.message || '注册成功，请登录';
    S.isRegister = false;
    render();
  } else if (!S.isRegister && r.ok) {
    S.token = r.token;
    S.username = r.username;
    localStorage.setItem('token', S.token);
    localStorage.setItem('username', S.username);
    S.mode = 'welcome';
    S.currentSessionId = null;
    S.messages = [];
    await loadSessions();
    render();
  } else {
    showAuthError(r.detail || '操作失败');
  }
  setBusy(false);
}

function showAuthError(msg) {
  const el = $('#auth-error');
  el.style.display = 'block';
  el.className = 'error';
  el.textContent = msg;
}

async function handleLogout() {
  await api('POST', '/api/auth/logout');
  localStorage.removeItem('token');
  localStorage.removeItem('username');
  S.token = '';
  S.username = '';
  S.mode = 'auth';
  S.isRegister = false;
  S.sessions = [];
  S.currentSessionId = null;
  S.messages = [];
  render();
}

// Research
async function handleResearch(flowerName) {
  if (S.busy || !flowerName.trim()) return;
  setBusy(true);

  const flower_name = flowerName.trim();
  S.messages = [{ type: 'user', content: flower_name }];
  S.currentSessionId = null;
  renderMessages();
  $('#welcome-screen').style.display = 'none';
  $('#messages').style.display = '';
  $('#input-area').style.display = 'none';

  const r = await api('POST', '/api/research', { flower_name });
  if (r.ok) {
    S.currentSessionId = r.session_id;
    if (r.flower_info) {
      r.flower_info._image_url = r.image_url;
      S.messages.push({ type: 'flower_card', data: r.flower_info });
    }
    if (r.stage === 1) {
      S.messages.push({ type: 'ai', content: '以上是自动生成的' + flower_name + '研究报告。你可以继续追问任何问题。' });
    }
    await loadSessions();
    $('#input-area').style.display = 'flex';
  } else {
    S.messages.push({ type: 'system', content: r.detail || '研究失败', error: true });
    S.currentSessionId = null;
  }
  render();
  setBusy(false);
}

// Chat
async function handleChat(message) {
  if (S.busy || !message.trim() || !S.currentSessionId) return;
  setBusy(true);
  S.messages.push({ type: 'user', content: message.trim() });
  render();

  const r = await api('POST', '/api/chat', { message: message.trim(), session_id: S.currentSessionId });
  if (r.ok) {
    S.messages.push({ type: 'ai', content: r.reply });
  } else {
    S.messages.push({ type: 'system', content: r.detail || '聊天失败', error: true });
  }
  render();
  setBusy(false);
}

// Upload
async function handleUpload(file, flowerName) {
  if (S.busy || !file) return;
  setBusy(true);

  S.messages = [{ type: 'system', content: '正在上传图片并识别花卉...' }];
  S.currentSessionId = null;
  renderMessages();
  $('#welcome-screen').style.display = 'none';
  $('#messages').style.display = '';
  $('#input-area').style.display = 'none';

  const form = new FormData();
  form.append('file', file);
  if (flowerName.trim()) form.append('flower_name', flowerName.trim());

  const r = await api('POST', '/api/upload', form);
  if (r.ok) {
    S.currentSessionId = r.session_id;
    S.messages = [];
    if (r.flower_info) {
      r.flower_info._image_url = r.image_url;
      S.messages.push({ type: 'flower_card', data: r.flower_info });
    }
    S.messages.push({ type: 'ai', content: '以上是基于图片生成的' + (r.flower_name || '花卉') + '研究报告。你可以继续追问任何问题。' });
    await loadSessions();
    $('#input-area').style.display = 'flex';
  } else {
    S.messages.push({ type: 'system', content: r.detail || '上传失败', error: true });
    S.currentSessionId = null;
  }
  render();
  setBusy(false);
}

// Session switching
async function switchSession(sid) {
  if (S.busy || sid === S.currentSessionId) return;
  setBusy(true);
  S.currentSessionId = sid;

  // Load cached flower_info from session list
  const session = S.sessions.find(s => s.session_id === sid);
  S.messages = [];
  if (session && session.flower_info) {
    session.flower_info._image_url = session.image_url;
    S.messages.push({ type: 'flower_card', data: session.flower_info });
    S.messages.push({ type: 'system', content: '已切换到会话：' + session.name });
  } else {
    S.messages.push({ type: 'system', content: '已切换到会话：' + (session ? session.name : sid) });
  }
  render();
  setBusy(false);
}

// New session
function newSession() {
  if (S.busy) return;
  S.currentSessionId = null;
  S.messages = [];
  render();
}

function setBusy(v) {
  S.busy = v;
  $$('button').forEach(b => { if (b.id !== 'logout-btn') b.disabled = v; });
  $$('input[type=text], input[type=password]').forEach(i => i.disabled = v);
}

// ===========================================================================
// Event bindings
// ===========================================================================
$('#auth-submit').addEventListener('click', handleAuth);
$('#auth-toggle').addEventListener('click', () => { S.isRegister = !S.isRegister; render(); });
$('#logout-btn').addEventListener('click', handleLogout);
$('#new-session-btn').addEventListener('click', newSession);

$('#welcome-btn').addEventListener('click', () => handleResearch($('#welcome-input').value));
$('#welcome-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') handleResearch($('#welcome-input').value); });

$('#chat-send-btn').addEventListener('click', () => {
  const input = $('#chat-input');
  handleChat(input.value);
  input.value = '';
});
$('#chat-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const input = $('#chat-input');
    handleChat(input.value);
    input.value = '';
  }
});

// Auth form enter key
$('#auth-username').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('#auth-password').focus(); });
$('#auth-password').addEventListener('keydown', (e) => { if (e.key === 'Enter') handleAuth(); });

// File upload
$('#file-input').addEventListener('change', () => {
  const file = $('#file-input').files[0];
  if (file) {
    $('#upload-name-group').hidden = false;
  }
});
$('#upload-btn').addEventListener('click', () => {
  const file = $('#file-input').files[0];
  if (file) {
    handleUpload(file, $('#upload-flower-name').value);
    $('#upload-name-group').hidden = true;
    $('#file-input').value = '';
    $('#upload-flower-name').value = '';
  }
});

// ===========================================================================
// Init
// ===========================================================================
if (S.token && S.username) {
  S.mode = 'welcome';
  $('#auth-panel').style.display = 'none';
  $('#main-panel').style.display = 'flex';
  $('#sidebar-user').textContent = S.username;
  loadSessions().then(() => render());
} else {
  render();
}
