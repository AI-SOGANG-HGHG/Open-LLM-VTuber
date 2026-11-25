const assets = {
  standard: new URL('./assets/kang-iseo-expressions.png', import.meta.url),
  clearer: new URL('./assets/kang-iseo-expressions-clearer.png', import.meta.url),
};

// The source sheet is registered to the portrait crop (350, 365, 340, 240).
const tileFor = { neutral: 0, joy: 1, surprise: 2, anger: 3, sadness: 4 };

const regions = {
  eyeL: { x: 384, y: 433, width: 113, height: 69, feather: 5, topInset: 11, sourceOffsetY: -8 },
  eyeR: { x: 540, y: 433, width: 113, height: 69, feather: 5, topInset: 11, sourceOffsetX: -5, sourceOffsetY: -8 },
  browL: { x: 398, y: 397, width: 97, height: 41, feather: 6 },
  browR: { x: 542, y: 397, width: 102, height: 41, feather: 6, sourceOffsetX: -5 },
  mouth: { x: 474, y: 550, width: 87, height: 40, feather: 4, sourceOffsetY: -14 },
};

export const kangIseoBrowArea = { x: 398, y: 397, width: 246, height: 41 };
const faceArt = new Map();

function makeCanvas(width, height) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function createFaceArt(variantSource, standardSource = variantSource) {
  const patches = new Map();
  const mattes = new Map();

  function patch(name, tile) {
    const key = name + ':' + tile;
    if (patches.has(key)) return patches.get(key);
    const { x, y, width, height, feather, topInset = feather, sourceOffsetX = 0, sourceOffsetY = 0 } = regions[name];
    // The neutral face and the painted blink are shared across both versions.
    const { image, columns, rowHeight } = tile === 0 || tile === 5 ? standardSource : variantSource;
    const col = tile % 3;
    const scaleX = (columns[col + 1] - columns[col]) / 340;
    const scaleY = rowHeight / 240;
    const canvas = makeCanvas(width, height);
    const context = canvas.getContext('2d');
    context.drawImage(
      image, columns[col] + (x - 350 + sourceOffsetX) * scaleX,
      Math.floor(tile / 3) * rowHeight + (y - 365 + sourceOffsetY) * scaleY,
      width * scaleX, height * scaleY, 0, 0, width, height,
    );

    if (!mattes.has(name)) {
      const mask = makeCanvas(width, height);
      const brush = mask.getContext('2d');
      brush.filter = `blur(${feather / 2}px)`;
      brush.fillRect(feather, topInset, width - 2 * feather, height - topInset - feather);
      mattes.set(name, mask);
    }
    context.globalCompositeOperation = 'destination-in';
    context.drawImage(mattes.get(name), 0, 0);
    patches.set(key, canvas);
    return canvas;
  }

  function paintedEye(context, x, y, right, expression, openness) {
    const name = right ? 'eyeR' : 'eyeL';
    const open = patch(name, tileFor[expression]);
    const closed = patch(name, 5);
    if (openness <= 0.05) {
      context.drawImage(closed, x, y);
      return;
    }
    if (openness >= 0.99) {
      context.drawImage(open, x, y);
      return;
    }
    // Crossfade at the end of a blink so the closed painted lash stays clean.
    const weight = Math.min(1, openness / 0.3);
    const scale = 0.38 + 0.62 * openness;
    context.save();
    context.globalAlpha = 1 - weight;
    context.drawImage(closed, x, y);
    context.globalAlpha = weight;
    context.drawImage(open, x, y + (1 - scale) * 39, open.width, open.height * scale);
    context.restore();
  }

  function paintedMouth(context, x, y, expression, openness) {
    const resting = patch('mouth', tileFor[expression]);
    if (openness < 0.08) {
      context.drawImage(resting, x, y);
      return;
    }
    const spoken = patch('mouth', tileFor.surprise);
    const weight = Math.min(1, (openness - 0.08) / 0.28);
    const scale = 1 + 0.32 * openness;
    context.save();
    context.globalAlpha = 1 - weight;
    context.drawImage(resting, x, y);
    context.globalAlpha = weight;
    context.drawImage(spoken, x, y - (scale - 1) * 17, spoken.width, spoken.height * scale);
    context.restore();
  }

  function paintedBrows(context, expression, offsetX = 0, offsetY = 0) {
    for (const name of ['browL', 'browR']) {
      const { x, y } = regions[name];
      context.drawImage(patch(name, tileFor[expression]), x + offsetX, y + offsetY);
    }
  }

  return { source: variantSource, paintedEye, paintedMouth, paintedBrows };
}

async function loadSource(variant) {
  const image = new Image();
  image.src = assets[variant].href;
  await image.decode();
  const { naturalWidth: width, naturalHeight: height } = image;
  if (width < 1020 || height < 480 || Math.abs(width / height - 17 / 8) > 0.12) {
    throw new Error('Unexpected Kang Iseo face sheet size');
  }
  const columnWidth = Math.floor(width / 3);
  return { image, columns: [0, columnWidth, columnWidth * 2, width], rowHeight: height / 2 };
}

export function loadKangIseoFaceArt(variant = 'standard') {
  if (!Object.hasOwn(assets, variant)) return Promise.resolve(null);
  if (!faceArt.has(variant)) {
    const standard = variant === 'standard' ? null : loadKangIseoFaceArt();
    const pending = Promise.all([loadSource(variant), standard]).then(([source, base]) => {
      if (standard && !base) throw new Error('Kang Iseo base face sheet unavailable');
      return createFaceArt(source, base?.source);
    }).catch(() => {
      faceArt.delete(variant);
      return null;
    });
    faceArt.set(variant, pending);
  }
  return faceArt.get(variant);
}
