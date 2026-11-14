const query = new URLSearchParams(location.search);
let connection;
export function studioEvent(type, detail = {}) {
  if (connection) parent.postMessage({ channel: 'persona-studio-runtime', instanceId: connection.instanceId, type, ...detail }, connection.origin);
}
export async function getStudioProfile() {
  if (query.get('studio') !== '1') return null;
  if (parent === window) throw Error('Studio runtime must be opened inside the Studio');
  const origin = query.get('parentOrigin');
  const instanceId = query.get('instanceId');
  const expected = new URL(origin);
  const local = (name) => ['localhost', '127.0.0.1', '[::1]'].includes(name);
  if (expected.origin !== origin || !['http:', 'https:'].includes(expected.protocol)
      || (origin !== location.origin && !(local(expected.hostname) && local(location.hostname) && expected.protocol === location.protocol))) throw Error('Invalid Studio origin');
  if (!instanceId || !/^[\w-]{1,100}$/.test(instanceId)) throw Error('Invalid Studio instance');
  connection = { origin, instanceId };
  document.documentElement.dataset.studio = 'true';
  const css = document.createElement('link');
  css.rel = 'stylesheet'; css.href = './studio.css?v=5'; document.head.append(css);
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { window.removeEventListener('message', receive); reject(Error('Studio settings not received')); }, 20000);
    function receive(event) {
      if (event.source !== parent || event.origin !== origin || event.data?.channel !== 'persona-studio-runtime' || event.data.instanceId !== instanceId || event.data.type !== 'configure') return;
      const profile = event.data.profile;
      if (!profile || typeof profile.name !== 'string' || !['sogangi', 'mao', 'symbol'].includes(profile.avatar)) return;
      if (query.has('characterId') && profile.character_id !== query.get('characterId')) return;
      if (query.has('avatar') && profile.avatar !== query.get('avatar')) return;
      clearTimeout(timeout); window.removeEventListener('message', receive);
      resolve(profile);
    }
    window.addEventListener('message', receive);
    studioEvent('ready');
  });
}
export function onStudioShutdown(callback) {
  if (!connection) return;
  window.addEventListener('message', (event) => {
    if (event.source === parent && event.origin === connection.origin && event.data?.channel === 'persona-studio-runtime' && event.data.instanceId === connection.instanceId && event.data.type === 'shutdown') callback();
  });
}
