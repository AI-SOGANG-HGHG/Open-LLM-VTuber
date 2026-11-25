/* Local developer inspector; no conversation WebSocket, model API or audio synthesis. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const stage = $('modelStage');
  let app,
    model,
    epoch = 0,
    closed = false,
    sweep = null;
  const controls = new Map();
  let motionDefinitions = {};
  function updateMotionEntries() {
    const entries = motionDefinitions[$('modelMotion').value] || [];
    $('modelMotionEntry').replaceChildren(
      ...entries.map((entry, index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = entry.File;
        return option;
      }),
    );
    $('modelMotionEntry').disabled = !entries.length;
    $('playMotion').disabled = !entries.length;
  }
  function status(text, error = false) {
    $('previewStatus').textContent = text;
    $('previewStatus').dataset.error = String(error);
  }
  function modelUrl(value) {
    if (typeof value !== 'string' || /[\\?#]/.test(value) || value.split('/').includes('..'))
      throw new Error('로컬 모델 경로를 확인해 주세요.');
    const url = new URL(value, location.origin);
    if (
      url.origin !== location.origin ||
      !url.pathname.startsWith('/live2d-models/') ||
      !url.pathname.endsWith('.model3.json')
    )
      throw new Error('/live2d-models/ 아래 model3.json 경로를 입력해 주세요.');
    return url;
  }
  function checkReference(value, base) {
    if (typeof value !== 'string' || !value || /[\\?#]/.test(value))
      throw new Error('잘못된 모델 참조 경로예요.');
    const decoded = decodeURIComponent(value);
    if (/[\\?#]/.test(decoded)) throw new Error('잘못된 모델 참조 경로예요.');
    const url = new URL(decoded, base);
    const directory = base.pathname.slice(0, base.pathname.lastIndexOf('/') + 1);
    if (url.origin !== location.origin || !url.pathname.startsWith(directory))
      throw new Error('모델 폴더 밖을 참조하는 파일은 불러오지 않아요.');
  }
  function checkSettings(settings, url) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings))
      throw new Error('모델 설정은 JSON 객체여야 해요.');
    if (
      settings.Version !== 3 ||
      !settings.FileReferences ||
      typeof settings.FileReferences.Moc !== 'string' ||
      !Array.isArray(settings.FileReferences.Textures) ||
      !settings.FileReferences.Textures.length
    )
      throw new Error('Cubism 3/4 model3.json 구조를 확인해 주세요.');
    const refs = settings.FileReferences;
    if (
      settings.Groups !== undefined &&
      (!Array.isArray(settings.Groups) ||
        settings.Groups.some(
          (group) =>
            !group ||
            typeof group.Name !== 'string' ||
            !Array.isArray(group.Ids) ||
            !group.Ids.every((id) => typeof id === 'string'),
        ))
    )
      throw new Error('모델의 눈·입 그룹 선언을 확인해 주세요.');
    if (
      refs.Expressions !== undefined &&
      (!Array.isArray(refs.Expressions) ||
        refs.Expressions.some(
          (item) => !item || typeof item.Name !== 'string' || typeof item.File !== 'string',
        ))
    )
      throw new Error('모델의 표정 목록을 확인해 주세요.');
    if (
      refs.Motions !== undefined &&
      (!refs.Motions ||
        typeof refs.Motions !== 'object' ||
        Array.isArray(refs.Motions) ||
        Object.values(refs.Motions).some(
          (entries) =>
            !Array.isArray(entries) ||
            entries.some((item) => !item || typeof item.File !== 'string'),
        ))
    )
      throw new Error('모델의 모션 목록을 확인해 주세요.');
    for (const value of [
      refs.Moc,
      ...refs.Textures,
      ...['Physics', 'Pose', 'DisplayInfo', 'UserData']
        .filter((key) => refs[key])
        .map((key) => refs[key]),
      ...(refs.Expressions || []).map((item) => item.File),
      ...Object.values(refs.Motions || {})
        .flat()
        .flatMap((item) => [item.File, ...(item.Sound ? [item.Sound] : [])]),
    ])
      checkReference(value, url);
  }
  function fit() {
    if (!app || closed) return;
    app.renderer.resize(stage.clientWidth, stage.clientHeight);
    if (!model) return;
    const { originalWidth, originalHeight } = model.internalModel;
    model.scale.set(
      Math.min(stage.clientWidth / originalWidth, stage.clientHeight / originalHeight) * 0.92,
    );
    model.position.set(stage.clientWidth / 2, stage.clientHeight / 2);
  }
  function facts(items) {
    $('modelFacts').replaceChildren();
    for (const [name, value] of items) {
      const term = document.createElement('dt'),
        detail = document.createElement('dd');
      term.textContent = name;
      detail.textContent = String(value);
      $('modelFacts').append(term, detail);
    }
  }
  function parameterControls(settings, loaded, modelPath) {
    controls.clear();
    $('parameterControls').replaceChildren();
    const parameters = loaded.internalModel.coreModel.getModel().parameters;
    const ids = Array.from(parameters.ids);
    const declared = settings.SogangiMinimum?.WiredParameters;
    const wired =
      Array.isArray(declared) && declared.every((id) => typeof id === 'string' && ids.includes(id))
        ? new Set(declared)
        : null;
    stage.dataset.wiredParameters = wired ? [...wired].join(',') : '';
    const lip = settings.Groups?.find((group) => group.Name === 'LipSync')?.Ids || [];
    const moodLabel = modelPath === '/live2d-models/kang-iseo/runtime/kang-iseo.model3.json'
      ? '표정 · 0 중립 / 1 기쁨 / 2 놀람 / 3 분노 / 4 슬픔'
      : '표정 · 0 중립 / 1 화남 / 2 놀람';
    for (const [key, label, candidates] of [
      ['mouth', '입 벌림', [...lip, 'ParamMouthOpenY', 'ParamA']],
      ['eyeL', '왼쪽 눈', ['ParamEyeLOpen']],
      ['eyeR', '오른쪽 눈', ['ParamEyeROpen']],
      ['tilt', '고개 기울기', ['ParamAngleZ']],
      ['breath', '상체 호흡', ['ParamBreath']],
      ['wave', '화면 오른팔 인사', ['ParamArmRWave']],
      ['mood', moodLabel, ['ParamFaceMood']],
    ]) {
      const id = candidates.find((id) => ids.includes(id));
      if (!id) continue;
      const index = ids.indexOf(id);
      const row = document.createElement('label');
      row.className = 'parameter-control';
      row.htmlFor = 'parameter-' + key;
      const title = document.createElement('span'),
        value = document.createElement('output'),
        input = document.createElement('input'),
        note = document.createElement('small');
      title.textContent = label;
      input.type = 'range';
      input.id = 'parameter-' + key;
      input.min = String(parameters.minimumValues[index]);
      input.max = String(parameters.maximumValues[index]);
      input.step = String((Number(input.max) - Number(input.min)) / 200 || 0.01);
      if (id === 'ParamFaceMood') input.step = '1';
      input.value = String(parameters.defaultValues[index]);
      input.disabled = Boolean(wired && !wired.has(id));
      value.value = Number(input.value).toFixed(2);
      value.htmlFor = input.id;
      note.textContent = input.disabled ? `${id} · 아직 키폼 미연결` : id;
      input.addEventListener('input', () => {
        $('manualMode').checked = true;
        sweep = null;
        value.value = Number(input.value).toFixed(2);
      });
      row.append(title, value, input, note);
      $('parameterControls').append(row);
      if (!input.disabled)
        controls.set(key, { id, input, value, default: parameters.defaultValues[index] });
    }
    loaded.internalModel.on('beforeModelUpdate', () => {
      if (model !== loaded) return;
      if (!$('manualMode').checked) {
        stage.dataset.appliedParameters = JSON.stringify(
          Object.fromEntries(
            [...controls.values()].map(({ id }) => [
              id,
              loaded.internalModel.coreModel.getParameterValueById(id),
            ]),
          ),
        );
        return;
      }
      if (sweep !== null) {
        const elapsed = performance.now() - sweep;
        const mouth = controls.get('mouth');
        mouth.input.value = String(
          elapsed >= 2400
            ? mouth.default
            : Number(mouth.input.min) +
                ((Number(mouth.input.max) - Number(mouth.input.min)) *
                  (1 - Math.cos((elapsed / 2400) * Math.PI * 4))) /
                  2,
        );
        mouth.value.value = Number(mouth.input.value).toFixed(2);
        if (elapsed >= 2400) sweep = null;
      }
      for (const { id, input } of controls.values())
        loaded.internalModel.coreModel.setParameterValueById(id, Number(input.value));
      stage.dataset.appliedMouth = controls.get('mouth')?.input.value || '';
      stage.dataset.appliedParameters = JSON.stringify(
        Object.fromEntries(
          [...controls.values()].map(({ id }) => [
            id,
            loaded.internalModel.coreModel.getParameterValueById(id),
          ]),
        ),
      );
    });
    $('mouthSweep').disabled = !controls.has('mouth');
    $('resetPose').disabled = false;
  }
  async function load() {
    const ticket = ++epoch;
    stage.dataset.loading = 'true';
    let loaded;
    try {
      const url = modelUrl($('modelUrl').value.trim());
      status('모델과 참조 파일을 불러오고 있어요.');
      const response = await fetch(url, { cache: 'no-cache' });
      if (!response.ok)
        throw new Error('모델 설정 파일을 읽지 못했어요. 경로와 서버 파일을 확인해 주세요.');
      const settings = await response.json();
      checkSettings(settings, url);
      if (ticket !== epoch || closed) return;
      if (!window.PIXI?.live2d?.Live2DModel || !window.Live2DCubismCore)
        throw new Error('로컬 Cubism 렌더링 라이브러리를 불러오지 못했어요.');
      if (!app) {
        app = new PIXI.Application({
          view: $('modelCanvas'),
          width: stage.clientWidth,
          height: stage.clientHeight,
          backgroundAlpha: 0,
          antialias: true,
          preserveDrawingBuffer: true,
          resolution: Math.min(devicePixelRatio, 2),
          autoDensity: true,
        });
        app.ticker.add(() => {
          stage.dataset.frames = String(Number(stage.dataset.frames || 0) + 1);
        });
        PIXI.live2d.SoundManager.volume = 0;
      }
      const visualSettings = structuredClone(settings);
      // Separate texture identities per load: destroying the old model must not
      // destroy a texture shared by the new model, or reuse an artist's stale export.
      const fresh = (value) => {
        const resource = new URL(value, url);
        resource.searchParams.set('_preview', `${ticket}-${Date.now()}`);
        return resource.href;
      };
      const refs = visualSettings.FileReferences;
      refs.Moc = fresh(refs.Moc);
      refs.Textures = refs.Textures.map(fresh);
      for (const key of ['Physics', 'Pose', 'DisplayInfo', 'UserData'])
        if (refs[key]) refs[key] = fresh(refs[key]);
      for (const entry of refs.Expressions || []) entry.File = fresh(entry.File);
      for (const entries of Object.values(visualSettings.FileReferences.Motions || {}))
        for (const entry of entries) {
          delete entry.Sound;
          entry.File = fresh(entry.File);
        }
      loaded = await PIXI.live2d.Live2DModel.from(
        { ...visualSettings, url: url.href },
        {
          autoInteract: false,
          idleMotionGroup: '__manual_preview__',
          motionPreload: PIXI.live2d.MotionPreloadStrategy.NONE,
        },
      );
      if (ticket !== epoch || closed) {
        loaded.destroy({ children: true, texture: true, baseTexture: true });
        return;
      }
      model?.destroy({ children: true, texture: true, baseTexture: true });
      model = loaded;
      sweep = null;
      model.anchor.set(0.5, 0.5);
      app.stage.addChild(model);
      parameterControls(settings, model, url.pathname);
      fit();
      const expressions = settings.FileReferences.Expressions || [];
      $('modelExpression').replaceChildren(
        ...expressions.map((item, index) => {
          const option = document.createElement('option');
          option.value = String(index);
          option.textContent = item.Name || `표정 ${index}`;
          return option;
        }),
      );
      $('modelExpression').disabled = !expressions.length;
      const groups = Object.keys(settings.FileReferences.Motions || {});
      $('modelMotion').replaceChildren(
        ...groups.map((name) => {
          const option = document.createElement('option');
          option.value = name;
          option.textContent = name;
          return option;
        }),
      );
      $('modelMotion').disabled = !groups.length;
      motionDefinitions = settings.FileReferences.Motions || {};
      updateMotionEntries();
      facts([
        ['모델', url.pathname],
        ['Core 파라미터', model.internalModel.coreModel.getParameterCount()],
        ...(stage.dataset.wiredParameters
          ? [['최소 리깅 연결', stage.dataset.wiredParameters]]
          : []),
        ['표정 / 모션 그룹', `${expressions.length} / ${groups.length}`],
        [
          '립싱크 그룹',
          (settings.Groups?.find((group) => group.Name === 'LipSync')?.Ids || []).join(', ') ||
            '선언 없음',
        ],
      ]);
      stage.dataset.modelUrl = url.pathname;
      stage.dataset.loaded = 'true';
      stage.dataset.revision = String(ticket);
      status(
        stage.dataset.wiredParameters
          ? stage.dataset.wiredParameters.includes('ParamFaceMood')
            ? '표정 모델이에요. 중립·화남·놀람 슬라이더와 표정 파일을 확인해 보세요. 기쁨 파일은 감은 눈을 사용해요.'
            : stage.dataset.wiredParameters.includes('ParamArmRWave')
              ? '팔 인사 모델이에요. 눈·입·고개·호흡과 오른팔을 함께 조작하고 초기화해 보세요.'
              : stage.dataset.wiredParameters.includes('ParamBreath')
                ? '고개·호흡 확장 모델이에요. 눈·입과 기울기·호흡을 함께 조작하고 초기화해 보세요.'
                : '서강이 최소 모델을 표시했어요. 눈·입 슬라이더와 입 왕복 시험을 확인해 주세요. 고개·몸은 아직 미연결이에요.'
          : '실제 Cubism 모델을 표시했어요. 눈·입·기울기와 표정을 확인해 주세요.',
      );
    } catch (error) {
      if (ticket === epoch && !closed)
        status(
          error instanceof Error && !/^[A-Za-z]/.test(error.message)
            ? error.message
            : '모델을 불러오지 못했어요. 파일·텍스처와 Core 호환성을 확인해 주세요.',
          true,
        );
      if (loaded && loaded !== model)
        loaded.destroy({ children: true, texture: true, baseTexture: true });
    } finally {
      if (ticket === epoch) stage.dataset.loading = 'false';
    }
  }
  $('modelForm').addEventListener('submit', (event) => {
    event.preventDefault();
    load();
  });
  const presets = {
    'sogangi-expressions': '/live2d-models/sogangi-expressions/runtime/sogangi.model3.json',
    'sogangi-greeting': '/live2d-models/sogangi-greeting/runtime/sogangi.model3.json',
    'sogangi-motion': '/live2d-models/sogangi-motion/runtime/sogangi.model3.json',
    'sogangi-minimum': '/live2d-models/sogangi-minimum/runtime/sogangi.model3.json',
    mao: '/live2d-models/mao_pro/runtime/mao_pro.model3.json',
  };
  function selectPreset(name) {
    $('modelUrl').value = presets[name];
    load();
  }
  $('loadSogangi').addEventListener('click', () => selectPreset('sogangi-minimum'));
  $('loadSogangiMotion').addEventListener('click', () => selectPreset('sogangi-motion'));
  $('loadSogangiGreeting').addEventListener('click', () => selectPreset('sogangi-greeting'));
  $('loadSogangiExpressions').addEventListener('click', () => selectPreset('sogangi-expressions'));
  $('loadMao').addEventListener('click', () => selectPreset('mao'));
  const initialPreset = new URLSearchParams(location.search).get('model');
  if (Object.hasOwn(presets, initialPreset)) selectPreset(initialPreset);
  $('modelExpression').addEventListener('change', () => {
    const target = model;
    target?.expression(Number($('modelExpression').value)).catch(() => {
      if (target === model) status('표정 파일을 읽지 못했어요.', true);
    });
  });
  $('playMotion').addEventListener('click', () => {
    const target = model,
      group = $('modelMotion').value,
      index = $('modelMotionEntry').value;
    target
      ?.motion(group, Number(index), 3)
      .then((started) => {
        if (started && target === model && !closed) {
          stage.dataset.motionGroup = group;
          stage.dataset.motionIndex = index;
        }
      })
      .catch(() => {
        if (target === model) status('모션 파일을 읽지 못했어요.', true);
      });
  });
  $('modelMotion').addEventListener('change', updateMotionEntries);
  $('mouthSweep').addEventListener('click', () => {
    $('manualMode').checked = true;
    sweep = performance.now();
  });
  $('resetPose').addEventListener('click', () => {
    sweep = null;
    $('manualMode').checked = true;
    model?.internalModel.motionManager.stopAllMotions();
    for (const control of controls.values()) {
      control.input.value = String(control.default);
      control.value.value = Number(control.input.value).toFixed(2);
    }
  });
  const resizeObserver = new ResizeObserver(fit);
  resizeObserver.observe(stage);
  window.addEventListener('pagehide', () => {
    closed = true;
    epoch++;
    resizeObserver.disconnect();
    app?.destroy(true, { children: true, texture: true, baseTexture: true });
  });
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) location.reload();
  });
})();
