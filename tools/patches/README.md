# Padded atlas adapter for the Sogangi minimum model

`autolive2d-padded-atlas.patch` targets [autoLive2d commit 4fcdf472d21488c8e8258fd05a601b2822855705](https://github.com/KonshinHaoshin/autoLive2d/tree/4fcdf472d21488c8e8258fd05a601b2822855705). Upstream MIT notice: [autoLive2d-MIT.txt](../licenses/autoLive2d-MIT.txt).

The original bridge put adjacent images into 4096 textures without gaps. The actual browser showed thin neighbouring-image pixels at some boundaries. The adapter packs source images into one 2048 texture with four-pixel gutters using a deterministic rectangle split. It fails rather than silently resizing or creating extra atlases. The tested 24-part model fits at full resolution.

Only this open-source bridge is patched. No Editor/Core binaries or authentication files are modified or redistributed. They must be present in a legitimately installed local Cubism Editor 5.1.03. Rebuilds do not purchase or activate licenses.

From the repository root, after obtaining the pinned converter in `../reference-sources/autoLive2d`:

```powershell
$converterDirectory = (Resolve-Path ../reference-sources/autoLive2d).Path
$atlasPatch = (Resolve-Path tools/patches/autolive2d-padded-atlas.patch).Path
git -C $converterDirectory apply --check $atlasPatch
git -C $converterDirectory apply $atlasPatch
# Prepare the converter dependencies with its frozen pnpm lockfile, scripts disabled.
# Node >=22 and a JDK >=17 must be available; locally checked with Node 24/JDK 23.
.\tmp\browser-tools\Lib\site-packages\playwright\driver\node.exe tools/build_sogangi_minimum.mjs --stage-preview
.\.venv\Scripts\python.exe tools/check_live2d_bundle.py live2d-models/sogangi-minimum/runtime/sogangi.model3.json
.\tmp\browser-tools\Scripts\python.exe tests/browser/live2d_preview.py
```

If already applied, `git apply --reverse --check $atlasPatch` succeeds; do not apply it twice. The builder checks the converter commit and adapter marker. `--converter`, `--editor` and `--output` can specify local paths; output must remain under project `tmp/`. `--stage-preview` copies only the generated model, texture, editing project, bindings and sanitized build manifest to the Sogangi minimum folder. It does not register a character or replace the main SVG renderer.

The Java subprocess uses UTF-8 explicitly: Windows console encoding otherwise corrupted Korean paths in its JSON output. The builder rejects texture references outside its output folder, checks the real MOC/PNG/CMO headers and native consistency, and requires a single 2048 texture. Native validation does not certify visual quality: the browser regression checks actual pixel changes, reset and mobile layout.

## Composed motion keys

`tools/build_sogangi_minimum.mjs --motion --stage-preview` builds the separate `sogangi-motion` folder; the facial baseline stays intact. `tools/sogangi-motion-bridge.mjs` replaces the single-axis binding helper in a generated module under project `tmp/`. It resolves the pinned TypeScript dependencies from the reference checkout without editing that checkout or Editor/Core files. Its source hash is included in the motion build manifest.

The upstream helper clears a mesh's existing keyforms on each parameter. It also mutates the default geometry before later keys are copied. The adapter snapshots the original form and composes explicit affine states in parameter order into one Cartesian grid per mesh. Missing targets/defaults/states, duplicate axes and grids over 81 forms fail the build. This supports simultaneous facial controls, small head tilt and breath; it does not create deformers or infer missing artwork. The browser motion check compares neutral pixels to the preserved baseline and exercises combinations and reset. Native source reopening, runtime verification and actual chat playback remain separately recorded checks.

`--greeting --stage-preview` builds `sogangi-greeting` separately. `tools/sogangi-greeting-bridge.mjs` extends that adapter with a single allowlisted `ParamArmRWave` (0–1), adds it to the model parameter set/root group, and keeps other unknown IDs as errors. Five shoulder keys compose before breathing. The model has 28 parameters, six wired, and no added artwork. Both adapter hashes are recorded. Existing model artifacts remain intact; regenerate their respective profile only when needed.

`--expressions --stage-preview` builds `sogangi-expressions` from the separate 29-layer PSD produced by `tools/prepare_sogangi_expressions.py`. The expression bridge adds only `ParamFaceMood` (0 neutral/joy, 1 anger, 2 surprise), multiplies explicit opacity contributions across axes, and keeps all baseline image placements before packing the five official face additions. This avoids neutral-edge sampling changes when the atlas grows. No grid exceeds the existing 81-form budget. The model has 29 parameters, seven wired, and four real exp3 files without mouth bindings. Zero expression fade avoids interpolating through a different discrete mood. `tools/sogangi-expression-bindings.mjs` specifies all facial targets; hashes of both new files are recorded. Native rendering and exported-file playback are checked separately from source pixel/PSD round trips.
