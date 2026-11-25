import { card } from '../components/card.js';
import { $, escapeHtml, main, pageHeading } from '../dom.js';
import { avatarAssets, demoPersonas } from '../presets.js';
import { state } from '../state.js';

const demoCharacterIds = new Set(demoPersonas.map(({ id }) => id));

export function renderCards() {
  const normalized = state.searchQuery.toLocaleLowerCase();
  const chars = state.data.characters.filter((char) => `${char.name} ${char.description}`.toLocaleLowerCase().includes(normalized)
    && (state.collectionFilter !== 'favorites' || char.favorite)
    && (state.collectionFilter !== 'live2d' || avatarAssets[char.avatar].model));
  chars.sort((left, right) => Number(demoCharacterIds.has(left.id)) - Number(demoCharacterIds.has(right.id)));
  const emptyState = '<div class="empty-state">여기에는 아직 캐릭터가 없어요.<br />검색어나 필터를 바꾸거나 새로운 캐릭터를 만들어 보세요.</div>';
  $('#characterGrid').innerHTML = chars.length ? chars.map((char) => card(char)).join('') : emptyState;
  $('#resultCount').textContent = `캐릭터 ${chars.length}명`;
  document.querySelectorAll('[data-filter]').forEach((button) => { button.classList.toggle('active', button.dataset.filter === state.collectionFilter); button.setAttribute('aria-pressed', String(button.dataset.filter === state.collectionFilter)); });
}
export function renderCharacters() {
  main.innerHTML = pageHeading('내 캐릭터', '', '<button class="button secondary" data-action="create">캐릭터 만들기</button>') +
    `<div class="section-toolbar"><div class="filter-tabs" aria-label="캐릭터 필터"><button class="filter-button" data-filter="all">전체 <span>${state.data.characters.length}</span></button><button class="filter-button" data-filter="favorites">즐겨찾기</button><button class="filter-button" data-filter="live2d">Live2D</button></div><label class="search-wrap"><input class="search" id="characterSearch" type="search" placeholder="캐릭터 검색" aria-label="캐릭터 검색" maxlength="100" value="${escapeHtml(state.searchQuery)}" /></label></div>
    <p class="collection-caption" id="resultCount" aria-live="polite"></p><div class="character-grid" id="characterGrid"></div>`;
  renderCards();
}
