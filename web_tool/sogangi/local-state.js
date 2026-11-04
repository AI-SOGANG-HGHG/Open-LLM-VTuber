// Preferences persist on this browser. Draft/history identifiers belong to this tab.
const PREFERENCES_KEY = 'sogangi.preferences.v1';
const SESSION_KEY = 'sogangi.session.v1';
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
export function loadSession() {
  const value = read('sessionStorage', SESSION_KEY);
  return {
    historyUid:
      typeof value?.historyUid === 'string' && /^[\w-]{1,120}$/.test(value.historyUid)
        ? value.historyUid
        : null,
    draft: typeof value?.draft === 'string' ? value.draft.slice(0, 4000) : '',
  };
}
export function saveSession(value) {
  return write('sessionStorage', SESSION_KEY, {
    historyUid: value.historyUid || null,
    draft: String(value.draft || '').slice(0, 4000),
  });
}
