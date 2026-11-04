const $ = (id) => document.getElementById(id);
async function init() {
  try {
    const response = await fetch('./rigging-map.json');
    if (!response.ok) throw new Error('map');
    const map = await response.json();
    $('riggingCanvas').setAttribute('viewBox', `0 0 ${map.canvas.width} ${map.canvas.height}`);
    const image = $('riggingCanvas').querySelector('image');
    image.setAttribute('width', map.canvas.width);
    image.setAttribute('height', map.canvas.height);
    $('riggingCanvasNote').textContent =
      `좌상단 (0, 0) · PSD ${map.canvas.width}×${map.canvas.height} · L/R은 화면 기준`;
    const parts = new Map(map.parts.map((part) => [part.id, part]));
    let mode = 'deformers';
    function select(item, button) {
      for (const entry of $('riggingItems').children)
        entry.setAttribute('aria-pressed', String(entry === button));
      $('riggingId').textContent = item.id;
      $('riggingLabel').textContent = item.label;
      $('riggingNote').textContent = item.note;
      let bounds = item.bounds;
      const names = item.parts || [item.id];
      if (!bounds) {
        const boxes = names.map((id) => parts.get(id)?.bounds).filter(Boolean);
        const minX = Math.min(...boxes.map((box) => box[0])),
          minY = Math.min(...boxes.map((box) => box[1]));
        bounds = [
          minX,
          minY,
          Math.max(...boxes.map((box) => box[0] + box[2])) - minX,
          Math.max(...boxes.map((box) => box[1] + box[3])) - minY,
        ];
      }
      for (const [index, key] of ['x', 'y', 'width', 'height'].entries())
        $('rigBounds').setAttribute(key, bounds[index]);
      $('rigBounds').style.stroke = mode === 'underpainting' ? '#b58027' : '#b51f38';
      $('rigBounds').style.strokeDasharray = mode === 'underpainting' ? '10 7' : 'none';
      $('rigPivot').style.display = item.pivot ? '' : 'none';
      if (item.pivot) $('rigPivot').setAttribute('transform', `translate(${item.pivot.join(' ')})`);
      $('riggingFacts').replaceChildren();
      const details = [
        [
          '상태',
          mode === 'parts'
            ? '실제 PSD 레이어 경계'
            : mode === 'underpainting'
              ? '보완 검토 영역'
              : '제작자 검토용 피벗 초안',
        ],
        ['상위 계층', item.parent || '—'],
        ['범위', bounds.map((value) => Number(value).toFixed(1)).join(', ')],
      ];
      if (item.pivot)
        details.push(['피벗 X / Y', item.pivot.map((value) => value.toFixed(1)).join(' / ')]);
      if (mode === 'parts')
        details.push(['기본 가시성', item.visible ? '보임' : '숨김 · 표정 후보']);
      for (const [name, value] of details) {
        const term = document.createElement('dt'),
          detail = document.createElement('dd');
        term.textContent = name;
        detail.textContent = value;
        $('riggingFacts').append(term, detail);
      }
      $('riggingParts').replaceChildren(
        ...names.map((name) => {
          const li = document.createElement('li');
          li.textContent = name;
          return li;
        }),
      );
      const bindings = map.bindings.filter((binding) => binding.deformer === item.id);
      $('riggingBindings').replaceChildren(
        ...(bindings.length
          ? bindings.map((binding) => {
              const li = document.createElement('li');
              li.textContent = `${binding.parameter}: ${binding.initial_keys.join(' / ')} · ${binding.note}`;
              return li;
            })
          : [
              Object.assign(document.createElement('li'), {
                textContent: '이 항목에 직접 연결한 파라미터 초안은 없어요.',
              }),
            ]),
      );
      $('riggingCanvas').dataset.selected = item.id;
      $('riggingCanvas').dataset.mode = mode;
    }
    function render() {
      $('riggingItems').replaceChildren();
      for (const item of map[mode]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = item.label;
        button.addEventListener('click', () => select(item, button));
        $('riggingItems').append(button);
      }
      $('riggingItems').firstElementChild.click();
    }
    for (const button of document.querySelectorAll('[data-rig-mode]'))
      button.addEventListener('click', () => {
        mode = button.dataset.rigMode;
        for (const entry of document.querySelectorAll('[data-rig-mode]'))
          entry.setAttribute('aria-pressed', String(entry === button));
        render();
      });
    render();
  } catch {
    $('riggingError').hidden = false;
  }
}
init();
