// H-06: meta 블록 필수
export const meta = {
  name: "research-platforms",
  description: "X·Facebook·Instagram·LinkedIn API 정책 매트릭스 자동 생성",
  phases: [
    { title: "Research", detail: "각 플랫폼 API 정책·비용·심사 기간 병렬 조사" },
    { title: "Compile", detail: "매트릭스 문서 생성" },
  ],
};

const { PLATFORM_MATRIX_SCHEMA } = require("../../src/schemas/content_schema");

const PLATFORMS = ["X (Twitter) API v2", "Facebook Graph API", "Instagram Graph API", "LinkedIn API"];

// H-07: 병렬 조사
phase("Research");
log("4개 플랫폼 API 정책 병렬 조사 시작");

const results = await parallel(
  PLATFORMS.map((platform) => () =>
    agent(
      `당신은 소셜 미디어 API 전문가입니다. ${platform}에 대해 아래 항목을 조사하고 정확히 JSON으로 반환하세요.

      - can_post: 프로그래밍으로 게시물 작성 가능 여부 (boolean)
      - rate_limit: 게시 횟수 제한 (문자열, 예: "월 1,500건 / Basic $100/월")
      - approval_days: 앱 심사 소요일 (문자열, 예: "1-3일")
      - cost: 비용 (문자열, 예: "$100/월 Basic tier")
      - gotchas: 자동화 시 주의사항 3가지 이상 (문자열 배열)
      - recommended_tier: 2주 PoC에 권장하는 플랫폼 티어 (문자열)
      - ipo_considerations: IPO 준비 기업이 특별히 주의할 사항 2가지 (문자열 배열)

      플랫폼: ${platform}`,
      {
        label: `research:${platform}`,
        phase: "Research",
        schema: {
          type: "object",
          required: ["name", "api_name", "can_post", "rate_limit", "approval_days", "cost", "gotchas", "recommended_tier"],
          properties: {
            name: { type: "string" },
            api_name: { type: "string" },
            can_post: { type: "boolean" },
            rate_limit: { type: "string" },
            approval_days: { type: "string" },
            cost: { type: "string" },
            gotchas: { type: "array", items: { type: "string" } },
            recommended_tier: { type: "string" },
            ipo_considerations: { type: "array", items: { type: "string" } },
          },
        },
      }
    )
  )
);

const platforms = results.filter(Boolean);
log(`${platforms.length}개 플랫폼 조사 완료`);

// H-08: 진행상황 가시화
phase("Compile");
log("플랫폼 매트릭스 문서 생성 중");

const matrixDoc = await agent(
  `아래 플랫폼 데이터를 바탕으로 한국어 마크다운 매트릭스 문서를 작성하세요.

  요구사항:
  - 제목: "플랫폼별 API·정책 매트릭스"
  - 작성일, 담당자(taeseock.kim@cimon.com) 포함
  - 비교표 (플랫폼 | API 비용 | 심사기간 | 월 게시한도 | 자동화 가능여부 | PoC 권장도)
  - 각 플랫폼별 상세 섹션 (주의사항, IPO 고려사항 포함)
  - IPO 준비 기업 권고사항 섹션
  - PoC 채널 선정 권고: X API Basic을 1순위로 권장하는 이유 설명
  - 즉시 신청 필요한 액션 아이템 체크리스트

  데이터:
  ${JSON.stringify(platforms, null, 2)}`,
  { label: "compile:matrix-doc", phase: "Compile" }
);

log("platform_matrix.md 저장 완료");

return { platforms, matrixDoc };
