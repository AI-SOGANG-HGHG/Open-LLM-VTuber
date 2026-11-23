const studioCopy = {
  name: "캐릭터",
  stageLabel: "캐릭터",
  stageEyebrow: "",
  stageIntro: "",
  avatarLabel: "캐릭터 로딩 중",
  conversationLabel: "캐릭터와 대화",
  conversationEyebrow: "",
  conversationHeading: "대화",
  initialStatus: "대화방을 준비하고 있어요.",
  welcomeHeading: "",
  welcomeText: "편하게 이야기해 주세요.",
  introPrompt: "안녕, 짧게 자기소개해 줘.",
  introButton: "안녕, 반가워",
  restoreQuestion: "이전 질문 불러오기",
  messageLabel: "캐릭터에게 보낼 말",
  messagePlaceholder: "메시지를 입력해 주세요.",
  answerNotice: "답변에는 틀린 내용이 있을 수 있어요.",
  historyEyebrow: "",
  historyHeading: "대화 기록",
  historyHelp: "대화를 선택하면 이어서 이야기할 수 있어요.",
  settingsHeading: "대화 설정",
  volumeLabel: "음성 크기",
  avatarRetry: "Live2D 다시 불러오기",
  storageHelp: "대화는 서버에 저장돼요. 입력 중인 메시지는 이 탭을 새로고침해도 남아 있어요.",
};

const standaloneCopy = {
  name: "서강이",
  stageLabel: "서강이 캐릭터",
  stageEyebrow: "<p class=\"eyebrow\">YOUR CAMPUS COMPANION</p>",
  stageIntro: "여기서, 같이.",
  avatarLabel: "서강대학교 공식 캐릭터 서강이",
  conversationLabel: "서강이와 대화",
  conversationEyebrow: "<p class=\"eyebrow\">OUR CONVERSATION</p>",
  conversationHeading: "오늘은 무슨 이야기할까?",
  initialStatus: "대화방을 준비하고 있어",
  welcomeHeading: "<h3>오늘은 어떤 하루야?</h3>",
  welcomeText: "편하게 한마디 건네 줘.<br />작은 고민부터 같이 풀어보자.",
  introPrompt: "서강아, 짧게 자기소개해 줘.",
  introButton: "서강아, 반가워",
  restoreQuestion: "질문 다시 쓰기",
  messageLabel: "서강이에게 보낼 말",
  messagePlaceholder: "서강아, 오늘은…",
  answerNotice: "답변 내용은 확인이 필요할 수 있어요.",
  historyEyebrow: "<p class=\"eyebrow\">PREVIOUS CONVERSATIONS</p>",
  historyHeading: "서강이와 나눈 이야기",
  historyHelp: "이 PC의 서강이 대화 기록이에요. 선택하면 이어서 이야기할 수 있어요.",
  settingsHeading: "나에게 맞게",
  volumeLabel: "목소리 크기",
  avatarRetry: "Live2D 다시 읽기",
  storageHelp: "이 탭의 대화와 초안은 새로고침 후 이어져요. 대화 원문은 로컬 서버에, 초안은 이 탭의 브라우저 저장소에 남아요.",
};

export function mountConversationShell(studio) {
  const copy = studio ? studioCopy : standaloneCopy;
  const sogangiHome = new URL('../../../sogangi/', import.meta.url);
  const planUrl = new URL('live2d-plan.html', sogangiHome).href;
  const avatarImage = studio
    ? new URL('../../assets/mark.svg', import.meta.url).href
    : new URL('assets/sogangi-neutral.svg', sogangiHome).href;
  document.body.innerHTML = `
    <header class="topbar">
      <a class="brand" href="${sogangiHome.href}" aria-label="${copy.name} 프로젝트룸 홈"
        ><span class="brand-mark" aria-hidden="true">S</span
        ><span>${copy.name} <b>프로젝트룸</b></span></a
      >
      <div class="header-right">
        <button id="settingsButton" class="quiet-button" type="button">설정</button>
        <span class="prototype-tag">서강대학교 학생 프로젝트</span
        ><span id="connection" class="connection" role="status">연결 중</span>
      </div>
    </header>
    <main class="workspace">
      <section class="stage" aria-label="${copy.stageLabel}">
        <div class="stage-copy">
          ${copy.stageEyebrow}
          <h1>${copy.name}</h1>
          <p>${copy.stageIntro}</p>
        </div>
        <div class="mascot-wrap" id="mascotWrap" data-state="idle">
          <div class="mascot-halo" aria-hidden="true"></div>
          <span class="mascot-note" id="mascotNote">반가워, 학우야!</span>
          <svg
            id="mascot"
            class="mascot"
            viewBox="0 0 270 337"
            role="img"
            aria-label="${copy.avatarLabel}"
          >
            <image href="${avatarImage}" width="270" height="337" />
          </svg>
          <canvas
            id="avatarCanvas"
            class="mascot mascot-live2d"
            role="img"
            aria-label="Live2D ${copy.name}"
            aria-hidden="true"
            hidden
          ></canvas>
          <div class="mascot-shadow" aria-hidden="true"></div>
        </div>
        <div class="stage-bottom">
          <span class="stage-location"><span aria-hidden="true">●</span> 캠퍼스 라운지</span>
          <div class="stage-actions">
            <button id="greetButton" class="quiet-button" type="button" disabled>손 흔들기</button>
            <button id="motionToggle" class="quiet-button" type="button" aria-pressed="false">
              움직임 줄이기
            </button>
          </div>
        </div>
      </section>
      <section class="conversation" aria-label="${copy.conversationLabel}">
        <div class="conversation-heading">
          <div>
            ${copy.conversationEyebrow}
            <h2>${copy.conversationHeading}</h2>
          </div>
          <div class="conversation-actions">
            <button id="historyButton" class="quiet-button" type="button" disabled>기록</button>
            <button
              id="newChat"
              class="icon-button"
              type="button"
              title="새 대화"
              aria-label="새 대화"
            >
              ＋
            </button>
          </div>
        </div>
        <div class="conversation-toolbar">
          <span id="phase" role="status" aria-live="polite">${copy.initialStatus}</span
          ><button id="soundToggle" class="quiet-button" type="button" aria-pressed="false">
            음성 켜짐
          </button>
        </div>
        <div id="messages" class="messages" role="log" aria-label="대화 기록" aria-live="polite">
          <div class="welcome" id="welcome">
            <span class="welcome-spark" aria-hidden="true">✳</span>
            ${copy.welcomeHeading}
            <p>${copy.welcomeText}</p>
            <div class="suggestions">
              <button type="button" data-prompt="${copy.introPrompt}">${copy.introButton}</button
              ><button type="button" data-prompt="프로젝트를 시작하려는데 첫 할 일을 같이 정해 줘.">
                프로젝트 같이 시작하기</button
              ><button type="button" data-prompt="오늘 공부하느라 지쳤어. 짧게 응원해 줘.">
                응원이 필요해
              </button>
            </div>
          </div>
        </div>
        <div id="notice" class="notice" role="alert" hidden>
          <span id="noticeText"></span
          ><button id="retry" class="quiet-button" type="button" hidden>다시 연결</button>
          <button id="restoreQuestion" class="quiet-button" type="button" hidden>
            ${copy.restoreQuestion}
          </button>
        </div>
        <form id="composer" class="composer">
          <label class="sr-only" for="messageInput">${copy.messageLabel}</label
          ><textarea
            id="messageInput"
            rows="2"
            maxlength="4000"
            placeholder="${copy.messagePlaceholder}"
            disabled
          ></textarea>
          <div class="composer-bottom">
            <div class="composer-tools">
              <button
                id="micButton"
                class="quiet-button"
                type="button"
                disabled
                aria-pressed="false"
              >
                마이크</button
              ><button id="stopButton" class="quiet-button stop" type="button" disabled>
                멈추기
              </button>
            </div>
            <button
              id="sendButton"
              class="send-button"
              type="submit"
              disabled
              aria-label="메시지 보내기"
            >
              보내기 <span aria-hidden="true">↗</span>
            </button>
          </div>
        </form>
        <div class="conversation-footnote">
          <span id="timing">${copy.answerNotice}</span
          ><a
            href="https://pr.sogang.ac.kr/front/boardview.do?bbsConfigFK=264&amp;pkid=901406"
            target="_blank"
            rel="noopener noreferrer"
            >캐릭터 출처 ↗</a
          >
        </div>
      </section>
    </main>
    <dialog id="historyDialog" aria-labelledby="historyTitle">
      <div class="history-heading">
        <div>
          ${copy.historyEyebrow}
          <h2 id="historyTitle">${copy.historyHeading}</h2>
        </div>
        <button id="historyClose" class="icon-button" type="button" aria-label="대화 기록 닫기">
          ×
        </button>
      </div>
      <p class="history-help">
        ${copy.historyHelp}
      </p>
      <label class="sr-only" for="historySearch">대화 기록 검색</label>
      <input
        id="historySearch"
        class="history-search"
        type="search"
        placeholder="최근 대화 내용으로 찾기"
        autocomplete="off"
      />
      <button id="exportChat" class="quiet-button" type="button" disabled>
        현재 대화 내려받기
      </button>
      <div id="historyItems" class="history-items" role="list"></div>
    </dialog>
    <dialog id="settingsDialog" class="settings-dialog" aria-labelledby="settingsTitle">
      <div class="history-heading">
        <h2 id="settingsTitle">${copy.settingsHeading}</h2>
        <button id="settingsClose" class="icon-button" type="button" aria-label="설정 닫기">
          ×
        </button>
      </div>
      <p class="settings-help">이 브라우저에서 사용하는 설정이에요.</p>
      <label class="setting-row" for="volumeInput"
        ><span>${copy.volumeLabel} <output id="volumeValue" for="volumeInput">80%</output></span>
        <input id="volumeInput" type="range" min="0" max="100" step="5" value="80" />
      </label>
      <label class="setting-row" for="rateInput"
        ><span>말하는 속도</span>
        <select id="rateInput">
          <option value="0.85">천천히 · 0.85배</option>
          <option value="1" selected>보통 · 1배</option>
          <option value="1.15">조금 빠르게 · 1.15배</option>
          <option value="1.3">빠르게 · 1.3배</option>
        </select>
      </label>
      <label class="setting-row" for="backgroundInput"
        ><span>배경</span>
        <select id="backgroundInput">
          <option value="campus">캠퍼스 라운지</option>
          <option value="paper">차분한 단색</option>
        </select>
      </label>
      <label class="setting-check"
        ><input id="largeTextInput" type="checkbox" />대화 글씨 크게</label
      >
      <label class="setting-row" for="avatarInput"
        ><span>캐릭터 움직임</span>
        <select id="avatarInput">
          <option value="live2d">Live2D · 표정·고개·호흡·인사</option>
          <option value="svg">SVG 모션 · 고개·인사</option>
        </select>
      </label>
      <p id="avatarStatus" class="settings-status" role="status">캐릭터를 준비하고 있어요.</p>
      <button id="avatarRetry" class="quiet-button" type="button" hidden>${copy.avatarRetry}</button>
      <label class="setting-check"
        ><input id="reducedMotionInput" type="checkbox" />움직임 줄이기</label
      >
      <label class="setting-check"><input id="mutedInput" type="checkbox" />음성 끄기</label>
      <p id="settingsStatus" class="settings-status" role="status">설정은 바꾸는 즉시 적용돼요.</p>
      <div class="settings-about">
        <strong>${copy.name} · 로컬 개발 버전</strong>
        <p>AI의 답변은 틀릴 수 있어요. 학교 공식 행정 서비스가 아니에요.</p>
        <p>
          ${copy.storageHelp}
        </p>
      </div>
    </dialog>
    <footer class="page-footer">
      <span>서강대학교 캐릭터로 만드는, 우리만의 AI 동반자.</span
      ><a href="${planUrl}">Live2D 제작 설계 ↗</a>
      <a href="/">기존 Live2D 화면으로 ↗</a>
    </footer>
  `;
}
