let rigImport;
let rigAttempt = 0;

const eyeOpenness = Object.freeze({ neutral: 1, joy: 0.72, surprise: 1.10 });

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
  await Promise.all([portrait.decode(), loadRig()]);

  canvas.width = portrait.naturalWidth;
  canvas.height = portrait.naturalHeight;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D is unavailable');
  const rig = globalThis.makeIvoryCrownRig(portrait);
  const pose = { eyeL: 1, eyeR: 1, mouth: 0 };
  const systemMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let expression = 'neutral';
  let blinkOpenness = 1;
  let gaze = 0;
  let timer;
  let frame;
  let breath;
  let reduced = false;

  function draw() {
    pose.eyeL = pose.eyeR = Math.round(eyeOpenness[expression] * blinkOpenness * 100) / 100;
    rig.draw(context, pose);
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
      function blink(now) {
        const progress = Math.min(1, (now - start) / 210);
        blinkOpenness = 1 - Math.sin(Math.PI * progress) ** 2;
        draw();
        if (progress < 1) frame = requestAnimationFrame(blink);
        else scheduleBlink();
      }
      frame = requestAnimationFrame(blink);
    }, 2000 + Math.random() * 1800);
  }

  function motionReduced() {
    return reduced || systemMotion.matches;
  }

  function applyTilt() {
    canvas.style.rotate = `${motionReduced() ? 0 : gaze * 2.5}deg`;
  }

  function applyMotion() {
    stopBlink();
    breath?.cancel();
    blinkOpenness = 1;
    applyTilt();
    draw();
    if (motionReduced()) return;
    scheduleBlink();
    // The PSD has a single head/body layer. Keep this motion on the entire portrait.
    breath = canvas.animate(
      [{ scale: '1' }, { scale: '1.008 1.012' }, { scale: '1' }],
      { duration: 5000, iterations: Infinity, easing: 'ease-in-out' },
    );
  }

  canvas.style.transformOrigin = '50% 72%';
  systemMotion.addEventListener('change', applyMotion);
  applyMotion();
  return {
    setMouthOpen(amount) {
      const rounded = Math.round(amount * 100) / 100;
      if (pose.mouth === rounded) return;
      pose.mouth = rounded;
      draw();
    },
    setExpression(name) {
      const next = Object.hasOwn(eyeOpenness, name) ? name : 'neutral';
      if (next === expression) return;
      expression = next;
      draw();
    },
    lookAt(x = 0) {
      gaze = Math.max(-1, Math.min(1, Number(x) || 0));
      applyTilt();
    },
    setReducedMotion(value) {
      if (value === reduced) return;
      reduced = value;
      applyMotion();
    },
    destroy() {
      stopBlink();
      breath?.cancel();
      systemMotion.removeEventListener('change', applyMotion);
    },
  };
}
