# Local Cubism inspector dependencies

These files are loaded only by `live2d-preview.html`. The normal Sogangi SVG app does not load Pixi or Cubism.

- `pixi.min.js`: `pixi.js@6.5.10`, official npm package. Its MIT notice is retained as `pixi.js.LICENSE.txt`.
- `cubism4.min.js`: `pixi-live2d-display@0.4.0`, official npm package. The package MIT notice is retained as `pixi-live2d-display.LICENSE.txt`.
- The Cubism 4 bundle includes framework code; its upstream notice is retained separately in `CubismFramework.NOTICE.md`. The wrapper's MIT notice does not replace the underlying Live2D terms.
- Cubism Core is served from the existing frontend's `/libs/live2dcubismcore.min.js`; it was not copied or replaced by this work. The existing model/SDK conditions remain applicable.

`manifest.json` records npm tarball integrity and the exact browser-file SHA-256 values. `tools/fetch_live2d_preview_vendor.py` downloads from the official npm registry, checks archive integrity and extracts only the selected files and notices. No CDN requests are needed while using the inspector.

Primary references: [plugin usage](https://guansss.github.io/pixi-live2d-display/), [model loading](https://guansss.github.io/pixi-live2d-display/models/), [motions/expressions](https://guansss.github.io/pixi-live2d-display/motions_expressions/), [Cubism Framework notice](https://github.com/Live2D/CubismWebFramework/blob/4bbfb54/LICENSE.md).
