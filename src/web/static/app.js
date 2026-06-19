/**
 * SSE EventSource 구독 — 서버 이벤트를 실시간으로 UI에 반영
 */

(function () {
  const es = new EventSource('/events');

  // 페이지 이동/닫기 시 반드시 연결 종료 — 미종료 시 브라우저 연결 슬롯(6개) 소진
  function closeSSE() { es.close(); }
  window.addEventListener('beforeunload', closeSSE);
  window.addEventListener('pagehide', closeSSE);

  // 초기 연결: 미열람 알림 수 반영
  es.addEventListener('init', function (e) {
    const data = JSON.parse(e.data);
    updateNotifCount(data.unread_count);
  });

  // 새 알림: 벨 카운터 갱신
  es.addEventListener('notification.new', function (e) {
    const data = JSON.parse(e.data);
    updateNotifCount(data.unread_count);
    showToast(data.severity || 'info', '새 알림이 도착했습니다.');
  });

  // 모니터링 이벤트: 모니터링 페이지 테이블 최상단에 행 추가
  es.addEventListener('monitor.event', function (e) {
    const data = JSON.parse(e.data);
    const table = document.getElementById('monitor-table');
    if (table && data.id) {
      htmx.ajax('GET', '/partial/monitor-event/' + data.id, {
        target: '#monitor-table',
        swap: 'afterbegin',
      });
    }
    const dashEvents = document.getElementById('dashboard-events');
    if (dashEvents && data.id) {
      htmx.ajax('GET', '/partial/monitor-event/' + data.id, {
        target: '#dashboard-events',
        swap: 'afterbegin',
      });
    }
  });

  es.addEventListener('queue.updated', function () {});

  es.onerror = function () {
    console.warn('[SSE] 연결 끊김 — 자동 재연결 중...');
  };

  function updateNotifCount(count) {
    ['notif-count', 'notif-count-mobile'].forEach(function (id) {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = count > 0 ? count : '0';
      el.classList.toggle('nav-badge-hidden', count <= 0);
    });
  }

  function showToast(severity, message) {
    const colors = {
      critical: 'bg-red-600',
      warning: 'bg-amber-500',
      success: 'bg-green-600',
      info: 'bg-blue-600',
    };
    const color = colors[severity] || colors.info;

    const toast = document.createElement('div');
    toast.className = `fixed bottom-4 right-4 z-50 px-4 py-3 rounded-lg text-white text-sm font-medium shadow-lg ${color} transition-opacity duration-300`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(function () {
      toast.style.opacity = '0';
      setTimeout(function () { toast.remove(); }, 300);
    }, 3500);
  }
})();
