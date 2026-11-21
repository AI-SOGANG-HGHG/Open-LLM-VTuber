import { bindAuthEvents, restoreSession } from './auth.js';
import { bindPreviewEvents, closePreview, openPreview } from './components/avatar-preview.js';
import { avatar } from './components/card.js';
import { $, charLink, main, now } from './dom.js';
import { avatarAssets, catalogCharacters, studioPresets } from './presets.js';
import { bindRouterEvents, render } from './router.js';
import { bindRuntimeEvents, connectRuntime, disposeRuntime, setConversationFocus } from './runtime-bridge.js';
import { getCharacter, state } from './state.js';
import { loadData, logActivity, persist } from './store.js';
import { bindCharacterDetailEvents, openDelete } from './views/character-detail.js';
import { renderCards } from './views/characters.js';
import { bindConnectionEvents } from './views/connections.js';
import { bindCreateFormEvents, openCreate } from './views/create-form.js';

// Local Studio settings; live conversations use the existing backend inside an embedded runtime.
state.data = loadData();

bindAuthEvents();
bindRuntimeEvents();
bindPreviewEvents();
bindCreateFormEvents();
bindConnectionEvents();

$('#aboutButton').addEventListener('click', () => $('#aboutDialog').showModal());

document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => {
  const dialog = button.closest('dialog');
  if (dialog.id === 'avatarDialog') closePreview();
  dialog.close();
}));
main.addEventListener('input', (event) => {
  if (event.target.id === 'characterSearch') { state.searchQuery = event.target.value; renderCards(); }
  if (event.target.id === 'editExploration') $('#explorationValue').textContent = event.target.value;
  if (event.target.id === 'editStudioPreset') $('#editExploration').disabled = Object.hasOwn(studioPresets, event.target.value);
  if (event.target.id === 'editName' && $('#previewName')) $('#previewName').textContent = event.target.value;
  if (event.target.id === 'editGreeting' && $('#previewGreeting')) $('#previewGreeting').textContent = `“${event.target.value}”`;
  if (event.target.name === 'avatar' && $('#settingsAvatar')) {
    const value = event.target.value;
    const char = getCharacter(event.target.closest('form').dataset.id);
    if (char && Object.hasOwn(avatarAssets, value)) { $('#settingsAvatar').className = `preview-art ${value}`; $('#settingsAvatar').innerHTML = avatar({ ...char, avatar: value }); }
  }
});
main.addEventListener('click', (event) => {
  const filter = event.target.closest('[data-filter]');
  if (filter) { state.collectionFilter = filter.dataset.filter; renderCards(); return; }
  const button = event.target.closest('[data-action]');
  if (!button) return;
  event.preventDefault();
  const char = getCharacter(button.dataset.id);
  const action = button.dataset.action;
  if (action === 'create') openCreate();
  if (action === 'runtime-layout') setConversationFocus(!document.body.classList.contains('conversation-focus'));
  if (action === 'runtime-connect' && char) connectRuntime(char);
  if (action === 'runtime-disconnect') {
    disposeRuntime(); $('#studioFrame').removeAttribute('src'); $('#runtimeStatus').textContent = '연결을 해제했어요. 다시 연결하면 이어서 대화할 수 있어요.';
  }
  if (action === 'preset') openCreate(catalogCharacters().find((preset) => preset.id === button.dataset.id));
  if (action === 'preview') {
    const target = button.dataset.catalog === 'true' ? catalogCharacters().find((preset) => preset.id === button.dataset.id) : char;
    if (target) openPreview(target);
  }
  if (action === 'favorite' && char) {
    char.favorite = !char.favorite; persist(); renderCards();
  }
  if (action === 'suggest') { $('#chatInput').value = button.dataset.message; $('#chatForm').requestSubmit(); }
  if (action === 'duplicate' && char) {
    const copy = { ...structuredClone(char), id: crypto.randomUUID(), name: `${char.name.slice(0, 25)} 복사본`, favorite: false, messages: [], memories: [], createdAt: now(), updatedAt: now() };
    state.data.characters.push(copy); logActivity(copy, '캐릭터 설정 복제'); persist('캐릭터를 복제했어요. 대화와 기억은 새로 시작해요.'); location.hash = charLink(copy);
  }
  if (action === 'delete' && char) openDelete(char);
  if (action === 'remove-memory' && char) {
    char.memories = char.memories.filter((memory) => memory.id !== button.dataset.memory);
    logActivity(char, '직접 등록한 기억 삭제'); persist('기억을 삭제했어요.'); render();
  }
});

bindCharacterDetailEvents(render);
bindRouterEvents();

render();
restoreSession();
