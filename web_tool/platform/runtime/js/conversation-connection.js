const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000];

export function createConversationConnection({ path = '/client-ws', onConnecting, onMessage, onDisconnected, onError }) {
  let socket = null;
  let connectTimer = null;
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let closed = false;

  function connect() {
    if (closed) return;
    clearTimeout(reconnectTimer);
    clearTimeout(connectTimer);
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
    onConnecting();

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const current = new WebSocket(`${protocol}//${location.host}${path}`);
    socket = current;
    connectTimer = setTimeout(() => {
      if (current === socket) current.close(4000, 'Initialization timeout');
    }, 20000);

    current.onmessage = (event) => {
      if (current !== socket || closed) return;
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      onMessage(data);
    };
    current.onclose = () => {
      if (current !== socket || closed) return;
      clearTimeout(connectTimer);
      const delay = navigator.onLine && reconnectAttempts < RECONNECT_DELAYS.length
        ? RECONNECT_DELAYS[reconnectAttempts++]
        : null;
      onDisconnected(delay);
      if (delay !== null) reconnectTimer = setTimeout(connect, delay);
    };
    current.onerror = () => {
      if (current === socket && !closed) onError();
    };
  }

  return {
    connect,
    retry() {
      reconnectAttempts = 0;
      connect();
    },
    send(payload) {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(payload));
    },
    markReady() {
      clearTimeout(connectTimer);
      reconnectAttempts = 0;
    },
    restartAfterFailure(reason) {
      socket?.close(4000, reason);
    },
    dispose() {
      closed = true;
      clearTimeout(connectTimer);
      clearTimeout(reconnectTimer);
      socket?.close();
    },
  };
}
