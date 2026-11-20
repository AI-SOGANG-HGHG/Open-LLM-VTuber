import { charLink, escapeHtml } from '../dom.js';
import { state } from '../state.js';

export function renderConnections(char) {
  const selected = char || state.data.characters.find((item) => item.id === 'sogangi') || state.data.characters[0];
  return `<div class="connection-grid"><section class="connection-card"><span class="connection-icon" aria-hidden="true">↗</span><span class="tag">스튜디오 대화실</span><h2>음성·Live2D 대화</h2><p>선택한 캐릭터의 성격과 등록한 기억을 적용하고, 스튜디오 안에서 목소리와 움직임으로 이야기해요.</p>${selected ? `<a class="button primary" href="${charLink(selected, 'chat')}">${escapeHtml(selected.name)} 대화실 연결 ↗</a>` : '<button class="button primary" data-action="create">먼저 캐릭터 만들기</button>'}<p class="field-help">대화 서버 필요 · 메시지 전송 시 API 사용</p></section>
    <section class="connection-card"><span class="connection-icon" aria-hidden="true">◉</span><span class="tag">준비 중</span><h2>방송 스튜디오</h2><p>채팅과 방송 이벤트를 받아, ${char ? escapeHtml(char.name) : '선택한 캐릭터'}의 목소리와 표정으로 시청자와 만나요.</p><button class="button secondary" disabled>방송 연결 준비 중</button></section>
    <section class="connection-card"><span class="connection-icon" aria-hidden="true">◇</span><span class="tag">준비 중</span><h2>Minecraft 월드</h2><p>같은 성격과 기억을 가진 캐릭터로, 블록 너머 새로운 모험을 시작해요.</p><button class="button secondary" disabled>게임 연결 준비 중</button></section></div><p class="bottom-note">앞으로 연결할 무대를 미리 보여드려요. 방송·게임 접속과 에이전트 실행은 아직 지원하지 않아요.</p>`;
}
