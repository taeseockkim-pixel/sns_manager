// H-06: meta 블록 필수
export const meta = {
  name: "publish",
  description: "H-01: 승인된 콘텐츠만 플랫폼에 게시 — approved: true 검증 필수",
  phases: [
    { title: "Verify", detail: "승인 상태 최종 확인 (이중 검증)" },
    { title: "Publish", detail: "플랫폼 API로 게시" },
    { title: "Log", detail: "게시 결과 기록" },
  ],
};

// args: { queue_id, content, platform }
const { queue_id, content, platform } = args || {};

if (!content) {
  throw new Error("content가 필요합니다.");
}

// H-01: approved 상태 이중 검증 (절대 원칙)
phase("Verify");
log("H-01: 승인 상태 최종 이중 검증");

if (!content.approved) {
  log("❌ 게시 차단: approved = false. 사람의 승인 없이 게시 불가 (H-01)");
  return {
    published: false,
    reason: "not_approved",
    message: "H-01 위반: 사람의 명시적 승인 없이 게시할 수 없습니다.",
  };
}

if (content.brand_safety_score < 80) {
  log(`❌ 게시 차단: 브랜드 안전 점수 부족 (${content.brand_safety_score}/80)`);
  return {
    published: false,
    reason: "brand_safety_failed",
    message: `H-03 위반: 브랜드 안전 점수 ${content.brand_safety_score} < 80`,
  };
}

log(`✅ 승인 확인 완료 (queue_id: ${queue_id}, 점수: ${content.brand_safety_score}/100)`);

// H-05: 플랫폼별 독립 에이전트
phase("Publish");
log(`${platform.toUpperCase()} 플랫폼에 게시 시작`);

// 게시 텍스트 결정 (국문 우선, 글로벌 채널은 영문)
const isGlobal = platform === "linkedin" || (platform === "x" && content.en);
const postText = isGlobal
  ? `${content.en.text}\n${content.en.hashtags.join(" ")}`
  : `${content.ko.text}\n${content.ko.hashtags.join(" ")}`;

// 플랫폼별 게시 방법 안내 (실제 API 호출은 Python 클라이언트에서 수행)
const publishInstructions = {
  x: `python -c "from src.api.x_client import post_tweet; print(post_tweet('''${postText.replace(/'/g, "\\'")}'''))"`,
  facebook: `python -c "from src.api.meta_client import post_to_page; print(post_to_page('''${postText.replace(/'/g, "\\'")}'''))"`,
  instagram: "미디어 URL이 필요합니다. meta_client.post_to_instagram(image_url, caption) 직접 호출",
};

log(`게시 명령어: ${publishInstructions[platform] || "지원하지 않는 플랫폼"}`);

// H-08: 게시 결과 가시화
phase("Log");
log("게시 결과를 publish_log 테이블에 기록");
log(`python -c "from src.db.queue import log_publish; log_publish(${queue_id}, '${platform}', 'POST_ID', 'success')"`);

log("══════════════════════════════════════");
log(`✅ 게시 준비 완료`);
log(`플랫폼: ${platform.toUpperCase()}`);
log(`텍스트 (${postText.length}자): ${postText.substring(0, 100)}...`);
log("위 명령어를 터미널에서 실행하여 실제 게시하세요.");
log("══════════════════════════════════════");

return {
  published: false,
  ready_to_publish: true,
  platform,
  post_text: postText,
  command: publishInstructions[platform],
  queue_id,
};
