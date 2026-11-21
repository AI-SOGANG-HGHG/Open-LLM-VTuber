import { charLink, escapeHtml, main } from '../dom.js';
import { getCharacter, state } from '../state.js';

function chatAction(char) {
  const description = '<p>선택한 캐릭터와 음성으로 대화해요.</p>';
  if (char) {
    return `${description}<a class="button primary" href="${charLink(char, 'chat')}">${escapeHtml(char.name)} 대화 시작</a>`;
  }

  if (!state.data.characters.length) {
    return '<p>캐릭터를 만들고 대화를 시작해 보세요.</p><button type="button" class="button primary" data-action="create">캐릭터 만들기</button>';
  }

  const options = state.data.characters.map((item) =>
    `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`
  ).join('');
  return `${description}<form class="connection-chat-form" id="connectionChatForm">
    <label for="connectionCharacter">대화할 캐릭터</label>
    <select id="connectionCharacter" name="characterId" required>
      <option value="" selected disabled>내 캐릭터에서 선택</option>
      ${options}
    </select>
    <button type="submit" class="button primary">대화 시작</button>
  </form>`;
}

export function renderConnections(char) {
  return `<div class="connection-grid"><section class="connection-card"><h2>음성·Live2D 대화</h2>${chatAction(char)}<p class="field-help">대화 서버가 필요해요.</p></section>
    <section class="connection-card"><h2>방송 스튜디오</h2><p>방송 채팅이나 이벤트에 캐릭터가 반응하는 기능을 준비하고 있어요.</p></section>
    <section class="connection-card"><h2>Minecraft</h2><p>스튜디오에서 만든 캐릭터를 게임에 연결하는 기능을 준비하고 있어요.</p></section></div>`;
}

export function bindConnectionEvents() {
  main.addEventListener('submit', (event) => {
    const form = event.target;
    if (form.id !== 'connectionChatForm') return;
    event.preventDefault();
    const char = getCharacter(new FormData(form).get('characterId'));
    if (char) location.hash = charLink(char, 'chat');
  });
}
