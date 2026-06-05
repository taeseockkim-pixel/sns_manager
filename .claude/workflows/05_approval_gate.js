// H-06: meta 블록 필수
export const meta = {
  name: "approval-gate",
  description: "H-01: Human-in-the-Loop 승인 게이트 — 사람이 승인하기 전 게시 절대 불가",
  phases: [
    { title: "Queue", detail: "승인 대기 콘텐츠 DB 저장 및 담당자 알림" },
    { title: "Review", detail: "승인 대기 목록 출력 (사람이 직접 approve/reject 명령 실행)" },
  ],
};

// args: 04_brand_safety.js 반환 content 객체
const content = args;

if (!content) {
  throw new Error("content 객체가 필요합니다. 04_brand_safety.js 출력을 args로 전달하세요.");
}

// H-03: 브랜드 안전 검사 미통과 콘텐츠 차단
if (!content.brand_safety_passed) {
  log(`❌ 브랜드 안전 검사 실패로 승인 게이트 차단`);
  log(`반려 이유: ${content.rejection_reason}`);
  return {
    queued: false,
    reason: "brand_safety_failed",
    details: content.rejection_reason,
  };
}

phase("Queue");
log("브랜드 안전 검사 통과 — 승인 대기열에 등록");

// 승인 대기 정보 요약 생성
const summary = await agent(
  `아래 SNS 콘텐츠의 담당자 검토용 요약을 한국어로 작성하세요. 간결하게 3줄 이내.

  플랫폼: ${content.platform}
  주제: ${content.topic}
  국문: ${content.ko.text}
  영문: ${content.en.text}
  브랜드 안전 점수: ${content.brand_safety_score}/100
  예약 시간: ${content.scheduled_at || "즉시"}

  출력 형식: 단순 텍스트 (마크다운 없이)`,
  { label: "queue:summary", phase: "Queue" }
);

log("DB 저장 및 담당자 알림 발송 필요 (Python queue.py 연동)");

phase("Review");

// H-01: 담당자가 직접 확인해야 하는 정보 출력
log("══════════════════════════════════════");
log("🔔 SNS 게시물 승인 요청");
log("══════════════════════════════════════");
log(`플랫폼: ${content.platform.toUpperCase()}`);
log(`브랜드 안전 점수: ${content.brand_safety_score}/100`);
log("");
log("📝 [국문]");
log(content.ko.text);
log(`해시태그: ${content.ko.hashtags.join(" ")}`);
log("");
log("📝 [English]");
log(content.en.text);
log(`Hashtags: ${content.en.hashtags.join(" ")}`);
log("");
log("══════════════════════════════════════");
log("✅ 승인하려면: python src/db/queue.py approve <id>");
log("❌ 반려하려면: python src/db/queue.py reject <id> \"반려 이유\"");
log("📋 대기 목록: python src/db/queue.py list");
log("══════════════════════════════════════");

return {
  queued: true,
  content,
  summary,
  next_step: "python src/db/queue.py list 명령으로 대기 목록 확인 후 approve/reject 실행",
};
