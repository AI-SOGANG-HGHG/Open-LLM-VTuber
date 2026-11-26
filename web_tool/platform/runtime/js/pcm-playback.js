// Schedule incoming mono PCM on one clock so network packets play without seams.
export function createPcmPlayback({ preferences, renderer, onStart, onDrain, onError }) {
  let context;
  let gain;
  let analyser;
  let nextStart = 0;
  let frame = 0;
  const scheduled = new Set();
  const levels = new Float32Array(256);

  function prepare() {
    try {
      if (!context) {
        context = new AudioContext();
        gain = context.createGain();
        analyser = context.createAnalyser();
        analyser.fftSize = levels.length;
        analyser.connect(gain).connect(context.destination);
      }
      gain.gain.value = preferences.volume;
      if (context.state !== 'running') void context.resume().catch(() => {});
    } catch {
      return false;
    }
    return true;
  }

  function animate() {
    for (const item of scheduled) {
      if (item.start > context.currentTime) break;
      if (item.expression) {
        onStart(item.expression);
        item.expression = null;
      }
    }
    analyser.getFloatTimeDomainData(levels);
    let energy = 0;
    for (const sample of levels) energy += sample * sample;
    renderer.setMouthOpen(Math.min(1, 5 * Math.sqrt(energy / levels.length)));
    frame = requestAnimationFrame(animate);
  }

  function enqueue(pcm, rate, expression) {
    if (!context || context.state !== 'running') {
      onError('소리를 재생하려면 음성을 켜고 다시 말을 걸어 주세요.');
      return false;
    }
    const bytes = Uint8Array.from(atob(pcm), char => char.charCodeAt(0));
    const samples = new DataView(bytes.buffer);
    const buffer = context.createBuffer(1, bytes.length / 2, rate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < channel.length; i++) channel[i] = samples.getInt16(i * 2, true) / 32768;
    const node = context.createBufferSource();
    node.buffer = buffer;
    node.playbackRate.value = preferences.rate;
    node.connect(analyser);
    const start = Math.max(nextStart, context.currentTime + .025);
    nextStart = start + buffer.duration / node.playbackRate.value;
    const item = { node, expression, start };
    scheduled.add(item);
    node.onended = () => {
      node.disconnect();
      if (!scheduled.delete(item)) return;
      if (item.expression) onStart(item.expression);
      if (!scheduled.size) {
        cancelAnimationFrame(frame);
        frame = 0;
        renderer.setMouthOpen(0);
        onDrain();
      }
    };
    node.start(start);
    if (!frame) animate();
    return true;
  }

  return {
    prepare, enqueue,
    get pending() { return scheduled.size > 0; },
    updateSettings() { if (gain) gain.gain.value = preferences.volume; },
    stop() {
      for (const { node } of scheduled) {
        node.onended = null;
        node.stop();
        node.disconnect();
      }
      scheduled.clear();
      cancelAnimationFrame(frame);
      frame = 0;
      nextStart = 0;
    },
    dispose() { if (context) void context.close(); },
  };
}
