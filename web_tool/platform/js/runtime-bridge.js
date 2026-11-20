import { $, createUuid } from './dom.js';
import { getCharacter, state } from './state.js';
import { logActivity, persist } from './store.js';

let activeRuntime;

function runtimeOrigin() { return location.pathname.startsWith('/web-tool/') ? location.origin : 'http://localhost:12393'; }

export function disposeRuntime() {
  if (!activeRuntime) return;
  clearTimeout(activeRuntime.timeout);
  activeRuntime.frame.contentWindow?.postMessage({ channel: 'persona-studio-runtime', instanceId: activeRuntime.instanceId, type: 'shutdown' }, activeRuntime.origin);
  activeRuntime = null;
}
export function setConversationFocus(enabled) {
  document.body.classList.toggle('conversation-focus', enabled);
  const button = document.querySelector('[data-action="runtime-layout"]');
  if (button) { button.textContent = enabled ? '스튜디오 보기' : '대화에 집중'; button.setAttribute('aria-pressed', String(enabled)); }
}
export function connectRuntime(char) {
  disposeRuntime();
  persist(); // Keep the browser workspace stable before giving the server its history scope.
  const frame = $('#studioFrame');
  const instanceId = createUuid();
  const origin = runtimeOrigin();
  const payload = {
    workspace_id: state.data.workspaceId, character_id: char.id, name: char.name,
    description: char.description,
    avatar: char.avatar, greeting: char.greeting,
    memories: char.memories.slice(-50).map((memory) => memory.text.trim()).filter(Boolean),
    ...(char.studioPreset
      ? { preset_id: char.studioPreset }
      : { persona: char.persona, tone: char.tone, exploration: char.exploration }),
  };
  activeRuntime = { frame, instanceId, origin, charId: char.id, payload, turns: new Set() };
  $('#runtimeStatus').textContent = `${char.name}의 설정으로 대화 서버에 연결 중…`;
  const url = new URL('/web-tool/platform/runtime/', origin);
  url.searchParams.set('studio', '1'); url.searchParams.set('parentOrigin', location.origin); url.searchParams.set('instanceId', instanceId);
  url.searchParams.set('characterId', char.id); url.searchParams.set('avatar', char.avatar);
  frame.src = url.href;
  activeRuntime.timeout = setTimeout(() => {
    if (activeRuntime?.instanceId === instanceId) $('#runtimeStatus').textContent = '대화 서버 연결을 확인해 주세요. 서버 실행 후 다시 연결할 수 있어요.';
  }, 25000);
}

export function bindRuntimeEvents() {
  window.addEventListener('message', (event) => {
    const runtime = activeRuntime;
    const message = event.data;
    if (!runtime || event.source !== runtime.frame.contentWindow || event.origin !== runtime.origin || message?.channel !== 'persona-studio-runtime' || message.instanceId !== runtime.instanceId) return;
    if (message.type === 'ready') {
      runtime.frame.contentWindow.postMessage({ channel: 'persona-studio-runtime', instanceId: runtime.instanceId, type: 'configure', profile: runtime.payload }, runtime.origin);
    } else if (message.type === 'connected') {
      clearTimeout(runtime.timeout);
      if (message.characterId !== runtime.charId || message.avatar !== runtime.payload.avatar || message.name !== runtime.payload.name) {
        disposeRuntime(); $('#studioFrame').removeAttribute('src');
        $('#runtimeStatus').textContent = '선택한 캐릭터와 다른 연결 정보가 도착해 중단했어요. 다시 연결해 주세요.';
        return;
      }
      $('#runtimeStatus').textContent = `${runtime.payload.name} · 실제 대화 연결됨`;
    } else if (message.type === 'disconnected') {
      $('#runtimeStatus').textContent = '서버 연결이 끊겼어요. 대화실에서 자동으로 재연결하고 있어요.';
    } else if (message.type === 'error') {
      clearTimeout(runtime.timeout);
      $('#runtimeStatus').textContent = '캐릭터 설정을 적용하지 못했어요. 서버와 설정을 확인한 뒤 다시 연결해 주세요.';
    } else if (message.type === 'turn-complete' && typeof message.requestId === 'string' && !runtime.turns.has(message.requestId)) {
      runtime.turns.add(message.requestId);
      const char = getCharacter(runtime.charId);
      if (!char) return;
      char.liveTurns = (Number.isSafeInteger(char.liveTurns) ? char.liveTurns : 0) + 1;
      logActivity(char, '스튜디오 음성 대화 진행'); persist();
    }
  });
  window.addEventListener('pagehide', disposeRuntime);
}
