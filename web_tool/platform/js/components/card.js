import { charLink, escapeHtml } from '../dom.js';
import { avatarAssets, presets } from '../presets.js';

export function avatar(char) {
  const asset = avatarAssets[char.avatar];
  return asset.image ? `<img src="${asset.image}" alt="${escapeHtml(char.name)} 캐릭터" />` : '<span class="stage-symbol" aria-hidden="true">✳</span>';
}
export function tags(char) { return presets[char.template].tags.map((tag) => `<span class="tag">${tag}</span>`).join(''); }

export function card(char, catalog = false) {
  const asset = avatarAssets[char.avatar];
  const target = catalog ? '#discover' : charLink(char, 'chat');
  return `<article class="character-card">
    <a href="${target}" ${catalog ? `data-action="preset" data-id="${escapeHtml(char.id)}"` : ''} class="card-stage ${char.avatar} ${char.template === 'calm' ? 'calm' : ''}" aria-label="${escapeHtml(char.name)} ${catalog ? '프리셋 선택' : '대화 열기'}"><span class="stage-label">${char.avatar === 'mao' ? 'ORIGINAL LIVE2D' : char.avatar === 'sogangi' ? 'CAMPUS COMPANION' : 'YOUR OWN PERSONA'}</span>${avatar(char)}${asset.credit ? `<span class="model-credit">${asset.credit}</span>` : ''}</a>
    ${catalog ? '' : `<button class="favorite-button" data-action="favorite" data-id="${escapeHtml(char.id)}" aria-label="${escapeHtml(char.name)} 즐겨찾기" aria-pressed="${char.favorite}">${char.favorite ? '♥' : '♡'}</button>`}
    <div class="card-body"><div class="card-title"><h3>${escapeHtml(char.name)}</h3><span class="card-type">${asset.label}</span></div><p class="card-description">${escapeHtml(char.description)}</p><div class="tags">${tags(char)}</div>
    <div class="card-meta"><span>${catalog ? presets[char.template].label : `기억 ${char.memories.length}개 · 실제 대화 ${Number.isSafeInteger(char.liveTurns) ? char.liveTurns : 0}회`}</span><span>${catalog ? '프리셋' : '내 캐릭터'}</span></div>
    <div class="card-actions">${catalog ? `<button class="button primary" data-action="preset" data-id="${escapeHtml(char.id)}">이 캐릭터로 시작 ↗</button>` : `<a class="button secondary" href="${charLink(char)}">설정</a><a class="button primary" href="${charLink(char, 'chat')}">대화 시작 ↗</a>`}<button class="button secondary preview-button" data-action="preview" data-id="${escapeHtml(char.id)}" data-catalog="${catalog}" aria-label="${escapeHtml(char.name)} 외형 미리보기">◉</button></div></div>
  </article>`;
}
