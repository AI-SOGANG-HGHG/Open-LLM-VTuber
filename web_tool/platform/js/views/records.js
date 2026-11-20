import { escapeHtml, shortDate } from '../dom.js';
import { state } from '../state.js';

export function renderRecords(char) {
  const activities = char ? state.data.activities.filter((event) => event.characterId === char.id) : state.data.activities;
  return `<section class="panel"><p class="eyebrow">YOUR STUDIO JOURNAL</p><h2>${char ? escapeHtml(char.name) + '와 함께한' : '스튜디오의'} 발자취</h2><p class="muted">캐릭터를 만들고 다듬어 온 작은 순간들을 모았어요.</p>${activities.length ? `<ul class="event-list">${activities.map((event) => `<li><span class="event-marker" aria-hidden="true">↗</span><div><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.name)} · 브라우저 데모</small></div><time datetime="${escapeHtml(event.at)}">${shortDate(event.at)}</time></li>`).join('')}</ul>` : '<div class="empty-state">아직 기록된 활동이 없어요.<br />캐릭터를 만들거나 첫 대화를 시작해 보세요.</div>'}<p class="field-help" style="margin-top:20px">이 데모에서 직접 수행한 활동만 표시해요.</p></section>`;
}
