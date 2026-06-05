// H-06: meta 블록 필수
export const meta = {
  name: "tone-manual",
  description: "CIMON사 SNS 콘텐츠 톤매뉴얼 생성 (영문/국문 병렬)",
  phases: [
    { title: "Analysis", detail: "회사 특성·IPO 맥락 분석" },
    { title: "Draft", detail: "영문/국문 톤매뉴얼 병렬 초안 작성" },
    { title: "Compile", detail: "최종 톤매뉴얼 문서 통합" },
  ],
};

const COMPANY_CONTEXT = `
회사명: CIMON (사이몬)
업종: B2B 기술 기업 (산업 자동화, 스마트팩토리 분야)
현황: IPO 준비 단계
SNS 목표:
  - 투자자·파트너 대상 회사 인지도 강화
  - 영문 글로벌 채널 + 국문 국내 채널 동시 운영
  - 마케팅 팀 공수 절감
주요 타겟:
  - 국문: 국내 투자자, 제조업 파트너, 채용 지원자
  - 영문: 글로벌 파트너, 해외 투자자, 기술 미디어
`;

const IPO_RESTRICTIONS = `
IPO 준비 기업 SNS 금지 사항:
- 실적/매출 수치 직접 언급 금지 (미공개 정보 규정)
- 상장 일정·공모가 관련 발언 금지
- 경쟁사 직접 비교 금지
- 과장된 성장 전망 표현 금지
- "세계 최고", "업계 1위" 등 검증 불가 주장 금지
`;

phase("Analysis");
log("회사 맥락 분석 및 IPO 제약 사항 정리");

const contextAnalysis = await agent(
  `아래 회사 정보를 바탕으로 SNS 톤·보이스 전략을 분석하세요.

  회사 정보:
  ${COMPANY_CONTEXT}

  IPO 제약:
  ${IPO_RESTRICTIONS}

  분석 항목:
  1. 브랜드 퍼소나 (3가지 핵심 특성)
  2. 절대 피해야 할 표현 10가지
  3. 권장 표현 패턴 10가지
  4. 플랫폼별 톤 차이 (X vs LinkedIn vs Facebook)
  5. IPO 민감 키워드 리스트 (20개 이상)`,
  {
    label: "analysis:context",
    phase: "Analysis",
    schema: {
      type: "object",
      required: ["brand_persona", "avoid_expressions", "recommended_patterns", "platform_tones", "ipo_keywords"],
      properties: {
        brand_persona: { type: "array", items: { type: "string" }, minItems: 3 },
        avoid_expressions: { type: "array", items: { type: "string" }, minItems: 10 },
        recommended_patterns: { type: "array", items: { type: "string" }, minItems: 10 },
        platform_tones: {
          type: "object",
          properties: {
            x: { type: "string" },
            linkedin: { type: "string" },
            facebook: { type: "string" },
            instagram: { type: "string" },
          },
        },
        ipo_keywords: { type: "array", items: { type: "string" }, minItems: 20 },
      },
    },
  }
);

log(`브랜드 퍼소나 ${contextAnalysis.brand_persona.length}개, IPO 민감 키워드 ${contextAnalysis.ipo_keywords.length}개 도출`);

// H-07: 영문/국문 병렬 생성
phase("Draft");
log("영문·국문 톤매뉴얼 초안 병렬 작성");

const [koManual, enManual] = await parallel([
  () => agent(
    `아래 분석 결과를 바탕으로 CIMON 국문 SNS 톤매뉴얼 초안을 작성하세요.

    대상 채널: X(국문 계정), Facebook, Instagram
    대상 독자: 국내 투자자, 제조업 파트너, 채용 지원자

    분석 데이터: ${JSON.stringify(contextAnalysis)}

    포함 내용:
    1. 브랜드 보이스 가이드 (3가지 핵심 특성 설명)
    2. 금지 표현 목록 (예시 포함)
    3. 권장 표현 패턴 (예시 포함)
    4. 플랫폼별 게시물 예시 (X 3개, Facebook 2개, Instagram 2개)
    5. 이모지 사용 가이드
    6. 해시태그 전략 (국문)
    7. IPO 준비 기간 특별 가이드라인`,
    { label: "draft:ko-manual", phase: "Draft" }
  ),
  () => agent(
    `아래 분석 결과를 바탕으로 CIMON English SNS tone manual draft를 write.

    Target channels: X (English account), LinkedIn
    Target audience: Global partners, overseas investors, tech media

    Analysis data: ${JSON.stringify(contextAnalysis)}

    Include:
    1. Brand voice guide (3 core characteristics with descriptions)
    2. Prohibited expressions (with examples)
    3. Recommended expression patterns (with examples)
    4. Sample posts per platform (X: 3, LinkedIn: 3)
    5. Hashtag strategy (English)
    6. IPO period special guidelines
    7. Cultural localization notes for global audience`,
    { label: "draft:en-manual", phase: "Draft" }
  ),
]);

log("영문·국문 초안 완료");

phase("Compile");
log("최종 톤매뉴얼 통합 문서 생성");

const finalManual = await agent(
  `아래 국문·영문 톤매뉴얼 초안을 하나의 마크다운 문서로 통합하세요.

  문서 구조:
  # CIMON SNS 콘텐츠 톤매뉴얼 v1.0
  - 작성일, 담당자 기재
  ## 1. 브랜드 정체성
  ## 2. 국문 채널 가이드
  ## 3. English Channel Guide
  ## 4. IPO 준비 기간 특별 규정 (가장 중요 섹션)
  ## 5. 브랜드 안전 체크리스트 (게시 전 확인 사항)
  ## 6. 콘텐츠 예시 모음

  국문 초안: ${koManual}
  영문 초안: ${enManual}
  IPO 민감 키워드: ${JSON.stringify(contextAnalysis.ipo_keywords)}`,
  { label: "compile:final-manual", phase: "Compile" }
);

log("tone_manual.md 생성 완료 — deliverables/ 폴더에 저장 필요");

return { contextAnalysis, koManual, enManual, finalManual };
