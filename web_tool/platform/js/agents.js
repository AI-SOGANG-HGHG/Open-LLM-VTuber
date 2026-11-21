import { escapeHtml, now } from './dom.js';
import { createCharacter, presets } from './presets.js';
import { state } from './state.js';
import { persist } from './store.js';

export const serverProfiles = location.pathname.startsWith('/web-tool/');
const traitLabels = {
  openness: ['개방성', '익숙한 방식', '새 접근 탐색'],
  conscientiousness: ['성실성', '유연한 진행', '체계적인 계획'],
  extraversion: ['외향성', '상대의 이야기를 기다림', '먼저 대화를 시작함'],
  agreeableness: ['친화성', '직접적으로 의견을 짚음', '공감과 합의를 중시함'],
  neuroticism: ['정서 민감도', '차분하게 반응함', '걱정과 감정 변화가 드러남'],
};
let workspaceRegistration;
let presetRequest;

async function request(path, method = 'GET', body) {
  const response = await fetch(path, {
    method, cache: 'no-store', credentials: 'same-origin',
    ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const error = new Error('Studio request failed');
    error.status = response.status;
    throw error;
  }
  if (response.status !== 204) return response.json();
}

export function loadPresets() {
  if (!presetRequest) {
    presetRequest = request('/studio/presets').catch((error) => {
      presetRequest = undefined;
      throw error;
    });
  }
  return presetRequest;
}

function registerWorkspace() {
  if (!workspaceRegistration) {
    persist();
    workspaceRegistration = request(`/studio/workspaces/${state.data.workspaceId}`, 'POST').catch((error) => {
      workspaceRegistration = undefined;
      throw error;
    });
  }
  return workspaceRegistration;
}

function agentPath(char) {
  return `/studio/workspaces/${state.data.workspaceId}/agents/${char.agentId}`;
}

function characterPayload(char) {
  return {
    workspace_id: state.data.workspaceId, character_id: char.id, name: char.name,
    description: char.description, greeting: char.greeting, avatar: char.avatar,
    preset_id: char.studioPreset || null,
    persona: char.studioPreset ? char.instructions || null : char.persona,
    tone: char.studioPreset ? char.agentTone || null : char.tone,
    exploration: char.exploration, traits: char.traits || null,
    memories: char.memories.slice(-50).map(({ text }) => text.trim()).filter(Boolean),
  };
}

function syncAgent(char, record, previousNotes = char.memories) {
  const profile = record.profile;
  const memories = [...new Set(profile.memories)].map((text) => (
    previousNotes.find((memory) => memory.text === text) || { id: crypto.randomUUID(), text, at: now() }
  ));
  Object.assign(char, {
    agentId: record.agent_id, agentVersion: record.version, studioPreset: profile.preset_id || '',
    name: profile.name, description: profile.description, greeting: profile.greeting || char.greeting,
    avatar: profile.avatar, exploration: profile.exploration, traits: record.personality.traits,
    persona: profile.persona || '', instructions: profile.persona, agentTone: profile.tone,
    tone: profile.tone || (record.personality.style.includes('존댓말') ? '차분한 존댓말' : '친근한 반말'),
    memories,
  });
}

export async function ensureAgent(char) {
  if (!serverProfiles) return;
  await registerWorkspace();
  const record = char.agentId
    ? await request(agentPath(char))
    : await request('/studio/agents/import', 'POST', characterPayload(char));
  syncAgent(char, record);
  persist();
}

export async function restoreAgents() {
  if (!serverProfiles) return;
  const workspace = await request('/studio/workspace');
  if (!workspace) return;
  const data = state.data;
  const sameWorkspace = data.workspaceId === workspace.workspace_id;
  const local = sameWorkspace ? data.characters : [];
  const archived = new Set(workspace.archived_characters);
  data.characters = local.filter((char) => !archived.has(char.id));
  if (!sameWorkspace) data.activities = [];
  data.workspaceId = workspace.workspace_id;
  for (const record of workspace.agents) {
    const profile = record.profile;
    let char = local.find((entry) => entry.id === profile.character_id);
    if (!char) {
      const template = Object.hasOwn(presets, profile.preset_id) ? profile.preset_id : 'calm';
      char = createCharacter(profile.character_id, profile.name, profile.description, template, profile.avatar);
      data.characters.push(char);
    }
    syncAgent(char, record);
  }
  persist();
}

export async function createAgent(char, source) {
  if (!serverProfiles) return;
  await registerWorkspace();
  const path = source ? `/studio/agents/${source.agentId}/copy` : '/studio/agents';
  syncAgent(char, await request(path, 'POST', characterPayload(char)));
}

export async function editAgent(char, draft) {
  if (!serverProfiles) {
    Object.assign(char, draft);
    return;
  }
  const record = await request(`/studio/agents/${char.agentId}`, 'PUT', {
    version: char.agentVersion, profile: characterPayload(draft),
  });
  syncAgent(char, record, draft.memories);
}

export async function archiveAgent(char) {
  if (!serverProfiles) return;
  await ensureAgent(char);
  await request(agentPath(char), 'DELETE');
}

export function agentError(error) {
  if (error.status === 409) return '다른 화면에서 변경사항을 저장했어요. 최신 설정을 확인하고 다시 시도해 주세요.';
  if (error.status === 404) return '이 작업공간의 캐릭터에 접근할 수 없어요. 처음 등록한 브라우저의 사이트 데이터를 확인해 주세요.';
  return '스튜디오 서버에 저장하거나 불러오지 못했어요. 연결을 확인해 주세요.';
}

export function traitControls(traits = {}) {
  return `<details class="trait-settings"><summary>성격 세부 조정 · Big Five</summary><div class="form-columns">${Object.entries(traitLabels).map(([axis, [label, low, high]]) => {
    const value = Math.round(100 * (traits[axis] ?? 0.5));
    return `<label class="trait-control"><span>${escapeHtml(label)} <output>${value}</output></span><input name="trait-${axis}" type="range" min="0" max="100" value="${value}"><small>${low} ↔ ${high}</small></label>`;
  }).join('')}</div><p class="field-help">값이 높을수록 그 성향에 해당하는 행동 규칙이 더 자주 선택돼요.</p></details>`;
}

export function updateTraitOutput(event) {
  const input = event.target;
  if (input.name?.startsWith('trait-')) input.closest('label').querySelector('output').value = input.value;
}

export function readTraits(values) {
  return Object.fromEntries(Object.keys(traitLabels).map((axis) => [axis, Number(values.get(`trait-${axis}`)) / 100]));
}
