// Independently read the preparation PSD with autoLive2d's ag-psd parser.
// No Editor jars, authentication, native export, MCP registration or API calls.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

function option(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Missing ${name}`);
  return path.resolve(process.argv[index + 1]);
}
const converter = option('--converter');
const psdPath = option('--psd');
const manifestPath = option('--manifest');
const reportPath = option('--output');
const sha = (data) => createHash('sha256').update(data).digest('hex');
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
if (sha(await readFile(psdPath)) !== manifest.psd_sha256)
  throw new Error('PSD differs from the reviewed manifest');
const { tsImport } = await import(
  pathToFileURL(path.join(converter, 'node_modules/tsx/dist/esm/api/index.mjs'))
);
const parser = await tsImport(
  pathToFileURL(path.join(converter, 'src/psd/parse.ts')).href,
  import.meta.url,
);
const infer = await tsImport(
  pathToFileURL(path.join(converter, 'src/pipeline/inferredBinding.ts')).href,
  import.meta.url,
);
const { model } = await parser.parsePsdToIntermediateModel(psdPath, 'infer-sample');
const expected = new Map(manifest.parts.map((part) => [part.name, part]));
if (
  model.drawables.length !== expected.size ||
  model.canvas.width !== manifest.canvas.width ||
  model.canvas.height !== manifest.canvas.height
)
  throw new Error('Independent PSD reader returned different canvas or layer count');
const layers = model.drawables.map((drawable) => {
  const reference = expected.get(drawable.name);
  const expectedHash = reference?.trimmed_rgba_sha256 || reference?.rgba_sha256;
  const actualHash = sha(drawable.raster.data);
  if (!reference || actualHash !== expectedHash)
    throw new Error(`Raster mismatch: ${drawable.name}`);
  if (reference.path && reference.path.join('/') !== drawable.sourcePath.join('/'))
    throw new Error(`Group path mismatch: ${drawable.name}`);
  const bounds = drawable.bounds;
  if (
    reference.bounds &&
    [bounds.left, bounds.top, bounds.right, bounds.bottom].some(
      (value, index) => value !== reference.bounds[index],
    )
  )
    throw new Error(`Offset mismatch: ${drawable.name}`);
  return { name: drawable.name, path: drawable.sourcePath, bounds, rgba_sha256: actualHash };
});
const inferred = infer.buildInferredBindingManifest(model);
const actualGroups = new Set(
  layers.flatMap((layer) =>
    layer.path.slice(0, -1).map((_, index) => layer.path.slice(0, index + 1).join('/')),
  ),
);
const report = {
  status: 'independent_psd_parser_verified_not_editor_import',
  reader: 'autoLive2d TypeScript parser / ag-psd',
  psd_sha256: manifest.psd_sha256,
  canvas: model.canvas,
  group_count: actualGroups.size,
  root_part_count: model.parts.length,
  layer_count: layers.length,
  layer_pixels_exact: true,
  layers,
  heuristic_parameter_ids: inferred.manifest?.parameters.map((parameter) => parameter.id) || [],
  heuristic_messages: inferred.messages,
  default_visibility_source:
    'Original preparation manifest; converter intermediate drawables omit visibility',
  auto_inference_approved: false,
  editor_import_verified: false,
  cmo3_available: false,
  moc3_available: false,
};
await mkdir(path.dirname(reportPath), { recursive: true });
await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log(
  JSON.stringify({
    status: report.status,
    groups: report.group_count,
    layers: report.layer_count,
    pixels_exact: true,
    heuristic_parameter_ids: report.heuristic_parameter_ids,
    heuristic_messages: report.heuristic_messages,
  }),
);
