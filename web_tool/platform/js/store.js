import { createRandomId } from '../../shared/random-id.js';
import { $, now, toast } from './dom.js';
import { avatarAssets, catalogCharacters, catalogProfiles, defaultGreeting, demoCharacters, presets, studioPresets } from './presets.js';
import { state } from './state.js';

const DATA_KEY = 'persona-studio.demo.v1';
const CATALOG_VERSION = 3;

function initialData() {
  return {
    version: 1,
    catalogVersion: CATALOG_VERSION,
    workspaceId: createRandomId(),
    characters: [...demoCharacters(), ...catalogCharacters()],
    activities: [],
  };
}

function updateDefaultCopy(char) {
  const catalog = catalogProfiles.find(({ id }) => id === char.id);
  if (catalog?.previousDescription === char.description) {
    char.description = catalog.description;
    state.needsMigration = true;
  }
  if (typeof char.greeting !== 'string'
    || char.greeting === `안녕! 나는 ${char.name}야. 오늘은 어떤 이야기를 해볼까?`
    || char.greeting === `안녕하세요. ${char.name}입니다. 오늘 함께할 일을 이야기해 주세요.`) {
    char.greeting = defaultGreeting(char);
    state.needsMigration = true;
  } else if (catalog?.previousGreeting === char.greeting) {
    char.greeting = catalog.greeting;
    state.needsMigration = true;
  }
}
export function loadData() {
  try {
    const raw = localStorage.getItem(DATA_KEY);
    if (!raw) return initialData();
    const data = JSON.parse(raw);
    if (data.version !== 1 || !Array.isArray(data.characters) || !Array.isArray(data.activities)) throw Error('Invalid data');
    const ids = new Set();
    for (const char of data.characters) {
      if (!char || typeof char.id !== 'string' || ids.has(char.id)
        || !['name', 'description', 'persona', 'tone'].every((key) => typeof char[key] === 'string')
        || !Object.hasOwn(presets, char.template) || !Object.hasOwn(avatarAssets, char.avatar)
        || !Number.isFinite(char.exploration) || char.exploration < 0 || char.exploration > 100
        || !Array.isArray(char.messages) || !Array.isArray(char.memories)
        || !char.messages.every((msg) => msg && ['user', 'assistant'].includes(msg.role) && typeof msg.content === 'string')
        || !char.memories.every((memory) => memory && ['id', 'text', 'at'].every((key) => typeof memory[key] === 'string'))) throw Error('Invalid character');
      ids.add(char.id);
      updateDefaultCopy(char);
      char.favorite = char.favorite === true;
      if (!char.agentId && !Object.hasOwn(studioPresets, char.studioPreset)) char.studioPreset = '';
    }
    if (!data.activities.every((entry) => entry && ['id', 'characterId', 'name', 'title', 'at'].every((key) => typeof entry[key] === 'string'))) throw Error('Invalid activity');
    if (typeof data.workspaceId !== 'string' || !/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(data.workspaceId)) {
      data.workspaceId = createRandomId(); state.needsMigration = true;
    }
    const catalogVersion = Number.isSafeInteger(data.catalogVersion) ? data.catalogVersion : 0;
    // Add defaults once per catalog release so edits and deletions survive reloads.
    if (catalogVersion < CATALOG_VERSION) {
      if (catalogVersion < 2 && !ids.has('mao')) data.characters.unshift(catalogCharacters()[0]);
      data.characters.unshift(...demoCharacters().filter((char) => !ids.has(char.id)));
      data.catalogVersion = CATALOG_VERSION;
      state.needsMigration = true;
    }
    return data;
  } catch { state.storageWarning = true; return initialData(); }
}

export function persist(message) {
  try {
    if (state.storageWarning) throw Error('Preserve unreadable stored data');
    localStorage.setItem(DATA_KEY, JSON.stringify(state.data));
    if (message) toast(message);
    return true;
  } catch {
    $('.workspace-footer > span:last-child').textContent = '저장 불가 · 현재 화면에서만 유지됩니다.';
    toast('브라우저 저장소를 사용할 수 없어 현재 화면에서만 변경사항을 유지해요.', true);
    return false;
  }
}
export function logActivity(char, title) {
  state.data.activities.unshift({ id: createRandomId(), characterId: char.id, name: char.name, title, at: now() });
  state.data.activities = state.data.activities.slice(0, 100);
}
