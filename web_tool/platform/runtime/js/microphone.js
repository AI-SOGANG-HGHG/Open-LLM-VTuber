async function wavForRecognition(blob) {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    const renderer = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
    const source = renderer.createBufferSource();
    source.buffer = decoded;
    source.connect(renderer.destination);
    source.start();
    const samples = (await renderer.startRendering()).getChannelData(0);
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const chars = (offset, value) => {
      for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
    };
    chars(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    chars(8, 'WAVE');
    chars(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, 16000, true);
    view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    chars(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) {
      const value = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(44 + i * 2, value < 0 ? value * 32768 : value * 32767, true);
    }
    return new Blob([buffer], { type: 'audio/wav' });
  } finally {
    await context.close();
  }
}

export function createMicrophone({ micButton, messageInput, phase }, {
  isReady,
  onStateChange,
  onReady,
  onNotice,
  onDraftChange,
}) {
  let recording = false;
  let permissionPending = false;
  let transcribing = false;
  let micEpoch = 0;
  let asrController = null;
  let recordingTimer = null;
  let activeRecorder = null;
  let activeStream = null;

  function cancel() {
    micEpoch++;
    asrController?.abort();
    asrController = null;
    clearTimeout(recordingTimer);
    if (activeRecorder && activeRecorder.state !== 'inactive') {
      activeRecorder.onstop = null;
      activeRecorder.stop();
    }
    activeStream?.getTracks().forEach((track) => track.stop());
    activeStream = null;
    activeRecorder = null;
    recording = false;
    permissionPending = false;
    transcribing = false;
    micButton.textContent = '마이크';
    micButton.setAttribute('aria-pressed', 'false');
    onStateChange();
  }
  micButton.addEventListener('click', async () => {
    if (recording) {
      if (activeRecorder?.state === 'recording') activeRecorder.stop();
      return;
    }
    if (permissionPending || transcribing) {
      cancel();
      onReady();
      onNotice('음성 입력을 취소했어요.');
      return;
    }
    const epoch = ++micEpoch;
    const previousDraft = messageInput.value;
    permissionPending = true;
    micButton.textContent = '권한 요청 취소';
    phase.textContent = '마이크 권한을 확인하고 있어요.';
    onStateChange();
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
        throw new Error('unsupported');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (epoch !== micEpoch || !isReady()) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      permissionPending = false;
      activeStream = stream;
      const recorder = new MediaRecorder(stream);
      const chunks = [];
      activeRecorder = recorder;
      recording = true;
      micButton.textContent = '녹음 끝내기';
      micButton.setAttribute('aria-pressed', 'true');
      phase.textContent = '녹음 중이에요. ‘녹음 끝내기’를 누르면 멈춰요.';
      onStateChange();
      onNotice('');
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onerror = () => {
        if (epoch === micEpoch) {
          cancel();
          onReady();
          onNotice('녹음이 중단됐어요. 마이크를 확인해 주세요.');
        }
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        if (epoch !== micEpoch) return;
        clearTimeout(recordingTimer);
        recording = false;
        activeStream = null;
        activeRecorder = null;
        transcribing = true;
        micButton.textContent = '인식 취소';
        micButton.setAttribute('aria-pressed', 'false');
        phase.textContent = '음성을 글로 바꾸고 있어요.';
        onStateChange();
        const controller = new AbortController();
        asrController = controller;
        const deadline = setTimeout(() => controller.abort(), 30000);
        try {
          const wav = await wavForRecognition(new Blob(chunks, { type: recorder.mimeType }));
          if (epoch !== micEpoch) return;
          const form = new FormData();
          form.append('file', wav, 'recording.wav');
          const response = await fetch('/asr', {
            method: 'POST',
            body: form,
            signal: controller.signal,
          });
          if (!response.ok) throw new Error('ASR');
          const data = await response.json();
          if (epoch !== micEpoch || !isReady()) return;
          transcribing = false;
          micButton.textContent = '마이크';
          onReady();
          if (data.text?.trim()) {
            messageInput.value = [previousDraft.trim(), data.text.trim()]
              .filter(Boolean)
              .join('\n');
            messageInput.value = messageInput.value.slice(0, 4000);
            onDraftChange();
            onNotice('입력된 내용을 확인하고 ‘보내기’를 눌러 주세요.');
            messageInput.focus();
          } else onNotice('음성을 알아듣지 못했어요. 다시 말씀해 주세요.');
        } catch {
          if (epoch !== micEpoch) return;
          transcribing = false;
          micButton.textContent = '마이크';
          onReady();
          onNotice('음성을 글로 바꾸지 못했어요. 직접 입력하거나 다시 녹음해 주세요.');
        } finally {
          clearTimeout(deadline);
          if (epoch === micEpoch) asrController = null;
        }
      };
      recorder.start();
      recordingTimer = setTimeout(() => {
        if (epoch === micEpoch && recorder.state === 'recording') recorder.stop();
      }, 60000);
    } catch {
      if (epoch !== micEpoch) return;
      cancel();
      onReady();
      onNotice('마이크를 사용할 수 없어요. 브라우저 권한과 마이크 연결을 확인해 주세요.');
    }
  });

  return {
    get busy() {
      return recording || permissionPending || transcribing;
    },
    cancel,
  };
}
