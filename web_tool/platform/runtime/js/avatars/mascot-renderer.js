// SVG-part animation for the image prototype, not a Cubism/Live2D runtime.
function smoothTransition(value, end) {
  const progress = Math.max(0, Math.min(1, value / end));
  return progress * progress * (3 - 2 * progress);
}

export class SvgMascot {
  constructor(host, { padding = 0 } = {}) {
    this.host = host;
    this.padding = padding;
    this.ready = false;
    this.disposed = false;
    this.phase = 'idle';
    this.expression = 'neutral';
    this.expressionStart = 0;
    this.parts = new Map();
    this.eyeValues = [1, 1];
    this.mouth = 0;
    this.frame = null;
    this.lastFrame = 0;
    this.nextBlink = performance.now() + 2800;
    this.blinkStart = null;
    this.reduced = false;
    this.manual = false;
    this.greetingStart = null;
    this.gaze = { x: 0, y: 0 };
    this.targetGaze = { x: 0, y: 0 };
    this.preference = matchMedia('(prefers-reduced-motion: reduce)');
  }

  async init() {
    try {
      const response = await fetch(new URL('../../../../sogangi/assets/layers/sogangi-visible-layers.svg', import.meta.url));
      if (!response.ok) throw new Error('Missing mascot parts');
      const sourceText = await response.text();
      if (this.disposed) return false;
      const doc = new DOMParser().parseFromString(sourceText, 'image/svg+xml');
      const source = doc.documentElement;
      const allowed = new Set(['svg', 'defs', 'g', 'path', 'clipPath']);
      if (doc.querySelector('parsererror') || source.localName !== 'svg')
        throw new Error('Invalid SVG');
      for (const node of [source, ...source.querySelectorAll('*')]) {
        if (node.namespaceURI !== 'http://www.w3.org/2000/svg' || !allowed.has(node.localName))
          throw new Error('Unsupported SVG element');
        for (const attribute of node.attributes) {
          const name = attribute.localName.toLowerCase();
          if (name.startsWith('on') || (name === 'href' && !attribute.value.startsWith('#')))
            throw new Error('Active SVG content rejected');
          if (/url\(/i.test(attribute.value) && !/^url\(#[\w-]+\)$/.test(attribute.value))
            throw new Error('External SVG resource rejected');
        }
      }
      const available = new Set(
        [...source.querySelectorAll('g[data-layer]')].map((node) => node.dataset.layer),
      );
      for (const id of ['Mouth_Open', 'Mouth_Closed', 'EyeL_Closed', 'EyeR_Closed'])
        if (!available.has(id)) throw new Error('Missing expression candidates');
      const prefix = `sogangi-${crypto.randomUUID()}-`;
      for (const node of [source, ...source.querySelectorAll('*')]) {
        if (node.id) node.id = prefix + node.id;
        for (const attribute of [...node.attributes]) {
          if (attribute.localName === 'href' && attribute.value.startsWith('#'))
            node.setAttributeNS(
              attribute.namespaceURI,
              attribute.name,
              '#' + prefix + attribute.value.slice(1),
            );
          else if (/url\(#/.test(attribute.value))
            node.setAttribute(
              attribute.name,
              attribute.value.replace(/url\(#([^)]+)\)/g, (_, id) => `url(#${prefix}${id})`),
            );
        }
      }
      this.host.replaceChildren(
        ...[...source.children].map((node) => document.importNode(node, true)),
      );
      this.host.setAttribute('viewBox', source.getAttribute('viewBox'));
      if (this.padding) {
        const [x, y, width, height] = source.getAttribute('viewBox').split(/\s+/).map(Number);
        this.host.setAttribute(
          'viewBox',
          `${x - this.padding} ${y - this.padding} ${width + 2 * this.padding} ${height + 2 * this.padding}`,
        );
      }
      this.head = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      this.head.id = prefix + 'head';
      for (const node of [...this.host.querySelectorAll(':scope > g[data-layer]')]) {
        const id = node.dataset.layer;
        if (!this.parts.has(id)) this.parts.set(id, []);
        this.parts.get(id).push(node);
        if (/^(Hood|Face|Eye|Mouth)/.test(id)) this.head.append(node);
      }
      this.host.append(this.head);
      this.ready = true;
      this.host.dataset.expression = this.expression;
      this.host.dataset.renderer = 'svg-parts';
      this.setEyeOpen(1, 1);
      this.setMouthOpen(0);
      this.frame = requestAnimationFrame((now) => this.tick(now));
      return true;
    } catch (error) {
      console.warn('SVG part preview unavailable; keeping the image fallback.', error.message);
      return false;
    }
  }

  each(id, update) {
    for (const node of this.parts.get(id) || []) update(node);
  }
  opacity(id, value) {
    this.each(id, (node) => {
      node.style.opacity = String(value);
    });
  }

  setEyeOpen(left, right) {
    if (!this.ready) return;
    for (const [index, side, x] of [
      [0, 'L', 268.44],
      [1, 'R', 349.95],
    ]) {
      const value = Math.max(0, Math.min(1, index === 0 ? left : right));
      if (this.eyeValues[index] === value && this.host.dataset.eyesInitialized) continue;
      this.eyeValues[index] = value;
      const visible = smoothTransition(Math.max(0, value - 0.04), 0.2);
      for (const part of ['Open', 'Highlight']) {
        this.opacity(`Eye${side}_${part}`, visible);
        this.each(`Eye${side}_${part}`, (node) =>
          node.setAttribute(
            'transform',
            `translate(${x} 446.57) scale(1 ${Math.max(0.08, value)}) translate(${-x} -446.57)`,
          ),
        );
      }
      this.opacity(`Eye${side}_Closed`, 1 - visible);
    }
    this.host.dataset.eyesInitialized = 'true';
    this.host.dataset.eyeOpen = `${this.eyeValues[0].toFixed(2)},${this.eyeValues[1].toFixed(2)}`;
  }

  setMouthOpen(amount) {
    if (!this.ready) return;
    const value = Math.round(Math.max(0, Math.min(1, amount)) * 100) / 100;
    if (this.mouth === value && this.host.dataset.mouthOpen !== undefined) return;
    this.mouth = value;
    // Crossfade through small openings rather than snapping between source
    // shapes at a volume threshold. Keep the original neutral/full-open ends.
    const opened = smoothTransition(value, 0.25);
    this.opacity('Mouth_Closed', 1 - opened);
    this.opacity('Mouth_Open', opened);
    this.each('Mouth_Open', (node) =>
      node.setAttribute(
        'transform',
        `translate(309.19 493) scale(${0.74 + value * 0.26} ${0.25 + value * 0.75}) translate(-309.19 -493)`,
      ),
    );
    this.host.dataset.mouthOpen = value.toFixed(2);
  }

  setPhase(phase) {
    this.phase = phase;
    if (phase !== 'speaking') this.setMouthOpen(0);
  }
  setExpression(name) {
    const next = name === 'joy' ? 'joy' : 'neutral';
    if (next !== this.expression) this.expressionStart = performance.now();
    this.expression = next;
    this.host.dataset.expression = next;
  }
  setReducedMotion(reduced) {
    this.reduced = reduced;
    if (reduced) this.cancelGesture();
  }
  cancelGesture() {
    this.greetingStart = null;
    this.host.dataset.greeting = 'false';
    if (this.ready)
      this.each('ArmR_Base', (node) => node.setAttribute('transform', 'rotate(0 337 533)'));
  }
  greet() {
    if (!this.ready || this.reduced || this.preference.matches) return false;
    this.manual = false;
    this.greetingStart = performance.now();
    return true;
  }
  lookAt(x = 0, y = 0) {
    this.targetGaze = {
      x: Math.max(-1, Math.min(1, x)),
      y: Math.max(-1, Math.min(1, y)),
    };
  }
  previewPose({ left = 1, right = 1, mouth = 0, tilt = 0 } = {}) {
    if (!this.ready) return;
    this.manual = true;
    this.setEyeOpen(left, right);
    this.setMouthOpen(mouth);
    this.head.setAttribute('transform', `rotate(${Math.max(-3, Math.min(3, tilt))} 309.19 517)`);
  }
  autoPreview(enabled) {
    this.manual = !enabled;
    if (enabled) {
      this.setPhase('idle');
      this.nextBlink = performance.now() + 800;
    }
  }

  tick(now) {
    if (this.disposed) return;
    this.frame = requestAnimationFrame((time) => this.tick(time));
    if (!this.ready || this.manual || now - this.lastFrame < 45) return;
    this.lastFrame = now;
    const reduced = this.reduced || this.preference.matches;
    const greetingElapsed = this.greetingStart === null ? null : now - this.greetingStart;
    const greeting = !reduced && greetingElapsed !== null && greetingElapsed < 1600;
    if (!greeting) this.greetingStart = null;
    let openness = 1;
    if (!reduced) {
      if (this.blinkStart === null && now >= this.nextBlink) this.blinkStart = now;
      if (this.blinkStart !== null) {
        const elapsed = now - this.blinkStart;
        openness = Math.min(1, Math.abs(elapsed - 90) / 90);
        if (elapsed >= 180) {
          this.blinkStart = null;
          this.nextBlink = now + 3000 + Math.random() * 2000;
          openness = 1;
        }
      }
    }
    // Joy uses the existing smiling-eye candidate briefly, then returns to blinking.
    const joyElapsed = now - this.expressionStart;
    if (!reduced && this.expression === 'joy' && joyElapsed > 100 && joyElapsed < 480) openness = 0;
    // A brief smiling blink accompanies the greeting, without holding the eyes shut.
    if (greeting && greetingElapsed > 180 && greetingElapsed < 520) openness = 0;
    this.setEyeOpen(openness, openness);
    const gazeX = reduced ? 0 : this.targetGaze.x;
    const gazeY = reduced ? 0 : this.targetGaze.y;
    this.gaze.x += (gazeX - this.gaze.x) * 0.16;
    this.gaze.y += (gazeY - this.gaze.y) * 0.16;
    // CSS translation composes with the original SVG transform used by the blink.
    for (const side of ['L', 'R'])
      for (const part of ['Open', 'Highlight'])
        this.each(`Eye${side}_${part}`, (node) => {
          node.style.translate = `${(this.gaze.x * 2.2).toFixed(2)}px ${(this.gaze.y * 1.4).toFixed(2)}px`;
        });
    const wave = greeting
      ? Math.sin((Math.PI * greetingElapsed) / 1600) * (28 + 8 * Math.sin(greetingElapsed / 90))
      : 0;
    this.each('ArmR_Base', (node) =>
      node.setAttribute('transform', `rotate(${-wave.toFixed(2)} 337 533)`),
    );
    this.host.dataset.greeting = String(greeting);
    const amplitude = reduced
      ? 0
      : this.phase === 'waiting'
        ? 1.4
        : this.phase === 'speaking'
          ? 0.7
          : 0.4;
    this.head.setAttribute(
      'transform',
      `rotate(${(Math.sin(now / 1500) * amplitude + (greeting ? Math.sin(greetingElapsed / 400) * 1.6 : this.gaze.x * 0.7)).toFixed(2)} 309.19 517)`,
    );
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.frame = null;
    this.setMouthOpen(0);
    this.ready = false;
    this.disposed = true;
  }
}
