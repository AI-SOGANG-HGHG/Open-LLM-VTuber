import { SvgMascot } from '../../../platform/runtime/js/avatars/mascot-renderer.js';

async function loadDesign() {
  try {
    const response = await fetch('./workshop/live2d-plan/live2d-spec.json');
    if (!response.ok) throw new Error('spec');
    const spec = await response.json();
    const text = (id, value) => {
      document.getElementById(id).textContent = value;
    };
    const select = (layer, button) => {
      for (const item of document.querySelectorAll('#layerButtons button'))
        item.setAttribute('aria-pressed', String(item === button));
      const [x, y, width, height] = layer.bounds;
      const rect = document.getElementById('layerBounds');
      for (const [key, value] of Object.entries({ x, y, width, height }))
        rect.setAttribute(key, String(value));
      text('layerId', layer.id);
      text('layerLabel', layer.label);
      text('layerNote', layer.note);
      text('layerCaption', `${layer.label}의 위치 안내 · 실제 분리 원화 아님`);
      const list = document.getElementById('layerParts');
      list.replaceChildren(
        ...layer.parts.map((part) => {
          const li = document.createElement('li');
          li.textContent = `${layer.id}/${part}`;
          return li;
        }),
      );
    };
    for (const layer of spec.layers) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = layer.label;
      button.addEventListener('click', () => select(layer, button));
      document.getElementById('layerButtons').append(button);
    }
    document.querySelector('#layerButtons button').click();
    for (const motion of spec.motions) {
      const card = document.createElement('article');
      card.className = 'motion-card';
      const label = document.createElement('p');
      label.className = 'motion-id';
      label.textContent = motion.id;
      const heading = document.createElement('h3');
      heading.textContent = motion.label;
      const duration = document.createElement('p');
      duration.textContent =
        motion.duration_seconds === null
          ? '음성 재생에 맞춰 제어'
          : `${motion.duration_seconds}초 · ${motion.loop ? '반복' : '한 번 실행'}`;
      const note = document.createElement('p');
      note.textContent = motion.acceptance;
      const parameters = document.createElement('code');
      parameters.textContent = motion.parameters.join(' · ');
      card.append(label, heading, duration, note, parameters);
      document.getElementById('motionCards').append(card);
    }
    for (const parameter of spec.parameters) {
      const row = document.createElement('tr');
      for (const value of [
        parameter.label,
        parameter.id,
        parameter.min,
        parameter.default,
        parameter.max,
        parameter.stage === 'mvp' ? '첫 모델' : '선택 사항',
      ]) {
        const td = document.createElement('td');
        td.textContent = String(value);
        row.append(td);
      }
      document.getElementById('parameterRows').append(row);
    }
  } catch {
    document.getElementById('designError').hidden = false;
  }
}
loadDesign();

const preview = new SvgMascot(document.getElementById('motionPreview'), { padding: 12 });
const autoButton = document.getElementById('poseAuto');
const sliderIds = ['poseLeft', 'poseRight', 'poseMouth', 'poseTilt'];
function applyPose() {
  autoButton.setAttribute('aria-pressed', 'false');
  autoButton.textContent = '자동 움직임 보기';
  const values = sliderIds.map((id) => {
    const value = Number(document.getElementById(id).value);
    document.getElementById(id + 'Value').textContent = value.toFixed(2);
    return value;
  });
  preview.previewPose({ left: values[0], right: values[1], mouth: values[2], tilt: values[3] });
}
preview.init().then((loaded) => {
  if (!loaded) return;
  for (const id of sliderIds) {
    const slider = document.getElementById(id);
    slider.disabled = false;
    slider.addEventListener('input', applyPose);
  }
  autoButton.disabled = false;
  for (const button of document.querySelectorAll('[data-preview-expression]')) {
    button.disabled = false;
    button.addEventListener('click', () => {
      preview.setExpression('neutral');
      preview.setExpression(button.dataset.previewExpression);
      preview.autoPreview(true);
      autoButton.setAttribute('aria-pressed', 'true');
      autoButton.textContent = '직접 움직임 조절하기';
    });
  }
  applyPose();
});
autoButton.addEventListener('click', () => {
  const automatic = autoButton.getAttribute('aria-pressed') !== 'true';
  autoButton.setAttribute('aria-pressed', String(automatic));
  autoButton.textContent = automatic ? '직접 움직임 조절하기' : '자동 움직임 보기';
  preview.autoPreview(automatic);
  if (!automatic) applyPose();
});
window.addEventListener('pagehide', () => preview.dispose());
window.addEventListener('pageshow', (event) => {
  if (event.persisted) location.reload();
});
