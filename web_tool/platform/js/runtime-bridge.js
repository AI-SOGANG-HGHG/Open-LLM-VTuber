import { agentError, ensureAgent, serverProfiles } from './agents.js';
import { $, LIVE_CHAT_ACTIVITY } from './dom.js';
import { getCharacter, state } from './state.js';
import { logActivity, persist } from './store.js';

let activeRuntime;
let connectEpoch = 0;

export function disposeRuntime() {
  connectEpoch++;
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
export async function connectRuntime(char) {
  disposeRuntime();
  const ticket = connectEpoch;
  const frame = $('#studioFrame');
  if (!serverProfiles) {
    $('#runtimeStatus').textContent = '실시간 대화는 서버의 /web-tool/platform/에서 연결할 수 있어요.';
    return;
  }
  try {
    await ensureAgent(char);
  } catch (error) {
    if (ticket === connectEpoch && frame.isConnected) $('#runtimeStatus').textContent = agentError(error);
    return;
  }
  if (ticket !== connectEpoch || !frame.isConnected) return;
  const instanceId = crypto.randomUUID();
  const origin = location.origin;
  const payload = {
    workspace_id: state.data.workspaceId, character_id: char.id, name: char.name,
    description: char.description,
    avatar: char.avatar, greeting: char.greeting,
    agent_id: char.agentId,
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
      if (message.agentId !== runtime.payload.agent_id || message.characterId !== runtime.charId || message.avatar !== runtime.payload.avatar || message.name !== runtime.payload.name) {
        disposeRuntime(); $('#studioFrame').removeAttribute('src');
        $('#runtimeStatus').textContent = '다른 캐릭터로 연결되어 대화를 멈췄어요. 다시 연결해 주세요.';
        return;
      }
      $('#runtimeStatus').textContent = `${runtime.payload.name} · 대화할 수 있어요`;
    } else if (message.type === 'disconnected') {
      $('#runtimeStatus').textContent = '연결이 끊겨 다시 연결하고 있어요.';
    } else if (message.type === 'error') {
      clearTimeout(runtime.timeout);
      $('#runtimeStatus').textContent = '캐릭터 설정을 적용하지 못했어요. 서버와 설정을 확인한 뒤 다시 연결해 주세요.';
    } else if (message.type === 'turn-complete' && typeof message.requestId === 'string' && !runtime.turns.has(message.requestId)) {
      runtime.turns.add(message.requestId);
      const char = getCharacter(runtime.charId);
      if (!char) return;
      char.liveTurns = (Number.isSafeInteger(char.liveTurns) ? char.liveTurns : 0) + 1;
      logActivity(char, LIVE_CHAT_ACTIVITY); persist();
    }
  });
  window.addEventListener('pagehide', disposeRuntime);
}
