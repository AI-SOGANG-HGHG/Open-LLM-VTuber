import { createLivePreview } from '../../../../shared/live2d-loader.js';

// The existing app's speech queue drives this adapter through the same mouth/phase interface.
export class StudioAvatarRenderer {
  constructor(host, canvas, onChange, avatar) {
    this.host = host; this.canvas = canvas; this.onChange = onChange; this.avatar = avatar;
    this.active = 'image'; this.degraded = false; this.ready = false; this.closed = false;
    this.state = { mouth: 0, reduced: false, gaze: 0, expression: 'neutral' };
    this.requested = null; this.epoch = 0;
  }
  get canGreet() { return this.ready && this.active === 'live2d'; }
  placeholder() {
    const ns = 'http://www.w3.org/2000/svg';
    this.host.replaceChildren(); this.host.setAttribute('viewBox', '0 0 270 337');
    if (this.avatar === 'mao') {
      const image = document.createElementNS(ns, 'image');
      image.setAttribute('href', new URL('../../../assets/mao.png', import.meta.url).href); image.setAttribute('width', '270'); image.setAttribute('height', '337'); this.host.append(image);
    } else {
      const text = document.createElementNS(ns, 'text');
      text.setAttribute('x', '135'); text.setAttribute('y', '205'); text.setAttribute('text-anchor', 'middle'); text.setAttribute('font-size', '130'); text.setAttribute('fill', '#b9dbcc'); text.textContent = '✳'; this.host.append(text);
    }
    this.host.style.visibility = ''; this.host.setAttribute('aria-hidden', 'false');
    this.canvas.hidden = true; this.canvas.setAttribute('aria-hidden', 'true');
  }
  init(mode) { return this.setMode(mode); }
  setMode(mode, { force = false } = {}) {
    if (this.closed) return Promise.resolve(false);
    if (this.requested === mode && !force) return this.pending;
    this.requested = mode; this.pending = this.switch(mode); return this.pending;
  }
  async switch(mode) {
    const ticket = ++this.epoch;
    this.engine?.destroy(); this.engine = null; this.ready = false;
    this.placeholder(); this.active = 'image'; this.degraded = false;
    if (this.avatar !== 'mao' || mode !== 'live2d') { this.ready = true; this.onChange(); return true; }
    this.active = 'loading'; this.onChange();
    const canvas = this.canvas.cloneNode(false); this.canvas.replaceWith(canvas); this.canvas = canvas;
    const engine = createLivePreview(canvas, canvas.parentElement, () => {
      if (ticket !== this.epoch || this.closed) return;
      this.engine?.destroy(); this.engine = null; this.active = 'image'; this.ready = false; this.degraded = true; this.placeholder(); this.onChange();
    });
    this.engine = engine;
    try {
      await engine.load('/live2d-models/mao_pro/runtime/mao_pro.model3.json');
      if (ticket !== this.epoch || this.closed) { engine.destroy(); return false; }
      this.active = 'live2d'; this.ready = true;
      this.host.style.visibility = 'hidden'; this.host.setAttribute('aria-hidden', 'true');
      canvas.hidden = false; canvas.setAttribute('aria-hidden', 'false');
      engine.setMouthOpen(this.state.mouth); engine.setReducedMotion(this.state.reduced); engine.lookAt(this.state.gaze); engine.setExpression(this.state.expression);
      this.onChange(); return true;
    } catch {
      if (ticket !== this.epoch || this.closed) return false;
      engine.destroy(); this.engine = null; this.degraded = true; this.active = 'image'; this.placeholder(); this.onChange(); return false;
    }
  }
  setPhase(phase) { if (phase !== 'speaking') this.setMouthOpen(0); }
  setMouthOpen(amount) { this.state.mouth = Math.max(0, Math.min(1, Number(amount) || 0)); this.host.dataset.mouthOpen = this.state.mouth.toFixed(2); this.engine?.setMouthOpen(this.state.mouth); }
  setExpression(name) { this.state.expression = name; this.engine?.setExpression(name); }
  setReducedMotion(value) { this.state.reduced = value; this.engine?.setReducedMotion(value); }
  lookAt(x) { this.state.gaze = x; this.engine?.lookAt(x); }
  greet() { return this.canGreet && this.engine.greet(); }
  cancelGesture() { this.engine?.cancelGesture(); }
  dispose() { this.closed = true; this.epoch++; this.engine?.destroy(); this.engine = null; }
}
