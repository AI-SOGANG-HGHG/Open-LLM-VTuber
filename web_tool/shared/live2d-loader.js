import { createRandomId } from './random-id.js';
import { kangIseoFaces } from './kang-iseo-expressions.js';
// Loads only the approved local model paths.
let libraries;
export const maoExpressionIndices = Object.freeze({
  neutral: 0, sadness: 1, anger: 2, joy: 3, surprise: 3,
});
export const kangIseoModel = '/live2d-models/kang-iseo/runtime/kang-iseo.model3.json';
export const kangIseoExpressions = Object.freeze(Object.keys(kangIseoFaces));

const approvedModels = [
  '/live2d-models/mao_pro/runtime/mao_pro.model3.json',
  '/live2d-models/sogangi-expressions/runtime/sogangi.model3.json',
  kangIseoModel,
];
const eyeParameters = ['ParamEyeLOpen', 'ParamEyeROpen'];
const mouthParameter = 'ParamMouthOpenY';

function loadScript(url, ready) {
  if (ready()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    const timer = setTimeout(() => finish(false), 12000);
    function finish(ok) {
      clearTimeout(timer);
      script.onload = script.onerror = null;
      if (!ok) script.remove();
      ok && ready() ? resolve() : reject(Error('Preview library unavailable'));
    }
    script.src = url;
    script.onload = () => finish(true);
    script.onerror = () => finish(false);
    document.head.append(script);
  });
}
function loadLibraries() {
  if (!libraries) libraries = (async () => {
    await loadScript('/libs/live2dcubismcore.min.js', () => Boolean(window.Live2DCubismCore));
    await loadScript(new URL('./vendor/pixi.min.js', import.meta.url).href, () => Boolean(window.PIXI));
    await loadScript(new URL('./vendor/cubism4.min.js', import.meta.url).href, () => Boolean(window.PIXI?.live2d?.Live2DModel));
  })().catch((error) => { libraries = null; throw error; });
  return libraries;
}
export function createLivePreview(canvas, stage, onFailure = () => {}) {
  let app, model, disposed = false, kangIseo = false;
  let expressionIndices = maoExpressionIndices;
  const pose = { mouth: 0, gaze: 0, reduced: false, expression: 'neutral' };
  const started = performance.now();
  const request = new AbortController();
  const resize = new ResizeObserver(fit);
  function fail(error) {
    if (disposed) return;
    app?.ticker.stop();
    onFailure(error);
  }
  function contextLost(event) {
    event.preventDefault();
    fail(Error('WebGL context lost'));
  }
  canvas.addEventListener('webglcontextlost', contextLost);
  function fit() {
    if (!app || disposed || !model) return;
    try {
      if (app.renderer.gl?.isContextLost()) { fail(Error('WebGL context lost')); return; }
      app.renderer.resize(stage.clientWidth, stage.clientHeight);
      const { originalWidth, originalHeight } = model.internalModel;
      model.scale.set(Math.min(stage.clientWidth / originalWidth, stage.clientHeight / originalHeight) * .96);
      model.position.set(stage.clientWidth / 2, stage.clientHeight / 2);
      app.renderer.render(app.stage);
    } catch (error) { fail(error); }
  }
  return {
    async load(path) {
      if (!approvedModels.includes(path)) throw Error('Unknown model');
      kangIseo = path === kangIseoModel;
      const response = await fetch(path, { signal: request.signal, cache: 'no-cache' });
      if (!response.ok) throw Error('Model unavailable');
      const settings = await response.json();
      const url = new URL(path, location.origin);
      const directory = url.pathname.slice(0, url.pathname.lastIndexOf('/') + 1);
      const identity = createRandomId();
      function fresh(value) {
        const resource = new URL(value, url);
        if (resource.origin !== url.origin || !resource.pathname.startsWith(directory)) throw Error('Invalid model resource');
        resource.searchParams.set('_preview', identity);
        return resource.href;
      }
      const refs = settings.FileReferences;
      refs.Moc = fresh(refs.Moc);
      refs.Textures = refs.Textures.map(fresh);
      for (const key of ['Physics', 'Pose', 'DisplayInfo', 'UserData']) if (refs[key]) refs[key] = fresh(refs[key]);
      for (const item of refs.Expressions || []) item.File = fresh(item.File);
      for (const entries of Object.values(refs.Motions || {})) for (const item of entries) { item.File = fresh(item.File); delete item.Sound; }
      if (kangIseo) {
        expressionIndices = Object.fromEntries((refs.Expressions || []).map((item, index) => [item.Name, index]));
        const hasParameters = (name, ids) => settings.Groups?.some((group) =>
          group.Target === 'Parameter' && group.Name === name && ids.every((id) => group.Ids?.includes(id)),
        );
        if (!hasParameters('EyeBlink', eyeParameters) || !hasParameters('LipSync', [mouthParameter]) ||
            !kangIseoExpressions.every((name) => Object.hasOwn(expressionIndices, name))) {
          throw Error('Kang Iseo model is missing eye, lip sync, or expression bindings');
        }
      }
      await loadLibraries();
      if (disposed) throw Error('Preview closed');
      app = new PIXI.Application({ view: canvas, width: stage.clientWidth, height: stage.clientHeight, backgroundAlpha: 0, antialias: true, powerPreference: 'low-power', resolution: Math.min(devicePixelRatio, 1.5), autoDensity: true });
      const loaded = await PIXI.live2d.Live2DModel.from({ ...settings, url: url.href }, { autoInteract: false, idleMotionGroup: '__preview__', motionPreload: PIXI.live2d.MotionPreloadStrategy.NONE });
      if (disposed) { loaded.destroy({ children: true, texture: true, baseTexture: true }); throw Error('Preview closed'); }
      model = loaded;
      model.anchor.set(.5, .5);
      const core = model.internalModel.coreModel;
      const ids = new Set(Array.from(core.getModel().parameters.ids));
      if (kangIseo) {
        if (![...eyeParameters, mouthParameter].every((id) => ids.has(id))) {
          throw Error('Kang Iseo MOC is missing eye or lip sync parameters');
        }
        const manager = model.internalModel.motionManager.expressionManager;
        const expressions = await Promise.all(
          kangIseoExpressions.map((name) => manager.loadExpression(expressionIndices[name])),
        );
        if (disposed) throw Error('Preview closed');
        if (expressions.some((expression) => !expression)) throw Error('Kang Iseo expression unavailable');
        await model.expression(expressionIndices.neutral);
        if (disposed) throw Error('Preview closed');
        canvas.dataset.expression = 'neutral';
      }
      const set = (id, value) => { if (ids.has(id)) core.setParameterValueById(id, value); };
      model.internalModel.on('beforeModelUpdate', () => {
        if (disposed) return;
        const elapsed = performance.now() - started;
        const reduced = pose.reduced || matchMedia('(prefers-reduced-motion: reduce)').matches;
        const blink = elapsed % 4300;
        const eyes = reduced || blink > 180 ? 1 : Math.min(1, Math.abs(blink - 90) / 90);
        for (const id of eyeParameters) set(id, eyes);
        set(mouthParameter, pose.mouth);
        set('ParamBreath', reduced ? 0 : (1 - Math.cos(elapsed / 4800 * Math.PI * 2)) / 2);
        set('ParamAngleZ', reduced ? 0 : pose.gaze * (kangIseo ? 3 : 8));
        canvas.dataset.appliedMouth = String(kangIseo ? core.getParameterValueById(mouthParameter) : pose.mouth);
        if (kangIseo) canvas.dataset.eyeOpen = String(core.getParameterValueById(eyeParameters[0]));
        canvas.dataset.frames = String(Number(canvas.dataset.frames || 0) + 1);
      });
      app.stage.addChild(model);
      fit();
      if (disposed) throw Error('Preview closed');
      resize.observe(stage);
      canvas.dataset.loaded = 'true';
    },
    setMouthOpen(amount) { pose.mouth = Math.max(0, Math.min(1, Number(amount) || 0)); },
    setReducedMotion(reduced) { pose.reduced = reduced; },
    lookAt(x) { pose.gaze = Math.max(-1, Math.min(1, Number(x) || 0)); },
    setExpression(name) {
      const expression = Object.hasOwn(expressionIndices, name) ? name : 'neutral';
      if (pose.expression === expression) return;
      pose.expression = expression;
      model?.expression(expressionIndices[expression]).then((applied) => {
        if (kangIseo && applied && !disposed && pose.expression === expression) canvas.dataset.expression = expression;
      }).catch((error) => { if (kangIseo) fail(error); });
    },
    greet() {
      if (!model || disposed || pose.reduced) return false;
      model.motion('Idle', 0, 3).catch(() => {});
      return true;
    },
    cancelGesture() { model?.internalModel.motionManager.stopAllMotions(); },
    destroy() {
      if (disposed) return;
      disposed = true;
      request.abort();
      resize.disconnect();
      canvas.removeEventListener('webglcontextlost', contextLost);
      app?.destroy(false, { children: true, texture: true, baseTexture: true });
      app = null; model = null;
      delete canvas.dataset.loaded;
    },
  };
}
