// Semantic names are independent of the fallback Mao model's numeric indices.
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
export function expressionFor(text) {
  const matches = [...String(text || '').matchAll(expressionTag)];
  const name = matches.at(-1)?.[1].toLowerCase();
  return name === undefined ? null : expressionAliases[name] ?? name;
}
