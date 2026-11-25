import { kangIseoBrowArea } from './kang-iseo-face-art.js';

// The exported atlas uses unrotated cells with a one-pixel guard around the art.
function atlasCell(drawables, id, width, height) {
  const index = drawables.ids.indexOf(id);
  if (index === -1 || drawables.textureIndices[index] !== 0) return null;
  const uv = drawables.vertexUvs[index];
  const u = uv.filter((_, i) => i % 2 === 0);
  const v = uv.filter((_, i) => i % 2 === 1);
  const left = Math.round(Math.min(...u) * width);
  const right = Math.round(Math.max(...u) * width);
  const top = Math.round((1 - Math.max(...v)) * height);
  const bottom = Math.round((1 - Math.min(...v)) * height);
  return { x: left + 1, y: top + 1, width: right - left - 2, height: bottom - top - 2 };
}

export function createKangIseoAtlas(model, pixi, faceArt) {
  if (!faceArt) return null;
  const original = model.textures[0];
  const source = original?.baseTexture.resource?.source;
  if (!source) return null;
  const drawables = model.internalModel.coreModel.getModel().drawables;
  const rect = (id) => atlasCell(drawables, id, source.width, source.height);
  const base = rect('Base_HeadBody');
  const closed = rect('Mouth_Closed');
  const open = rect('Mouth_Open');
  const eyes = ['EyeL_Open', 'EyeL_Closed', 'EyeR_Open', 'EyeR_Closed'].map(rect);
  if (base?.width !== 1024 || base.height !== 1536 ||
      closed?.width !== 87 || closed.height !== 40 || open?.width !== 87 || open.height !== 40 ||
      eyes.some((cell) => cell?.width !== 113 || cell.height !== 69)) return null;

  const canvas = document.createElement('canvas');
  canvas.width = source.width;
  canvas.height = source.height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(source, 0, 0);
  let texture;
  let current = 'neutral';

  function restoreFace() {
    const { x, y, width, height } = kangIseoBrowArea;
    const left = base.x + x;
    const top = base.y + y;
    context.clearRect(left, top, width, height);
    context.drawImage(source, left, top, width, height, left, top, width, height);
  }

  function renderCell(cell, paint) {
    context.clearRect(cell.x - 1, cell.y - 1, cell.width + 2, cell.height + 2);
    context.save();
    context.beginPath();
    context.rect(cell.x, cell.y, cell.width, cell.height);
    context.clip();
    paint();
    context.restore();
  }

  function paintExpression(name) {
    restoreFace();
    faceArt.paintedBrows(context, name, base.x, base.y);
    eyes.forEach((cell, index) => {
      renderCell(cell, () => faceArt.paintedEye(context, cell.x, cell.y, index >= 2, name, 1 - index % 2));
    });
    for (const [cell, openness] of [[closed, 0], [open, 1]]) {
      renderCell(cell, () => faceArt.paintedMouth(context, cell.x, cell.y, name, openness));
    }
    // Cubism binds the uploaded texture directly. Keep the old GL resource
    // alive through the current draw before releasing it.
    const retired = texture;
    if (retired) queueMicrotask(() => retired.destroy(true));
    texture = new pixi.Texture(new pixi.BaseTexture(canvas));
    model.textures[0] = texture;
  }

  paintExpression(current);
  return {
    setExpression(name) {
      if (current === name) return;
      current = name;
      paintExpression(current);
    },
    setFaceArt(next) {
      if (faceArt === next) return;
      faceArt = next;
      paintExpression(current);
    },
    destroy() {
      model.textures[0] = original;
      texture?.destroy(true);
    },
  };
}
