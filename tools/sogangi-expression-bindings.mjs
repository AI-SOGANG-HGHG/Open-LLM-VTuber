// Explicit facial variant bindings; lip opening remains an independent axis.
export function addExpressionBindings(parameters, preparation) {
  const partPath = (name) => {
    const part = preparation.parts.find((part) => part.name === name);
    if (!part) throw new Error(`Missing expression artwork: ${name}`);
    return part.path;
  };
  for (const side of ['L', 'R']) {
    parameters
      .find((parameter) => parameter.id === `ParamEye${side}Open`)
      .targets.push({
        mode: 'affine-transform',
        relativeDrawablePath: partPath(`Eye${side}_Anger`),
        states: [0, 1].map((value) => ({
          keyValue: value,
          stateName: value ? 'open' : 'closed',
          transform: { scaleY: value ? 1 : 0.1 },
        })),
      });
  }
  const mouth = parameters.find((parameter) => parameter.id === 'ParamMouthOpenY');
  for (const name of ['Mouth_AngerClosed', 'Mouth_AngerOpen', 'Mouth_SurpriseOpen']) {
    mouth.targets.push({
      mode: 'affine-transform',
      relativeDrawablePath: partPath(name),
      states: [0, 0.25, 1].map((value) => ({
        keyValue: value,
        stateName: value ? 'open' : 'closed',
        opacity: name.endsWith('Closed') ? (value === 0 ? 1 : 0) : value === 0 ? 0 : 1,
        ...(!name.endsWith('Closed')
          ? {
              transform: {
                scaleX: (0.6 + 0.4 * value) * (name === 'Mouth_AngerOpen' ? 1.6 : 1),
                scaleY: (0.1 + 0.9 * value) * (name === 'Mouth_AngerOpen' ? 0.6 : 1),
              },
            }
          : {}),
      })),
    });
  }
  const choices = [
    ...['L', 'R'].flatMap((side) => [
      [`Eye${side}_Open`, [1, 0, 1]],
      [`Eye${side}_Highlight`, [1, 0, 1]],
      [`Eye${side}_Closed`, [1, 0, 1]],
      [`Eye${side}_Anger`, [0, 1, 0]],
    ]),
    ['Mouth_Closed', [1, 0, 1]],
    ['Mouth_Open', [1, 0, 0]],
    ['Mouth_AngerClosed', [0, 1, 0]],
    ['Mouth_AngerOpen', [0, 1, 0]],
    ['Mouth_SurpriseOpen', [0, 0, 1]],
  ];
  parameters.push({
    id: 'ParamFaceMood',
    kind: 'openness',
    defaultValue: 0,
    keys: [0, 1, 2].map((value) => ({ name: value === 0 ? 'default' : 'expression', value })),
    targets: choices.map(([name, opacities]) => ({
      mode: 'affine-transform',
      relativeDrawablePath: partPath(name),
      states: [0, 1, 2].map((value) => ({
        keyValue: value,
        stateName: 'expression',
        opacity: opacities[value],
        ...(value === 2 && /Eye[LR]_(Open|Highlight)$/.test(name)
          ? { transform: { scaleX: 1.12, scaleY: 1.12 } }
          : {}),
      })),
    })),
  });
}
