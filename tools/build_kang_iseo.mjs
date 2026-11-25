// Export the seven-layer Kang Iseo PSD with the same Editor bridge as Sogangi.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { copyFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { expressionBridgeSource } from './sogangi-expression-bridge.mjs';
import { kangIseoFaces } from '../web_tool/shared/kang-iseo-expressions.js';

const root = path.resolve('.');
const tmp = path.join(root, 'tmp');
const source = path.join(root, 'docs/assets/vtuber-concepts/sogang-mascot-vtubers/ivory-crown-rig-draft/ivory-crown-facial-draft.psd');
const reviewedConverter = '4fcdf472d21488c8e8258fd05a601b2822855705';
const sha = (data) => createHash('sha256').update(data).digest('hex');

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1) return fallback;
  const value = process.argv[index + 1];
  if (!value || value.startsWith('--')) throw Error(`Missing ${name} value`);
  return path.resolve(value);
}

const converter = option('--converter', path.join(tmp, 'autoLive2d'));
const editor = option('--editor', path.join(tmp, 'tools/cubism-editor-5.1.03'));
const output = option('--output', path.join(tmp, 'cubism-export/kang-iseo'));
const relativeOutput = path.relative(tmp, output);
if (!relativeOutput || relativeOutput === '..' || relativeOutput.startsWith(`..${path.sep}`) || path.isAbsolute(relativeOutput)) {
  throw Error('Build output must be in a subdirectory of project tmp');
}

const parts = [
  ['Base_HeadBody'], ['Eye L', 'EyeL_Open'], ['Eye L', 'EyeL_Closed'],
  ['Eye R', 'EyeR_Open'], ['Eye R', 'EyeR_Closed'], ['Mouth', 'Mouth_Closed'], ['Mouth', 'Mouth_Open'],
];
const eyeIds = ['ParamEyeLOpen', 'ParamEyeROpen'];
const mouthId = 'ParamMouthOpenY';
const expressions = Object.keys(kangIseoFaces);
const faceValues = expressions.map((_, index) => index);

function parameter(id, defaultValue, values, drawables, stateFor, kind = 'openness') {
  const keyName = (value) => value === defaultValue ? 'default' : 'key';
  return {
    id, kind, defaultValue,
    keys: values.map((value) => ({ value, name: keyName(value) })),
    targets: drawables.map((drawable) => ({
      mode: 'affine-transform', relativeDrawablePath: drawable,
      states: values.map((value) => ({ keyValue: value, stateName: keyName(value), ...stateFor(drawable.at(-1), value) })),
    })),
  };
}

const parameters = [];
for (const [side, pivotX] of [['L', 440.5], ['R', 596.5]]) {
  parameters.push(parameter(`ParamEye${side}Open`, 1, [0, 0.2, 1], parts.filter(([group]) => group === `Eye ${side}`), (name, value) => (
    name.endsWith('_Closed') ? { opacity: value === 0 ? 1 : 0 } : {
      opacity: value === 0 ? 0 : 1,
      transform: { scaleY: Math.max(0.2, value), pivotX, pivotY: 479 },
    }
  )));
}
parameters.push(parameter(mouthId, 0, [0, 0.25, 1], parts.filter(([group]) => group === 'Mouth'), (name, value) => (
  name.endsWith('_Closed') ? { opacity: value === 0 ? 1 : 0 } : {
    opacity: value === 0 ? 0 : 1,
    transform: { scaleY: 0.45 + value * 0.55, pivotX: 517.5, pivotY: 563.5 },
  }
)));
parameters.push(parameter('ParamFaceMood', 0, faceValues, parts.filter((part) => part.at(-1).endsWith('_Open')), (name, value) => {
  const { eyeScale, eyeTilt = 0, mouthWidth = 1, mouthHeight = 1 } = kangIseoFaces[expressions[value]];
  if (name === 'Mouth_Open') {
    return { transform: { scaleX: mouthWidth, scaleY: mouthHeight, pivotX: 517.5, pivotY: 563.5 } };
  }
  const left = name.startsWith('EyeL');
  return { transform: { scaleY: eyeScale, rotationDeg: left ? eyeTilt : -eyeTilt, pivotX: left ? 440.5 : 596.5, pivotY: 479 } };
}));
parameters.push(parameter('ParamAngleZ', 0, [-3, 0, 3], parts, (_name, value) => ({
  transform: { rotationDeg: value, pivotX: 512, pivotY: 1106 },
}), 'angle'));
parameters.push(parameter('ParamBreath', 0, [0, 1], parts, (_name, value) => ({
  transform: { scaleX: 1 + value * 0.008, scaleY: 1 + value * 0.012, pivotX: 512, pivotY: 1106 },
})));

const commit = execFileSync('git', ['-C', converter, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
if (commit !== reviewedConverter) throw Error('Use the reviewed autoLive2d revision');
const bridge = await readFile(path.join(converter, 'src/cubism/official.ts'), 'utf8');
if (!bridge.includes('Project adapter: preserve source resolution') || !bridge.includes('final int atlasSize = 2048;')) {
  throw Error('Apply tools/patches/autolive2d-padded-atlas.patch first');
}
process.env.JAVA_TOOL_OPTIONS = `${process.env.JAVA_TOOL_OPTIONS || ''} -Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8 -Dsun.stdout.encoding=UTF-8 -Dsun.stderr.encoding=UTF-8`.trim();

await mkdir(path.dirname(output), { recursive: true });
await mkdir(output);
const { tsImport } = await import(pathToFileURL(path.join(converter, 'node_modules/tsx/dist/esm/api/index.mjs')));
const { serializeBindingManifestXml } = await tsImport(pathToFileURL(path.join(converter, 'src/pipeline/strictBinding.ts')).href, import.meta.url);
const bindingXml = path.join(output, 'kang-iseo.binding.xml');
await writeFile(bindingXml, serializeBindingManifestXml({ profile: 'infer-sample', parameters }));
const adapter = path.join(output, 'expression-export-adapter.mts');
// The open eyes and mouth each compose 3 openness × 5 moods × 3 tilt × 2 breath forms.
await writeFile(adapter, expressionBridgeSource(bridge, converter, { faceMoods: expressions, maxForms: 90 }));
const { exportOfficialMoc3FromPsd } = await tsImport(pathToFileURL(adapter).href, import.meta.url);
const mocFile = 'kang-iseo.moc3';
const cmoFile = 'from-psd.cmo3';
const report = await exportOfficialMoc3FromPsd({
  sourceDir: editor, vendorDir: path.join(tmp, 'cubism-bridge'), psdPath: source,
  outputMoc3Path: path.join(output, mocFile), outputTextureDir: path.join(output, 'textures'),
  bindingManifestPath: bindingXml, reportPath: path.join(output, 'export-report.json'),
});
if (!report.moc3Written || !report.selectedConsistency || report.selectedDrawableCount !== parts.length) {
  throw Error(`Cubism export did not validate all seven parts: ${report.error || report.status}`);
}

const textures = report.texturePaths.map((file) => path.relative(output, file).split(path.sep).join('/'));
if (textures.length !== 1 || !/^textures\/texture_\d+\.png$/.test(textures[0])) throw Error('Unexpected texture export');
const [moc, cmo, texture] = await Promise.all([mocFile, cmoFile, textures[0]].map((file) => readFile(path.join(output, file))));
if (moc.subarray(0, 4).toString() !== 'MOC3' || cmo.subarray(0, 4).toString() !== 'CAFF' ||
    texture.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a' ||
    texture.readUInt32BE(16) !== 2048 || texture.readUInt32BE(20) !== 2048) {
  throw Error('Cubism project, MOC or texture failed its file check');
}

const expressionFiles = expressions.map((Name) => ({ Name, File: `expressions/${Name}.exp3.json` }));
await mkdir(path.join(output, 'expressions'));
for (const [index, { File }] of expressionFiles.entries()) {
  const expression = {
    Type: 'Live2D Expression', FadeInTime: 0, FadeOutTime: 0,
    Parameters: [{ Id: 'ParamFaceMood', Value: index, Blend: 'Overwrite' }],
  };
  await writeFile(path.join(output, File), JSON.stringify(expression, null, 2) + '\n');
}
const manifest = 'kang-iseo.model3.json';
await writeFile(path.join(output, manifest), JSON.stringify({
  Version: 3,
  FileReferences: { Moc: mocFile, Textures: textures, Expressions: expressionFiles },
  Groups: [
    { Target: 'Parameter', Name: 'EyeBlink', Ids: eyeIds },
    { Target: 'Parameter', Name: 'LipSync', Ids: [mouthId] },
  ],
}, null, 2) + '\n');
const build = {
  source_psd_sha256: sha(await readFile(source)), converter_commit: commit,
  moc_sha256: sha(moc), cmo_sha256: sha(cmo), texture_sha256: sha(texture),
  drawables: report.selectedDrawableCount, core_parameters: report.selectedParameterCount,
  wired_parameters: parameters.map(({ id }) => id), native_consistency: report.selectedConsistency,
};
await writeFile(path.join(output, 'build-manifest.json'), JSON.stringify(build, null, 2) + '\n');

if (process.argv.includes('--stage-preview')) {
  const destination = path.join(root, 'live2d-models/kang-iseo');
  for (const directory of ['runtime/textures', 'runtime/expressions', 'source']) {
    await mkdir(path.join(destination, directory), { recursive: true });
  }
  for (const file of [manifest, mocFile, ...textures, ...expressionFiles.map(({ File }) => File)]) {
    await copyFile(path.join(output, file), path.join(destination, 'runtime', file));
  }
  await copyFile(path.join(output, cmoFile), path.join(destination, 'source/kang-iseo.cmo3'));
  await copyFile(bindingXml, path.join(destination, 'source/kang-iseo.binding.xml'));
  await copyFile(path.join(output, 'build-manifest.json'), path.join(destination, 'build-manifest.json'));
}
console.log(JSON.stringify(build, null, 2));
