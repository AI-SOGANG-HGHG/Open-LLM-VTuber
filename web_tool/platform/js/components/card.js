import { charLink, escapeHtml } from '../dom.js';
import { avatarAssets, demoPersonas, presets } from '../presets.js';

export function avatar(char) {
  const asset = avatarAssets[char.avatar];
  return asset.image ? `<img src="${asset.image}" alt="${escapeHtml(char.name)} 캐릭터" />` : '<span class="stage-symbol" aria-hidden="true">✳</span>';
}
export function tags(char) {
  const demoPersona = demoPersonas.find(({ id }) => id === char.studioPreset);
  const labels = demoPersona?.tags ?? presets[char.template].tags;
  return labels.map((tag) => `<span class="tag">${tag}</span>`).join('');
}

export function card(char, { catalog = false, demoPersona, showAvatar = true } = {}) {
  const asset = avatarAssets[char.avatar];
  const target = catalog ? '#discover' : charLink(char, 'chat');
  return `<article class="character-card${demoPersona ? ' comparison-card' : ''}">
    ${showAvatar ? `<a href="${target}" ${catalog ? `data-action="preset" data-id="${escapeHtml(char.id)}"` : ''} class="card-stage ${char.avatar}" aria-label="${escapeHtml(char.name)} ${catalog ? '프리셋 선택' : '대화 열기'}">${avatar(char)}${asset.credit ? `<span class="model-credit">${asset.credit}</span>` : ''}</a>` : ''}
    ${catalog ? '' : `<button class="favorite-button" data-action="favorite" data-id="${escapeHtml(char.id)}" aria-label="${escapeHtml(char.name)} 즐겨찾기" aria-pressed="${char.favorite}">${char.favorite ? '♥' : '♡'}</button>`}
    <div class="card-body"><div class="card-title"><h3>${escapeHtml(char.name)}</h3>${demoPersona ? '' : `<span class="card-type">${asset.label}</span>`}</div><p class="card-description">${escapeHtml(demoPersona?.description ?? char.description)}</p>
    ${demoPersona ? '' : `<div class="card-meta"><span>${catalog ? presets[char.template].label : `기억 ${char.memories.length}개 · 대화 ${Number.isSafeInteger(char.liveTurns) ? char.liveTurns : 0}회`}</span></div>`}
    <div class="card-actions">${catalog ? `<button class="button primary" data-action="preset" data-id="${escapeHtml(char.id)}">이 캐릭터로 시작</button>` : `<a class="button primary" href="${charLink(char, 'chat')}">대화 시작</a><a class="button secondary" href="${charLink(char)}">설정</a>`}<button class="button secondary preview-button" data-action="preview" data-id="${escapeHtml(char.id)}" data-catalog="${catalog}" aria-label="${escapeHtml(char.name)} 외형 미리보기">미리보기</button>${catalog ? '' : `<button type="button" class="button secondary" data-action="delete" data-id="${escapeHtml(char.id)}" aria-label="${escapeHtml(char.name)} 삭제">삭제</button>`}</div></div>
  </article>`;
}
