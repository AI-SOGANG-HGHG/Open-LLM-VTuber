import { avatar, tags } from '../components/card.js';
import { $, charLink, escapeHtml, main, now, shortDate, toast } from '../dom.js';
import { avatarAssets, defaultGreeting, presets, studioPresets } from '../presets.js';
import { connectRuntime, setConversationFocus } from '../runtime-bridge.js';
import { getCharacter, state } from '../state.js';
import { logActivity, persist } from '../store.js';
import { renderConnections } from './connections.js';
import { renderRecords } from './records.js';

let deleteId;

function avatarPicker(char) {
  return `<fieldset class="avatar-picker"><legend>캐릭터 외형</legend>${Object.entries(avatarAssets).map(([id, asset]) => `<label class="avatar-option"><input type="radio" name="avatar" value="${id}" ${char.avatar === id ? 'checked' : ''} /><span class="avatar-option-art ${id}">${asset.image ? `<img src="${asset.image}" alt="" />` : '<span aria-hidden="true">✳</span>'}</span><strong>${asset.name}</strong><small>${id === 'mao' ? '기본 Live2D' : id === 'sogangi' ? '서강대학교 캐릭터' : '아이콘 사용'}</small></label>`).join('')}</fieldset>`;
}
function profilePreview(char, chat = false) {
  const liveProfile = char.studioPreset
    ? `<dt>대화에 적용할 성격</dt><dd>${escapeHtml(studioPresets[char.studioPreset])}</dd>`
    : `<dt>말투</dt><dd>${escapeHtml(char.tone)}</dd>`;
  return `<aside class="preview-card ${chat ? 'chat-character' : 'settings-preview'}"><div class="preview-art ${char.avatar}" id="settingsAvatar">${avatar(char)}</div><div class="preview-profile"><h2 id="previewName">${escapeHtml(char.name)}</h2><p>${escapeHtml(char.description)}</p><div class="tags">${tags(char)}</div>${chat ? `<p class="field-help" style="margin:17px 0">${escapeHtml(char.tone)} · ${presets[char.template].label}</p><button class="button secondary" data-action="preview" data-id="${escapeHtml(char.id)}">외형 미리보기</button>` : `<div class="greeting-quote" id="previewGreeting">“${escapeHtml(char.greeting)}”</div><dl class="definition-list">${liveProfile}<dt>기억</dt><dd>${char.memories.length}개 · 직접 등록</dd><dt>연결</dt><dd>방송·게임 준비 중</dd></dl>`}${char.avatar === 'mao' ? '<p class="asset-credit">Mao · © Live2D Inc.</p>' : ''}</div></aside>`;
}
function settingsPanel(char) {
  return `<div class="detail-grid"><form class="panel" id="settingsForm" data-id="${escapeHtml(char.id)}"><h2>프로필과 성격</h2>${avatarPicker(char)}
    <div class="form-columns"><div><label for="editName">이름</label><input id="editName" name="name" value="${escapeHtml(char.name)}" maxlength="30" required /></div><div><label for="editTone">말투</label><select id="editTone" name="tone">${['친근한 반말', '활기찬 반말', '차분한 존댓말'].map((tone) => `<option${char.tone === tone ? ' selected' : ''}>${tone}</option>`).join('')}</select></div></div>
    <label for="editDescription">한 줄 소개</label><input id="editDescription" name="description" value="${escapeHtml(char.description)}" maxlength="100" required />
    <label for="editGreeting">첫 인사</label><textarea id="editGreeting" name="greeting" maxlength="300" style="min-height:85px" required>${escapeHtml(char.greeting)}</textarea><p class="field-help">대화방을 처음 열면 이 인사가 보여요.</p>
    <label for="editStudioPreset">대화에 적용할 성격</label><select id="editStudioPreset" name="studioPreset"><option value="">직접 작성한 성격과 말투</option>${Object.entries(studioPresets).map(([id, label]) => `<option value="${id}"${char.studioPreset === id ? ' selected' : ''}>${label}</option>`).join('')}</select><p class="field-help">팀에서 정해 둔 성격과 말투로 대화해요. 상황에 따라 감정이 달라지고, 답변할 때 관련 기억을 찾아봐요.</p>
    <label for="editPersona">성격과 대화 지침</label><textarea id="editPersona" name="persona" maxlength="2000" required>${escapeHtml(char.persona)}</textarea>
    <label for="editExploration">탐색 성향 <span id="explorationValue">${char.exploration}</span></label>
    <input id="editExploration" name="exploration" type="range" min="0" max="100" value="${char.exploration}" aria-describedby="explorationHelp"${char.studioPreset ? ' disabled' : ''} />
    <div class="range-label"><span>익숙함을 선호</span><span>새로운 시도를 선호</span></div>
    <p id="explorationHelp" class="field-help">성격을 직접 설정할 때 이 값을 바꿀 수 있어요. 팀 프리셋에는 정해진 값이 있어요.</p>
    <div class="panel-actions"><button type="submit" class="button primary">변경사항 저장</button></div><p class="field-help">저장한 설정은 대화실에 다시 연결할 때 적용돼요.</p></form>${profilePreview(char)}</div>`;
}
function chatPanel(char) {
  return `<section class="runtime-toolbar"><div><a class="runtime-back" href="#characters">← 스튜디오</a><span class="status-dot"></span><strong id="runtimeStatus" role="status">${escapeHtml(char.name)} 연결 준비 중…</strong></div><div><a class="button secondary" href="${charLink(char)}">캐릭터 설정</a><button class="button secondary" data-action="runtime-layout">스튜디오 보기</button><button class="button secondary" data-action="runtime-connect" data-id="${escapeHtml(char.id)}">다시 연결</button><button class="button secondary" data-action="runtime-disconnect">연결 해제</button></div></section><div class="studio-runtime" id="studioRuntime"><iframe id="studioFrame" title="${escapeHtml(char.name)} 실제 음성·Live2D 대화실" allow="microphone; autoplay" referrerpolicy="no-referrer"></iframe></div><p class="field-help">${char.studioPreset ? '답변 아래에서 캐릭터의 성격, 감정 변화, 참고한 기억을 확인할 수 있어요.' : '직접 설정한 성격으로 대화하고, 적어 둔 기억을 참고해요.'}</p>`;
}
function sampleChatPanel(char) {
  return `<div class="chat-layout">${profilePreview(char, true)}<section class="panel chat-panel"><div class="chat-top"><div><h2>${escapeHtml(char.name)}</h2><p>${escapeHtml(char.tone)} · ${presets[char.template].label}</p></div><span class="demo-pill">샘플 대화</span></div><div id="chatMessages" class="chat-messages" role="log" aria-label="샘플 대화 기록"></div><form id="chatForm" class="chat-compose" data-id="${escapeHtml(char.id)}"><input name="message" id="chatInput" placeholder="${escapeHtml(char.name)}에게 메시지 보내기…" aria-label="샘플 메시지" maxlength="500" autocomplete="off" required /><button class="button primary" type="submit" aria-label="메시지 보내기">↑</button></form><p class="chat-footnote">미리 준비한 답변으로 대화해 볼 수 있어요.</p></section></div>`;
}
function renderMessages(char) {
  const container = $('#chatMessages');
  container.innerHTML = char.messages.length ? char.messages.map((msg) => `<div class="chat-message${msg.role === 'user' ? ' user' : ''}">${msg.role === 'user' ? '' : `<span class="chat-author">${escapeHtml(char.name)} · 샘플</span>`}${escapeHtml(msg.content)}</div>`).join('') : `<div class="chat-empty"><p>${escapeHtml(char.greeting)}</p><div class="chat-suggestions"><button data-action="suggest" data-message="안녕!">인사하기</button><button data-action="suggest" data-message="오늘 할 일이 많아">오늘 할 일 이야기하기</button></div></div>`;
  container.scrollTop = container.scrollHeight;
}
function memoryPanel(char) {
  return `<section class="panel"><h2>기억 노트</h2><p class="muted">캐릭터에게 기억해 달라고 할 취향이나 약속, 함께한 일을 적어 주세요.</p><form id="memoryForm" class="memory-form" data-id="${escapeHtml(char.id)}"><input name="memory" placeholder="예: 매주 수요일에 프로젝트 회의를 한다." aria-label="새 기억" maxlength="300" required /><button type="submit" class="button primary">기억 추가</button></form>
    ${char.memories.length ? char.memories.map((memory) => `<div class="memory-item"><span>${escapeHtml(memory.text)}<small>직접 등록 · ${shortDate(memory.at)}</small></span><button class="icon-button" data-action="remove-memory" data-id="${escapeHtml(char.id)}" data-memory="${escapeHtml(memory.id)}" aria-label="기억 삭제">×</button></div>`).join('') : '<div class="empty-state">아직 적어 둔 기억이 없어요.</div>'}<p class="field-help" style="margin-top:22px">${char.studioPreset ? '최근에 적어 둔 기억 가운데 최대 50개를 살펴보고 대화에 관련된 내용을 찾아요.' : '성격을 직접 설정하면 최근에 적어 둔 기억을 최대 50개까지 참고해요.'}</p></section>`;
}

export function renderDetail(char, tab) {
  const tabs = { settings: '프로필·성격', chat: '음성·Live2D 대화', memory: '기억 노트', connections: '연결', records: '기록', sample: '샘플 대화' };
  if (!Object.hasOwn(tabs, tab)) tab = 'settings';
  $('#breadcrumb').textContent = `스튜디오 / ${char.name} / ${tabs[tab]}`;
  main.innerHTML = `<a class="back-link" href="#characters">← 내 캐릭터로 돌아가기</a><div class="detail-heading"><div class="detail-avatar ${char.avatar}">${avatar(char)}</div><div><h1>${escapeHtml(char.name)}</h1><p>${escapeHtml(char.description)}</p></div><div class="detail-actions"><button class="button secondary" data-action="preview" data-id="${escapeHtml(char.id)}">외형 미리보기</button><button class="button secondary" data-action="duplicate" data-id="${escapeHtml(char.id)}">복제</button><button class="button secondary" data-action="delete" data-id="${escapeHtml(char.id)}">삭제</button></div></div><nav class="tabs" aria-label="캐릭터 관리 메뉴">${Object.entries(tabs).map(([key, label]) => `<a href="${charLink(char, key)}" class="${tab === key ? 'active' : ''}"${tab === key ? ' aria-current="page"' : ''}>${label}</a>`).join('')}</nav>`;
  if (tab === 'settings') main.innerHTML += settingsPanel(char);
  if (tab === 'chat') { main.innerHTML += chatPanel(char); setConversationFocus(true); connectRuntime(char); }
  if (tab === 'sample') { main.innerHTML += sampleChatPanel(char); renderMessages(char); }
  if (tab === 'memory') main.innerHTML += memoryPanel(char);
  if (tab === 'connections') main.innerHTML += renderConnections(char);
  if (tab === 'records') main.innerHTML += renderRecords(char);
}

function sampleReply(char, text) {
  const polite = char.tone === '차분한 존댓말';
  if (/안녕|반가/.test(text)) return defaultGreeting(char);
  if (/할 일|과제|프로젝트|공부|계획/.test(text)) {
    if (char.template === 'curious') return polite ? '새로운 방법도 시도해 볼까요? 오늘 해보고 싶은 일 하나부터 골라보세요.' : '새로운 방법도 시도해 볼까? 오늘 제일 해보고 싶은 일 하나부터 골라보자!';
    if (char.template === 'calm') return polite ? '먼저 목표와 마감 시간을 정리해 보세요. 그다음 우선순위가 높은 일부터 작은 단계로 나눠보겠습니다.' : '먼저 목표와 마감 시간을 정리하자. 그다음 중요한 일부터 작은 단계로 나눠보면 돼.';
    return polite ? '할 일이 많아 부담스러우셨겠어요. 가장 작은 일 하나부터 함께 정리해 볼까요?' : '할 일이 많아서 막막했겠다. 가장 작은 일 하나부터 같이 정리해 보자. 내가 옆에 있을게!';
  }
  return polite ? '샘플 대화에서는 “오늘 할 일이 많아요”라고 보내 보세요.' : '샘플 대화에서는 “오늘 할 일이 많아”라고 보내 봐.';
}

export function openDelete(char) {
  deleteId = char.id;
  $('#deleteTitle').textContent = `“${char.name}” 캐릭터를 삭제할까요?`;
  $('#deleteDialog').showModal();
}

export function bindCharacterDetailEvents(render) {
  $('#deleteForm').addEventListener('submit', (event) => {
    event.preventDefault();
    state.data.characters = state.data.characters.filter((char) => char.id !== deleteId);
    state.data.activities = state.data.activities.filter((entry) => entry.characterId !== deleteId);
    persist('캐릭터를 삭제했어요.');
    $('#deleteDialog').close();
    deleteId = null;
    if (location.hash === '#characters') {
      render();
      main.focus({ preventScroll: true });
    } else {
      location.hash = 'characters';
    }
  });
  main.addEventListener('submit', (event) => {
    const form = event.target;
    if (!form.matches('#settingsForm, #memoryForm, #chatForm')) return;
    event.preventDefault();
    const char = getCharacter(form.dataset.id);
    if (!char) return;
    const values = new FormData(form);
    if (form.id === 'settingsForm') {
      const name = values.get('name').trim(), description = values.get('description').trim(), persona = values.get('persona').trim(), greeting = values.get('greeting').trim();
      if (!name || !description || !persona || !greeting) { toast('이름, 소개, 첫 인사, 성격 지침을 입력해 주세요.', true); return; }
      const studioPreset = values.get('studioPreset');
      const exploration = Number(form.elements.namedItem('exploration').value);
      Object.assign(char, { name, description, persona, greeting, avatar: values.get('avatar'), tone: values.get('tone'), exploration, studioPreset: Object.hasOwn(studioPresets, studioPreset) ? studioPreset : '', updatedAt: now() });
      logActivity(char, '캐릭터 설정 저장'); persist('캐릭터 설정을 저장했어요.'); render(); $('#editName').focus({ preventScroll: true });
    } else if (form.id === 'memoryForm') {
      const text = values.get('memory').trim(); if (!text) return;
      char.memories.push({ id: crypto.randomUUID(), text, at: now() }); logActivity(char, '기억 직접 등록'); persist('기억을 등록했어요.'); render(); $('#memoryForm input').focus({ preventScroll: true });
    } else if (form.id === 'chatForm') {
      const text = values.get('message').trim(); if (!text) return;
      char.messages.push({ role: 'user', content: text }, { role: 'assistant', content: sampleReply(char, text) }); char.messages = char.messages.slice(-80);
      logActivity(char, '샘플 대화 진행'); persist(); renderMessages(char); form.reset(); $('#chatInput').focus({ preventScroll: true });
    }
  });
}
