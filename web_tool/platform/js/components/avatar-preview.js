import { $ } from '../dom.js';
import { avatarAssets } from '../presets.js';
import { avatar } from './card.js';

let avatarPreview;
let previewEpoch = 0;

export async function openPreview(char) {
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
  $('#avatarStatus').textContent = avatarAssets[char.avatar].model ? 'Live2D 캐릭터를 불러오고 있어요…' : '프로필에서 다른 외형을 선택할 수 있어요.';
  $('#avatarDialog').showModal();
  if (!avatarAssets[char.avatar].model) return;
  try {
    const { createLivePreview } = await import('../../live-preview.js');
    if (ticket !== previewEpoch) return;
    const instance = createLivePreview($('#liveAvatarCanvas'), $('#liveAvatarStage'), () => {
      if (ticket !== previewEpoch) return;
      closePreview();
      $('#liveAvatarCanvas').hidden = true;
      $('#avatarFallback').hidden = false;
      $('#avatarStatus').textContent = '미리보기가 멈춰 캐릭터를 이미지로 보여드려요.';
    });
    avatarPreview = instance;
    await instance.load(avatarAssets[char.avatar].model);
    if (ticket !== previewEpoch) { instance.destroy(); return; }
    $('#avatarFallback').hidden = true;
    $('#liveAvatarCanvas').hidden = false;
    $('#avatarStatus').textContent = '';
  } catch {
    if (ticket === previewEpoch) {
      avatarPreview?.destroy(); avatarPreview = null;
      $('#avatarStatus').textContent = 'Live2D를 불러오지 못해 캐릭터를 이미지로 보여드려요.';
    }
  }
}
export function closePreview() { ++previewEpoch; avatarPreview?.destroy(); avatarPreview = null; }

export function bindPreviewEvents() {
  $('#avatarDialog').addEventListener('cancel', closePreview);
  $('#avatarDialog').addEventListener('close', () => { if (!$('#avatarDialog').open) closePreview(); });
}
