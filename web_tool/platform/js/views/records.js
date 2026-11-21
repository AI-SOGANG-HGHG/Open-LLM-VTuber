import { escapeHtml, LIVE_CHAT_ACTIVITY, shortDate } from '../dom.js';
import { state } from '../state.js';

export function renderRecords(char) {
  const activities = char ? state.data.activities.filter((event) => event.characterId === char.id) : state.data.activities;
  return `<section class="panel"${char ? ' aria-label="캐릭터 활동 기록"' : ' aria-label="최근 활동"'}>${char ? '<h2>캐릭터 활동 기록</h2>' : ''}${activities.length ? `<ul class="event-list">${activities.map((event) => `<li><div><strong>${escapeHtml(event.title === '스튜디오 음성 대화 진행' ? LIVE_CHAT_ACTIVITY : event.title)}</strong><small>${escapeHtml(event.name)}</small></div><time datetime="${escapeHtml(event.at)}">${shortDate(event.at)}</time></li>`).join('')}</ul>` : '<p class="muted">아직 기록된 활동이 없어요.</p>'}</section>`;
}
