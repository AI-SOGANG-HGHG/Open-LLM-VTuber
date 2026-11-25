import { kangIseoModel } from '../../shared/live2d-loader.js';
import { createRandomId } from '../../shared/random-id.js';
import { now } from './dom.js';

const DEMO_MEMORY = '프로젝트 발표는 오전 10시에 시작하고 발표 시간은 5분이다.';

export const presets = {
  warm: { label: '다정한 동료', tone: '친근한 반말', persona: '따뜻하고 호기심 많은 동료. 상대의 이야기에 공감하고, 함께할 수 있는 작은 다음 행동을 제안한다.', tags: ['다정한', '공감하는', '함께하는'], exploration: 40 },
  curious: { label: '호기심 많은 탐험가', tone: '활기찬 반말', persona: '새로운 장소와 아이디어에 호기심이 많다. 다양한 가능성을 이야기하고 새로운 시도를 제안한다.', tags: ['호기심', '탐험', '새로운 시도'], exploration: 85 },
  calm: { label: '차분한 전략가', tone: '차분한 존댓말', persona: '차분하고 계획적인 동료. 목표를 확인하고, 일을 작은 단계로 나누어 설명한다.', tags: ['차분한', '계획적인', '신중한'], exploration: 25 },
  'kang-iseo': {
    label: '강이서',
    tone: '차분한 존댓말',
    persona: '작은 노트에 마음에 남은 순간을 적는 동료. 일상에는 호기심을 보이고 기쁜 일에는 함께 기뻐한다. 도움을 원할 때 고민을 정리하고 다음 행동 하나를 제안한다.',
    tags: ['차분한', '잘 들어주는', '함께 정리하는'],
    exploration: 35,
  },
};
export const studioPresets = {
  'direct-reviewer': '직설적인 검토자',
  'supportive-coach': '다정한 코치',
  calm: '차분한 전략가',
  'kang-iseo': presets['kang-iseo'].label,
  warm: '다정한 동료',
  curious: '호기심 많은 탐험가',
};
export const demoPersonas = [
  { id: 'direct-reviewer', description: '마감에 맞추려면 지금 뭘 해야 할지 짚어줘요.', tags: ['마감 점검', '우선순위 정하기'] },
  { id: 'supportive-coach', description: '막막할 때 지금 할 수 있는 일부터 함께 정해요.', tags: ['부담 덜기', '작은 단계로 나누기'] },
];
export const avatarAssets = {
  mao: { name: 'Mao', label: 'Open-LLM-VTuber 기본 캐릭터', image: './assets/mao.png', model: '/live2d-models/mao_pro/runtime/mao_pro.model3.json', credit: '© Live2D Inc.' },
  sogangi: { name: '서강이', label: '서강대학교 캐릭터', image: '../sogangi/assets/sogangi-neutral.svg', model: '/live2d-models/sogangi-expressions/runtime/sogangi.model3.json', credit: '' },
  'ivory-crown': { name: '강이서', label: 'Live2D 아바타', image: new URL('../assets/ivory-crown.webp', import.meta.url).href, model: kangIseoModel, credit: '' },
  symbol: { name: '아이콘', label: '아이콘으로 표시', image: '', model: '', credit: '' },
};
export const catalogProfiles = [
  {
    id: 'mao', name: 'Mao', template: 'curious', avatar: 'mao',
    description: '호기심이 많고 새로운 이야기를 좋아해요.',
    greeting: '안녕, 나는 Mao야! 오늘은 무슨 얘기 해 볼까?',
    previousDescription: '새로운 이야기를 좋아하는, 당신의 첫 번째 버추얼 파트너.',
    previousGreeting: '안녕, 나는 Mao야! 오늘은 어떤 재미있는 이야기를 만들어볼까?',
  },
  {
    id: 'sogangi', name: '서강이', template: 'warm', avatar: 'sogangi',
    description: '공부나 팀 프로젝트가 막힐 때 같이 방법을 찾아줘요.',
    greeting: '반가워! 오늘은 어떤 얘기부터 해 볼까?',
    previousDescription: '공부도 프로젝트도, 언제나 네 편인 캠퍼스 동료.',
    previousGreeting: '반가워, 학우야! 오늘도 같이 한 걸음씩 해보자.',
  },
  {
    id: 'kang-iseo', name: '강이서', template: 'kang-iseo', studioPreset: 'kang-iseo', avatar: 'ivory-crown',
    description: '복잡한 고민을 들어주고 다음에 할 일을 차근차근 정리해 줘요.',
    greeting: '안녕하세요. 강이서입니다. 오늘 어땠어요? 사소한 이야기부터 편하게 들려주세요.',
  },
  {
    id: 'moa', name: '모아', template: 'curious', avatar: 'symbol',
    description: '새로운 생각이나 해 보고 싶은 일을 함께 이야기해요.',
    previousDescription: '작은 호기심에서 시작하는, 우리만의 새로운 모험.',
  },
];

export function defaultGreeting({ name, tone }) {
  if (tone === '차분한 존댓말') return `안녕하세요. ${name}입니다. 오늘은 어떤 이야기를 나눌까요?`;
  const lastSyllable = name.normalize('NFC').slice(-1);
  if (!/[가-힣]/.test(lastSyllable)) return '안녕! 만나서 반가워. 오늘은 무슨 얘기 해 볼까?';
  const hasFinalConsonant = (lastSyllable.charCodeAt(0) - '가'.charCodeAt(0)) % 28 !== 0;
  return `안녕! 나는 ${name}${hasFinalConsonant ? '이야' : '야'}. 오늘은 무슨 얘기 해 볼까?`;
}
export function createCharacter(id, name, description, template, avatar = 'symbol') {
  const char = { id, name, description, template, avatar, tone: presets[template].tone, persona: presets[template].persona, exploration: presets[template].exploration, createdAt: now(), updatedAt: now(), favorite: false, memories: [], messages: [] };
  char.greeting = defaultGreeting(char);
  return char;
}
export function catalogCharacters() {
  return catalogProfiles.map(({ id, name, description, template, studioPreset, avatar, greeting }) => {
    const char = createCharacter(id, name, description, template, avatar);
    if (studioPreset) char.studioPreset = studioPreset;
    if (greeting) char.greeting = greeting;
    return char;
  });
}
export function demoCharacters() {
  return demoPersonas.map(({ id, description }) => {
    const char = createCharacter(id, studioPresets[id], description, 'calm', 'mao');
    char.studioPreset = id;
    char.memories.push({ id: createRandomId(), text: DEMO_MEMORY, at: now() });
    return char;
  });
}
