import { createUuid, now } from './dom.js';

const DEMO_MEMORY = '프로젝트 발표는 오전 10시에 시작하고 발표 시간은 5분이다.';

export const presets = {
  warm: { label: '다정한 동료', tone: '친근한 반말', persona: '따뜻하고 호기심 많은 동료. 상대의 이야기에 공감하고, 함께할 수 있는 작은 다음 행동을 제안한다.', tags: ['다정한', '공감하는', '함께하는'], exploration: 40 },
  curious: { label: '호기심 많은 탐험가', tone: '활기찬 반말', persona: '새로운 장소와 아이디어에 호기심이 많다. 다양한 가능성을 이야기하고 새로운 시도를 제안한다.', tags: ['호기심', '탐험', '새로운 시도'], exploration: 85 },
  calm: { label: '차분한 전략가', tone: '차분한 존댓말', persona: '차분하고 계획적인 동료. 목표를 확인하고, 일을 작은 단계로 나누어 설명한다.', tags: ['차분한', '계획적인', '신중한'], exploration: 25 },
};
export const studioPresets = {
  'direct-reviewer': '직설적인 검토자',
  'supportive-coach': '다정한 코치',
  calm: '차분한 전략가',
  warm: '다정한 동료',
};
export const avatarAssets = {
  mao: { name: 'Mao', label: 'Open-LLM-VTuber 기본', image: './assets/mao.png', model: '/live2d-models/mao_pro/runtime/mao_pro.model3.json', credit: '© Live2D Inc.' },
  sogangi: { name: '서강이', label: '캠퍼스 캐릭터', image: '../sogangi/assets/sogangi-neutral.svg', model: '/live2d-models/sogangi-expressions/runtime/sogangi.model3.json', credit: '' },
  symbol: { name: '심볼', label: '커스텀 페르소나', image: '', model: '', credit: '' },
};

export function defaultGreeting(char) { return char.tone === '차분한 존댓말' ? `안녕하세요. ${char.name}입니다. 오늘 함께할 일을 이야기해 주세요.` : `안녕! 나는 ${char.name}야. 오늘은 어떤 이야기를 해볼까?`; }
export function createCharacter(id, name, description, template, avatar = 'symbol') {
  const char = { id, name, description, template, avatar, tone: presets[template].tone, persona: presets[template].persona, exploration: presets[template].exploration, createdAt: now(), updatedAt: now(), favorite: false, memories: [], messages: [] };
  char.greeting = defaultGreeting(char);
  return char;
}
export function catalogCharacters() {
  const mao = createCharacter('mao', 'Mao', '새로운 이야기를 좋아하는, 당신의 첫 번째 버추얼 파트너.', 'curious', 'mao');
  mao.greeting = '안녕, 나는 Mao야! 오늘은 어떤 재미있는 이야기를 만들어볼까?';
  const sogangi = createCharacter('sogangi', '서강이', '공부도 프로젝트도, 언제나 네 편인 캠퍼스 동료.', 'warm', 'sogangi');
  sogangi.greeting = '반가워, 학우야! 오늘도 같이 한 걸음씩 해보자.';
  const moa = createCharacter('moa', '모아', '작은 호기심에서 시작하는, 우리만의 새로운 모험.', 'curious');
  return [mao, sogangi, moa];
}
export function demoCharacters() {
  const demos = [
    ['direct-reviewer', '마감 위험을 짚고 지금 할 일을 분명하게 제안해요.'],
    ['supportive-coach', '부담을 함께 살피고 시작하기 쉬운 단계를 제안해요.'],
  ];
  return demos.map(([id, description]) => {
    const char = createCharacter(id, studioPresets[id], description, 'calm', 'mao');
    char.studioPreset = id;
    char.memories.push({ id: createUuid(), text: DEMO_MEMORY, at: now() });
    return char;
  });
}
