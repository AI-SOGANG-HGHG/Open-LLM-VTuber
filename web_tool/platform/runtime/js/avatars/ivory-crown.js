import { kangIseoFaces, kangIseoThinkingEyeOpen } from '../../../../shared/kang-iseo-expressions.js?face=2';
import { kangIseoBrowArea, loadKangIseoFaceArt } from '../../../../shared/kang-iseo-face-art.js';

let rigImport;
let rigAttempt = 0;

function loadRig() {
  if (!rigImport) {
    const source = new URL('../../../../shared/ivory-crown-rig.js', import.meta.url);
    // Browsers cache failed module loads by URL for the life of the document.
    if (rigAttempt > 0) source.searchParams.set('retry', rigAttempt);
    rigAttempt += 1;
    rigImport = import(source.href).catch((error) => {
      rigImport = undefined;
      throw error;
    });
  }
  return rigImport;
}

export async function createIvoryCrownAvatar(canvas, imageUrl) {
  const portrait = new Image();
  portrait.src = imageUrl;
  const [faceArt] = await Promise.all([loadKangIseoFaceArt(), portrait.decode(), loadRig()]);

  canvas.width = portrait.naturalWidth;
  canvas.height = portrait.naturalHeight;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D is unavailable');
  const rig = globalThis.makeIvoryCrownRig(portrait);
  const pose = { eyeL: 1, eyeR: 1, mouth: 0 };
  const systemMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let expression = 'neutral';
  let thinking = false;
  let reduced = false;
  let timer;
  let frame;
  let blink = 1;

  function draw() {
    const face = kangIseoFaces[expression];
    const eyeOpen = thinking && expression === 'neutral' ? kangIseoThinkingEyeOpen : (faceArt ? 1 : face.eyeScale);
    pose.eyeL = pose.eyeR = Math.round(blink * eyeOpen * 100) / 100;
    rig.draw(context, pose, {
      ...face, expression, faceArea: kangIseoBrowArea,
      paintEye: faceArt?.paintedEye, paintDetails: faceArt?.paintedBrows, paintEmotionMouth: faceArt?.paintedMouth,
    });
    canvas.dataset.appliedMouth = String(pose.mouth);
    canvas.dataset.eyeOpen = String(pose.eyeL);
    canvas.dataset.expression = expression;
  }

  function stopBlink() {
    clearTimeout(timer);
    cancelAnimationFrame(frame);
  }

  function scheduleBlink() {
    timer = setTimeout(() => {
      const start = performance.now();
      function animateBlink(now) {
        const progress = Math.min(1, (now - start) / 210);
        blink = 1 - Math.sin(Math.PI * progress) ** 2;
        draw();
        if (progress < 1) frame = requestAnimationFrame(animateBlink);
        else scheduleBlink();
      }
      frame = requestAnimationFrame(animateBlink);
    }, 2000 + Math.random() * 1800);
  }

  function updateBlink() {
    stopBlink();
    blink = 1;
    draw();
    if (!reduced && !systemMotion.matches) scheduleBlink();
  }

  systemMotion.addEventListener('change', updateBlink);
  updateBlink();
  return {
    setMouthOpen(amount) {
      const rounded = Math.round(amount * 100) / 100;
      if (pose.mouth === rounded) return;
      pose.mouth = rounded;
      draw();
    },
    setExpression(name) {
      const next = Object.hasOwn(kangIseoFaces, name) ? name : 'neutral';
      if (next === expression) return;
      expression = next;
      draw();
    },
    setThinking(value) {
      if (value === thinking) return;
      thinking = value;
      draw();
    },
    setReducedMotion(value) {
      if (value === reduced) return;
      reduced = value;
      updateBlink();
    },
    destroy() {
      stopBlink();
      systemMotion.removeEventListener('change', updateBlink);
    },
  };
}
