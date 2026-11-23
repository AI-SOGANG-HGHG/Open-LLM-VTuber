import { maoExpressionIndices } from '../../../shared/live2d-loader.js';

// Sogangi's semantic names are independent of Mao's numeric indices.
// Native Cubism supports four states; the SVG engine keeps its neutral/joy fallback.
export const supportedExpressions = ['neutral', 'joy', 'anger', 'surprise'];
const expressionAliases = {
  smirk: 'joy',
  fear: 'surprise',
  disgust: 'anger',
  sadness: 'neutral',
};
const expressionTag = new RegExp(
  '\\[(' + [...supportedExpressions, ...Object.keys(expressionAliases)].join('|') + ')\\]',
  'gi',
);

export function normalizeExpression(name) {
  return supportedExpressions.includes(name) ? name : 'neutral';
}

function resolveAvatarExpression(name, avatar) {
  if (avatar === 'sogangi') return normalizeExpression(name);
  if (avatar === 'mao' && Object.hasOwn(maoExpressionIndices, name)) return name;
  return 'neutral';
}

export function expressionFor(text, { avatar, expression } = {}) {
  if (typeof expression === 'string') return resolveAvatarExpression(expression, avatar);
  const matches = [...String(text || '').matchAll(expressionTag)];
  const name = matches.at(-1)?.[1].toLowerCase();
  return name === undefined ? null : expressionAliases[name] ?? name;
}
