// Local Studio settings; live conversations use the existing backend inside an embedded runtime.
const DATA_KEY = 'persona-studio.demo.v1';
const SESSION_KEY = 'persona-studio.demo-session.v1';
const $ = (selector) => document.querySelector(selector);
const main = $('#mainContent');
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const presets = {
  warm: { label: '다정한 동료', tone: '친근한 반말', persona: '따뜻하고 호기심 많은 동료. 상대의 이야기에 공감하고, 함께할 수 있는 작은 다음 행동을 제안한다.', tags: ['다정한', '공감하는', '함께하는'], exploration: 40 },
  curious: { label: '호기심 많은 탐험가', tone: '활기찬 반말', persona: '새로운 장소와 아이디어에 호기심이 많다. 다양한 가능성을 이야기하고 새로운 시도를 제안한다.', tags: ['호기심', '탐험', '새로운 시도'], exploration: 85 },
  calm: { label: '차분한 전략가', tone: '차분한 존댓말', persona: '차분하고 계획적인 동료. 목표를 확인하고, 일을 작은 단계로 나누어 설명한다.', tags: ['차분한', '계획적인', '신중한'], exploration: 25 },
};
const avatarAssets = {
  mao: { name: 'Mao', label: 'Open-LLM-VTuber 기본', image: './assets/mao.png', model: '/live2d-models/mao_pro/runtime/mao_pro.model3.json', credit: '© Live2D Inc.' },
  sogangi: { name: '서강이', label: '캠퍼스 캐릭터', image: '../sogangi/assets/sogangi-neutral.svg', model: '/live2d-models/sogangi-expressions/runtime/sogangi.model3.json', credit: '' },
  symbol: { name: '심볼', label: '커스텀 페르소나', image: '', model: '', credit: '' },
};
const now = () => new Date().toISOString();
function defaultGreeting(char) { return char.tone === '차분한 존댓말' ? `안녕하세요. ${char.name}입니다. 오늘 함께할 일을 이야기해 주세요.` : `안녕! 나는 ${char.name}야. 오늘은 어떤 이야기를 해볼까?`; }
function createCharacter(id, name, description, template, avatar = 'symbol') {
  const char = { id, name, description, template, avatar, tone: presets[template].tone, persona: presets[template].persona, exploration: presets[template].exploration, createdAt: now(), updatedAt: now(), favorite: false, memories: [], messages: [] };
  char.greeting = defaultGreeting(char);
  return char;
}
function catalogCharacters() {
  const mao = createCharacter('mao', 'Mao', '새로운 이야기를 좋아하는, 당신의 첫 번째 버추얼 파트너.', 'curious', 'mao');
  mao.greeting = '안녕, 나는 Mao야! 오늘은 어떤 재미있는 이야기를 만들어볼까?';
  const sogangi = createCharacter('sogangi', '서강이', '공부도 프로젝트도, 언제나 네 편인 캠퍼스 동료.', 'warm', 'sogangi');
  sogangi.greeting = '반가워, 학우야! 오늘도 같이 한 걸음씩 해보자.';
  const moa = createCharacter('moa', '모아', '작은 호기심에서 시작하는, 우리만의 새로운 모험.', 'curious');
  return [mao, sogangi, moa];
}
function initialData() { return { version: 1, catalogVersion: 2, workspaceId: crypto.randomUUID(), characters: catalogCharacters(), activities: [] }; }
let storageWarning = false;
let needsMigration = false;
function loadData() {
  try {
    const raw = localStorage.getItem(DATA_KEY);
    if (!raw) return initialData();
    const data = JSON.parse(raw);
    if (data.version !== 1 || !Array.isArray(data.characters) || !Array.isArray(data.activities)) throw Error('Invalid data');
    const ids = new Set();
    for (const char of data.characters) {
      if (!char || typeof char.id !== 'string' || ids.has(char.id)
        || !['name', 'description', 'persona', 'tone'].every((key) => typeof char[key] === 'string')
        || !Object.hasOwn(presets, char.template) || !Object.hasOwn(avatarAssets, char.avatar)
        || !Number.isFinite(char.exploration) || char.exploration < 0 || char.exploration > 100
        || !Array.isArray(char.messages) || !Array.isArray(char.memories)
        || !char.messages.every((msg) => msg && ['user', 'assistant'].includes(msg.role) && typeof msg.content === 'string')
        || !char.memories.every((memory) => memory && ['id', 'text', 'at'].every((key) => typeof memory[key] === 'string'))) throw Error('Invalid character');
      ids.add(char.id);
      char.greeting = typeof char.greeting === 'string' ? char.greeting : defaultGreeting(char);
      char.favorite = char.favorite === true;
    }
    if (!data.activities.every((entry) => entry && ['id', 'characterId', 'name', 'title', 'at'].every((key) => typeof entry[key] === 'string'))) throw Error('Invalid activity');
    if (typeof data.workspaceId !== 'string' || !/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i.test(data.workspaceId)) {
      data.workspaceId = crypto.randomUUID(); needsMigration = true;
    }
    // Add the newly offered default once, preserving all previous user edits and deletions afterward.
    if (data.catalogVersion !== 2) {
      if (!ids.has('mao')) data.characters.unshift(catalogCharacters()[0]);
      data.catalogVersion = 2;
      needsMigration = true;
    }
    return data;
  } catch { storageWarning = true; return initialData(); }
}
let data = loadData();
let profile = '';
let toastTimer;
let deleteId;
let collectionFilter = 'all';
let searchQuery = '';
let avatarPreview;
let previewEpoch = 0;
let activeRuntime;
try { profile = sessionStorage.getItem(SESSION_KEY) || ''; } catch { /* Page-local demo remains usable. */ }
function toast(message, error = false) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.toggle('error-toast', error);
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, 3500);
}
function persist(message) {
  try {
    if (storageWarning) throw Error('Preserve unreadable stored data');
    localStorage.setItem(DATA_KEY, JSON.stringify(data));
    if (message) toast(message);
    return true;
  } catch {
    $('.workspace-footer > span:last-child').textContent = '저장 불가 · 현재 화면에서만 유지됩니다.';
    toast('브라우저 저장소를 사용할 수 없어 현재 화면에서만 변경사항을 유지해요.', true);
    return false;
  }
}
function logActivity(char, title) {
  data.activities.unshift({ id: crypto.randomUUID(), characterId: char.id, name: char.name, title, at: now() });
  data.activities = data.activities.slice(0, 100);
}
function avatar(char) {
  const asset = avatarAssets[char.avatar];
  return asset.image ? `<img src="${asset.image}" alt="${escapeHtml(char.name)} 캐릭터" />` : '<span class="stage-symbol" aria-hidden="true">✳</span>';
}
function tags(char) { return presets[char.template].tags.map((tag) => `<span class="tag">${tag}</span>`).join(''); }
function charLink(char, tab = 'settings') { return `#character/${encodeURIComponent(char.id)}/${tab}`; }
function runtimeOrigin() { return location.pathname.startsWith('/web-tool/') ? location.origin : 'http://localhost:12393'; }
function getCharacter(id) { return data.characters.find((char) => char.id === id); }
function shortDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}
function pageHeading(eyebrow, title, description, action = '') {
  return `<div class="page-heading"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="muted">${description}</p></div>${action}</div>`;
}
function card(char, catalog = false) {
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
function renderCards() {
  const normalized = searchQuery.toLocaleLowerCase();
  const chars = data.characters.filter((char) => `${char.name} ${char.description}`.toLocaleLowerCase().includes(normalized)
    && (collectionFilter !== 'favorites' || char.favorite)
    && (collectionFilter !== 'live2d' || avatarAssets[char.avatar].model));
  $('#characterGrid').innerHTML = chars.length ? chars.map((char) => card(char)).join('') : '<div class="empty-state">여기에는 아직 캐릭터가 없어요.<br />검색어나 필터를 바꾸거나 새로운 캐릭터를 만들어 보세요.</div>';
  $('#resultCount').textContent = `${chars.length}개의 캐릭터`;
  document.querySelectorAll('[data-filter]').forEach((button) => { button.classList.toggle('active', button.dataset.filter === collectionFilter); button.setAttribute('aria-pressed', String(button.dataset.filter === collectionFilter)); });
}
function renderCharacters() {
  main.innerHTML = pageHeading('YOUR PERSONAL CAST', '내 캐릭터', `${escapeHtml(profile)}님, 오늘은 누구와 이야기를 나눌까요?`, '<button class="button primary" data-action="create">＋ 캐릭터 만들기</button>') +
    `<section class="collection-hero"><div class="hero-copy"><p class="eyebrow">A LITTLE PERSONALITY. ENDLESS POSSIBILITIES.</p><h2>상상에,<br /><em>성격을 더하다.</em></h2><p>말투부터 기억까지, 당신의 취향을 담아.<br />함께할 캐릭터를 만나보세요.</p><a class="button" href="#discover">캐릭터 둘러보기 <span aria-hidden="true">↗</span></a></div><div class="hero-art"><span class="hero-ring"></span><img src="./assets/mao.png" alt="Mao, 기본 Live2D 캐릭터" /><span class="hero-character-label">MEET THE ORIGINAL<strong>Mao</strong></span><span class="floating-label">✧ Open-LLM-VTuber의 첫 번째 캐릭터</span></div></section>
    <div class="section-toolbar"><div class="filter-tabs" aria-label="캐릭터 필터"><button class="filter-button" data-filter="all">전체 <span>${data.characters.length}</span></button><button class="filter-button" data-filter="favorites">♡ 즐겨찾기</button><button class="filter-button" data-filter="live2d">Live2D</button></div><label class="search-wrap" style="margin:0"><span aria-hidden="true">⌕</span><input class="search" id="characterSearch" type="search" placeholder="어떤 캐릭터를 찾고 있나요?" aria-label="캐릭터 검색" maxlength="100" value="${escapeHtml(searchQuery)}" /></label></div>
    <div class="collection-caption"><span id="resultCount"></span><span>나만의 성격, 나만의 이야기.</span></div><div class="character-grid" id="characterGrid"></div>
    <div class="create-strip"><div><strong>아직 만나지 못한 캐릭터가 있나요?</strong><p>외형과 성격을 골라, 당신만의 페르소나를 만들어보세요.</p></div><button class="button secondary" data-action="create">직접 만들기 ＋</button></div>`;
  renderCards();
}
function renderDiscover() {
  main.innerHTML = pageHeading('FIND YOUR NEXT CHARACTER', '어떤 캐릭터를 만나볼까요?', '마음에 드는 모습에서 시작해, 당신만의 성격을 더해보세요.') + '<div class="discover-intro"><span aria-hidden="true">✧</span>처음이라면 프리셋으로 가볍게 시작하세요. 설정은 나중에도 바꿀 수 있어요.</div><div class="character-grid">' + catalogCharacters().map((char) => card(char, true)).join('') + '</div><p class="bottom-note">Mao는 Open-LLM-VTuber에 등록된 기본 Live2D 모델이에요. 프리셋을 선택하면 이름·말투·첫 인사를 정해 내 캐릭터로 만들 수 있어요.</p>';
}
function avatarPicker(char) {
  return `<fieldset class="avatar-picker"><legend>캐릭터 외형</legend>${Object.entries(avatarAssets).map(([id, asset]) => `<label class="avatar-option"><input type="radio" name="avatar" value="${id}" ${char.avatar === id ? 'checked' : ''} /><span class="avatar-option-art ${id}">${asset.image ? `<img src="${asset.image}" alt="" />` : '<span aria-hidden="true">✳</span>'}</span><strong>${asset.name}</strong><small>${id === 'mao' ? '기본 Live2D' : id === 'sogangi' ? '캠퍼스 동료' : '나만의 심볼'}</small></label>`).join('')}</fieldset>`;
}
function profilePreview(char, chat = false) {
  return `<aside class="preview-card ${chat ? 'chat-character' : 'settings-preview'}"><div class="preview-art ${char.avatar}" id="settingsAvatar">${avatar(char)}</div><div class="preview-profile"><p class="eyebrow">${chat ? 'YOUR CONVERSATION PARTNER' : 'CHARACTER PREVIEW'}</p><h2 id="previewName">${escapeHtml(char.name)}</h2><p>${escapeHtml(char.description)}</p><div class="tags">${tags(char)}</div>${chat ? `<p class="field-help" style="margin:17px 0">${escapeHtml(char.tone)} · ${presets[char.template].label}</p><button class="button secondary" data-action="preview" data-id="${escapeHtml(char.id)}">외형만 미리보기 ◉</button>` : `<div class="greeting-quote" id="previewGreeting">“${escapeHtml(char.greeting)}”</div><dl class="definition-list"><dt>말투</dt><dd>${escapeHtml(char.tone)}</dd><dt>기억</dt><dd>${char.memories.length}개 · 직접 등록</dd><dt>연결</dt><dd>방송·게임 준비 중</dd></dl>`}${char.avatar === 'mao' ? '<p class="asset-credit">Mao · © Live2D Inc.</p>' : ''}</div></aside>`;
}
function settingsPanel(char) {
  return `<div class="detail-grid"><form class="panel" id="settingsForm" data-id="${escapeHtml(char.id)}"><p class="eyebrow">MAKE IT YOURS</p><h2>이 캐릭터만의 매력을 담아주세요.</h2><p class="muted">외형부터 첫 인사까지, 원하는 모습으로 다듬어보세요.</p>${avatarPicker(char)}
    <div class="form-columns"><div><label for="editName">이름</label><input id="editName" name="name" value="${escapeHtml(char.name)}" maxlength="30" required /></div><div><label for="editTone">말투</label><select id="editTone" name="tone">${['친근한 반말', '활기찬 반말', '차분한 존댓말'].map((tone) => `<option${char.tone === tone ? ' selected' : ''}>${tone}</option>`).join('')}</select></div></div>
    <label for="editDescription">한 줄 소개</label><input id="editDescription" name="description" value="${escapeHtml(char.description)}" maxlength="100" required />
    <label for="editGreeting">첫 인사</label><textarea id="editGreeting" name="greeting" maxlength="300" style="min-height:85px" required>${escapeHtml(char.greeting)}</textarea><p class="field-help">대화 실험실을 처음 열었을 때 표시할 한마디예요.</p>
    <label for="editPersona">성격과 대화 지침</label><textarea id="editPersona" name="persona" maxlength="2000" required>${escapeHtml(char.persona)}</textarea>
    <label for="editExploration">탐색 성향 <span id="explorationValue">${char.exploration}</span></label><input id="editExploration" name="exploration" type="range" min="0" max="100" value="${char.exploration}" /><div class="range-label"><span>익숙함을 선호</span><span>새로운 시도를 선호</span></div><p class="field-help">행동 성향 설정 예시예요. 게임 행동에는 아직 연결되지 않아요.</p><div class="panel-actions"><button type="submit" class="button primary">변경사항 저장 ↗</button></div><p class="field-help">저장한 설정은 다음 대화실 연결에 적용돼요. 기존 서강이 앱의 기본 설정은 변경하지 않아요.</p></form>${profilePreview(char)}</div>`;
}
function chatPanel(char) {
  return `<section class="runtime-toolbar"><div><a class="runtime-back" href="#characters">← 스튜디오</a><span class="status-dot"></span><strong id="runtimeStatus" role="status">${escapeHtml(char.name)} 연결 준비 중…</strong></div><div><a class="button secondary" href="${charLink(char)}">캐릭터 설정</a><button class="button secondary" data-action="runtime-layout">스튜디오 보기</button><button class="button secondary" data-action="runtime-connect" data-id="${escapeHtml(char.id)}">다시 연결</button><button class="button secondary" data-action="runtime-disconnect">연결 해제</button></div></section><div class="studio-runtime" id="studioRuntime"><iframe id="studioFrame" title="${escapeHtml(char.name)} 실제 음성·Live2D 대화실" allow="microphone; autoplay" referrerpolicy="no-referrer"></iframe></div><p class="field-help">현재 설정과 직접 등록한 기억 메모를 적용한 실제 대화예요. 메시지를 보내면 서버에 설정된 모델·음성 API를 사용해요. 자동 기억 추출과 RAG 검색은 아직 연결되지 않았어요.</p>`;
}
function sampleChatPanel(char) {
  return `<div class="chat-layout">${profilePreview(char, true)}<section class="panel chat-panel"><div class="chat-top"><div><h2>${escapeHtml(char.name)}</h2><p>${escapeHtml(char.tone)} · ${presets[char.template].label}</p></div><span class="demo-pill">샘플 대화</span></div><div id="chatMessages" class="chat-messages" role="log" aria-label="샘플 대화 기록"></div><form id="chatForm" class="chat-compose" data-id="${escapeHtml(char.id)}"><input name="message" id="chatInput" placeholder="${escapeHtml(char.name)}에게 메시지 보내기…" aria-label="샘플 메시지" maxlength="500" autocomplete="off" required /><button class="button primary" type="submit" aria-label="메시지 보내기">↑</button></form><p class="chat-footnote">시나리오 기반 샘플 응답이에요. 실제 AI 모델은 연결되지 않았어요.</p></section></div>`;
}
function renderMessages(char) {
  const container = $('#chatMessages');
  container.innerHTML = char.messages.length ? char.messages.map((msg) => `<div class="chat-message${msg.role === 'user' ? ' user' : ''}">${msg.role === 'user' ? '' : `<span class="chat-author">${escapeHtml(char.name)} · 샘플</span>`}${escapeHtml(msg.content)}</div>`).join('') : `<div class="chat-empty"><span class="mini-spark" aria-hidden="true">✳</span><h3>우리의 첫 번째 이야기.</h3><p>${escapeHtml(char.greeting)}</p><div class="chat-suggestions"><button data-action="suggest" data-message="안녕!">반갑게 인사하기 ↗</button><button data-action="suggest" data-message="오늘 할 일이 많아">오늘 할 일 이야기하기 ↗</button></div></div>`;
  container.scrollTop = container.scrollHeight;
}
function memoryPanel(char) {
  return `<section class="panel"><p class="eyebrow">THINGS TO REMEMBER</p><h2>작은 기억이, 특별한 캐릭터를 만들어요.</h2><p class="muted">취향, 약속, 함께한 일. 캐릭터가 기억했으면 하는 내용을 모아두세요.</p><form id="memoryForm" class="memory-form" data-id="${escapeHtml(char.id)}"><input name="memory" placeholder="예: 매주 수요일에 프로젝트 회의를 한다." aria-label="새 기억" maxlength="300" required /><button type="submit" class="button primary">＋ 기억 추가</button></form>
    ${char.memories.length ? char.memories.map((memory) => `<div class="memory-item"><span>${escapeHtml(memory.text)}<small>직접 등록 · ${shortDate(memory.at)}</small></span><button class="icon-button" data-action="remove-memory" data-id="${escapeHtml(char.id)}" data-memory="${escapeHtml(memory.id)}" aria-label="기억 삭제">×</button></div>`).join('') : '<div class="empty-state">아직 비어 있는 기억 노트.<br />위 입력란에서 첫 번째 기억을 남겨보세요.</div>'}<p class="field-help" style="margin-top:22px">대화실을 연결할 때 최근 메모 최대 50개를 참고 문맥으로 전달해요. 자동 추출·RAG 검색은 아직 없어요.</p></section>`;
}
function renderConnections(char) {
  const selected = char || data.characters.find((item) => item.id === 'sogangi') || data.characters[0];
  return `<div class="connection-grid"><section class="connection-card"><span class="connection-icon" aria-hidden="true">↗</span><span class="tag">스튜디오 대화실</span><h2>음성·Live2D 대화</h2><p>선택한 캐릭터의 성격과 등록한 기억을 적용하고, 스튜디오 안에서 목소리와 움직임으로 이야기해요.</p>${selected ? `<a class="button primary" href="${charLink(selected, 'chat')}">${escapeHtml(selected.name)} 대화실 연결 ↗</a>` : '<button class="button primary" data-action="create">먼저 캐릭터 만들기</button>'}<p class="field-help">대화 서버 필요 · 메시지 전송 시 API 사용</p></section>
    <section class="connection-card"><span class="connection-icon" aria-hidden="true">◉</span><span class="tag">준비 중</span><h2>방송 스튜디오</h2><p>채팅과 방송 이벤트를 받아, ${char ? escapeHtml(char.name) : '선택한 캐릭터'}의 목소리와 표정으로 시청자와 만나요.</p><button class="button secondary" disabled>방송 연결 준비 중</button></section>
    <section class="connection-card"><span class="connection-icon" aria-hidden="true">◇</span><span class="tag">준비 중</span><h2>Minecraft 월드</h2><p>같은 성격과 기억을 가진 캐릭터로, 블록 너머 새로운 모험을 시작해요.</p><button class="button secondary" disabled>게임 연결 준비 중</button></section></div><p class="bottom-note">앞으로 연결할 무대를 미리 보여드려요. 방송·게임 접속과 에이전트 실행은 아직 지원하지 않아요.</p>`;
}
function renderRecords(char) {
  const activities = char ? data.activities.filter((event) => event.characterId === char.id) : data.activities;
  return `<section class="panel"><p class="eyebrow">YOUR STUDIO JOURNAL</p><h2>${char ? escapeHtml(char.name) + '와 함께한' : '스튜디오의'} 발자취</h2><p class="muted">캐릭터를 만들고 다듬어 온 작은 순간들을 모았어요.</p>${activities.length ? `<ul class="event-list">${activities.map((event) => `<li><span class="event-marker" aria-hidden="true">↗</span><div><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.name)} · 브라우저 데모</small></div><time datetime="${escapeHtml(event.at)}">${shortDate(event.at)}</time></li>`).join('')}</ul>` : '<div class="empty-state">아직 기록된 활동이 없어요.<br />캐릭터를 만들거나 첫 대화를 시작해 보세요.</div>'}<p class="field-help" style="margin-top:20px">이 데모에서 직접 수행한 활동만 표시해요.</p></section>`;
}
function renderDetail(char, tab) {
  const tabs = { settings: '프로필·성격', chat: '음성·Live2D 대화', memory: '기억 노트', connections: '연결', records: '기록', sample: '샘플 대화' };
  if (!Object.hasOwn(tabs, tab)) tab = 'settings';
  $('#breadcrumb').textContent = `스튜디오 / ${char.name} / ${tabs[tab]}`;
  main.innerHTML = `<a class="back-link" href="#characters">← 내 캐릭터로 돌아가기</a><div class="detail-heading"><div class="detail-avatar ${char.avatar}">${avatar(char)}</div><div><h1>${escapeHtml(char.name)}</h1><p>${escapeHtml(char.description)}</p></div><div class="detail-actions"><button class="button secondary" data-action="preview" data-id="${escapeHtml(char.id)}">외형 미리보기 ◉</button><button class="button secondary" data-action="duplicate" data-id="${escapeHtml(char.id)}">복제</button><button class="button secondary" data-action="delete" data-id="${escapeHtml(char.id)}">삭제</button></div></div><nav class="tabs" aria-label="캐릭터 관리 메뉴">${Object.entries(tabs).map(([key, label]) => `<a href="${charLink(char, key)}" class="${tab === key ? 'active' : ''}"${tab === key ? ' aria-current="page"' : ''}>${label}</a>`).join('')}</nav>`;
  if (tab === 'settings') main.innerHTML += settingsPanel(char);
  if (tab === 'chat') { main.innerHTML += chatPanel(char); setConversationFocus(true); connectRuntime(char); }
  if (tab === 'sample') { main.innerHTML += sampleChatPanel(char); renderMessages(char); }
  if (tab === 'memory') main.innerHTML += memoryPanel(char);
  if (tab === 'connections') main.innerHTML += renderConnections(char);
  if (tab === 'records') main.innerHTML += renderRecords(char);
}
function disposeRuntime() {
  if (!activeRuntime) return;
  clearTimeout(activeRuntime.timeout);
  activeRuntime.frame.contentWindow?.postMessage({ channel: 'persona-studio-runtime', instanceId: activeRuntime.instanceId, type: 'shutdown' }, activeRuntime.origin);
  activeRuntime = null;
}
function setConversationFocus(enabled) {
  document.body.classList.toggle('conversation-focus', enabled);
  const button = document.querySelector('[data-action="runtime-layout"]');
  if (button) { button.textContent = enabled ? '스튜디오 보기' : '대화에 집중'; button.setAttribute('aria-pressed', String(enabled)); }
}
function connectRuntime(char) {
  disposeRuntime();
  persist(); // Keep the browser workspace stable before giving the server its history scope.
  const frame = $('#studioFrame');
  const instanceId = crypto.randomUUID();
  const origin = runtimeOrigin();
  const payload = {
    workspace_id: data.workspaceId, character_id: char.id, name: char.name,
    description: char.description, persona: char.persona, tone: char.tone,
    avatar: char.avatar, exploration: char.exploration, greeting: char.greeting,
    memories: char.memories.slice(-50).map((memory) => memory.text.trim()).filter(Boolean),
  };
  activeRuntime = { frame, instanceId, origin, charId: char.id, payload, turns: new Set() };
  $('#runtimeStatus').textContent = `${char.name}의 설정으로 대화 서버에 연결 중…`;
  const url = new URL('/web-tool/platform/runtime/', origin);
  url.searchParams.set('studio', '1'); url.searchParams.set('parentOrigin', location.origin); url.searchParams.set('instanceId', instanceId);
  url.searchParams.set('characterId', char.id); url.searchParams.set('avatar', char.avatar);
  frame.src = url.href;
  activeRuntime.timeout = setTimeout(() => {
    if (activeRuntime?.instanceId === instanceId) $('#runtimeStatus').textContent = '대화 서버 연결을 확인해 주세요. 서버 실행 후 다시 연결할 수 있어요.';
  }, 25000);
}
window.addEventListener('message', (event) => {
  const runtime = activeRuntime;
  const message = event.data;
  if (!runtime || event.source !== runtime.frame.contentWindow || event.origin !== runtime.origin || message?.channel !== 'persona-studio-runtime' || message.instanceId !== runtime.instanceId) return;
  if (message.type === 'ready') {
    runtime.frame.contentWindow.postMessage({ channel: 'persona-studio-runtime', instanceId: runtime.instanceId, type: 'configure', profile: runtime.payload }, runtime.origin);
  } else if (message.type === 'connected') {
    clearTimeout(runtime.timeout);
    if (message.characterId !== runtime.charId || message.avatar !== runtime.payload.avatar || message.name !== runtime.payload.name) {
      disposeRuntime(); $('#studioFrame').removeAttribute('src');
      $('#runtimeStatus').textContent = '선택한 캐릭터와 다른 연결 정보가 도착해 중단했어요. 다시 연결해 주세요.';
      return;
    }
    $('#runtimeStatus').textContent = `${runtime.payload.name} · 실제 대화 연결됨`;
  } else if (message.type === 'disconnected') {
    $('#runtimeStatus').textContent = '서버 연결이 끊겼어요. 대화실에서 자동으로 재연결하고 있어요.';
  } else if (message.type === 'error') {
    clearTimeout(runtime.timeout);
    $('#runtimeStatus').textContent = '캐릭터 설정을 적용하지 못했어요. 서버와 설정을 확인한 뒤 다시 연결해 주세요.';
  } else if (message.type === 'turn-complete' && typeof message.requestId === 'string' && !runtime.turns.has(message.requestId)) {
    runtime.turns.add(message.requestId);
    const char = getCharacter(runtime.charId);
    if (!char) return;
    char.liveTurns = (Number.isSafeInteger(char.liveTurns) ? char.liveTurns : 0) + 1;
    logActivity(char, '스튜디오 음성 대화 진행'); persist();
  }
});
window.addEventListener('pagehide', disposeRuntime);
function renderShell() {
  $('#profileName').textContent = profile;
  $('#profileAvatar').textContent = profile.slice(0, 1).toUpperCase();
  $('#navCount').textContent = data.characters.length;
  $('#quickChats').innerHTML = data.characters.slice(0, 3).map((char) => `<a class="shortcut" href="${charLink(char, 'chat')}"><span class="shortcut-avatar ${char.avatar}">${avatar(char)}</span>${escapeHtml(char.name)}<span aria-hidden="true">↗</span></a>`).join('');
}
function render() {
  setConversationFocus(false);
  disposeRuntime();
  $('#loginView').hidden = Boolean(profile);
  $('#workspaceView').hidden = !profile;
  if (!profile) return;
  renderShell();
  const route = location.hash.slice(1).split('/');
  const section = ['discover', 'connections', 'records'].includes(route[0]) ? route[0] : 'characters';
  const sectionNames = { characters: '내 캐릭터', discover: '둘러보기', connections: '연결 허브', records: '활동 기록' };
  document.querySelectorAll('[data-nav]').forEach((link) => { link.classList.toggle('active', link.dataset.nav === section); if (link.dataset.nav === section) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); });
  $('#breadcrumb').textContent = `스튜디오 / ${sectionNames[section]}`;
  if (route[0] === 'character') {
    let id;
    try { id = decodeURIComponent(route[1]); } catch { id = ''; }
    const char = getCharacter(id);
    if (char) renderDetail(char, route[2]);
    else main.innerHTML = '<div class="empty-state">이 캐릭터를 찾을 수 없어요.<br /><a class="button secondary" style="margin-top:18px" href="#characters">내 캐릭터로 돌아가기</a></div>';
  } else if (section === 'discover') renderDiscover();
  else if (section === 'connections') main.innerHTML = pageHeading('BEYOND THE CONVERSATION', '캐릭터의 다음 무대.', '대화에서 방송, 게임까지. 같은 캐릭터와 더 넓은 세상으로.') + renderConnections();
  else if (section === 'records') main.innerHTML = pageHeading('STUDIO ACTIVITY', '우리가 만들어 온 이야기.', '캐릭터의 시작부터 지금까지, 스튜디오의 활동을 확인하세요.') + renderRecords();
  else renderCharacters();
  document.title = `${sectionNames[section]} · Persona Studio`;
}
function openCreate(preset) {
  $('#characterForm').reset();
  if (preset) {
    $('#characterName').value = preset.name;
    $('#characterDescription').value = preset.description;
    $('#characterTemplate').value = preset.template;
    $('#characterGreeting').value = preset.greeting;
    $('#characterForm').elements.avatar.value = preset.avatar;
  }
  $('#characterDialog').showModal();
}
async function openPreview(char) {
  const ticket = ++previewEpoch;
  avatarPreview?.destroy(); avatarPreview = null;
  // PIXI releases its WebGL context on teardown; use a fresh canvas for each preview.
  const canvas = document.createElement('canvas');
  canvas.id = 'liveAvatarCanvas';
  canvas.setAttribute('aria-label', 'Live2D 캐릭터 미리보기');
  $('#liveAvatarCanvas').replaceWith(canvas);
  $('#avatarTitle').textContent = `${char.name} · 캐릭터 미리보기`;
  $('#avatarCredit').textContent = avatarAssets[char.avatar].credit;
  $('#avatarFallback').innerHTML = avatar(char);
  $('#avatarFallback').hidden = false;
  $('#liveAvatarCanvas').hidden = true;
  $('#avatarStatus').textContent = avatarAssets[char.avatar].model ? 'Live2D 캐릭터를 불러오고 있어요…' : '나만의 캐릭터를 위한 심볼이에요. 외형을 바꾸려면 프로필에서 선택해 주세요.';
  $('#avatarDialog').showModal();
  if (!avatarAssets[char.avatar].model) return;
  try {
    const { createLivePreview } = await import('./live-preview.js');
    if (ticket !== previewEpoch) return;
    const instance = createLivePreview($('#liveAvatarCanvas'), $('#liveAvatarStage'), () => {
      if (ticket !== previewEpoch) return;
      closePreview();
      $('#liveAvatarCanvas').hidden = true;
      $('#avatarFallback').hidden = false;
      $('#avatarStatus').textContent = '그래픽 연결이 끊겨 캐릭터 이미지로 전환했어요. 설정과 대화는 계속 사용할 수 있어요.';
    });
    avatarPreview = instance;
    await instance.load(avatarAssets[char.avatar].model);
    if (ticket !== previewEpoch) { instance.destroy(); return; }
    $('#avatarFallback').hidden = true;
    $('#liveAvatarCanvas').hidden = false;
    $('#avatarStatus').textContent = '실제 Live2D 모델이에요. 모델/API 대화 없이 외형만 미리 보고 있어요.';
  } catch {
    if (ticket === previewEpoch) {
      avatarPreview?.destroy(); avatarPreview = null;
      $('#avatarStatus').textContent = '지금은 캐릭터 이미지로 보여드려요. Live2D 미리보기에는 로컬 모델과 렌더링 라이브러리가 필요해요.';
    }
  }
}
function closePreview() { ++previewEpoch; avatarPreview?.destroy(); avatarPreview = null; }
$('#avatarDialog').addEventListener('cancel', closePreview);
$('#avatarDialog').addEventListener('close', () => { if (!$('#avatarDialog').open) closePreview(); });
$('#aboutButton').addEventListener('click', () => $('#aboutDialog').showModal());
$('#sidebarCreate').addEventListener('click', () => openCreate());
$('#loginForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const name = $('#displayName').value.trim();
  if (!name) return;
  profile = name;
  try { sessionStorage.setItem(SESSION_KEY, profile); } catch { toast('현재 페이지에서만 데모 입장을 유지해요.'); }
  location.hash = 'characters'; render(); main.focus({ preventScroll: true });
  if (storageWarning) persist();
});
$('#logoutButton').addEventListener('click', () => {
  profile = '';
  try { sessionStorage.removeItem(SESSION_KEY); } catch { /* No credentials exist. */ }
  document.querySelectorAll('dialog[open]').forEach((dialog) => dialog.close());
  $('#displayName').value = '';
  render(); document.title = 'Persona Studio · 상상에 성격을 더하다'; $('#displayName').focus();
});
document.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', () => {
  const dialog = button.closest('dialog');
  if (dialog.id === 'avatarDialog') closePreview();
  dialog.close();
}));
main.addEventListener('input', (event) => {
  if (event.target.id === 'characterSearch') { searchQuery = event.target.value; renderCards(); }
  if (event.target.id === 'editExploration') $('#explorationValue').textContent = event.target.value;
  if (event.target.id === 'editName' && $('#previewName')) $('#previewName').textContent = event.target.value;
  if (event.target.id === 'editGreeting' && $('#previewGreeting')) $('#previewGreeting').textContent = `“${event.target.value}”`;
  if (event.target.name === 'avatar' && $('#settingsAvatar')) {
    const value = event.target.value;
    const char = getCharacter(event.target.closest('form').dataset.id);
    if (char && Object.hasOwn(avatarAssets, value)) { $('#settingsAvatar').className = `preview-art ${value}`; $('#settingsAvatar').innerHTML = avatar({ ...char, avatar: value }); }
  }
});
main.addEventListener('click', (event) => {
  const filter = event.target.closest('[data-filter]');
  if (filter) { collectionFilter = filter.dataset.filter; renderCards(); return; }
  const button = event.target.closest('[data-action]');
  if (!button) return;
  event.preventDefault();
  const char = getCharacter(button.dataset.id);
  const action = button.dataset.action;
  if (action === 'create') openCreate();
  if (action === 'runtime-layout') setConversationFocus(!document.body.classList.contains('conversation-focus'));
  if (action === 'runtime-connect' && char) connectRuntime(char);
  if (action === 'runtime-disconnect') {
    disposeRuntime(); $('#studioFrame').removeAttribute('src'); $('#runtimeStatus').textContent = '연결을 해제했어요. 다시 연결하면 이어서 대화할 수 있어요.';
  }
  if (action === 'preset') openCreate(catalogCharacters().find((preset) => preset.id === button.dataset.id));
  if (action === 'preview') {
    const target = button.dataset.catalog === 'true' ? catalogCharacters().find((preset) => preset.id === button.dataset.id) : char;
    if (target) openPreview(target);
  }
  if (action === 'favorite' && char) {
    char.favorite = !char.favorite; persist(); renderCards();
  }
  if (action === 'suggest') { $('#chatInput').value = button.dataset.message; $('#chatForm').requestSubmit(); }
  if (action === 'duplicate' && char) {
    const copy = { ...structuredClone(char), id: crypto.randomUUID(), name: `${char.name.slice(0, 25)} 복사본`, favorite: false, messages: [], memories: [], createdAt: now(), updatedAt: now() };
    data.characters.push(copy); logActivity(copy, '캐릭터 설정 복제'); persist('캐릭터를 복제했어요. 대화와 기억은 새로 시작해요.'); location.hash = charLink(copy);
  }
  if (action === 'delete' && char) { deleteId = char.id; $('#deleteDialog').showModal(); }
  if (action === 'remove-memory' && char) {
    char.memories = char.memories.filter((memory) => memory.id !== button.dataset.memory);
    logActivity(char, '직접 등록한 기억 삭제'); persist('기억을 삭제했어요.'); render();
  }
});
$('#characterForm').addEventListener('submit', (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const name = form.get('name').trim(), description = form.get('description').trim();
  if (!name || !description) { toast('이름과 한 줄 소개를 입력해 주세요.', true); return; }
  const char = createCharacter(crypto.randomUUID(), name, description, form.get('template'), form.get('avatar'));
  char.greeting = form.get('greeting').trim() || char.greeting;
  data.characters.push(char); logActivity(char, '새 캐릭터 생성'); persist('새로운 캐릭터를 만들었어요.');
  $('#characterDialog').close(); collectionFilter = 'all'; searchQuery = ''; location.hash = charLink(char);
});
$('#deleteForm').addEventListener('submit', (event) => {
  event.preventDefault();
  data.characters = data.characters.filter((char) => char.id !== deleteId);
  data.activities = data.activities.filter((entry) => entry.characterId !== deleteId);
  persist('캐릭터를 삭제했어요.'); $('#deleteDialog').close(); deleteId = null; location.hash = 'characters';
});
function sampleReply(char, text) {
  const polite = char.tone === '차분한 존댓말';
  if (/안녕|반가/.test(text)) return defaultGreeting(char);
  if (/할 일|과제|프로젝트|공부|계획/.test(text)) {
    if (char.template === 'curious') return polite ? '새로운 방법도 시도해 볼까요? 오늘 해보고 싶은 일 하나부터 골라보세요.' : '새로운 방법도 시도해 볼까? 오늘 제일 해보고 싶은 일 하나부터 골라보자!';
    if (char.template === 'calm') return polite ? '먼저 목표와 마감 시간을 정리해 보세요. 그다음 우선순위가 높은 일부터 작은 단계로 나눠보겠습니다.' : '먼저 목표와 마감 시간을 정리하자. 그다음 중요한 일부터 작은 단계로 나눠보면 돼.';
    return polite ? '할 일이 많아 부담스러우셨겠어요. 가장 작은 일 하나부터 함께 정리해 볼까요?' : '할 일이 많아서 막막했겠다. 가장 작은 일 하나부터 같이 정리해 보자. 내가 옆에 있을게!';
  }
  return polite ? '메시지를 확인했어요. 지금은 정해진 샘플 대화만 제공하고 있어요. “오늘 할 일이 많아”로 캐릭터별 응답 흐름을 살펴보세요.' : '이야기해 줘서 고마워! 지금은 정해진 샘플 대화만 할 수 있어. “오늘 할 일이 많아”라고 보내서 응답을 살펴봐 줘.';
}
main.addEventListener('submit', (event) => {
  event.preventDefault();
  const form = event.target, char = getCharacter(form.dataset.id);
  if (!char) return;
  const values = new FormData(form);
  if (form.id === 'settingsForm') {
    const name = values.get('name').trim(), description = values.get('description').trim(), persona = values.get('persona').trim(), greeting = values.get('greeting').trim();
    if (!name || !description || !persona || !greeting) { toast('이름, 소개, 첫 인사, 성격 지침을 입력해 주세요.', true); return; }
    Object.assign(char, { name, description, persona, greeting, avatar: values.get('avatar'), tone: values.get('tone'), exploration: Number(values.get('exploration')), updatedAt: now() });
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
window.addEventListener('hashchange', () => { render(); if (profile) { main.focus({ preventScroll: true }); window.scrollTo(0, 0); } });
render();
if (needsMigration || (storageWarning && profile)) persist();
