# Sogangi motion model

Small movement extension built on 2026-11-03, preserved as the head/breath baseline. The conversation page now uses the separate [right-arm greeting extension](../sogangi-greeting/README.md). The original three-parameter [facial baseline](../sogangi-minimum/README.md) is also preserved for comparison.

- 24 drawables, one original-resolution 2048 texture with four-pixel gutters. Five wired parameters: both eye openings, mouth opening, `ParamAngleZ` and `ParamBreath`.
- Shared head ArtMesh keyforms tilt the face/hood together by at most ±3° for parameter values ±30. Upper-body forms add a small lift/stretch for breath values 0–1, leaving the legs stationary. These are composed affine keyforms, without a deformer hierarchy or 3D head turning.
- Facial, tilt and breath keys share a Cartesian grid per mesh. Eye/mouth keys survive movement; each key starts from immutable original geometry. This also fixes repeated scaling of the old open-mouth form.
- Neutral pixels exactly match the facial baseline. Actual Core/browser checks combine eyes, mouth, head and breath, then restore the neutral image exactly. The cmo3 opens in Cubism Editor 5.1.03; direct GUI keyform editing is not certified.
- The conversation adapter adds smooth pointer-driven head tilt and a 4.8-second breath cycle. App/OS reduced motion returns head/breath to zero while retaining audio lip sync. Stop/mute closes the mouth; failed loading falls back to SVG.

[Conversation](http://localhost:12393/web-tool/sogangi/?avatar=live2d) · [Manual inspector](http://localhost:12393/web-tool/sogangi/live2d-preview.html?model=sogangi-motion). Arm greeting remains disabled; arm rigging, 3D turns, physics and expanded expressions are unfinished.

Rebuild using `tools/build_sogangi_minimum.mjs --motion --stage-preview` with the local Node/Editor prerequisites in [the build instructions](../../tools/patches/README.md). `tools/sogangi-motion-bridge.mjs` adapts the pinned open-source bridge in project `tmp/`; the reference checkout and Editor/Core binaries are unchanged. `build-manifest.json` records hashes; `verification.json` records observed checks for this build. No new LLM/TTS service call was needed for this renderer change; browser audio regressions use fixture WAVs with real playback clocks.

Original character artwork belongs to Sogang University/relevant owners, from official UI guide pages 19–20. This project-generated model is not an official school-issued Live2D model. The repository MIT license does not grant character artwork rights. Editor/Core binaries and license files are not included.
