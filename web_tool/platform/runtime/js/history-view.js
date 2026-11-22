const PAGE_SIZE = 30;

export function createHistoryView(elements, {
  historyTitle,
  characterName,
  downloadPrefix,
  cleanMessage,
  getActiveHistoryUid,
  onRequest,
  onSelect,
}) {
  const { historyButton, historyDialog, historyClose, historyItems, historySearch, exportChat, messages } = elements;
  let histories = [];
  let historyLimit = PAGE_SIZE;

  function render() {
    historyItems.replaceChildren();
    const query = historySearch.value.trim().toLocaleLowerCase('ko-KR');
    const filtered = histories.filter((history) =>
      String(history.latest_message?.content || '')
        .toLocaleLowerCase('ko-KR')
        .includes(query),
    );
    if (!filtered.length) {
      const empty = document.createElement('p');
      empty.className = 'history-empty';
      empty.textContent = query
        ? '검색어와 일치하는 대화가 없어요.'
        : '아직 저장된 대화가 없어요.';
      historyItems.append(empty);
      return;
    }

    const activeHistoryUid = getActiveHistoryUid();
    for (const history of filtered.slice(0, historyLimit)) {
      if (typeof history.uid !== 'string' || !/^[\w-]{1,120}$/.test(history.uid)) continue;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'history-item';
      button.dataset.historyUid = history.uid;
      if (history.uid === activeHistoryUid) button.setAttribute('aria-current', 'true');

      const title = document.createElement('span');
      title.className = 'history-item-title';
      title.textContent = cleanMessage(history.latest_message?.content).slice(0, 100) || '이전 대화';
      const date = document.createElement('span');
      date.className = 'history-item-date';
      const value = new Date(history.timestamp);
      date.textContent = Number.isNaN(value.getTime())
        ? '저장된 대화'
        : value.toLocaleString('ko-KR');

      button.append(title, date);
      button.addEventListener('click', () => onSelect(history.uid));
      const item = document.createElement('div');
      item.setAttribute('role', 'listitem');
      item.append(button);
      historyItems.append(item);
    }

    if (filtered.length > historyLimit) {
      const more = document.createElement('button');
      more.type = 'button';
      more.className = 'quiet-button history-more';
      more.textContent = `더 보기 · ${filtered.length - historyLimit}개 남음`;
      more.addEventListener('click', () => {
        const previousLimit = historyLimit;
        historyLimit += PAGE_SIZE;
        render();
        historyItems.querySelectorAll('.history-item')[previousLimit]?.focus();
      });
      historyItems.append(more);
    }
  }

  historyButton.addEventListener('click', () => {
    historyLimit = PAGE_SIZE;
    historySearch.value = '';
    historyItems.textContent = '대화 기록을 불러오고 있어요.';
    historyDialog.showModal();
    onRequest();
  });
  historyClose.addEventListener('click', () => historyDialog.close());
  historySearch.addEventListener('input', () => {
    historyLimit = PAGE_SIZE;
    render();
  });
  exportChat.addEventListener('click', () => {
    const lines = [historyTitle, new Date().toLocaleString('ko-KR'), ''];
    for (const node of messages.querySelectorAll('.message')) {
      const speaker = node.classList.contains('user') ? '나' : characterName;
      const message = node.querySelector('.message-body').textContent;
      lines.push(`${speaker}: ${message}`, '');
    }
    const url = URL.createObjectURL(
      new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/plain;charset=utf-8' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `${downloadPrefix}-대화-${new Date().toISOString().slice(0, 10)}.txt`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  return {
    showList(entries) {
      histories = entries;
      render();
    },
  };
}
