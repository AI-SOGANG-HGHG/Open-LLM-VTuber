import { card } from '../components/card.js';
import { main, pageHeading } from '../dom.js';
import { catalogCharacters } from '../presets.js';

export function renderDiscover() {
  main.innerHTML = pageHeading('캐릭터 둘러보기', '기본 캐릭터를 선택한 뒤 이름과 성격을 바꿀 수 있어요.') + '<div class="character-grid">' + catalogCharacters().map((char) => card(char, { catalog: true })).join('') + '</div>';
}
