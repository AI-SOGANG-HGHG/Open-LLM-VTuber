// Semantic names are independent of the fallback Mao model's numeric indices.
// Native Cubism supports four states; the SVG engine keeps its neutral/joy fallback.
export const supportedExpressions = ['neutral', 'joy', 'anger', 'surprise'];
export function normalizeExpression(name) {
  return supportedExpressions.includes(name) ? name : 'neutral';
}
export function expressionFor(text) {
  const matches = [
    ...String(text || '').matchAll(/\[(neutral|anger|disgust|fear|joy|smirk|sadness|surprise)\]/gi),
  ];
  const name = matches.at(-1)?.[1].toLowerCase();
  return normalizeExpression(name);
}
