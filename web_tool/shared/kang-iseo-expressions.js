// Screen-left eye rotation is mirrored on the screen-right eye.
export const kangIseoFaces = Object.freeze({
  neutral: { eyeScale: 1 },
  joy: { eyeScale: 0.72 },
  surprise: { eyeScale: 1.10 },
  anger: { eyeScale: 0.81, eyeTilt: 13, mouthWidth: 1.15, mouthHeight: 0.82 },
  sadness: { eyeScale: 0.62, eyeTilt: -11, mouthWidth: 0.84, mouthHeight: 0.9 },
});
