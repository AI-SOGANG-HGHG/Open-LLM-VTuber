import { agentError, restoreAgents } from './agents.js';
import { closePreview } from './components/avatar-preview.js';
import { $, toast } from './dom.js';
import { render } from './router.js';
import { state } from './state.js';
import { persist } from './store.js';

const SESSION_KEY = 'persona-studio.demo-session.v1';
const SESSION_CHECK_TIMEOUT_MS = 8_000;

let authMode = 'checking';
let authBusy = false;
let authChannel;

function loginError(message = '') {
  $('#loginError').textContent = message;
  $('#loginError').hidden = !message;
}
function configureLogin() {
  const demo = authMode === 'demo';
  $('#loginTitle').textContent = demo ? '스튜디오 미리보기' : '팀 계정으로 로그인';
  $('#loginUsernameLabel').textContent = demo ? '어떻게 불러드릴까요?' : '아이디';
  $('#loginUsername').placeholder = demo ? '이름 또는 닉네임' : '팀 계정 아이디';
  $('#loginUsername').autocomplete = demo ? 'nickname' : 'username';
  $('#loginPasswordField').hidden = demo;
  $('#loginPassword').required = !demo;
  $('#loginSubmit').disabled = authBusy;
  $('#loginSubmit').formNoValidate = authMode === 'error';
  $('#loginSubmit').textContent = authBusy ? (authMode === 'team' ? '로그인 중…' : '연결 확인 중…') : demo ? '스튜디오 둘러보기' : authMode === 'error' ? '다시 연결' : '로그인';
}
function clearProfile() {
  state.profile = '';
  closePreview();
  document.querySelectorAll('dialog[open]').forEach((dialog) => dialog.close());
  $('#loginPassword').value = '';
  history.replaceState(null, '', location.pathname + location.search);
  render();
  document.title = 'Persona Studio';
}
async function enterProfile(username) {
  try {
    await restoreAgents();
  } catch (error) {
    toast(agentError(error), true);
  }
  state.profile = username;
  $('#loginPassword').value = '';
  if (!location.hash) history.replaceState(null, '', location.pathname + location.search + '#characters');
  render();
  if (state.needsMigration || state.storageWarning) persist();
}
async function fetchSessionStatus() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SESSION_CHECK_TIMEOUT_MS);
  try {
    const response = await fetch('/auth/session', {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!response.ok) throw Error('Session check failed');
    return await response.json();
  } finally {
    clearTimeout(timeout);
  }
}

export async function restoreSession() {
  if (authBusy) return;
  authBusy = true;
  if (!state.profile) {
    $('#loginSubmit').disabled = true;
    $('#loginSubmit').textContent = '연결 확인 중…';
  }
  try {
    const status = location.pathname.startsWith('/web-tool/')
      ? await fetchSessionStatus()
      : { enabled: false };
    authMode = status.enabled ? 'team' : 'demo';
    loginError();
    if (authMode === 'demo') {
      let nickname = '';
      try { nickname = sessionStorage.getItem(SESSION_KEY) || ''; } catch { /* Page-local preview. */ }
      if (nickname && state.profile !== nickname) await enterProfile(nickname);
      else if (!nickname) render();
    } else if (status.authenticated && typeof status.username === 'string') {
      if (state.profile !== status.username) await enterProfile(status.username);
    } else if (state.profile) clearProfile();
  } catch {
    authMode = 'error';
    clearProfile();
    loginError('서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.');
  } finally {
    authBusy = false;
    configureLogin();
  }
}

export function bindAuthEvents() {
  try { authChannel = new BroadcastChannel('persona-studio-auth'); } catch { /* Focus checks still synchronize tabs. */ }
  if (authChannel) authChannel.onmessage = () => { if (authMode !== 'demo') restoreSession(); };
  window.addEventListener('focus', () => { if (authMode !== 'demo') restoreSession(); });
  window.addEventListener('pageshow', (event) => { if (event.persisted && authMode !== 'demo') restoreSession(); });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && authMode !== 'demo') restoreSession(); });
  setInterval(() => { if (authMode !== 'demo' && document.visibilityState === 'visible') restoreSession(); }, 60000);
  $('#loginForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (authBusy) return;
    if (authMode === 'checking' || authMode === 'error') { await restoreSession(); return; }
    const username = $('#loginUsername').value.trim();
    if (!username) return;
    if (authMode === 'demo') {
      try { sessionStorage.setItem(SESSION_KEY, username); } catch { /* This preview stays page-local. */ }
      await enterProfile(username); return;
    }
    authBusy = true; configureLogin(); loginError();
    $('#loginForm').setAttribute('aria-busy', 'true');
    try {
      const response = await fetch('/auth/login', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password: $('#loginPassword').value }),
      });
      if (!response.ok) {
        loginError(response.status === 429 ? '로그인 시도가 많아요. 1분 후 다시 시도해 주세요.' : response.status === 401 ? '아이디 또는 비밀번호를 확인해 주세요.' : '로그인하지 못했어요. 잠시 후 다시 시도해 주세요.');
        return;
      }
      const session = await response.json();
      await enterProfile(session.username);
      authChannel?.postMessage('refresh');
    } catch { loginError('서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.'); }
    finally { authBusy = false; configureLogin(); $('#loginForm').setAttribute('aria-busy', 'false'); }
  });
  $('#logoutButton').addEventListener('click', async () => {
    if (authBusy) return;
    authBusy = true;
    try {
      if (authMode === 'team') {
        const response = await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
        if (!response.ok) throw Error('Unavailable');
        authChannel?.postMessage('logout');
      } else { try { sessionStorage.removeItem(SESSION_KEY); } catch { /* Page-local preview. */ } }
      clearProfile(); loginError(); $('#loginUsername').focus();
    } catch { toast('로그아웃하지 못했어요. 다시 시도해 주세요.', true); }
    finally { authBusy = false; configureLogin(); }
  });
}
