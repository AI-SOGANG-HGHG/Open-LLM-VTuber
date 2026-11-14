// Project-only adapter for the pinned MIT autoLive2d Java bridge. Editor/Core
// binaries stay unchanged. Compose all affine bindings into one grid per mesh;
// the upstream single-parameter helper replaces previously bound parameters.
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const JAVA = String.raw`
  // Sogangi composed affine grid: original coordinates remain immutable.
  private static final class SogangiBinding {
    CParameterSource parameter;
    List<Float> keys = new ArrayList<>();
    Map<Float, Element> states = new LinkedHashMap<>();
  }

  private static void applyStrictBindings(CModelSource modelSource, File manifestFile)
    throws Exception {
    Map<String, CArtMeshSource> meshes = new HashMap<>();
    for (var mesh : modelSource.getAllArtMeshes()) meshes.put(buildImportedPath(mesh), mesh);
    Document document = new SAXBuilder().build(manifestFile);
    Map<CArtMeshSource, List<SogangiBinding>> bindings = new LinkedHashMap<>();
    for (Object rawParameter : document.getRootElement().getChildren("Parameter")) {
      Element parameterElement = (Element) rawParameter;
      String id = parameterElement.getAttributeValue("id", "");
      CParameterSource parameter = modelSource.getParameterSourceSet().get(new CParameterId(id));
      if (parameter == null) throw new IllegalStateException("Unknown parameter: " + id);
      for (Object rawTarget : parameterElement.getChildren("Target")) {
        Element target = (Element) rawTarget;
        if (!"affine-transform".equals(target.getAttributeValue("mode")))
          throw new IllegalStateException("Motion adapter accepts explicit affine bindings only");
        String meshPath = target.getAttributeValue("relativeDrawablePath", "");
        CArtMeshSource mesh = meshes.get(meshPath);
        if (mesh == null) throw new IllegalStateException("Missing mesh: " + meshPath);
        SogangiBinding binding = new SogangiBinding();
        binding.parameter = parameter;
        for (Object rawKey : parameterElement.getChildren("Key")) {
          float value = Float.parseFloat(((Element) rawKey).getAttributeValue("value"));
          if (!Float.isFinite(value) || value < parameter.getMinValue() || value > parameter.getMaxValue()
              || binding.keys.contains(value)) throw new IllegalStateException("Invalid key: " + id);
          binding.keys.add(value);
        }
        if (binding.keys.isEmpty() || !binding.keys.contains(parameter.getDefaultValue()))
          throw new IllegalStateException("Missing default key: " + id);
        for (Object rawState : target.getChildren("State")) {
          Element state = (Element) rawState;
          float value = Float.parseFloat(state.getAttributeValue("keyValue"));
          if (binding.states.put(value, state) != null) throw new IllegalStateException("Duplicate state");
        }
        if (binding.states.size() != binding.keys.size() || !binding.states.keySet().containsAll(binding.keys))
          throw new IllegalStateException("Incomplete states: " + meshPath);
        List<SogangiBinding> list = bindings.computeIfAbsent(mesh, ignored -> new ArrayList<>());
        for (var previous : list) if (previous.parameter == parameter)
          throw new IllegalStateException("Duplicate parameter on mesh: " + meshPath);
        list.add(binding);
      }
    }
    for (var entry : bindings.entrySet()) applySogangiGrid(modelSource, entry.getKey(), entry.getValue());
    modelSource.updateParamInstance(true);
  }

  private static void applySogangiGrid(CModelSource modelSource, CArtMeshSource mesh,
      List<SogangiBinding> bindings) throws Exception {
    CArtMeshForm original = mesh.getDefaultKeyForm();
    if (original == null) throw new IllegalStateException("Missing base form");
    CArtMeshForm baseline = (CArtMeshForm) original.deepCopy(new com.live2d.core.a());
    while (mesh.getKeyforms().size() > 1) mesh.getKeyforms().remove(mesh.getKeyforms().size() - 1);
    int count = 1;
    List<Pair<com.live2d.type.CParameterGuid, float[]>> axes = new ArrayList<>();
    for (var binding : bindings) {
      count = Math.multiplyExact(count, binding.keys.size());
      axes.add(new Pair<>(binding.parameter.getGuid(), toFloatArray(binding.keys)));
    }
    if (count > 81) throw new IllegalStateException("Grid exceeds reviewed form budget");
    List<com.live2d.type.CFormGuid> forms = new ArrayList<>();
    for (int cell = 0; cell < count; cell++) {
      int remainder = cell;
      List<Element> states = new ArrayList<>();
      boolean isDefault = true;
      for (var binding : bindings) {
        float value = binding.keys.get(remainder % binding.keys.size());
        remainder /= binding.keys.size();
        isDefault &= areEqual(value, binding.parameter.getDefaultValue());
        states.add(binding.states.get(value));
      }
      CArtMeshForm form = isDefault ? original : (CArtMeshForm) baseline.deepCopy(new com.live2d.core.a());
      if (!isDefault) {
        form.setGuid(new com.live2d.type.CFormGuid());
        form.setName(mesh.getLocalName() + "_composed_" + cell);
        mesh.getKeyforms().add(form);
      }
      form.setPositions(java.util.Arrays.copyOf(baseline.getPositions(), baseline.getPositions().length));
      form.setOpacity(baseline.getOpacity());
      for (var state : states) {
        // Opacity-only and identity keys must not accumulate coordinate roundoff.
        boolean transformed = parseFloatAttribute(state, "scaleX", 1f) != 1f
          || parseFloatAttribute(state, "scaleY", 1f) != 1f
          || parseFloatAttribute(state, "rotationDeg", 0f) != 0f
          || parseFloatAttribute(state, "translateX", 0f) != 0f
          || parseFloatAttribute(state, "translateY", 0f) != 0f;
        if (transformed) applyAffineState(form, form, state);
        else form.setOpacity(parseFloatAttribute(state, "opacity", form.getOpacity()));
      }
      forms.add(form.getGuid());
    }
    KeyformGridSource grid = new KeyformGridSource(mesh);
    grid.getClass().getMethod("import", CModelSource.class, List.class, List.class)
      .invoke(grid, modelSource, axes, forms);
    mesh.setKeyformGridSource(grid);
  }
`;

export function motionBridgeSource(source, converter) {
  const start = source.indexOf('  private static void applyStrictBindings(');
  const end = source.indexOf('  private static void applyStrictBindingParameter(', start);
  if (start < 0 || end <= start) throw new Error('Pinned binding bridge structure changed');
  let adapted = source.slice(0, start) + JAVA + '\n' + source.slice(end);
  for (const [relative, target] of [
    ['../errors.js', 'src/errors.ts'],
    ['../util/fs.js', 'src/util/fs.ts'],
  ]) {
    const token = `from "${relative}"`;
    if (!adapted.includes(token)) throw new Error('Pinned module imports changed');
    adapted = adapted.replace(
      token,
      `from ${JSON.stringify(pathToFileURL(path.join(converter, target)).href)}`,
    );
  }
  return adapted;
}
