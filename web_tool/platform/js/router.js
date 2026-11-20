import { avatar } from './components/card.js';
import { $, charLink, escapeHtml, main, pageHeading } from './dom.js';
import { disposeRuntime, setConversationFocus } from './runtime-bridge.js';
import { getCharacter, state } from './state.js';
import { renderDetail } from './views/character-detail.js';
import { renderCharacters } from './views/characters.js';
import { renderConnections } from './views/connections.js';
import { renderDiscover } from './views/discover.js';
import { renderRecords } from './views/records.js';

function renderShell() {
  $('#profileName').textContent = state.profile;
  $('#profileAvatar').textContent = state.profile.slice(0, 1).toUpperCase();
  $('#navCount').textContent = state.data.characters.length;
  $('#quickChats').innerHTML = state.data.characters.slice(0, 3).map((char) => `<a class="shortcut" href="${charLink(char, 'chat')}"><span class="shortcut-avatar ${char.avatar}">${avatar(char)}</span>${escapeHtml(char.name)}<span aria-hidden="true">↗</span></a>`).join('');
}
export function render() {
  setConversationFocus(false);
  disposeRuntime();
  $('#loginView').hidden = Boolean(state.profile);
  $('#workspaceView').hidden = !state.profile;
  if (!state.profile) return;
  renderShell();
  const route = location.hash.slice(1).split('/');
  const section = ['discover', 'connections', 'records'].includes(route[0]) ? route[0] : 'characters';
  const sectionNames = { characters: '내 캐릭터', discover: '둘러보기', connections: '연결 허브', records: '활동 기록' };
  document.querySelectorAll('[data-nav]').forEach((link) => { link.classList.toggle('active', link.dataset.nav === section); if (link.dataset.nav === section) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); });
  $('#breadcrumb').textContent = `스튜디오 / ${sectionNames[section]}`;
  if (route[0] === 'character') {
    let id;
    try { id = decodeURIComponent(route[1]); } catch { id = ''; }
    const char = getCharacter(id);
    if (char) renderDetail(char, route[2]);
    else main.innerHTML = '<div class="empty-state">이 캐릭터를 찾을 수 없어요.<br /><a class="button secondary" style="margin-top:18px" href="#characters">내 캐릭터로 돌아가기</a></div>';
  } else if (section === 'discover') renderDiscover();
  else if (section === 'connections') main.innerHTML = pageHeading('BEYOND THE CONVERSATION', '캐릭터의 다음 무대.', '대화에서 방송, 게임까지. 같은 캐릭터와 더 넓은 세상으로.') + renderConnections();
  else if (section === 'records') main.innerHTML = pageHeading('STUDIO ACTIVITY', '우리가 만들어 온 이야기.', '캐릭터의 시작부터 지금까지, 스튜디오의 활동을 확인하세요.') + renderRecords();
  else renderCharacters();
  document.title = `${sectionNames[section]} · Persona Studio`;
}

export function bindRouterEvents() {
  window.addEventListener('hashchange', () => { render(); if (state.profile) { main.focus({ preventScroll: true }); window.scrollTo(0, 0); } });
}
