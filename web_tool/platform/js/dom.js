export const $ = (selector) => document.querySelector(selector);
export const main = $('#mainContent');
export const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);

export const LIVE_CHAT_ACTIVITY = '캐릭터와 대화함';
export const now = () => new Date().toISOString();

export function charLink(char, tab = 'settings') { return `#character/${encodeURIComponent(char.id)}/${tab}`; }
export function shortDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}
export function pageHeading(title, description, action = '') {
  return `<div class="page-heading"><div><h1>${title}</h1>${description ? `<p class="muted">${description}</p>` : ''}</div>${action}</div>`;
}

let toastTimer;
export function toast(message, error = false) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.toggle('error-toast', error);
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, 3500);
}
