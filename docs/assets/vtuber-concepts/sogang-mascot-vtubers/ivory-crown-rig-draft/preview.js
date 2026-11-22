const stage = document.querySelector('#stage');
const ctx = stage.getContext('2d');
const fieldset = document.querySelector('#pose');
const status = document.querySelector('#status');
const autoBlink = document.querySelector('#autoBlink');
const controls = Object.fromEntries(['eyeL', 'eyeR', 'mouth'].map((id) => [id, document.getElementById(id)]));
const outputs = Object.fromEntries(Array.from(
  document.querySelectorAll('output'),
  (output) => [output.htmlFor.value, output],
));
const audio = document.querySelector('#audio');
const audioFile = document.querySelector('#audioFile');
const motion = matchMedia('(prefers-reduced-motion: reduce)');

const BLINK_MS = 210;
let rig;
let frameId = 0;
let nextBlink = Infinity;
let blinkAt = -Infinity;
let audioUrl;
let audioContext;
let analyser;
let samples;
let audioActive = false;
let audioMouth = 0;
let lastPose;

function drawFrame(now) {
  frameId = 0;
  if (autoBlink.checked && now >= nextBlink) {
    blinkAt = now;
    nextBlink = now + 3300 + Math.random() * 1600;
  }
  const progress = (now - blinkAt) / BLINK_MS;
  const blinking = progress >= 0 && progress < 1;
  const openFactor = blinking ? 1 - Math.sin(Math.PI * progress) ** 2 : 1;

  if (audioActive && analyser) {
    analyser.getFloatTimeDomainData(samples);
    const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
    const target = Math.min(1, Math.max(0, (rms - 0.017) * 5));
    audioMouth = audio.muted || audio.volume === 0
      ? 0
      : audioMouth + (target - audioMouth) * (target > audioMouth ? 0.62 : 0.34);
  }
  const pose = {
    eyeL: controls.eyeL.valueAsNumber * openFactor / 100,
    eyeR: controls.eyeR.valueAsNumber * openFactor / 100,
    mouth: audioActive ? audioMouth : controls.mouth.valueAsNumber / 100,
  };
  // Round to display resolution so idle frames leave the unchanged canvas alone.
  for (const key of Object.keys(pose)) pose[key] = Math.round(pose[key] * 100) / 100;
  if (!lastPose || Object.keys(pose).some((key) => lastPose[key] !== pose[key])) {
    rig.draw(ctx, pose);
    lastPose = pose;
    for (const [key, value] of Object.entries(pose)) {
      outputs[key].textContent = `${Math.round(value * 100)}%`;
    }
  }
  if (audioActive || blinking || autoBlink.checked) scheduleFrame();
}

function scheduleFrame() {
  if (rig && !frameId) frameId = requestAnimationFrame(drawFrame);
}

function setAutoBlink() {
  nextBlink = performance.now() + 1600;
  if (!autoBlink.checked) blinkAt = -Infinity;
  scheduleFrame();
}

function stopAudio() {
  if (!audioActive) return;
  audioActive = false;
  audioMouth = 0;
  controls.mouth.disabled = false;
  controls.mouth.value = '0';
  scheduleFrame();
}

async function startAudio() {
  try {
    if (!audioContext) {
      audioContext = new AudioContext();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 1024;
      samples = new Float32Array(analyser.fftSize);
      const source = audioContext.createMediaElementSource(audio);
      source.connect(analyser);
      analyser.connect(audioContext.destination);
    }
    await audioContext.resume();
    if (audio.paused || audio.ended) return;
    audioActive = true;
    controls.mouth.disabled = true;
    status.textContent = '';
    scheduleFrame();
  } catch {
    audio.pause();
    status.textContent = '이 브라우저에서 오디오 립싱크를 시작하지 못했어요.';
  }
}

audioFile.addEventListener('change', () => {
  const [file] = audioFile.files;
  if (!file) return;
  audio.pause();
  stopAudio();
  if (audioUrl) URL.revokeObjectURL(audioUrl);
  audioUrl = URL.createObjectURL(file);
  audio.src = audioUrl;
  audio.hidden = false;
  status.textContent = '';
});
audio.addEventListener('play', startAudio);
audio.addEventListener('pause', stopAudio);
audio.addEventListener('ended', stopAudio);
audio.addEventListener('error', () => {
  stopAudio();
  status.textContent = '이 오디오를 읽을 수 없어요. WAV나 MP3 파일을 선택해 주세요.';
});

for (const control of Object.values(controls)) control.addEventListener('input', scheduleFrame);
autoBlink.addEventListener('change', setAutoBlink);
motion.addEventListener('change', ({ matches }) => {
  if (matches) autoBlink.checked = false;
  setAutoBlink();
});
document.querySelector('#blink').addEventListener('click', () => {
  blinkAt = performance.now();
  nextBlink = blinkAt + 3300;
  scheduleFrame();
});
document.querySelector('#reset').addEventListener('click', () => {
  audio.pause();
  stopAudio();
  autoBlink.checked = false;
  blinkAt = -Infinity;
  controls.eyeL.value = '100';
  controls.eyeR.value = '100';
  controls.mouth.value = '0';
  scheduleFrame();
});

const artwork = new Image();
artwork.src = '../ivory-crown-front-base.png';
artwork.decode().then(() => {
  rig = globalThis.makeIvoryCrownRig(artwork);
  fieldset.disabled = false;
  autoBlink.checked = !motion.matches;
  status.textContent = '';
  setAutoBlink();
}).catch(() => {
  status.textContent = '정면 원화를 불러오지 못했어요. 원화와 이 폴더의 경로를 확인해 주세요.';
});
