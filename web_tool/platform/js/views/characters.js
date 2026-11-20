import { card } from '../components/card.js';
import { $, escapeHtml, main, pageHeading } from '../dom.js';
import { avatarAssets, demoPersonas } from '../presets.js';
import { state } from '../state.js';

function comparisonContent(pair) {
  const avatarId = pair[0].avatar;
  const shared = pair.every(({ avatar }) => avatar === avatarId) ? avatarAssets[avatarId] : null;
  const figure = shared?.image ? `<figure class="comparison-art ${avatarId}">
    <img src="${shared.image}" alt="" />
    <figcaption>${shared.name}${shared.credit ? ` <span>${shared.credit}</span>` : ''}</figcaption>
  </figure>` : '';
  return `<h2 id="comparisonTitle">두 캐릭터의 답변 비교</h2>
    <p>두 캐릭터에게 같은 질문을 보내고 답변과 참고한 기억을 비교해 보세요.${figure ? ' 두 캐릭터의 외형은 같아요.' : ''}</p>
    <div class="comparison-layout">${figure}<div class="comparison-grid">
      ${pair.map((char, index) => card(char, { demoPersona: demoPersonas[index], showAvatar: !figure })).join('')}
    </div></div>`;
}

export function renderCards() {
  const normalized = state.searchQuery.toLocaleLowerCase();
  const chars = state.data.characters.filter((char) => `${char.name} ${char.description}`.toLocaleLowerCase().includes(normalized)
    && (state.collectionFilter !== 'favorites' || char.favorite)
    && (state.collectionFilter !== 'live2d' || avatarAssets[char.avatar].model));
  const demoPair = !normalized && state.collectionFilter === 'all'
    ? demoPersonas.map(({ id }) => chars.find((char) => char.id === id && char.studioPreset === id))
    : [];
  const showComparison = demoPair.length === demoPersonas.length && demoPair.every(Boolean);
  const remaining = showComparison ? chars.filter((char) => !demoPair.includes(char)) : chars;
  const comparison = $('#demoComparison');
  comparison.hidden = !showComparison;
  comparison.innerHTML = showComparison ? comparisonContent(demoPair) : '';
  const emptyState = '<div class="empty-state">여기에는 아직 캐릭터가 없어요.<br />검색어나 필터를 바꾸거나 새로운 캐릭터를 만들어 보세요.</div>';
  $('#characterGrid').innerHTML = chars.length ? remaining.map((char) => card(char)).join('') : emptyState;
  const count = $('#resultCount');
  count.hidden = showComparison && !remaining.length;
  count.textContent = `${showComparison ? '다른 캐릭터' : '캐릭터'} ${remaining.length}명`;
  document.querySelectorAll('[data-filter]').forEach((button) => { button.classList.toggle('active', button.dataset.filter === state.collectionFilter); button.setAttribute('aria-pressed', String(button.dataset.filter === state.collectionFilter)); });
}
export function renderCharacters() {
  main.innerHTML = pageHeading('내 캐릭터', '', '<button class="button secondary" data-action="create">캐릭터 만들기</button>') +
    `<div class="section-toolbar"><div class="filter-tabs" aria-label="캐릭터 필터"><button class="filter-button" data-filter="all">전체 <span>${state.data.characters.length}</span></button><button class="filter-button" data-filter="favorites">즐겨찾기</button><button class="filter-button" data-filter="live2d">Live2D</button></div><label class="search-wrap"><input class="search" id="characterSearch" type="search" placeholder="캐릭터 검색" aria-label="캐릭터 검색" maxlength="100" value="${escapeHtml(state.searchQuery)}" /></label></div>
    <section id="demoComparison" class="demo-comparison" aria-labelledby="comparisonTitle" hidden></section>
    <p class="collection-caption" id="resultCount" aria-live="polite"></p><div class="character-grid" id="characterGrid"></div>`;
  renderCards();
}
