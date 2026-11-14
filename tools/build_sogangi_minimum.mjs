// Build only the small Sogangi facial rig using a locally installed Editor.
// The pinned converter and its project patch are documented in tools/patches.
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { motionBridgeSource } from './sogangi-motion-bridge.mjs';
import { greetingBridgeSource } from './sogangi-greeting-bridge.mjs';
import { expressionBridgeSource } from './sogangi-expression-bridge.mjs';
import { addExpressionBindings } from './sogangi-expression-bindings.mjs';
const root = path.resolve('.');
const expressions = process.argv.includes('--expressions');
const greeting = process.argv.includes('--greeting') || expressions;
const motion = process.argv.includes('--motion') || greeting;
const profile = expressions ? 'expressions' : greeting ? 'greeting' : motion ? 'motion' : 'minimum';
function option(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index < 0) return fallback;
  if (!process.argv[index + 1] || process.argv[index + 1].startsWith('--'))
    throw new Error(`Missing ${name} value`);
  return path.resolve(process.argv[index + 1]);
}
function inside(base, file) {
  const relative = path.relative(base, file);
  return (
    relative !== '' &&
    relative !== '..' &&
    !relative.startsWith('..' + path.sep) &&
    !path.isAbsolute(relative)
  );
}
const sha = (data) => createHash('sha256').update(data).digest('hex');
// Windows console code pages must not corrupt Korean paths in Java JSON output.
process.env.JAVA_TOOL_OPTIONS = [
  process.env.JAVA_TOOL_OPTIONS || '',
  '-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8 -Dsun.stdout.encoding=UTF-8 -Dsun.stderr.encoding=UTF-8',
]
  .join(' ')
  .trim();
const converter = option('--converter', path.resolve('../reference-sources/autoLive2d'));
const editor = option('--editor', path.join(root, 'tmp/tools/cubism-editor-5.1.03'));
const output = option('--output', path.join(root, `tmp/cubism-export/${profile}`));
if (!inside(path.join(root, 'tmp'), output))
  throw new Error('Build output must stay in a subdirectory of project tmp');
const upstreamCommit = '4fcdf472d21488c8e8258fd05a601b2822855705';
const commit = execFileSync(
  'git',
  [
    '-c',
    `safe.directory=${converter.split(path.sep).join('/')}`,
    '-C',
    converter,
    'rev-parse',
    'HEAD',
  ],
  { encoding: 'utf8' },
).trim();
if (commit !== upstreamCommit)
  throw new Error('Review the converter before building with a different commit');
const converterSource = await readFile(path.join(converter, 'src/cubism/official.ts'), 'utf8');
if (
  !converterSource.includes('Project adapter: preserve source resolution') ||
  !converterSource.includes('final int atlasSize = 2048;')
)
  throw new Error(
    'Apply tools/patches/autolive2d-padded-atlas.patch to the pinned converter first',
  );
const source = path.join(
  root,
  expressions
    ? 'web_tool/sogangi/assets/expressions/sogangi-expressions.psd'
    : 'web_tool/sogangi/assets/cubism-import/sogangi-cubism-import.psd',
);
const preparation = JSON.parse(
  await readFile(path.join(path.dirname(source), 'import-manifest.json'), 'utf8'),
);
if (
  createHash('sha256')
    .update(await readFile(source))
    .digest('hex') !== preparation.psd_sha256
)
  throw new Error('Source PSD hash changed');
await mkdir(output, { recursive: true });
const { tsImport } = await import(
  pathToFileURL(path.join(converter, 'node_modules/tsx/dist/esm/api/index.mjs'))
);
let apiPath = path.join(converter, 'src/cubism/official.ts');
if (motion) {
  apiPath = path.join(output, 'motion-export-adapter.mts');
  await writeFile(
    apiPath,
    (expressions ? expressionBridgeSource : greeting ? greetingBridgeSource : motionBridgeSource)(
      converterSource,
      converter,
    ),
  );
}
const api = await tsImport(pathToFileURL(apiPath).href, import.meta.url);
const bindingApi = await tsImport(
  pathToFileURL(path.join(converter, 'src/pipeline/strictBinding.ts')).href,
  import.meta.url,
);
const parameters = [];
for (const side of ['L', 'R']) {
  parameters.push({
    id: `ParamEye${side}Open`,
    kind: 'openness',
    defaultValue: 1,
    keys: [
      { name: 'closed', value: 0 },
      { name: 'open', value: 1 },
    ],
    targets: ['Open', 'Highlight', 'Closed'].map((part) => ({
      mode: 'affine-transform',
      relativeDrawablePath: [`Eye ${side}`, `Eye${side}_${part}`],
      states: [0, 1].map((value) => ({
        keyValue: value,
        stateName: value ? 'open' : 'closed',
        opacity: part === 'Closed' ? 1 - value : value,
      })),
    })),
  });
}
parameters.push({
  id: 'ParamMouthOpenY',
  kind: 'openness',
  defaultValue: 0,
  keys: [
    { name: 'closed', value: 0 },
    { name: 'default', value: 0.25 },
    { name: 'open', value: 1 },
  ],
  targets: ['Closed', 'Open'].map((part) => ({
    mode: 'affine-transform',
    relativeDrawablePath: ['Mouth', `Mouth_${part}`],
    states: [0, 0.25, 1].map((value) => ({
      keyValue: value,
      stateName: value === 0 ? 'closed' : value === 1 ? 'open' : 'default',
      opacity: part === 'Closed' ? (value === 0 ? 1 : 0) : value === 0 ? 0 : 1,
      ...(part === 'Open'
        ? { transform: { scaleX: 0.74 + value * 0.26, scaleY: 0.25 + value * 0.75 } }
        : {}),
    })),
  })),
});
const manifest = { profile: 'infer-sample', parameters };
if (motion) {
  const rig = JSON.parse(
    await readFile(path.join(root, 'web_tool/sogangi/rigging-map.json'), 'utf8'),
  );
  if (greeting) {
    const arm = rig.deformers.find((deformer) => deformer.id === 'ArmRWave');
    if (!arm || arm.parts.length !== 1 || arm.parts[0] !== 'ArmR_Base')
      throw new Error('Reviewed right-arm binding changed');
    const values = [0, 0.25, 0.5, 0.75, 1];
    parameters.push({
      id: 'ParamArmRWave',
      kind: 'angle',
      defaultValue: 0,
      keys: values.map((value) => ({ name: value === 0 ? 'default' : 'motion', value })),
      targets: [
        {
          mode: 'affine-transform',
          relativeDrawablePath: preparation.parts.find((part) => part.name === 'ArmR_Base').path,
          states: values.map((value) => ({
            keyValue: value,
            stateName: value === 0 ? 'default' : 'motion',
            transform: { pivotX: arm.pivot[0], pivotY: arm.pivot[1], rotationDeg: -32 * value },
          })),
        },
      ],
    });
  }
  if (expressions) {
    addExpressionBindings(parameters, preparation);
    for (const group of ['HeadTurn', 'BodyBreath']) {
      rig.deformers
        .find((deformer) => deformer.id === group)
        .parts.push(
          'EyeL_Anger',
          'EyeR_Anger',
          'Mouth_AngerClosed',
          'Mouth_AngerOpen',
          'Mouth_SurpriseOpen',
        );
    }
  }
  for (const [id, group, values] of [
    ['ParamAngleZ', 'HeadTurn', [-30, 0, 30]],
    ['ParamBreath', 'BodyBreath', [0, 0.5, 1]],
  ]) {
    const design = rig.deformers.find((deformer) => deformer.id === group);
    if (
      !design ||
      design.parts.some((name) => !preparation.parts.some((part) => part.name === name))
    )
      throw new Error('Motion targets no longer match the reviewed PSD parts');
    parameters.push({
      id,
      kind: id === 'ParamAngleZ' ? 'angle' : 'openness',
      defaultValue: 0,
      keys: values.map((value) => ({ name: value === 0 ? 'default' : 'motion', value })),
      targets: design.parts.map((name) => ({
        mode: 'affine-transform',
        relativeDrawablePath: preparation.parts.find((part) => part.name === name).path,
        states: values.map((value) => ({
          keyValue: value,
          stateName: value === 0 ? 'default' : 'motion',
          transform: {
            pivotX: design.pivot[0],
            pivotY: design.pivot[1],
            ...(id === 'ParamAngleZ'
              ? { rotationDeg: value * 0.1 }
              : { scaleY: 1 + value * 0.004, translateY: -value * 4 }),
          },
        })),
      })),
    });
  }
}
await writeFile(path.join(output, `${profile}.binding.json`), JSON.stringify(manifest, null, 2));
const xmlPath = path.join(output, `${profile}.binding.xml`);
await writeFile(xmlPath, bindingApi.serializeBindingManifestXml(manifest));
console.log('Exporting real Cubism model using the installed Editor libraries...');
const report = await api.exportOfficialMoc3FromPsd({
  sourceDir: editor,
  vendorDir: path.join(root, 'tmp/cubism-bridge'),
  psdPath: source,
  outputMoc3Path: path.join(output, 'sogangi.moc3'),
  outputTextureDir: path.join(output, 'textures'),
  bindingManifestPath: xmlPath,
  reportPath: path.join(output, 'export-report.json'),
});
console.log(
  JSON.stringify({
    status: report.status,
    written: report.moc3Written,
    version: report.selectedVersion,
    consistent: report.selectedConsistency,
    drawables: report.selectedDrawableCount,
    parameters: report.selectedParameterCount,
    error: report.error,
  }),
);
if (
  !report.moc3Written ||
  !report.selectedConsistency ||
  report.selectedDrawableCount !== preparation.parts.length
)
  throw new Error('Native MOC export did not validate all source parts');
const moc = await readFile(path.join(output, 'sogangi.moc3'));
if (moc.subarray(0, 4).toString('ascii') !== 'MOC3')
  throw new Error('Native output is not a MOC3 file');
const model = {
  Version: 3,
  FileReferences: {
    Moc: 'sogangi.moc3',
    Textures: report.texturePaths.map((file) =>
      path.relative(output, file).split(path.sep).join('/'),
    ),
  },
  Groups: [
    { Target: 'Parameter', Name: 'EyeBlink', Ids: ['ParamEyeLOpen', 'ParamEyeROpen'] },
    { Target: 'Parameter', Name: 'LipSync', Ids: ['ParamMouthOpenY'] },
  ],
};
if (
  model.FileReferences.Textures.length !== 1 ||
  model.FileReferences.Textures.some(
    (file) => file.startsWith('../') || !/^textures\/texture_\d+\.png$/.test(file),
  )
)
  throw new Error('Native texture path encoding/containment did not validate');
const expressionFiles = [];
if (expressions) {
  await mkdir(path.join(output, 'expressions'), { recursive: true });
  model.FileReferences.Expressions = [];
  for (const [name, mood] of [
    ['neutral', 0],
    ['joy', 0],
    ['anger', 1],
    ['surprise', 2],
  ]) {
    const file = `expressions/${name}.exp3.json`;
    await writeFile(
      path.join(output, file),
      JSON.stringify(
        {
          Type: 'Live2D Expression',
          FadeInTime: 0,
          FadeOutTime: 0,
          Parameters: [
            { Id: 'ParamFaceMood', Value: mood, Blend: 'Overwrite' },
            ...['L', 'R'].map((side) => ({
              Id: `ParamEye${side}Open`,
              Value: name === 'joy' ? 0 : 1,
              Blend: 'Overwrite',
            })),
          ],
        },
        null,
        2,
      ),
    );
    expressionFiles.push(file);
    model.FileReferences.Expressions.push({ Name: name, File: file });
  }
}
const texture = await readFile(path.join(output, model.FileReferences.Textures[0]));
if (
  texture.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a' ||
  texture.readUInt32BE(16) !== 2048 ||
  texture.readUInt32BE(20) !== 2048
)
  throw new Error('Expected one real 2048 PNG atlas');
model.SogangiMinimum = {
  Stage: expressions
    ? 'four_semantic_expressions_rig'
    : greeting
      ? 'right_arm_greeting_rig'
      : motion
        ? 'small_head_tilt_and_breathing_rig'
        : 'minimum_facial_rig',
  WiredParameters: parameters.map((parameter) => parameter.id),
  Pending: expressions
    ? ['3D head turns', 'additional emotion artwork', 'physics', 'deformer hierarchy']
    : greeting
      ? ['3D head turns', 'expanded expressions', 'physics', 'deformer hierarchy']
      : motion
        ? ['3D head turns', 'arm greeting', 'expanded expressions', 'physics', 'deformer hierarchy']
        : ['head angles', 'breathing', 'arm greeting', 'expressions', 'physics'],
  Geometry: expressions
    ? 'Official face variants with project affine adaptations; composed mood/blink/lip/head/breath/arm keys; no deformers'
    : greeting
      ? 'PSD-import base ArtMeshes; composed facial, head/breath and right-arm shoulder rotation keys; no deformers'
      : motion
        ? 'PSD-import base ArtMeshes; composed eye/mouth, small 2D head tilt and upper-body breathing keys; no deformers'
        : 'PSD-import base ArtMeshes; facial opacity/affine keys',
};
await writeFile(path.join(output, 'sogangi.model3.json'), JSON.stringify(model, null, 2));
const cmo = await readFile(path.join(output, 'from-psd.cmo3'));
if (cmo.subarray(0, 4).toString('ascii') !== 'CAFF')
  throw new Error('Native editing project was not saved');
const build = {
  schema_version: 1,
  status: 'native_export_passed_browser_check_separate',
  source_psd_sha256: preparation.psd_sha256,
  converter_commit: commit,
  converter_source_sha256: sha(converterSource),
  ...(expressions
    ? {
        expression_adapter_sha256: sha(
          await readFile(path.join(root, 'tools/sogangi-expression-bridge.mjs')),
        ),
        expression_bindings_sha256: sha(
          await readFile(path.join(root, 'tools/sogangi-expression-bindings.mjs')),
        ),
        expression_files: Object.fromEntries(
          await Promise.all(
            expressionFiles.map(async (file) => [
              file,
              sha(await readFile(path.join(output, file))),
            ]),
          ),
        ),
      }
    : {}),
  ...(greeting
    ? {
        greeting_adapter_sha256: sha(
          await readFile(path.join(root, 'tools/sogangi-greeting-bridge.mjs')),
        ),
      }
    : {}),
  ...(motion
    ? {
        motion_adapter_sha256: sha(
          await readFile(path.join(root, 'tools/sogangi-motion-bridge.mjs')),
        ),
      }
    : {}),
  patch_sha256: sha(await readFile(path.join(root, 'tools/patches/autolive2d-padded-atlas.patch'))),
  moc_sha256: sha(moc),
  cmo_sha256: sha(cmo),
  texture_sha256: sha(texture),
  texture_size: [2048, 2048],
  drawables: report.selectedDrawableCount,
  core_parameters: report.selectedParameterCount,
  wired_parameters: parameters.map((parameter) => parameter.id),
  native_consistency: report.selectedConsistency,
  export_version: report.selectedVersion,
  geometry: model.SogangiMinimum.Geometry,
};
await writeFile(path.join(output, 'build-manifest.json'), JSON.stringify(build, null, 2));
if (process.argv.includes('--stage-preview')) {
  const staged = path.join(root, `live2d-models/sogangi-${profile}`);
  for (const directory of ['runtime/textures', 'source'])
    await mkdir(path.join(staged, directory), { recursive: true });
  if (expressions) await mkdir(path.join(staged, 'runtime/expressions'), { recursive: true });
  for (const file of [
    'sogangi.moc3',
    'sogangi.model3.json',
    ...model.FileReferences.Textures,
    ...expressionFiles,
  ])
    await copyFile(path.join(output, file), path.join(staged, 'runtime', file));
  await copyFile(
    path.join(output, 'from-psd.cmo3'),
    path.join(staged, `source/sogangi-${profile}.cmo3`),
  );
  for (const file of [`${profile}.binding.json`, `${profile}.binding.xml`])
    await copyFile(path.join(output, file), path.join(staged, 'source', file));
  await copyFile(
    path.join(output, 'build-manifest.json'),
    path.join(staged, 'build-manifest.json'),
  );
}
console.log(
  'Real model prepared. Run the browser checks; main character/model registration is a separate step.',
);
