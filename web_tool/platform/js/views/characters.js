import { card } from '../components/card.js';
import { $, escapeHtml, main, pageHeading } from '../dom.js';
import { avatarAssets } from '../presets.js';
import { state } from '../state.js';

export function renderCards() {
  const normalized = state.searchQuery.toLocaleLowerCase();
  const chars = state.data.characters.filter((char) => `${char.name} ${char.description}`.toLocaleLowerCase().includes(normalized)
    && (state.collectionFilter !== 'favorites' || char.favorite)
    && (state.collectionFilter !== 'live2d' || avatarAssets[char.avatar].model));
  $('#characterGrid').innerHTML = chars.length ? chars.map((char) => card(char)).join('') : '<div class="empty-state">여기에는 아직 캐릭터가 없어요.<br />검색어나 필터를 바꾸거나 새로운 캐릭터를 만들어 보세요.</div>';
  $('#resultCount').textContent = `${chars.length}개의 캐릭터`;
  document.querySelectorAll('[data-filter]').forEach((button) => { button.classList.toggle('active', button.dataset.filter === state.collectionFilter); button.setAttribute('aria-pressed', String(button.dataset.filter === state.collectionFilter)); });
}
export function renderCharacters() {
  main.innerHTML = pageHeading('YOUR PERSONAL CAST', '내 캐릭터', `${escapeHtml(state.profile)}님, 오늘은 누구와 이야기를 나눌까요?`, '<button class="button primary" data-action="create">＋ 캐릭터 만들기</button>') +
    `<section class="collection-hero"><div class="hero-copy"><p class="eyebrow">A LITTLE PERSONALITY. ENDLESS POSSIBILITIES.</p><h2>상상에,<br /><em>성격을 더하다.</em></h2><p>말투부터 기억까지, 당신의 취향을 담아.<br />함께할 캐릭터를 만나보세요.</p><a class="button" href="#discover">캐릭터 둘러보기 <span aria-hidden="true">↗</span></a></div><div class="hero-art"><span class="hero-ring"></span><img src="./assets/mao.png" alt="Mao, 기본 Live2D 캐릭터" /><span class="hero-character-label">MEET THE ORIGINAL<strong>Mao</strong></span><span class="floating-label">✧ Open-LLM-VTuber의 첫 번째 캐릭터</span></div></section>
    <div class="section-toolbar"><div class="filter-tabs" aria-label="캐릭터 필터"><button class="filter-button" data-filter="all">전체 <span>${state.data.characters.length}</span></button><button class="filter-button" data-filter="favorites">♡ 즐겨찾기</button><button class="filter-button" data-filter="live2d">Live2D</button></div><label class="search-wrap" style="margin:0"><span aria-hidden="true">⌕</span><input class="search" id="characterSearch" type="search" placeholder="어떤 캐릭터를 찾고 있나요?" aria-label="캐릭터 검색" maxlength="100" value="${escapeHtml(state.searchQuery)}" /></label></div>
    <div class="collection-caption"><span id="resultCount"></span><span>나만의 성격, 나만의 이야기.</span></div><div class="character-grid" id="characterGrid"></div>
    <div class="create-strip"><div><strong>아직 만나지 못한 캐릭터가 있나요?</strong><p>외형과 성격을 골라, 당신만의 페르소나를 만들어보세요.</p></div><button class="button secondary" data-action="create">직접 만들기 ＋</button></div>`;
  renderCards();
}
