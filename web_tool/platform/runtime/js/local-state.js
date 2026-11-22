// Preferences persist on this browser. Draft/history identifiers belong to this tab.
const PREFERENCES_KEY = 'sogangi.preferences.v1';
const SESSION_KEY = 'sogangi.session.v1';
export const studioScenes = Object.freeze({
  night: { label: 'Mao 기본 야경', image: '/bg/ceiling-window-room-night.jpeg' },
  room: { label: '따뜻한 방', image: '/bg/room-interior-illustration.jpeg' },
  classroom: { label: '교실', image: '/bg/lernado-diff-classroom-center.jpeg' },
  campus: { label: '서강이 캠퍼스', image: '/web-tool/sogangi/assets/campus-lounge.svg' },
  plain: { label: '단색 배경', image: '' },
});
export const defaults = Object.freeze({
  muted: false,
  reducedMotion: false,
  volume: 0.8,
  rate: 1,
  background: 'campus',
  largeText: false,
  avatarRenderer: 'live2d',
});
function storage(kind) {
  try {
    return window[kind];
  } catch {
    return null;
  }
}
function read(kind, key) {
  try {
    return JSON.parse(storage(kind)?.getItem(key) || 'null');
  } catch {
    return null;
  }
}
function write(kind, key, value) {
  try {
    const target = storage(kind);
    if (!target) return false;
    target.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
function preferences(value) {
  const source = value && typeof value === 'object' ? value : {};
  const result = { ...defaults };
  for (const key of ['muted', 'reducedMotion', 'largeText'])
    if (typeof source[key] === 'boolean') result[key] = source[key];
  if (typeof source.volume === 'number' && Number.isFinite(source.volume))
    result.volume = Math.max(0, Math.min(1, source.volume));
  if ([0.85, 1, 1.15, 1.3].includes(source.rate)) result.rate = source.rate;
  if (['campus', 'paper'].includes(source.background)) result.background = source.background;
  if (['svg', 'live2d'].includes(source.avatarRenderer))
    result.avatarRenderer = source.avatarRenderer;
  return result;
}
export function loadPreferences() {
  return preferences(read('localStorage', PREFERENCES_KEY));
}
export function savePreferences(value) {
  return write('localStorage', PREFERENCES_KEY, preferences(value));
}
export function loadStudioScene(scope, avatar) {
  const stored = read('localStorage', `persona-studio.scene.v1.${scope}`);
  if (typeof stored === 'string' && Object.hasOwn(studioScenes, stored)) return stored;
  if (avatar === 'mao') {
    const previous = read('localStorage', 'backgroundUrl');
    if (typeof previous === 'string') {
      try {
        const url = new URL(previous, location.origin);
        const match = Object.entries(studioScenes).find(([, scene]) => scene.image && url.origin === location.origin && scene.image === url.pathname);
        if (match) return match[0];
      } catch { /* Ignore an unavailable previous background. */ }
    }
  }
  if (avatar === 'ivory-crown') return 'room';
  return avatar === 'sogangi' ? 'campus' : 'night';
}
export function saveStudioScene(scope, scene) {
  return Object.hasOwn(studioScenes, scene) && write('localStorage', `persona-studio.scene.v1.${scope}`, scene);
}
export function loadSession(scope = '') {
  const value = read('sessionStorage', SESSION_KEY + (scope ? `.${scope}` : ''));
  return {
    historyUid:
      typeof value?.historyUid === 'string' && /^[\w-]{1,120}$/.test(value.historyUid)
        ? value.historyUid
        : null,
    draft: typeof value?.draft === 'string' ? value.draft.slice(0, 4000) : '',
  };
}
export function saveSession(value, scope = '') {
  return write('sessionStorage', SESSION_KEY + (scope ? `.${scope}` : ''), {
    historyUid: value.historyUid || null,
    draft: String(value.draft || '').slice(0, 4000),
  });
}
