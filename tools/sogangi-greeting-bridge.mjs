// Extend the pinned motion adapter with exactly one explicit custom parameter.
// Editor/Core binaries and the reference checkout remain untouched.
import { motionBridgeSource } from './sogangi-motion-bridge.mjs';

export function greetingBridgeSource(source, converter) {
  const adapted = motionBridgeSource(source, converter);
  const token =
    '      if (parameter == null) throw new IllegalStateException("Unknown parameter: " + id);';
  if (!adapted.includes(token)) throw new Error('Reviewed motion parameter binding changed');
  return adapted.replace(
    token,
    String.raw`
      if (parameter == null && "ParamArmRWave".equals(id)) {
        parameter = new CParameterSource();
        parameter.setGuid(new com.live2d.type.CParameterGuid());
        parameter.setId(new CParameterId(id));
        parameter.setName("Right arm greeting");
        parameter.setMinValue(0f);
        parameter.setMaxValue(1f);
        parameter.setDefaultValue(0f);
        modelSource.getParameterSourceSet().add(parameter, modelSource.getParameterSourceSet().getSources().size());
        var group = modelSource.getRootParameterGroup();
        group.add(parameter, group.getChildren().size());
      }
${token}`,
  );
}
