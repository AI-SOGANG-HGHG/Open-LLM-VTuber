import { createRandomId } from '../../../../shared/random-id.js';
import { SvgMascot } from './mascot-renderer.js';
import { normalizeExpression } from '../expressions.js';

const MODEL = '/live2d-models/sogangi-expressions/runtime/sogangi.model3.json';
const REQUIRED = [
  'ParamEyeLOpen',
  'ParamEyeROpen',
  'ParamMouthOpenY',
  'ParamAngleZ',
  'ParamBreath',
  'ParamArmRWave',
  'ParamFaceMood',
];
let libraries;
function bounded(promise, milliseconds) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Avatar timeout')), milliseconds);
    }),
  ]).finally(() => clearTimeout(timer));
}
function loadScript(url, ready) {
  if (ready()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    const timer = setTimeout(() => finish(false), 12000);
    function finish(ok) {
      clearTimeout(timer);
      script.onload = script.onerror = null;
      if (!ok) script.remove();
      ok && ready() ? resolve() : reject(new Error('Avatar library unavailable'));
    }
    script.src = url;
    script.onload = () => finish(true);
    script.onerror = () => finish(false);
    document.head.append(script);
  });
}
async function loadLibraries() {
  if (!libraries) {
    libraries = (async () => {
      await loadScript('/libs/live2dcubismcore.min.js', () => window.Live2DCubismCore);
      await loadScript(new URL('../../../../shared/vendor/pixi.min.js', import.meta.url).href, () => window.PIXI);
      await loadScript(new URL('../../../../shared/vendor/cubism4.min.js', import.meta.url).href, () => window.PIXI?.live2d?.Live2DModel);
    })().catch((error) => {
      libraries = null;
      throw error;
    });
  }
  return libraries;
}
function destroyModel(model) {
  if (model && !model.destroyed)
    model.destroy({ children: true, texture: true, baseTexture: true });
}

class CubismMascot {
  constructor(host, canvas, onFailure) {
    this.host = host;
    this.canvas = canvas;
    this.onFailure = onFailure;
    this.ready = false;
    this.disposed = false;
    this.failed = false;
    this.phase = 'idle';
    this.mouth = 0;
    this.expression = 'neutral';
    this.expressionStart = 0;
    this.nextBlink = performance.now() + 2800;
    this.blinkStart = null;
    this.reduced = false;
    this.started = performance.now();
    this.lastUpdate = this.started;
    this.head = 0;
    this.targetHead = 0;
    this.greetingStart = null;
    this.preference = matchMedia('(prefers-reduced-motion: reduce)');
    this.lost = (event) => {
      event.preventDefault();
      this.fail();
    };
    canvas.addEventListener('webglcontextlost', this.lost);
  }
  async init() {
    try {
      await loadLibraries();
      if (this.disposed) return false;
      const response = await fetch(MODEL, {
        signal: AbortSignal.timeout(12000),
        cache: 'no-cache',
      });
      if (!response.ok) throw new Error('Missing avatar');
      const settings = await response.json();
      // This adapter deliberately loads only our fixed motion model. Do not
      // follow arbitrary extra files, audio, motion or outside-model references.
      if (
        settings.Version !== 3 ||
        settings.FileReferences?.Moc !== 'sogangi.moc3' ||
        !Array.isArray(settings.FileReferences.Textures) ||
        settings.FileReferences.Textures.length !== 1 ||
        settings.FileReferences.Textures[0] !== 'textures/texture_00.png' ||
        !Array.isArray(settings.SogangiMinimum?.WiredParameters) ||
        !REQUIRED.every((id) => settings.SogangiMinimum.WiredParameters.includes(id))
      )
        throw new Error('Unexpected avatar manifest');
      if (this.disposed) return false;
      this.app = new PIXI.Application({
        view: this.canvas,
        width: 1,
        height: 1,
        backgroundAlpha: 0,
        antialias: true,
        preserveDrawingBuffer: true,
        resolution: Math.min(devicePixelRatio, 2),
        autoDensity: true,
      });
      const url = new URL(MODEL, location.origin);
      const identity = createRandomId();
      const fresh = (file) => {
        const target = new URL(file, url);
        target.searchParams.set('_avatar', identity);
        return target.href;
      };
      const pending = PIXI.live2d.Live2DModel.from(
        {
          Version: 3,
          url: url.href,
          FileReferences: {
            Moc: fresh('sogangi.moc3'),
            Textures: [fresh('textures/texture_00.png')],
          },
          Groups: [
            { Target: 'Parameter', Name: 'EyeBlink', Ids: REQUIRED.slice(0, 2) },
            { Target: 'Parameter', Name: 'LipSync', Ids: REQUIRED.slice(2, 3) },
          ],
        },
        {
          autoInteract: false,
          idleMotionGroup: '__chat_avatar__',
          motionPreload: PIXI.live2d.MotionPreloadStrategy.NONE,
        },
      );
      pending.then(
        (model) => {
          if (this.disposed) destroyModel(model);
        },
        () => {},
      );
      this.model = await bounded(pending, 20000);
      if (this.disposed) {
        destroyModel(this.model);
        return false;
      }
      this.core = this.model.internalModel.coreModel;
      this.parameters = this.core.getModel().parameters;
      const ids = Array.from(this.parameters.ids);
      if (!REQUIRED.every((id) => ids.includes(id))) throw new Error('Missing facial parameters');
      this.indices = REQUIRED.map((id) => ids.indexOf(id));
      this.model.anchor.set(0.5, 0.5);
      this.app.stage.addChild(this.model);
      this.model.internalModel.on('beforeModelUpdate', () => {
        if (this.disposed || !this.ready) return;
        try {
          this.update(performance.now());
        } catch {
          this.fail();
        }
      });
      this.resize = new ResizeObserver(() => this.fit());
      this.resize.observe(this.canvas.parentElement);
      this.ready = true;
      this.fit();
      this.update(performance.now());
      return true;
    } catch (error) {
      this.canvas.dataset.loadError =
        error instanceof Error ? `${error.name}: ${error.message}`.slice(0, 240) : 'Avatar failed';
      this.dispose();
      return false;
    }
  }
  fit() {
    if (!this.ready || this.disposed) return;
    const box = this.canvas.parentElement.getBoundingClientRect();
    if (!box.width || !box.height) return;
    this.app.renderer.resize(box.width, box.height);
    // Match the existing SVG's 270×337 viewport inside the 2048 prep canvas.
    const { originalWidth, originalHeight } = this.model.internalModel;
    const cropWidth = originalWidth * (((1792 / 337) * 270) / 2048);
    const cropHeight = originalHeight * (1792 / 2048);
    // Reserve room for the hood wings at the reviewed tilt extremes. Preserve
    // the foot baseline rather than making the smaller model float upward.
    this.model.scale.set(Math.min(box.width / cropWidth, box.height / cropHeight) * 0.94);
    this.model.position.set(box.width / 2, box.height * 0.53);
  }
  setMouthOpen(amount) {
    this.mouth = Math.max(0, Math.min(1, Number(amount) || 0));
    const displayed = this.mouth.toFixed(2);
    if (this.host.dataset.mouthOpen !== displayed) this.host.dataset.mouthOpen = displayed;
    if (this.ready && !this.disposed) {
      this.core.setParameterValueById(REQUIRED[2], this.mouth);
      const applied = String(this.parameters.values[this.indices[2]]);
      if (this.canvas.dataset.appliedMouth !== applied) this.canvas.dataset.appliedMouth = applied;
    }
  }
  setPhase(phase) {
    this.phase = phase;
    if (phase !== 'speaking') this.setMouthOpen(0);
  }
  setExpression(name) {
    const next = normalizeExpression(name);
    if (this.expression !== next) this.expressionStart = performance.now();
    this.expression = next;
    this.host.dataset.expression = next;
  }
  setReducedMotion(reduced) {
    this.reduced = reduced;
    if (reduced) this.cancelGesture();
  }
  lookAt(x = 0) {
    this.targetHead = Math.max(-1, Math.min(1, Number(x) || 0)) * 24;
  }
  greet() {
    if (
      !this.ready ||
      this.disposed ||
      this.reduced ||
      this.preference.matches ||
      this.greetingStart !== null
    )
      return false;
    this.greetingStart = performance.now();
    return true;
  }
  cancelGesture() {
    this.greetingStart = null;
    this.host.dataset.greeting = 'false';
    if (this.ready && !this.disposed) {
      this.core.setParameterValueById(REQUIRED[5], 0);
      this.canvas.dataset.appliedArm = String(this.parameters.values[this.indices[5]]);
    }
  }
  update(now) {
    const reduced = this.reduced || this.preference.matches;
    // Discrete semantic states must not interpolate through an unrelated mood.
    const mood = this.expression === 'anger' ? 1 : this.expression === 'surprise' ? 2 : 0;
    this.core.setParameterValueById(REQUIRED[6], mood);
    this.canvas.dataset.appliedMood = String(this.parameters.values[this.indices[6]]);
    const greetingElapsed = this.greetingStart === null ? 1600 : now - this.greetingStart;
    const greeting = !reduced && greetingElapsed >= 0 && greetingElapsed < 1600;
    if (!greeting) this.greetingStart = null;
    const t = greetingElapsed / 1600;
    const arm = greeting ? Math.sin(Math.PI * t) * (0.78 + 0.22 * Math.cos(6 * Math.PI * t)) : 0;
    this.core.setParameterValueById(REQUIRED[5], arm);
    this.canvas.dataset.appliedArm = String(this.parameters.values[this.indices[5]]);
    this.host.dataset.greeting = String(greeting);
    const elapsedFrame = Math.min(64, Math.max(0, now - this.lastUpdate));
    this.lastUpdate = now;
    this.head = reduced
      ? 0
      : this.head + (this.targetHead - this.head) * (1 - Math.exp(-elapsedFrame / 160));
    if (Math.abs(this.head) < 0.001 && this.targetHead === 0) this.head = 0;
    const breath = reduced ? 0 : (1 - Math.cos(((now - this.started) / 4800) * Math.PI * 2)) / 2;
    this.core.setParameterValueById(REQUIRED[3], this.head);
    this.core.setParameterValueById(REQUIRED[4], breath);
    this.canvas.dataset.appliedHead = String(this.parameters.values[this.indices[3]]);
    this.canvas.dataset.appliedBreath = String(this.parameters.values[this.indices[4]]);
    let eyes = 1;
    if (!reduced) {
      if (this.blinkStart === null && now >= this.nextBlink) this.blinkStart = now;
      if (this.blinkStart !== null) {
        const elapsed = now - this.blinkStart;
        eyes = Math.min(1, Math.abs(elapsed - 90) / 90);
        if (elapsed >= 180) {
          this.blinkStart = null;
          this.nextBlink = now + 3000 + Math.random() * 2000;
          eyes = 1;
        }
      }
      const elapsed = now - this.expressionStart;
      if (this.expression === 'joy' && elapsed > 100 && elapsed < 480) eyes = 0;
    }
    for (let index = 0; index < 2; index++) this.core.setParameterValueById(REQUIRED[index], eyes);
    this.setMouthOpen(this.mouth);
    const appliedEyes = this.indices
      .slice(0, 2)
      .map((index) => this.parameters.values[index].toFixed(2))
      .join(',');
    if (this.canvas.dataset.appliedEyes !== appliedEyes)
      this.canvas.dataset.appliedEyes = appliedEyes;
    if (this.host.dataset.eyeOpen !== appliedEyes) this.host.dataset.eyeOpen = appliedEyes;
    this.canvas.dataset.frames = String(Number(this.canvas.dataset.frames || 0) + 1);
  }
  fail() {
    if (this.failed || this.disposed) return;
    this.failed = true;
    // Let PIXI finish processing a context-loss event before destroying it.
    queueMicrotask(() => {
      if (!this.disposed) this.onFailure();
    });
  }
  dispose() {
    if (this.disposed) return;
    this.cancelGesture();
    this.disposed = true;
    this.ready = false;
    this.resize?.disconnect();
    this.canvas.removeEventListener('webglcontextlost', this.lost);
    const ownedByApp = this.model?.parent === this.app?.stage;
    const gl = this.app?.renderer?.gl;
    try {
      if (!ownedByApp) destroyModel(this.model);
    } catch {
      /* Context may already be gone. */
    }
    try {
      this.app?.destroy(false, { children: true, texture: true, baseTexture: true });
    } catch {
      /* Recover with a fresh canvas. */
    }
    try {
      gl?.getExtension('WEBGL_lose_context')?.loseContext();
    } catch {
      /* Already released. */
    }
    this.app = this.model = this.core = null;
  }
}

export class AvatarRenderer {
  constructor(host, canvas, onChange) {
    this.host = host;
    this.canvas = canvas;
    this.onChange = onChange;
    this.epoch = 0;
    this.closed = false;
    this.state = { phase: 'idle', expression: 'neutral', mouth: 0, reduced: false, gaze: [0, 0] };
    this.requested = null;
    this.active = 'image';
    this.degraded = false;
  }
  get ready() {
    return Boolean(this.engine?.ready);
  }
  get canGreet() {
    return this.ready && ['svg', 'live2d'].includes(this.active);
  }
  init(mode = 'svg') {
    return this.setMode(mode);
  }
  setMode(mode, { force = false } = {}) {
    if (this.closed) return Promise.resolve(false);
    mode = mode === 'live2d' ? 'live2d' : 'svg';
    if (mode === this.requested && !force) return this.pending;
    this.requested = mode;
    this.pending = this.switch(mode);
    return this.pending;
  }
  placeholder() {
    const image = document.createElementNS('http://www.w3.org/2000/svg', 'image');
    image.setAttribute(
      'href',
      new URL(`../../../../sogangi/assets/sogangi-${this.state.expression === 'joy' ? 'joy' : 'neutral'}.svg`, import.meta.url).href,
    );
    image.setAttribute('width', '270');
    image.setAttribute('height', '337');
    this.host.replaceChildren(image);
    this.host.setAttribute('viewBox', '0 0 270 337');
    this.host.style.visibility = '';
    this.host.setAttribute('aria-hidden', 'false');
    delete this.host.dataset.renderer;
    this.host.dataset.greeting = 'false';
    this.canvas.hidden = true;
    this.canvas.setAttribute('aria-hidden', 'true');
  }
  applyState() {
    if (!this.engine) return;
    this.engine.setReducedMotion(this.state.reduced);
    this.engine.setExpression(this.state.expression);
    this.engine.setPhase(this.state.phase);
    this.engine.setMouthOpen(this.state.mouth);
    this.engine.lookAt(...this.state.gaze);
  }
  async switch(mode) {
    const ticket = ++this.epoch;
    this.engine?.dispose();
    this.engine = null;
    this.active = 'loading';
    this.degraded = false;
    this.placeholder();
    this.onChange();
    if (mode === 'live2d') {
      const canvas = this.canvas.cloneNode(false);
      for (const key of [
        'appliedMouth',
        'appliedEyes',
        'appliedHead',
        'appliedBreath',
        'appliedArm',
        'appliedMood',
        'frames',
        'loadError',
      ])
        delete canvas.dataset[key];
      this.canvas.replaceWith(canvas);
      this.canvas = canvas;
      this.engine = new CubismMascot(this.host, canvas, () => {
        if (ticket === this.epoch && !this.closed) this.fallback(ticket);
      });
    } else this.engine = new SvgMascot(this.host);
    const engine = this.engine;
    this.applyState();
    const loaded = await engine.init();
    if (this.closed || ticket !== this.epoch) {
      engine.dispose();
      return false;
    }
    if (!loaded && mode === 'live2d') return this.fallback(ticket);
    this.active = loaded ? mode : 'image';
    if (loaded && mode === 'live2d') {
      this.canvas.hidden = false;
      this.canvas.setAttribute('aria-hidden', 'false');
      this.host.style.visibility = 'hidden';
      this.host.setAttribute('aria-hidden', 'true');
      this.host.dataset.renderer = 'live2d';
    }
    this.applyState();
    this.onChange();
    return loaded;
  }
  async fallback(ticket) {
    if (this.closed || ticket !== this.epoch) return false;
    const fallbackTicket = ++this.epoch;
    this.engine?.dispose();
    this.placeholder();
    const engine = new SvgMascot(this.host);
    this.engine = engine;
    this.active = 'loading';
    this.degraded = true;
    this.applyState();
    this.onChange();
    const loaded = await engine.init();
    if (this.closed || fallbackTicket !== this.epoch) {
      engine.dispose();
      return false;
    }
    this.active = loaded ? 'svg' : 'image';
    this.applyState();
    this.onChange();
    return loaded;
  }
  setPhase(phase) {
    if (this.closed) return;
    this.state.phase = phase;
    if (phase !== 'speaking') this.state.mouth = 0;
    this.engine?.setPhase(phase);
  }
  setMouthOpen(value) {
    if (this.closed) return;
    this.state.mouth = Math.max(0, Math.min(1, Number(value) || 0));
    this.host.dataset.mouthOpen = this.state.mouth.toFixed(2);
    this.engine?.setMouthOpen(this.state.mouth);
  }
  setExpression(name) {
    if (this.closed) return;
    this.state.expression = normalizeExpression(name);
    this.host.dataset.expression = this.state.expression;
    this.engine?.setExpression(this.state.expression);
  }
  setReducedMotion(value) {
    this.state.reduced = value;
    this.engine?.setReducedMotion(value);
  }
  lookAt(x = 0, y = 0) {
    this.state.gaze = [x, y];
    this.engine?.lookAt(x, y);
  }
  greet() {
    return this.canGreet && this.engine.greet();
  }
  cancelGesture() {
    this.engine?.cancelGesture();
  }
  dispose() {
    this.closed = true;
    this.epoch++;
    this.engine?.dispose();
    this.engine = null;
  }
}
