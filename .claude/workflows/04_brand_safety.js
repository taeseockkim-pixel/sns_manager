// H-06: meta 블록 필수
export const meta = {
  name: "brand-safety",
  description: "H-03: 게시 전 adversarial 브랜드 안전 검사 — score < 80 자동 반려",
  phases: [
    { title: "Check", detail: "IPO 민감 키워드·법적 리스크·브랜드 일관성 adversarial 검토" },
    { title: "Score", detail: "안전 점수 산정 및 게이트 판정" },
  ],
};

// H-02: BRAND_SAFETY_SCHEMA 강제 적용
const { BRAND_SAFETY_SCHEMA } = require("../../src/schemas/content_schema");

// args: 03_generate_content.js 반환 content 객체
const content = args;

if (!content || !content.ko || !content.en) {
  throw new Error("content 객체가 필요합니다. 03_generate_content.js 출력을 args로 전달하세요.");
}

const IPO_KEYWORDS = [
  "실적", "매출", "영업이익", "순이익", "적자", "흑자", "주가", "상장", "공모가",
  "증자", "유증", "insider", "내부자", "미공개", "기업가치", "valuation",
  "revenue", "profit", "earnings", "IPO price", "listing date",
];

phase("Check");
log("Adversarial 브랜드 안전 검사 시작 (3개 독립 에이전트)");

// Adversarial 패턴: 3개 독립 에이전트가 각자 다른 관점에서 검토
const [legalCheck, toneCheck, ipoCheck] = await parallel([
  () => agent(
    `당신은 기업 법무팀 검토관입니다. 아래 SNS 게시물을 법적 관점에서 adversarial하게 검토하세요.
    문제를 찾아내는 것이 목표입니다. 확실하지 않으면 위험으로 판정하세요.

    국문: ${content.ko.text}
    영문: ${content.en.text}

    검토 항목:
    - 허위·과장 광고 가능성
    - 명예훼손 리스크
    - 저작권 침해 소지
    - 금융 규제 위반 가능성 (IPO 준비 기업)
    - 공정거래법 위반 소지

    score: 0(매우 위험)~100(완전 안전)
    passed: score >= 80
    issues: 발견된 문제 목록 (없으면 빈 배열)`,
    {
      label: "check:legal",
      phase: "Check",
      schema: BRAND_SAFETY_SCHEMA,
    }
  ),
  () => agent(
    `당신은 브랜드 마케팅 전략가입니다. CIMON의 브랜드 가이드라인 관점에서 아래 SNS 게시물을 adversarial하게 검토하세요.
    브랜드 훼손 가능성을 찾아내는 것이 목표입니다.

    국문: ${content.ko.text}
    영문: ${content.en.text}

    CIMON 브랜드 원칙: 전문성, 신뢰, 혁신 (B2B 기술 기업)

    검토 항목:
    - 톤&보이스 일관성 (B2B 전문성 유지 여부)
    - 브랜드 이미지 훼손 가능성
    - 오해 유발 표현
    - 경쟁사 비방 소지
    - 문화적 민감도 (글로벌 채널)

    score: 0~100, passed: score >= 80`,
    {
      label: "check:tone",
      phase: "Check",
      schema: BRAND_SAFETY_SCHEMA,
    }
  ),
  () => agent(
    `당신은 IPO 컴플라이언스 전문가입니다. 상장 준비 기업의 SNS 게시물로서 규제 리스크를 adversarial하게 검토하세요.
    의심스러우면 위험으로 판정하세요.

    국문: ${content.ko.text}
    영문: ${content.en.text}

    IPO 민감 키워드: ${JSON.stringify(IPO_KEYWORDS)}

    검토 항목:
    - 미공개 중요정보 암시 여부
    - 주가 영향 가능한 표현
    - 금감원 규정 위반 가능성
    - 공시 의무 위반 소지
    - 투자자 오인 유발 가능성

    score: 0~100, passed: score >= 80
    ipo_risk_flags: IPO 관련 위험 항목`,
    {
      label: "check:ipo",
      phase: "Check",
      schema: BRAND_SAFETY_SCHEMA,
    }
  ),
]);

// H-08: 점수 산정 가시화
phase("Score");
const checks = [legalCheck, toneCheck, ipoCheck].filter(Boolean);
const avgScore = checks.reduce((sum, c) => sum + c.score, 0) / checks.length;
const allIssues = checks.flatMap((c) => c.issues || []);
const ipoFlags = checks.flatMap((c) => c.ipo_risk_flags || []);

// H-03: score < 80이면 자동 반려
const passed = avgScore >= 80 && checks.every((c) => c.passed);

log(`브랜드 안전 점수: ${avgScore.toFixed(1)} / 100 → ${passed ? "✅ 통과" : "❌ 반려"}`);

if (!passed) {
  log(`반려 이유: ${allIssues.join(", ")}`);
  if (ipoFlags.length > 0) {
    log(`IPO 리스크 플래그: ${ipoFlags.join(", ")}`);
  }
}

const result = {
  ...content,
  brand_safety_score: Math.round(avgScore),
  brand_safety_passed: passed,
  brand_safety_issues: allIssues,
  ipo_risk_flags: ipoFlags,
  approved: false,  // H-01: 사람이 승인해야 true로 변경
};

if (!passed) {
  result.rejection_reason = `브랜드 안전 점수 부족 (${avgScore.toFixed(1)}/80). 문제: ${allIssues.slice(0, 3).join("; ")}`;
}

return result;
