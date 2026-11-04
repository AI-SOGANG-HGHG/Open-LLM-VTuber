# Sogangi greeting model

Right-arm greeting extension built on 2026-11-03, preserved as a baseline. The conversation page now uses the separate [expression extension](../sogangi-expressions/README.md). The [facial baseline](../sogangi-minimum/README.md) and [head/breath baseline](../sogangi-motion/README.md) also remain intact.

- 24 drawables, one 2048 texture, 28 Core parameters with six wired controls: both eyes, mouth, head tilt, breath and `ParamArmRWave`.
- The custom arm parameter ranges from 0 to 1. Five shoulder-rotation keys move the screen-right arm from 0 to −32°, composed before upper-body breathing. This is a whole-arm affine motion using the existing artwork, without elbow/finger subdivision or a deformer hierarchy.
- Default pixels exactly match the head/breath baseline. Twelve intermediate arm/breath poses keep the same large connected silhouette components, and a combined face/head/breath/arm pose renders correctly. This detects detached artwork; visual shoulder review remains a separate check. Reset returns exactly to neutral.
- The chat button plays one 1.6-second gesture, ignores repeat clicks during that gesture, and makes no chat/model request. It can run during speech. Stop/mute, new chat, renderer disposal and app/OS reduced motion cancel it; changing modes or re-enabling motion does not replay it.
- The generated cmo3 opens in Cubism Editor 5.1.03. Direct GUI keyform editing, 3D head turns, physics and expanded expression artwork are not certified.

[Conversation](http://localhost:12393/web-tool/sogangi/?avatar=live2d) · [Manual inspector](http://localhost:12393/web-tool/sogangi/live2d-preview.html?model=sogangi-greeting). Use **손 흔들기** in the conversation page, or the arm slider in the inspector.

Rebuild with the local Node/Editor prerequisites and `tools/build_sogangi_minimum.mjs --greeting --stage-preview`. The project-only `tools/sogangi-greeting-bridge.mjs` allows creation of exactly one custom parameter; other unknown IDs still fail. It extends the reviewed composed-grid adapter without editing Editor/Core binaries or the reference checkout. Build hashes and observed checks are separate in `build-manifest.json` and `verification.json`.

Character artwork belongs to Sogang University/relevant owners, from official UI guide pages 19–20. This is a project-generated Live2D model. The repository MIT software license does not grant artwork rights. Editor/Core binaries and license files are not included.
