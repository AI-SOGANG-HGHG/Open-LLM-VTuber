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
  $('#avatarStatus').textContent = avatarAssets[char.avatar].model ? 'Live2D 캐릭터를 불러오고 있어요…' : '나만의 캐릭터를 위한 심볼이에요. 외형을 바꾸려면 프로필에서 선택해 주세요.';
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
export function closePreview() { ++previewEpoch; avatarPreview?.destroy(); avatarPreview = null; }

export function bindPreviewEvents() {
  $('#avatarDialog').addEventListener('cancel', closePreview);
  $('#avatarDialog').addEventListener('close', () => { if (!$('#avatarDialog').open) closePreview(); });
}
