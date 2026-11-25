export const state = {
  data: undefined,
  profile: '',
  collectionFilter: 'all',
  searchQuery: '',
  storageWarning: false,
  needsMigration: false,
};

export function getCharacter(id) { return state.data.characters.find((char) => char.id === id); }

const DRAFTS_KEY = 'persona-studio.profile-drafts.v1';
function loadProfileDrafts() {
  try { return new Map(JSON.parse(sessionStorage.getItem(DRAFTS_KEY) || '[]')); }
  catch { return new Map(); }
}
export const profileDrafts = loadProfileDrafts();

export function profileDraftKey(char) {
  return JSON.stringify([state.profile, state.data.workspaceId, char.id]);
}

export function storeProfileDraft(key, draft) {
  if (draft) profileDrafts.set(key, draft);
  else if (!profileDrafts.delete(key)) return;
  try {
    if (profileDrafts.size) sessionStorage.setItem(DRAFTS_KEY, JSON.stringify([...profileDrafts]));
    else sessionStorage.removeItem(DRAFTS_KEY);
  } catch { /* In-page navigation still retains the draft. */ }
}

export function clearProfileDrafts() {
  profileDrafts.clear();
  try { sessionStorage.removeItem(DRAFTS_KEY); } catch { /* No persistent drafts. */ }
}
