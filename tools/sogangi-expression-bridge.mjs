import { greetingBridgeSource } from './sogangi-greeting-bridge.mjs';

export function expressionBridgeSource(source, converter) {
  let adapted = greetingBridgeSource(source, converter);
  const missing =
    '      if (parameter == null) throw new IllegalStateException("Unknown parameter: " + id);';
  if (!adapted.includes(missing)) throw new Error('Reviewed parameter creation changed');
  adapted = adapted.replace(
    missing,
    String.raw`
      if (parameter == null && "ParamFaceMood".equals(id)) {
        parameter = new CParameterSource();
        parameter.setGuid(new com.live2d.type.CParameterGuid());
        parameter.setId(new CParameterId(id));
        parameter.setName("Face mood: neutral / anger / surprise");
        parameter.setMinValue(0f); parameter.setMaxValue(2f); parameter.setDefaultValue(0f);
        modelSource.getParameterSourceSet().add(parameter, modelSource.getParameterSourceSet().getSources().size());
        var group = modelSource.getRootParameterGroup();
        group.add(parameter, group.getChildren().size());
      }
${missing}`,
  );
  const start = '      for (var state : states) {';
  const end = '      forms.add(form.getGuid());';
  if (!adapted.includes(start) || !adapted.includes(end))
    throw new Error('Reviewed affine grid changed');
  adapted = adapted.replace(
    start,
    String.raw`
      float composedOpacity = 1f;
      boolean hasOpacity = false;
${start}
        if (state.getAttribute("opacity") != null) {
          composedOpacity *= parseFloatAttribute(state, "opacity", 1f);
          hasOpacity = true;
        }`,
  );
  adapted = adapted.replace(end, `      if (hasOpacity) form.setOpacity(composedOpacity);\n${end}`);
  const sort =
    '      int order = Integer.compare(Math.max(right.getWidth(), right.getHeight()), Math.max(left.getWidth(), left.getHeight()));';
  if (!adapted.includes(sort)) throw new Error('Reviewed atlas packing order changed');
  // Keep the baseline UV placements: insert the five new small face textures
  // after the existing 24 images rather than repacking the original face edges.
  return adapted.replace(
    sort,
    String.raw`
      boolean leftExtra = left.getName().contains("_Anger") || left.getName().contains("_Surprise");
      boolean rightExtra = right.getName().contains("_Anger") || right.getName().contains("_Surprise");
      if (leftExtra != rightExtra) return leftExtra ? 1 : -1;
${sort}`,
  );
}
