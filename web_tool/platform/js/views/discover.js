import { card } from '../components/card.js';
import { main, pageHeading } from '../dom.js';
import { catalogCharacters } from '../presets.js';

export function renderDiscover() {
  main.innerHTML = pageHeading('FIND YOUR NEXT CHARACTER', '어떤 캐릭터를 만나볼까요?', '마음에 드는 모습에서 시작해, 당신만의 성격을 더해보세요.') + '<div class="discover-intro"><span aria-hidden="true">✧</span>처음이라면 프리셋으로 가볍게 시작하세요. 설정은 나중에도 바꿀 수 있어요.</div><div class="character-grid">' + catalogCharacters().map((char) => card(char, true)).join('') + '</div><p class="bottom-note">Mao는 Open-LLM-VTuber에 등록된 기본 Live2D 모델이에요. 프리셋을 선택하면 이름·말투·첫 인사를 정해 내 캐릭터로 만들 수 있어요.</p>';
}
