/**
 * SSE EventSource 구독 — 서버 이벤트를 실시간으로 UI에 반영
 */

(function () {
  const es = new EventSource('/events');

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
    // 대시보드 이벤트 목록도 갱신 (있으면)
    const dashEvents = document.getElementById('dashboard-events');
    if (dashEvents && data.id) {
      htmx.ajax('GET', '/partial/monitor-event/' + data.id, {
        target: '#dashboard-events',
        swap: 'afterbegin',
      });
    }
  });

  // 큐 업데이트: 해당 행 새로고침 (이미 HTMX가 처리하므로 추가 작업 없음)
  es.addEventListener('queue.updated', function () {
    // 큐 페이지 Nav 배지를 새로고침하려면 페이지 리로드가 필요하지만
    // HTMX가 이미 행을 교체하므로 여기서는 생략
  });

  es.onerror = function () {
    // 연결 끊김 시 EventSource가 자동 재연결 시도
    console.warn('[SSE] 연결 끊김 — 자동 재연결 중...');
  };

  function updateNotifCount(count) {
    const el = document.getElementById('notif-count');
    if (!el) return;
    if (count > 0) {
      el.textContent = count;
      el.classList.remove('hidden');
    } else {
      el.textContent = '0';
      el.classList.add('hidden');
    }
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
