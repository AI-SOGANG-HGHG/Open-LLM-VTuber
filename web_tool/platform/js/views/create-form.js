import { $, charLink, toast } from '../dom.js';
import { createCharacter } from '../presets.js';
import { state } from '../state.js';
import { logActivity, persist } from '../store.js';

export function openCreate(preset) {
  $('#characterForm').reset();
  if (preset) {
    $('#characterName').value = preset.name;
    $('#characterDescription').value = preset.description;
    $('#characterTemplate').value = preset.template;
    $('#characterGreeting').value = preset.greeting;
    $('#characterForm').elements.avatar.value = preset.avatar;
  }
  $('#characterDialog').showModal();
}

export function bindCreateFormEvents() {
  $('#sidebarCreate').addEventListener('click', () => openCreate());
  $('#characterForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const name = form.get('name').trim(), description = form.get('description').trim();
    if (!name || !description) { toast('이름과 한 줄 소개를 입력해 주세요.', true); return; }
    const char = createCharacter(crypto.randomUUID(), name, description, form.get('template'), form.get('avatar'));
    char.greeting = form.get('greeting').trim() || char.greeting;
    state.data.characters.push(char); logActivity(char, '새 캐릭터 생성'); persist('새로운 캐릭터를 만들었어요.');
    $('#characterDialog').close(); state.collectionFilter = 'all'; state.searchQuery = ''; location.hash = charLink(char);
  });
}
