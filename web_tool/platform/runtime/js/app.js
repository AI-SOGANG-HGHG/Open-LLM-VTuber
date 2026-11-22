import { createRandomId } from '../../../shared/random-id.js';
import { AvatarRenderer } from './avatars/sogangi-renderer.js';
import { expressionFor } from './expressions.js';
import { loadPreferences, savePreferences, loadSession, saveSession, studioScenes, loadStudioScene, saveStudioScene } from './local-state.js?studio=5';
import { getStudioProfile, studioEvent, onStudioShutdown } from './studio-bridge.js';
import { StudioAvatarRenderer } from './avatars/live2d-avatar.js';
import { createHistoryView } from './history-view.js';
import { createAudioPlayback } from './audio-playback.js';
import { createMicrophone } from './microphone.js';
import { createConversationConnection } from './conversation-connection.js';
import { mountConversationShell } from './conversation-shell.js';

mountConversationShell(document.documentElement.hasAttribute('data-studio-pending'));
const studioProfile = await getStudioProfile();

(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const characterName = studioProfile?.name || '서강이';
  const historyTitle = `대화 기록 · ${characterName}`;
  const sessionScope = studioProfile ? `${studioProfile.workspace_id}.${studioProfile.character_id}` : '';
  const ui = Object.fromEntries(
    [
      'connection',
      'phase',
      'mascot',
      'avatarCanvas',
      'avatarInput',
      'avatarStatus',
      'avatarRetry',
      'mascotWrap',
      'mascotNote',
      'messages',
      'welcome',
      'notice',
      'noticeText',
      'retry',
      'composer',
      'messageInput',
      'sendButton',
      'stopButton',
      'micButton',
      'newChat',
      'soundToggle',
      'motionToggle',
      'greetButton',
      'timing',
      'historyButton',
      'historyDialog',
      'historyClose',
      'historyItems',
      'historySearch',
      'exportChat',
      'restoreQuestion',
      'settingsButton',
      'settingsDialog',
      'settingsClose',
      'settingsStatus',
      'volumeInput',
      'volumeValue',
      'rateInput',
      'backgroundInput',
      'largeTextInput',
      'reducedMotionInput',
      'mutedInput',
    ].map((id) => [id, $(id)]),
  );
  const frames = { neutral: 'neutral', joy: 'joy', thinking: 'discovery' };
  const preferences = loadPreferences();
  const avatarPreview = new URLSearchParams(location.search).get('avatar');
  if (['svg', 'live2d'].includes(avatarPreview)) {
    preferences.avatarRenderer = avatarPreview;
    savePreferences(preferences);
  }
  const savedSession = loadSession(sessionScope);
  if (studioProfile) {
    preferences.background = loadStudioScene(sessionScope, studioProfile.avatar);
    ui.backgroundInput.replaceChildren(...Object.entries(studioScenes).map(([value, scene]) => new Option(scene.label, value)));
    document.querySelector('.stage-actions').append(ui.settingsButton);
    ui.settingsButton.textContent = '대화 설정';
    document.title = `${characterName} · Persona Studio`;
    document.querySelector('.stage').setAttribute('aria-label', `${characterName} 캐릭터`);
    const conversationTitle = `대화 · ${characterName}`;
    document.querySelector('.conversation').setAttribute('aria-label', conversationTitle);
    ui.mascot.setAttribute('aria-label', `${characterName} 캐릭터`);
    ui.avatarCanvas.setAttribute('aria-label', `Live2D ${characterName}`);
    document.querySelector('label[for="messageInput"]').textContent = `${characterName}에게 보낼 말`;
    document.querySelector('.stage-copy h1').textContent = characterName;
    const description = document.querySelector('.stage-copy > p:last-child');
    description.textContent = studioProfile.description || '';
    description.hidden = !studioProfile.description;
    document.querySelector('.conversation-heading h2').textContent = conversationTitle;
    document.querySelector('#welcome p').textContent = studioProfile.greeting || '편하게 이야기해 주세요.';
    document.querySelector('#historyTitle').textContent = historyTitle;
    document.querySelector('.settings-about strong').textContent = `${characterName} · Persona Studio`;
    document.querySelector('#mascotNote').textContent = studioProfile.greeting || '반가워요!';
    document.querySelectorAll('[data-prompt]').forEach((button, index) => {
      if (index === 0) { button.textContent = '인사하기'; button.dataset.prompt = '안녕! 짧게 자기소개해 줘.'; }
    });
    document.documentElement.dataset.studioAvatar = studioProfile.avatar;
    document.querySelector('.conversation-footnote a').hidden = studioProfile.avatar !== 'sogangi';
  }
  const state = {
    ready: false,
    busy: false,
    failed: false,
    muted: preferences.muted,
    discard: false,
    assistant: null,
    studioTurn: null,
    started: 0,
    firstAudio: null,
    firstText: null,
    textStreaming: false,
    requestId: null,
    timeout: null,
    ticker: null,
    historyUid: savedSession.historyUid,
    historyPending: null,
    historyTimer: null,
    lastQuestion: null,
    lastExpression: 'neutral',
    recoverable: false,
    nextNotice: '',
  };
  let requestedConfig = false;
  const minimumSilentExpressionMs = 1500;
  const pendingExpressions = [];
  const pendingTextExpressions = [];
  let expressionHoldUntil = 0;
  let expressionTimer = null;
  const connection = createConversationConnection({
    onConnecting: prepareConnection,
    onMessage: handleServerMessage,
    onDisconnected: handleDisconnect,
    onError: () => notice('서버에 연결할 수 없어요. 서버가 실행 중인지 확인해 주세요.', true),
  });
  const historyView = createHistoryView(ui, {
    historyTitle,
    characterName,
    downloadPrefix: studioProfile ? '캐릭터' : '서강이',
    cleanMessage: clean,
    getActiveHistoryUid: () => state.historyUid,
    onRequest: () => connection.send({ type: 'fetch-history-list' }),
    onSelect: restoreHistory,
  });

  function avatarChanged() {
    ui.greetButton.disabled = !renderer.canGreet;
    ui.greetButton.title = '‘움직임 줄이기’를 켜면 인사 동작이 멈춰요.';
    ui.avatarRetry.hidden = !renderer.degraded;
    ui.avatarRetry.disabled = renderer.active === 'loading';
    ui.avatarStatus.textContent =
      renderer.active === 'loading'
        ? '캐릭터를 준비하고 있어요. 대화는 계속할 수 있어요.'
        : renderer.degraded
          ? 'Live2D를 불러오지 못해 기본 움직임을 사용하고 있어요.'
          : renderer.active === 'live2d'
            ? '표정이 바뀌고, 고개를 움직이거나 손을 흔들 수 있어요.'
            : renderer.active === 'svg'
              ? '고개 움직임과 인사 동작을 볼 수 있어요.'
              : '캐릭터를 이미지로 표시하고 있어요. 대화는 계속할 수 있어요.';
    if (studioProfile && studioProfile.avatar !== 'sogangi') {
      ui.avatarStatus.textContent = renderer.active === 'live2d' ? 'Live2D 캐릭터가 음성에 맞춰 입을 움직여요.' : renderer.active === 'loading' ? '캐릭터를 준비하고 있어요.' : '캐릭터를 이미지로 표시해요. 음성 대화는 계속 사용할 수 있어요.';
      ui.avatarInput.closest('label').hidden = true;
      ui.greetButton.textContent = '모션 재생';
      ui.greetButton.title = '기본 Live2D 모션을 재생해요.';
      ui.greetButton.hidden = studioProfile.avatar === 'symbol';
    }
  }
  const renderer = studioProfile && studioProfile.avatar !== 'sogangi'
    ? new StudioAvatarRenderer(ui.mascot, ui.avatarCanvas, avatarChanged, studioProfile.avatar)
    : new AvatarRenderer(ui.mascot, ui.avatarCanvas, avatarChanged);
  const playback = createAudioPlayback({
    preferences,
    renderer,
    canPlay: () => !state.muted && !state.failed,
    onStart(change) {
      ui.phase.textContent = '음성을 재생하고 있어요.';
      change.ready = true;
      applyPendingExpressions();
      mascot(state.lastExpression, 'speaking', '같이 이야기하자!');
    },
    onComplete: () => connection.send({ type: 'frontend-playback-complete' }),
    onError: notice,
  });
  const microphone = createMicrophone(ui, {
    isReady: () => state.ready,
    onStateChange: controls,
    onReady: ready,
    onNotice: notice,
    onDraftChange: persistSession,
  });
  renderer.init(preferences.avatarRenderer).then(() => {
    renderer.setPhase(ui.mascotWrap.dataset.state || 'idle');
    avatarChanged();
  });
  delete document.documentElement.dataset.studioPending;
  ui.messageInput.value = savedSession.draft;
  function persistSession() {
    if (!saveSession({ historyUid: state.historyUid, draft: ui.messageInput.value }, sessionScope))
      ui.timing.textContent = '입력 중인 메시지를 저장하지 못했어요. 탭을 닫기 전에 복사해 주세요.';
  }
  function applyPreferences(persist = true) {
    const wasMuted = state.muted;
    state.muted = preferences.muted;
    document.body.classList.toggle('reduce-motion', preferences.reducedMotion);
    document.body.classList.toggle('large-text', preferences.largeText);
    document.body.dataset.background = preferences.background;
    if (studioProfile) {
      const scene = studioScenes[preferences.background] || studioScenes.night;
      document.documentElement.dataset.studioScene = preferences.background;
      document.documentElement.style.setProperty('--studio-scene-image', scene.image ? `url("${scene.image}")` : 'none');
      document.querySelector('.stage-location').textContent = scene.label;
    }
    renderer.setReducedMotion(preferences.reducedMotion);
    renderer.setMode(preferences.avatarRenderer);
    ui.soundToggle.textContent = state.muted ? '음성 꺼짐' : '음성 켜짐';
    ui.soundToggle.setAttribute('aria-pressed', String(state.muted));
    ui.motionToggle.setAttribute('aria-pressed', String(preferences.reducedMotion));
    ui.motionToggle.textContent = preferences.reducedMotion ? '움직임 켜기' : '움직임 줄이기';
    ui.volumeInput.value = String(Math.round(preferences.volume * 100));
    ui.volumeValue.textContent = `${ui.volumeInput.value}%`;
    ui.rateInput.value = String(preferences.rate);
    ui.backgroundInput.value = preferences.background;
    ui.avatarInput.value = preferences.avatarRenderer;
    ui.largeTextInput.checked = preferences.largeText;
    ui.reducedMotionInput.checked = preferences.reducedMotion;
    ui.mutedInput.checked = preferences.muted;
    renderer.setMuted?.(state.muted);
    playback.updateSettings();
    if (!wasMuted && state.muted) {
      playback.stop();
      for (const change of pendingExpressions) {
        change.silent = true;
        change.ready = true;
      }
      applyPendingExpressions();
      queuePendingTextExpressions();
      playback.completeIfReady();
    }
    if (persist) {
      const sceneSaved = !studioProfile || saveStudioScene(sessionScope, preferences.background);
      const settingsSaved = savePreferences(studioProfile ? { ...preferences, background: loadPreferences().background } : preferences);
      ui.settingsStatus.textContent = sceneSaved && settingsSaved
        ? '저장했어요. 다음에 열 때도 적용돼요.'
        : '지금은 적용됐지만 저장하지 못했어요. 브라우저 저장 공간을 확인해 주세요.';
    }
  }
  function notice(text, reconnect = false, kind = 'info') {
    ui.noticeText.textContent = text;
    ui.notice.hidden = !text;
    ui.retry.hidden = !reconnect;
    ui.notice.dataset.kind = kind;
    ui.notice.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    ui.restoreQuestion.hidden = !text || !state.recoverable || !state.lastQuestion;
  }
  function setMascotExpression(frame) {
    renderer.setExpression(frame);
    if (!renderer.ready && (!studioProfile || studioProfile.avatar === 'sogangi'))
      ui.mascot
        .querySelector('image')
        ?.setAttribute('href', new URL(`../../../sogangi/assets/sogangi-${frames[frame] || frames.neutral}.svg`, import.meta.url).href);
  }
  function mascot(frame, phase, text) {
    setMascotExpression(frame);
    renderer.setPhase(phase);
    ui.mascotWrap.dataset.state = phase;
    ui.mascotNote.textContent = text;
  }
  function queueExpression(name, silent) {
    const change = { name, silent, ready: silent };
    if (name !== null && !state.failed) {
      pendingExpressions.push(change);
      applyPendingExpressions();
    }
    return change;
  }
  function queuePendingTextExpressions() {
    for (const entry of pendingTextExpressions) {
      if (entry.queued) continue;
      queueExpression(entry.name, true);
      entry.queued = true;
    }
  }
  function applyPendingExpressions() {
    if (expressionTimer !== null) return;
    while (pendingExpressions[0]?.ready) {
      const change = pendingExpressions[0];
      if (change.name === state.lastExpression) {
        pendingExpressions.shift();
        continue;
      }
      const delay = expressionHoldUntil - performance.now();
      if (delay > 0) {
        expressionTimer = setTimeout(() => {
          expressionTimer = null;
          applyPendingExpressions();
        }, delay);
        return;
      }
      pendingExpressions.shift();
      state.lastExpression = change.name;
      setMascotExpression(change.name);
      expressionHoldUntil = change.silent ? performance.now() + minimumSilentExpressionMs : 0;
    }
  }
  function clearPendingExpressions() {
    clearTimeout(expressionTimer);
    expressionTimer = null;
    expressionHoldUntil = 0;
    pendingExpressions.length = 0;
    pendingTextExpressions.length = 0;
  }
  function controls() {
    const microphoneBusy = microphone.busy;
    const blocked = !state.ready || state.busy || microphoneBusy;
    ui.messageInput.disabled = Boolean(microphoneBusy);
    ui.messageInput.placeholder = !state.ready
      ? '연결을 기다리는 동안 메시지를 적어 둘 수 있어요.'
      : state.busy
        ? '답변을 기다리는 동안 다음 메시지를 적어 둘 수 있어요.'
        : '메시지를 입력해 주세요.';
    ui.sendButton.disabled = blocked;
    ui.newChat.disabled = !state.ready || state.busy || Boolean(microphoneBusy);
    ui.historyButton.disabled = !state.ready || state.busy || Boolean(microphoneBusy);
    ui.stopButton.disabled = !state.busy;
    ui.micButton.disabled = !state.ready || state.busy;
    ui.exportChat.disabled = state.busy || !ui.messages.querySelector('.message');
    for (const b of document.querySelectorAll('[data-prompt]')) b.disabled = blocked;
  }
  function clean(text) {
    return String(text || '')
      .replace(/\[(neutral|anger|disgust|fear|joy|smirk|sadness|surprise)\]/gi, '')
      .replace(/\[(neutral|anger|disgust|fear|joy|smirk|sadness|surprise)$/gi, '')
      .trim();
  }
  function message(role, text = '') {
    ui.welcome.hidden = true;
    const node = document.createElement('div');
    node.className = `message ${role}`;
    const label = document.createElement('span');
    label.className = 'message-label';
    label.textContent = role === 'user' ? '나' : characterName;
    const body = document.createElement('div');
    body.className = 'message-body';
    body.textContent = role === 'user' ? String(text || '') : clean(text);
    node.append(label, body);
    ui.messages.append(node);
    ui.messages.scrollTop = ui.messages.scrollHeight;
    return { node, body };
  }
  function appendAssistant(text) {
    text = clean(text);
    if (!text) return;
    if (!state.assistant) {
      state.assistant = message('assistant');
      if (state.studioTurn) state.assistant.node.append(studioTurnDetails(state.studioTurn));
    }
    state.assistant.body.textContent += (state.assistant.body.textContent ? ' ' : '') + text;
    ui.messages.scrollTop = ui.messages.scrollHeight;
  }
  function studioTurnDetails({ preset, affect, previous_affect, appraisal, retrieval, rule_selection, rules, memories, unverified_memories = [], task_states = [] }) {
    const details = document.createElement('details');
    details.className = 'studio-turn-context';
    const summary = document.createElement('summary');
    summary.textContent = unverified_memories.length
      ? `${preset.label} · 기억 후보 ${unverified_memories.length}개`
      : `${preset.label} · 불러온 기억 ${memories.length}개`;
    const mood = document.createElement('p');
    const transition = (axis) => previous_affect
      ? `${previous_affect[axis].toFixed(2)} → ${affect[axis].toFixed(2)}`
      : affect[axis].toFixed(2);
    const affectChanged = !previous_affect || Object.keys(affect).some(axis => affect[axis] !== previous_affect[axis]);
    const moodLabel = appraisal === 'ok' && affectChanged ? '캐릭터 감정 변화' : '이전 감정 유지';
    mood.textContent = `${moodLabel} · 쾌·불쾌 ${transition('valence')} · 각성 ${transition('arousal')} · 통제감 ${transition('dominance')}`;
    details.append(summary, mood);
    const taskStatuses = { not_started: '시작 전', in_progress: '진행 중', completed: '완료' };
    for (const task of task_states) {
      const item = document.createElement('p');
      item.textContent = `현재 과제 · ${task.title} · ${taskStatuses[task.status]}`;
      details.append(item);
    }
    const evidence = document.createElement('p');
    evidence.textContent = unverified_memories.length ? '답변에 전달한 기억 후보 · 답변 모델이 관련성을 판단해요.'
      : retrieval !== 'ok' ? '기억 검색을 사용할 수 없었어요.'
      : appraisal !== 'ok' ? '기억의 관련성을 확인하지 못했어요.' : '답변에 전달된 기억';
    details.append(evidence);
    const list = document.createElement('ul');
    for (const memory of [...memories, ...unverified_memories]) {
      const item = document.createElement('li');
      const source = memory.source === 'manual_note' ? '기억 노트' : '이 캐릭터와의 이전 대화';
      item.textContent = `${source} · ${memory.text}`;
      list.append(item);
    }
    if (list.childElementCount) details.append(list);
    else if (retrieval === 'ok' && appraisal === 'ok') evidence.textContent += ' 없음';
    const traitLabels = {
      openness: '개방성', conscientiousness: '성실성', extraversion: '외향성',
      agreeableness: '친화성', neuroticism: '정서 민감도',
    };
    const appliedRules = rules.map(rule => {
      const trait = traitLabels[rule.trait];
      return trait ? `${trait} ${rule.direction === 'high' ? '높음' : '낮음'} · ${rule.behavior}` : rule.behavior;
    });
    if (rule_selection === 'unavailable') appliedRules.push('적용할 규칙을 확인하지 못했어요.');
    else if (!appliedRules.length && retrieval === 'ok' && (rule_selection || appraisal === 'ok')) appliedRules.push('적용된 규칙 없음');
    for (const behavior of appliedRules) {
      const item = document.createElement('p');
      item.textContent = `행동 규칙 · ${behavior}`;
      details.append(item);
    }
    return details;
  }
  function clearTimers() {
    clearTimeout(state.timeout);
    clearInterval(state.ticker);
    state.timeout = null;
    state.ticker = null;
  }
  function ready() {
    state.busy = false;
    clearTimers();
    controls();
    ui.phase.textContent = '메시지를 보낼 수 있어요.';
    mascot(state.lastExpression, 'idle', '네 이야기를 듣고 있어');
  }
  function interrupt(reason = '') {
    if (!state.busy) return;
    connection.send({ type: 'interrupt-signal', text: state.assistant?.body.textContent || '' });
    state.discard = true;
    playback.cancelTurn();
    clearPendingExpressions();
    state.recoverable = Boolean(reason);
    ready();
    if (reason) notice(reason);
  }
  function begin(text) {
    if (!state.ready || state.busy || !text.trim()) return;
    notice('');
    playback.startTurn();
    clearPendingExpressions();
    state.discard = false;
    state.busy = true;
    state.failed = false;
    state.recoverable = false;
    state.lastQuestion = text;
    state.lastExpression = 'neutral';
    state.assistant = null;
    state.studioTurn = null;
    state.firstAudio = null;
    state.firstText = null;
    state.textStreaming = false;
    state.requestId = createRandomId();
    state.started = performance.now();
    message('user', text);
    ui.messageInput.value = '';
    persistSession();
    controls();
    ui.phase.textContent = '답변을 기다리고 있어요 · 0초';
    mascot('thinking', 'waiting', '잠깐 생각해 볼게');
    state.ticker = setInterval(() => {
      if (state.firstAudio === null && state.busy)
        ui.phase.textContent = `${state.firstText === null ? '답변을 기다리고 있어요' : '음성을 준비하고 있어요'} · ${Math.floor((performance.now() - state.started) / 1000)}초`;
    }, 1000);
    state.timeout = setTimeout(
      () => interrupt('답변이 오래 걸려 요청을 멈췄어요. 다시 질문해 주세요.'),
      90000,
    );
    connection.send({
      type: 'text-input',
      text,
      text_stream: true,
      require_spoken_response: true,
      request_id: state.requestId,
    });
  }
  function newHistory() {
    if (state.busy) return;
    notice('');
    state.ready = false;
    controls();
    historyDeadline({ kind: 'new' });
    connection.send({ type: 'create-new-history' });
  }
  function historyDeadline(pending) {
    clearTimeout(state.historyTimer);
    state.historyPending = pending;
    state.historyTimer = setTimeout(() => {
      if (!state.historyPending) return;
      connection.restartAfterFailure('History response timeout');
    }, 12000);
  }
  function restoreHistory(uid, resuming = false) {
    state.ready = false;
    controls();
    ui.historyDialog.close();
    ui.phase.textContent = '이전 대화를 불러오고 있어요.';
    historyDeadline({ kind: 'fetch', uid, resuming });
    connection.send({ type: 'fetch-and-set-history', history_uid: uid });
  }
  function historyReady(uid) {
    clearTimeout(state.historyTimer);
    state.historyPending = null;
    state.historyUid = uid;
    state.ready = true;
    state.discard = false;
    connection.markReady();
    persistSession();
    ui.connection.textContent = '연결됨';
    ui.connection.className = 'connection connected';
    ready();
    studioEvent('connected', { historyUid: uid, agentId: studioProfile?.agent_id, characterId: studioProfile?.character_id, avatar: studioProfile?.avatar, name: characterName });
  }
  function resetMessages() {
    renderer.cancelGesture();
    for (const node of ui.messages.querySelectorAll('.message')) node.remove();
    ui.welcome.hidden = false;
    state.assistant = null;
    state.studioTurn = null;
    state.lastQuestion = null;
    clearPendingExpressions();
    state.recoverable = false;
    ui.timing.textContent = '답변에는 틀린 내용이 있을 수 있어요.';
  }
  function prepareConnection() {
    requestedConfig = false;
    clearPendingExpressions();
    clearTimeout(state.historyTimer);
    state.historyPending = null;
    microphone.cancel();
    state.ready = false;
    state.busy = false;
    state.discard = true;
    clearTimers();
    playback.stop();
    controls();
    notice('');
    ui.connection.className = 'connection';
    ui.connection.textContent = '연결 중';
    ui.phase.textContent = '대화방을 준비하고 있어요.';
  }
  function handleServerMessage(data) {
    if (data.request_id && data.request_id !== state.requestId) return;
    if (data.type === 'set-model-and-conf' && !requestedConfig) {
      requestedConfig = true;
      if (studioProfile) {
        connection.send({
          type: 'apply-studio-persona',
          workspace_id: studioProfile.workspace_id,
          agent_id: studioProfile.agent_id,
        });
      } else connection.send({ type: 'switch-config', file: 'ko_sogangi.yaml' });
    } else if (data.type === 'studio-persona-error') {
      notice('캐릭터 설정을 불러오지 못했어요. 스튜디오에서 다시 연결해 주세요.', false, 'error');
      studioEvent('error', { code: data.code });
    } else if (data.type === 'config-switched' || data.type === 'studio-persona-applied') {
      if (studioProfile && (
        data.type !== 'studio-persona-applied'
        || data.agent_id !== studioProfile.agent_id
        || data.character_id !== studioProfile.character_id
        || data.avatar !== studioProfile.avatar
        || data.name !== studioProfile.name
      )) {
        notice('다른 캐릭터로 연결되어 대화를 멈췄어요.', false, 'error');
        studioEvent('error', { code: 'character_mismatch' });
        connection.dispose();
        return;
      }
      if (state.historyUid) restoreHistory(state.historyUid, true);
      else newHistory();
    } else if (data.type === 'new-history-created') {
      resetMessages();
      historyReady(data.history_uid);
      notice(state.nextNotice);
      state.nextNotice = '';
    } else if (data.type === 'history-list') {
      historyView.showList(Array.isArray(data.histories) ? data.histories : []);
    } else if (data.type === 'history-data') {
      const pending = state.historyPending;
      if (
        !pending ||
        pending.kind !== 'fetch' ||
        (data.history_uid && data.history_uid !== pending.uid)
      )
        return;
      resetMessages();
      for (const item of data.messages || []) {
        if (item.role === 'human' || item.role === 'ai')
          message(item.role === 'human' ? 'user' : 'assistant', item.content);
      }
      historyReady(data.history_uid || pending.uid);
      notice('이전 대화를 불러왔어요.');
    } else if (data.type === 'history-error') {
      const pending = state.historyPending;
      if (!pending || (data.history_uid && pending.uid !== data.history_uid)) return;
      clearTimeout(state.historyTimer);
      state.historyPending = null;
      if (pending.kind === 'fetch' && pending.resuming) {
        state.historyUid = null;
        persistSession();
        state.nextNotice =
          '이전 대화를 불러오지 못해 새 대화를 열었어요.';
        newHistory();
      } else if (pending.kind === 'fetch' && state.historyUid) {
        state.ready = true;
        ready();
        notice('선택한 대화를 불러오지 못했어요. 지금 대화는 그대로 이어갈 수 있어요.');
      } else {
        connection.restartAfterFailure('History unavailable');
      }
    } else if (data.type === 'studio-turn-context' && studioProfile && state.busy && !state.discard) {
      state.studioTurn = data;
    } else if (data.type === 'text-response' && state.busy && !state.discard) {
      state.textStreaming = true;
      if (state.firstText === null) state.firstText = performance.now() - state.started;
      const text = data.display_text?.text;
      appendAssistant(text);
      const name = expressionFor(text);
      if (name !== null && !state.failed) {
        pendingTextExpressions.push({ text, name, queued: state.muted });
        if (state.muted) queueExpression(name, true);
      }
      ui.timing.textContent = `첫 문장 ${(state.firstText / 1000).toFixed(1)}초`;
    } else if (data.type === 'audio' && state.busy && !state.discard) {
      const text = data.display_text?.text;
      if (!state.textStreaming) appendAssistant(text);
      const textIndex = pendingTextExpressions.findIndex((entry) => entry.text === text);
      const textExpression = textIndex < 0 ? null : pendingTextExpressions.splice(textIndex, 1)[0];
      // Text may already have queued this expression while sound was muted.
      const expression = textExpression?.queued ? null : expressionFor(text);
      if (state.muted || !data.audio) queueExpression(expression, true);
      if (data.audio) {
        if (state.firstAudio === null) {
          state.firstAudio = performance.now() - state.started;
          ui.timing.textContent = `${state.firstText !== null ? `첫 문장 ${(state.firstText / 1000).toFixed(1)}초 · ` : ''}첫 음성 ${(state.firstAudio / 1000).toFixed(1)}초`;
        }
        if (!state.muted && !state.failed) {
          playback.enqueue({
            audio: data.audio,
            volumes: data.volumes,
            slice: data.slice_length,
            // Apply the change when playback starts. An empty tag keeps the current face.
            expression: queueExpression(expression, false),
          });
        }
      }
    } else if (data.type === 'backend-synth-complete' && state.busy && !state.discard) {
      playback.finishSynthesis();
    } else if (
      data.type === 'control' &&
      data.text === 'conversation-chain-end' &&
      state.busy &&
      !state.discard
    ) {
      queuePendingTextExpressions();
      pendingTextExpressions.length = 0;
      if (!state.failed && state.assistant?.body.textContent) studioEvent('turn-complete', { requestId: state.requestId });
      if (!state.failed && !state.assistant?.body.textContent) {
        state.recoverable = true;
        notice('답변을 끝까지 받지 못했어요. 이전 질문을 불러와 다시 보낼 수 있어요.');
      }
      ready();
    } else if (data.type === 'error') {
      clearPendingExpressions();
      state.recoverable = Boolean(state.lastQuestion);
      notice('답변을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.', !state.ready, 'error');
      if (state.busy) {
        state.failed = true;
        playback.stop();
        playback.completeIfReady();
        ui.phase.textContent = '답변을 마무리하고 있어요.';
      }
    }
  }
  function handleDisconnect(delay) {
    clearTimeout(state.historyTimer);
    state.historyPending = null;
    clearPendingExpressions();
    ui.historyDialog.close();
    microphone.cancel();
    state.ready = false;
    state.discard = true;
    state.busy = false;
    playback.cancelTurn();
    clearTimers();
    controls();
    ui.connection.textContent = '연결 끊김';
    ui.connection.className = 'connection disconnected';
    studioEvent('disconnected');
    ui.phase.textContent = '서버 연결을 확인해 주세요.';
    mascot(state.lastExpression, 'idle', '잠깐 연결을 기다릴게');
    if (delay !== null) {
      notice(
        `연결이 끊겼어요. ${delay / 1000}초 뒤에 다시 연결해 이전 대화를 불러와요.`,
        true,
      );
    } else {
      notice(
        '서버에 연결할 수 없어요. 서버를 확인한 뒤 ‘다시 연결’을 눌러 주세요. 입력 중인 메시지는 남아 있어요.',
        true,
      );
    }
  }
  ui.composer.addEventListener('submit', (event) => {
    event.preventDefault();
    begin(ui.messageInput.value);
  });
  ui.messageInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      begin(ui.messageInput.value);
    }
  });
  ui.messageInput.addEventListener('input', persistSession);
  for (const b of document.querySelectorAll('[data-prompt]'))
    b.addEventListener('click', () => begin(b.dataset.prompt));
  ui.stopButton.addEventListener('click', () =>
    interrupt('답변을 중단했어요. 다른 메시지를 보낼 수 있어요.'),
  );
  ui.newChat.addEventListener('click', newHistory);
  ui.retry.addEventListener('click', connection.retry);
  ui.restoreQuestion.addEventListener('click', () => {
    if (!state.lastQuestion) return;
    if (ui.messageInput.value.trim()) {
      notice('이전 질문을 불러오려면 입력 중인 메시지를 먼저 보내거나 지워 주세요.');
      return;
    }
    ui.messageInput.value = state.lastQuestion;
    persistSession();
    ui.messageInput.focus();
    notice('이전 질문을 불러왔어요. 확인한 뒤 ‘보내기’를 눌러 주세요.');
  });
  ui.settingsButton.addEventListener('click', () => ui.settingsDialog.showModal());
  ui.settingsClose.addEventListener('click', () => ui.settingsDialog.close());
  for (const [id, key, read] of [
    ['volumeInput', 'volume', (el) => Number(el.value) / 100],
    ['rateInput', 'rate', (el) => Number(el.value)],
    ['backgroundInput', 'background', (el) => el.value],
    ['avatarInput', 'avatarRenderer', (el) => el.value],
    ['largeTextInput', 'largeText', (el) => el.checked],
    ['reducedMotionInput', 'reducedMotion', (el) => el.checked],
    ['mutedInput', 'muted', (el) => el.checked],
  ])
    ui[id].addEventListener(id === 'volumeInput' ? 'input' : 'change', () => {
      preferences[key] = read(ui[id]);
      applyPreferences();
    });
  ui.soundToggle.addEventListener('click', () => {
    preferences.muted = !preferences.muted;
    applyPreferences();
  });
  ui.motionToggle.addEventListener('click', () => {
    preferences.reducedMotion = !preferences.reducedMotion;
    applyPreferences();
  });
  ui.greetButton.addEventListener('click', () => {
    if (renderer.greet() && !state.busy) ui.mascotNote.textContent = studioProfile?.greeting || (studioProfile ? '반가워요!' : '반가워, 학우야!');
  });
  ui.avatarRetry.addEventListener('click', () =>
    renderer.setMode(preferences.avatarRenderer, { force: true }),
  );
  const stage = ui.mascotWrap.closest('.stage');
  stage.addEventListener('pointermove', (event) => {
    if (event.pointerType !== 'mouse') return;
    const bounds = stage.getBoundingClientRect();
    renderer.lookAt(
      ((event.clientX - bounds.left) / bounds.width - 0.5) * 2,
      ((event.clientY - bounds.top) / bounds.height - 0.5) * 2,
    );
  });
  stage.addEventListener('pointerleave', () => renderer.lookAt());
  function dispose() {
    connection.dispose();
    clearTimeout(state.historyTimer);
    clearTimers();
    clearPendingExpressions();
    microphone.cancel();
    playback.stop();
    renderer.dispose();
  }
  window.addEventListener('pagehide', () => {
    persistSession();
    dispose();
  });
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) location.reload();
  });
  window.addEventListener('online', () => {
    if (!state.ready) connection.retry();
  });
  applyPreferences(false);
  onStudioShutdown(dispose);
  connection.connect();
})();
