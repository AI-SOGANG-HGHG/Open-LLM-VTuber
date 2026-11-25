export function createAudioPlayback({ preferences, renderer, canPlay, onStart, onUnavailable, onComplete, onError }) {
  const queue = [];
  let playing = null;
  let lipFrame = null;
  let epoch = 0;
  let synthesisDone = false;
  let acknowledged = false;

  function completeIfReady() {
    if (synthesisDone && !playing && !queue.length && !acknowledged) {
      acknowledged = true;
      onComplete();
    }
  }

  function updateSettings() {
    if (!playing) return;
    playing.volume = preferences.volume;
    playing.playbackRate = preferences.rate;
  }

  async function playNext() {
    if (playing) return;
    let item = queue.shift();
    while (item && item.epoch !== epoch) item = queue.shift();
    if (!item || !canPlay()) {
      queue.length = 0;
      completeIfReady();
      return;
    }

    const audio = new Audio(`data:audio/wav;base64,${item.audio}`);
    playing = audio;
    updateSettings();
    let started = false;
    const done = () => {
      if (playing !== audio) return;
      playing = null;
      cancelAnimationFrame(lipFrame);
      renderer.setMouthOpen(0);
      audio.onended = null;
      audio.onerror = null;
      playNext();
    };
    function failed(message) {
      if (playing !== audio || item.epoch !== epoch) return;
      if (!started) onUnavailable?.(item.expression);
      onError(message);
      done();
    }
    audio.onended = done;
    audio.onerror = () => failed('음성을 재생하지 못했어요. 화면에서 답변을 읽을 수 있어요.');
    try {
      await audio.play();
      if (playing !== audio || item.epoch !== epoch) return;
      started = true;
      onStart(item.expression);
      const syncMouth = () => {
        if (playing !== audio) return;
        const index = Math.floor((audio.currentTime * 1000) / (item.slice || 20));
        renderer.setMouthOpen(item.volumes?.[index] || 0);
        lipFrame = requestAnimationFrame(syncMouth);
      };
      syncMouth();
    } catch {
      failed('소리를 재생하지 못했어요. 음소거 상태와 스피커를 확인해 주세요.');
    }
  }

  function stop() {
    cancelAnimationFrame(lipFrame);
    renderer.cancelGesture();
    renderer.setMouthOpen(0);
    queue.length = 0;
    if (playing) {
      const audio = playing;
      playing = null;
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
  }

  return {
    startTurn() {
      epoch++;
      synthesisDone = false;
      acknowledged = false;
    },
    cancelTurn() {
      epoch++;
      stop();
    },
    enqueue(item) {
      queue.push({ ...item, epoch });
      playNext();
    },
    finishSynthesis() {
      synthesisDone = true;
      completeIfReady();
    },
    completeIfReady,
    stop,
    updateSettings,
  };
}
