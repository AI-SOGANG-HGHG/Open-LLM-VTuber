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
  await Promise.all([portrait.decode(), loadRig()]);

  canvas.width = portrait.naturalWidth;
  canvas.height = portrait.naturalHeight;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D is unavailable');
  const rig = globalThis.makeIvoryCrownRig(portrait);
  const pose = { eyeL: 1, eyeR: 1, mouth: 0 };
  let timer;
  let frame;
  let reduced = false;

  function draw() {
    rig.draw(context, pose);
    canvas.dataset.appliedMouth = String(pose.mouth);
    canvas.dataset.eyeOpen = String(pose.eyeL);
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
        const openness = 1 - Math.sin(Math.PI * progress) ** 2;
        pose.eyeL = pose.eyeR = Math.round(openness * 100) / 100;
        draw();
        if (progress < 1) frame = requestAnimationFrame(blink);
        else scheduleBlink();
      }
      frame = requestAnimationFrame(blink);
    }, 2000 + Math.random() * 1800);
  }

  draw();
  scheduleBlink();
  return {
    setMouthOpen(amount) {
      const rounded = Math.round(amount * 100) / 100;
      if (pose.mouth === rounded) return;
      pose.mouth = rounded;
      draw();
    },
    setReducedMotion(value) {
      if (value === reduced) return;
      reduced = value;
      stopBlink();
      pose.eyeL = pose.eyeR = 1;
      draw();
      if (!reduced) scheduleBlink();
    },
    destroy: stopBlink,
  };
}
