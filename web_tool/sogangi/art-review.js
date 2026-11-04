const $ = (id) => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const ROOT = './assets/overlap-candidates/';
const views = { full: '175 315 270 337', shoulder: '218 495 200 105', face: '208 367 200 166' };
async function init() {
  try {
    const response = await fetch(ROOT + 'review.json');
    if (!response.ok) throw new Error('Missing art review');
    const review = await response.json();
    if (!Array.isArray(review.poses) || !review.poses.length || !review.verification)
      throw new Error('Invalid art review');
    for (const pose of review.poses) {
      if (!/^[a-z]+(?:-[a-z]+)*$/.test(pose.id)) throw new Error('Invalid pose ID');
      const option = document.createElement('option');
      option.value = pose.id;
      option.textContent = pose.label;
      $('artPose').append(option);
    }
    $('artDecision').textContent =
      review.recommendation === 'keep_baseline_for_initial_rigid_motion'
        ? '이번 비교 결과: 첫 동작 범위에서 어깨 보완 후보가 보이는 결과를 바꾸지 않았습니다. 현재 앱은 기존 24개 원화를 유지합니다. 실제 Cubism 변형에서는 다시 검토해야 합니다.'
        : '어깨 보완 후보는 윤곽을 검토한 뒤 채택 여부를 정해야 합니다. 현재 앱에는 적용하지 않았습니다.';
    for (const stage of [$('originalArt'), $('candidateArt')]) {
      const guide = document.createElementNS(NS, 'g');
      guide.setAttribute('data-joint-guide', '');
      guide.style.display = 'none';
      for (const { pivot } of review.candidate_joints) {
        const path = document.createElementNS(NS, 'path');
        path.setAttribute('d', `M${pivot[0] - 6} ${pivot[1]}h12M${pivot[0]} ${pivot[1] - 6}v12`);
        path.setAttribute('stroke', '#087f70');
        path.setAttribute('stroke-width', '1.5');
        path.setAttribute('vector-effect', 'non-scaling-stroke');
        guide.append(path);
      }
      stage.append(guide);
    }
    const verified =
      review.verification.neutral_browser_rgba_exact_2048 &&
      review.verification.neutral_psd_max_channel_error_255 <= 1;
    $('artNeutral').textContent = verified
      ? `2048×2048 정면 브라우저 합성은 RGBA 픽셀이 동일합니다. PSD 합성은 ${review.verification.neutral_psd_changed_pixels_2048}픽셀에서 채널 최댓값 ${review.verification.neutral_psd_max_channel_error_255}/255의 차이가 있습니다. 기존 24개 레이어 픽셀은 그대로입니다.`
      : '정면 보존 검사를 다시 확인해야 합니다.';
    for (const entry of review.existing_hidden_art) {
      const dt = document.createElement('dt'),
        dd = document.createElement('dd');
      dt.textContent = entry.part;
      dd.textContent = `${((entry.fully_covered_pixels_2048 / entry.opaque_pixels_2048) * 100).toFixed(1)}% 가려짐`;
      $('artOverlap').append(dt, dd);
    }
    function selectPose() {
      const pose = review.poses.find((item) => item.id === $('artPose').value);
      for (const [stage, variant] of [
        [$('originalArt'), 'original'],
        [$('candidateArt'), 'candidate'],
      ]) {
        stage.querySelector('image').setAttribute('href', `${ROOT}poses/${pose.id}-${variant}.svg`);
        stage.dataset.pose = pose.id;
      }
      const note = pose.changed_pixels_1024
        ? `1024×1024 비교에서 ${pose.changed_pixels_1024.toLocaleString()}픽셀 변경 · 어깨 윤곽과 내부 선을 검토하세요.`
        : '이 자세에서는 후보를 추가해도 보이는 픽셀이 같아요. 추가 원화가 실제로 필요한지는 다른 동작도 함께 검토하세요.';
      $('artPoseNote').textContent =
        (pose.outside_initial_scope ? '첫 동작 범위 밖 점검입니다. ' : '') + note;
      $('artPoseNote').dataset.stress = String(Boolean(pose.outside_initial_scope));
    }
    $('artPose').addEventListener('change', selectPose);
    for (const button of document.querySelectorAll('[data-art-view]')) {
      button.addEventListener('click', () => {
        for (const stage of document.querySelectorAll('.art-stage')) {
          const view = views[button.dataset.artView];
          const [, , width, height] = view.split(' ').map(Number);
          stage.setAttribute('viewBox', view);
          stage.style.aspectRatio = `${width}/${height}`;
        }
        document.querySelector('.art-comparison').dataset.view = button.dataset.artView;
        for (const item of document.querySelectorAll('[data-art-view]'))
          item.setAttribute('aria-pressed', String(item === button));
      });
    }
    $('artGuide').addEventListener('change', () => {
      for (const guide of document.querySelectorAll('[data-joint-guide]'))
        guide.style.display = $('artGuide').checked ? '' : 'none';
    });
    selectPose();
    $('artContent').hidden = false;
  } catch {
    $('artError').hidden = false;
  }
}
init();
