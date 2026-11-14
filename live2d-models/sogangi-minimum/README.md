# Sogangi minimum Cubism model

First real facial rig, built and checked locally on 2026-11-03. This three-parameter build is preserved as a baseline. The conversation page now uses the separate [head/breath/right-arm extension](../sogangi-greeting/README.md) by default; SVG remains a saved choice and automatic load-failure fallback.

- 24 drawables, one 2048×2048 texture, four-pixel gutters at original texture resolution.
- Three wired parameters: `ParamEyeLOpen`, `ParamEyeROpen`, `ParamMouthOpenY`. Other standard parameters are present but unbound.
- Eyes crossfade the official open/closed artwork; mouth opacity and size have keyforms. Geometry uses base PSD-import ArtMeshes, without head/body deformers.
- Native MOC consistency and actual browser Core rendering passed. Manual eye/mouth values change pixels and restoring them returns exactly to the neutral image.
- The generated cmo3 was reopened in Cubism Editor 5.1.03. Eight conversation regressions cover actual Core/audio-clock lip sync, sentence expressions, stop/mute, mode changes, delayed loading and WebGL recovery. One real Gemini/TTS request also drove Core mouth values and finished with a closed mouth; history, draft and renderer survived refresh.
- Head angles, breathing, arm motion, expanded expression artwork and exported expression/motion files remain unfinished. The renderer uses the wired eye parameters for blinking and a brief joy reaction. Greeting is disabled in this mode.

Open the [local inspector](http://localhost:12393/web-tool/sogangi/live2d-preview.html?model=sogangi-minimum). `runtime/` contains the actual MOC3, model settings and PNG. `source/` contains the editing project and applied bindings. `build-manifest.json` identifies this exact build; it does not replace browser verification.

Try [Live2D conversation](http://localhost:12393/web-tool/sogangi/?avatar=live2d), or choose Live2D in settings, to use the newer extension. Failed loading or a lost WebGL context falls back to SVG; retry does not replay a question or restart audio. `verification.json` records this baseline's earlier integration checks; it does not certify the newer model.

Rebuild from the repository root with `tools/build_sogangi_minimum.mjs --stage-preview` using the documented local Node executable, installed Cubism Editor and pinned converter. See [the build patch](../../tools/patches/README.md) and [rigging integration](../../docs/sogangi-rigging-integration.md).

Original artwork: Sogang University/relevant owners, from the [official UI guide](https://www.sogang.ac.kr/intro/symbol/data/Sogang_UI_renewal.pdf), pages 19–20. This is a project-generated model, not an official school-issued Live2D model. The repository's MIT software license does not grant rights to the character artwork. Editor/Core binaries are not included in this model folder; their own terms apply.
