export const state = {
  data: undefined,
  profile: '',
  collectionFilter: 'all',
  searchQuery: '',
  storageWarning: false,
  needsMigration: false,
};

export function getCharacter(id) { return state.data.characters.find((char) => char.id === id); }
