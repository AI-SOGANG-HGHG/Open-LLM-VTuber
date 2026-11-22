import { createRandomId } from '../../../shared/random-id.js';
import { agentError, createAgent, loadPresets, readTraits, serverProfiles, traitControls, updateTraitOutput } from '../agents.js';
import { $, charLink, toast } from '../dom.js';
import { createCharacter, presets, studioPresets } from '../presets.js';
import { state } from '../state.js';
import { logActivity, persist } from '../store.js';

let options;

function showTraits() {
  $('#createTraitSettings').innerHTML = traitControls(options[$('#characterTemplate').value]?.traits);
}

export async function openCreate(preset) {
  try {
    options = serverProfiles
      ? await loadPresets()
      : Object.fromEntries(Object.entries(studioPresets).map(([id, label]) => [id, { label }]));
  } catch (error) {
    toast(agentError(error), true);
    return;
  }
  if ($('#characterDialog').open) return;
  $('#characterForm').reset();
  const select = $('#characterTemplate');
  select.replaceChildren(...Object.entries(options).map(([id, { label }]) => new Option(label, id)));
  select.value = preset?.studioPreset || preset?.template || 'warm';
  if (preset) {
    $('#characterName').value = preset.name;
    $('#characterDescription').value = preset.description;
    $('#characterGreeting').value = preset.greeting;
    $('#characterForm').elements.avatar.value = preset.avatar;
  }
  showTraits();
  $('#characterDialog').showModal();
}

export function bindCreateFormEvents() {
  $('#characterTemplate').addEventListener('change', showTraits);
  $('#characterForm').addEventListener('input', updateTraitOutput);
  $('#characterForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = event.submitter;
    if (button.disabled) return;
    const form = new FormData(event.target);
    const name = form.get('name').trim(), description = form.get('description').trim();
    if (!name || !description) { toast('이름과 한 줄 소개를 입력해 주세요.', true); return; }
    const presetId = form.get('studioPreset');
    const template = Object.hasOwn(presets, presetId) ? presetId : 'calm';
    const char = createCharacter(createRandomId(), name, description, template, form.get('avatar'));
    char.studioPreset = presetId;
    char.traits = readTraits(form);
    char.greeting = form.get('greeting').trim() || char.greeting;
    button.disabled = true;
    try {
      await createAgent(char);
    } catch (error) {
      toast(agentError(error), true);
      return;
    } finally {
      button.disabled = false;
    }
    state.data.characters.push(char); logActivity(char, '새 캐릭터 생성'); persist('새로운 캐릭터를 만들었어요.');
    $('#characterDialog').close(); state.collectionFilter = 'all'; state.searchQuery = ''; location.hash = charLink(char);
  });
}
