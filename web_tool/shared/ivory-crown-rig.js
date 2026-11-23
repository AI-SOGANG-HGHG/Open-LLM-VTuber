// Shared by the local-file art inspector and the Studio module loader.
globalThis.makeIvoryCrownRig = (() => {
  // Coordinates use the 1024 × 1536 neutral illustration. L/R follow screen order.
  const ivoryCrownFace = {
    EyeL: {
      x: 384, y: 433, width: 113, height: 69,
      mask: 'M 10 27 C 19 19 24 8 38 8 C 64 5 89 18 105 41 C 91 43 86 55 60 59 C 37 60 23 51 17 41 Z',
      skin: ['#f8d8ce', '#f4c7bc', '#f9d5c8'],
      lid: 'M 15 28 C 39 46 67 52 100 42 C 75 56 36 52 15 28 Z',
      crease: 'M 30 20 C 54 14 76 22 91 36',
    },
    EyeR: {
      x: 540, y: 433, width: 113, height: 69,
      mask: 'M 8 41 C 24 18 49 6 72 7 C 89 7 94 16 105 27 L 99 41 C 90 54 72 59 54 59 C 29 58 24 49 8 42 Z',
      skin: ['#f8d9ce', '#f4c8bc', '#f9d6c9'],
      lid: 'M 13 42 C 43 52 76 46 100 28 C 78 52 37 56 13 42 Z',
      crease: 'M 25 36 C 41 22 60 15 83 20',
    },
    Mouth: {
      x: 474, y: 550, width: 87, height: 40,
      mask: 'M 10 9 Q 19 5 34 11 Q 43 13 52 11 Q 70 5 77 9 Q 80 15 69 22 Q 57 34 43 34 Q 29 34 17 24 Q 7 17 10 9 Z',
      skin: ['#faddd1', '#f9d9cd', '#f8d9cd'],
    },
  };

  function rigCanvas(width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    return canvas;
  }

  function paintMouth(ctx, amount) {
    ctx.save();
    ctx.translate(43.5, 13.5);
    ctx.scale(0.80 + amount * 0.20, 0.20 + amount * 0.80);
    const outline = new Path2D('M -30 -1 C -19 2 -9 -3 0 -1 C 9 -3 19 2 30 -1 C 21 9 12 18 0 18 C -12 18 -21 9 -30 -1 Z');
    const interior = ctx.createLinearGradient(0, 0, 0, 18);
    interior.addColorStop(0, '#682e34');
    interior.addColorStop(1, '#b55c5e');
    ctx.fillStyle = interior;
    ctx.fill(outline);
    ctx.clip(outline);
    ctx.fillStyle = '#f3afa9';
    ctx.fill(new Path2D('M -19 17 Q -10 10 0 12 Q 10 10 19 17 L 15 21 H -15 Z'));
    ctx.fillStyle = '#fbe4de';
    ctx.fill(new Path2D('M -21 -2 H 21 Q 10 5 0 4 Q -10 5 -21 -2 Z'));
    ctx.restore();
  }

  function makeIvoryCrownRig(image) {
    if (image.naturalWidth !== 1024 || image.naturalHeight !== 1536) {
      throw new Error('정면 원화의 크기가 파츠 좌표와 일치하지 않아요.');
    }

    const features = {};
    for (const [name, region] of Object.entries(ivoryCrownFace)) {
      const { x, y, width, height, mask, skin, lid, crease } = region;
      const makeCanvas = () => rigCanvas(width, height);

      const feather = makeCanvas();
      const featherCtx = feather.getContext('2d');
      featherCtx.filter = 'blur(2px)';
      featherCtx.fill(new Path2D(mask));
      featherCtx.filter = 'none';

      const underpaint = makeCanvas();
      const skinCtx = underpaint.getContext('2d');
      const gradient = skinCtx.createLinearGradient(0, 7, 0, height - 6);
      for (const [index, color] of skin.entries()) gradient.addColorStop(index / 2, color);
      skinCtx.fillStyle = gradient;
      skinCtx.fillRect(0, 0, width, height);
      skinCtx.globalCompositeOperation = 'destination-in';
      skinCtx.drawImage(feather, 0, 0);
      skinCtx.globalCompositeOperation = 'source-over';

      const original = makeCanvas();
      const originalCtx = original.getContext('2d');
      originalCtx.drawImage(image, x, y, width, height, 0, 0, width, height);
      originalCtx.globalCompositeOperation = 'destination-in';
      originalCtx.drawImage(feather, 0, 0);

      const alternate = makeCanvas();
      const alternateCtx = alternate.getContext('2d');
      alternateCtx.drawImage(underpaint, 0, 0);
      if (lid) {
        alternateCtx.strokeStyle = '#c28e84';
        alternateCtx.lineWidth = 1.1;
        alternateCtx.stroke(new Path2D(crease));
        alternateCtx.fillStyle = '#4c2928';
        alternateCtx.fill(new Path2D(lid));
      } else {
        paintMouth(alternateCtx, 1);
      }
      features[name] = { x, y, original, alternate, underpaint };
    }

    const previousPoses = new WeakMap();
    function restoreRegion(ctx, name) {
      const { x, y, width, height } = ivoryCrownFace[name];
      ctx.clearRect(x, y, width, height);
      ctx.drawImage(image, x, y, width, height, x, y, width, height);
    }

    function draw(ctx, { eyeL, eyeR, mouth }) {
      const previous = previousPoses.get(ctx);
      previousPoses.set(ctx, { eyeL, eyeR, mouth });
      if (!previous) {
        ctx.clearRect(0, 0, image.naturalWidth, image.naturalHeight);
        ctx.drawImage(image, 0, 0);
      }
      ctx.save();
      for (const [name, amount, last] of [['EyeL', eyeL, previous?.eyeL], ['EyeR', eyeR, previous?.eyeR]]) {
        if (amount === last) continue;
        if (previous) restoreRegion(ctx, name);
        if (amount === 1) continue;
        const { x, y, original, alternate, underpaint } = features[name];
        if (amount === 0) {
          ctx.drawImage(alternate, x, y);
          continue;
        }

        // Scale the iris around the lower lash line. Near a closed blink,
        // crossfade to the closed crease once the iris has flattened.
        const lashLine = 46;
        const openWeight = Math.min(1, amount / 0.18);
        ctx.save();
        ctx.beginPath();
        ctx.rect(x, y, original.width, original.height);
        ctx.clip();
        ctx.drawImage(underpaint, x, y);
        ctx.globalAlpha = 1 - openWeight;
        ctx.drawImage(alternate, x, y);
        ctx.globalAlpha = openWeight;
        ctx.drawImage(original, x, y + lashLine * (1 - amount), original.width, original.height * amount);
        ctx.restore();
      }
      if (mouth !== previous?.mouth) {
        if (previous) restoreRegion(ctx, 'Mouth');
        if (mouth > 0) {
          const { x, y, underpaint } = features.Mouth;
          ctx.globalAlpha = Math.min(1, mouth * 5);
          ctx.drawImage(underpaint, x, y);
          ctx.translate(x, y);
          paintMouth(ctx, mouth);
        }
      }
      ctx.restore();
    }

    function layers() {
      const staticBase = rigCanvas(image.naturalWidth, image.naturalHeight);
      const baseCtx = staticBase.getContext('2d');
      baseCtx.drawImage(image, 0, 0);
      for (const { x, y, underpaint } of Object.values(features)) {
        baseCtx.drawImage(underpaint, x, y);
      }
      const { EyeL, EyeR, Mouth } = features;
      return [
        { name: 'Base_HeadBody', x: 0, y: 0, canvas: staticBase, visible: true },
        { name: 'EyeL_Open', x: EyeL.x, y: EyeL.y, canvas: EyeL.original, visible: true },
        { name: 'EyeL_Closed', x: EyeL.x, y: EyeL.y, canvas: EyeL.alternate, visible: false },
        { name: 'EyeR_Open', x: EyeR.x, y: EyeR.y, canvas: EyeR.original, visible: true },
        { name: 'EyeR_Closed', x: EyeR.x, y: EyeR.y, canvas: EyeR.alternate, visible: false },
        { name: 'Mouth_Closed', x: Mouth.x, y: Mouth.y, canvas: Mouth.original, visible: true },
        { name: 'Mouth_Open', x: Mouth.x, y: Mouth.y, canvas: Mouth.alternate, visible: false },
      ];
    }

    return { draw, layers };
  }

  return makeIvoryCrownRig;
})();
