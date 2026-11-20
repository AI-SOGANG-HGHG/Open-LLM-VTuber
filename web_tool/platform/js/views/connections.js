import { charLink, escapeHtml } from '../dom.js';
import { state } from '../state.js';

export function renderConnections(char) {
  const selected = char || state.data.characters.find((item) => item.id === 'sogangi') || state.data.characters[0];
  return `<div class="connection-grid"><section class="connection-card"><h2>음성·Live2D 대화</h2><p>선택한 캐릭터와 음성으로 대화해요.</p>${selected ? `<a class="button primary" href="${charLink(selected, 'chat')}">${escapeHtml(selected.name)} 대화 시작</a>` : '<button class="button primary" data-action="create">캐릭터 만들기</button>'}<p class="field-help">대화 서버가 필요해요.</p></section>
    <section class="connection-card"><h2>방송 스튜디오</h2><p>방송 채팅이나 이벤트에 캐릭터가 반응하는 기능을 준비하고 있어요.</p></section>
    <section class="connection-card"><h2>Minecraft</h2><p>스튜디오에서 만든 캐릭터를 게임에 연결하는 기능을 준비하고 있어요.</p></section></div>`;
}
