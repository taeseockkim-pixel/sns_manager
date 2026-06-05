// H-06: meta 블록 필수
export const meta = {
  name: "generate-content",
  description: "주제 입력 → 영문/국문 콘텐츠 병렬 생성 (CONTENT_SCHEMA 강제)",
  phases: [
    { title: "Generate", detail: "영문·국문 콘텐츠 병렬 생성" },
    { title: "Validate", detail: "글자수·형식 검증" },
  ],
};

// H-02: CONTENT_SCHEMA 강제 적용
const { CONTENT_SCHEMA } = require("../../src/schemas/content_schema");

// args로 주제 입력 받음: { topic, platform, scheduled_at }
const { topic, platform = "x", scheduled_at } = args || {};

if (!topic) {
  throw new Error("topic이 필요합니다. args: { topic, platform, scheduled_at }");
}

const PLATFORM_LIMITS = {
  x: 280,
  facebook: 63206,
  instagram: 2200,
  linkedin: 3000,
};

const charLimit = PLATFORM_LIMITS[platform] || 280;

// H-07: 영문/국문 병렬 생성
phase("Generate");
log(`주제 "${topic}" — ${platform} 영문/국문 콘텐츠 병렬 생성`);

const [koContent, enContent] = await parallel([
  () => agent(
    `당신은 CIMON(산업 자동화·스마트팩토리 B2B 기술 기업, IPO 준비 단계) SNS 담당자입니다.

    아래 주제로 ${platform} 국문 게시물을 작성하세요.

    주제: ${topic}
    플랫폼: ${platform}
    글자 제한: ${charLimit}자 이내

    CIMON 톤매뉴얼 준수사항:
    - 전문적이고 신뢰감 있는 어조
    - 실적·매출·상장 일정 언급 금지 (IPO 규정)
    - "세계 최고", "업계 1위" 등 검증 불가 표현 금지
    - 적절한 해시태그 3-5개

    JSON 형식으로 반환:
    { "text": "게시물 내용", "hashtags": ["#해시태그1", "#해시태그2"] }`,
    {
      label: "generate:ko",
      phase: "Generate",
      schema: {
        type: "object",
        required: ["text", "hashtags"],
        properties: {
          text: { type: "string" },
          hashtags: { type: "array", items: { type: "string" } },
        },
      },
    }
  ),
  () => agent(
    `You are a social media manager for CIMON (B2B industrial automation & smart factory tech company, preparing for IPO).

    Write an English ${platform} post for the following topic.

    Topic: ${topic}
    Platform: ${platform}
    Character limit: ${charLimit} characters

    CIMON tone guidelines:
    - Professional, trustworthy, innovative tone
    - NO mention of financial results, revenue, IPO timeline (regulatory compliance)
    - NO unverifiable claims like "world's best", "industry leader"
    - 3-5 relevant hashtags

    Return JSON:
    { "text": "post content", "hashtags": ["#hashtag1", "#hashtag2"] }`,
    {
      label: "generate:en",
      phase: "Generate",
      schema: {
        type: "object",
        required: ["text", "hashtags"],
        properties: {
          text: { type: "string" },
          hashtags: { type: "array", items: { type: "string" } },
        },
      },
    }
  ),
]);

log(`국문 ${koContent.text.length}자, 영문 ${enContent.text.length}자 생성 완료`);

// H-08: 검증 단계 가시화
phase("Validate");

const content = {
  platform,
  topic,
  ko: koContent,
  en: enContent,
  scheduled_at: scheduled_at || null,
  brand_safety_score: 0,  // 04_brand_safety.js에서 설정
  approved: false,
};

// 글자수 초과 경고
if (koContent.text.length > charLimit) {
  log(`⚠️ 국문 글자수 초과: ${koContent.text.length}자 (제한: ${charLimit}자)`);
}
if (enContent.text.length > charLimit) {
  log(`⚠️ 영문 글자수 초과: ${enContent.text.length}자 (제한: ${charLimit}자)`);
}

log("콘텐츠 생성 완료 → 04_brand_safety.js 실행 필요");

return content;
