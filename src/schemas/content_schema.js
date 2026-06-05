// H-02: 모든 콘텐츠 생성 에이전트가 사용하는 공통 스키마

const CONTENT_SCHEMA = {
  type: "object",
  required: ["platform", "ko", "en", "brand_safety_score", "approved"],
  properties: {
    platform: { type: "string", enum: ["x", "facebook", "instagram", "linkedin"] },
    topic: { type: "string" },
    ko: {
      type: "object",
      required: ["text", "hashtags"],
      properties: {
        text: { type: "string", maxLength: 280 },
        hashtags: { type: "array", items: { type: "string" } }
      }
    },
    en: {
      type: "object",
      required: ["text", "hashtags"],
      properties: {
        text: { type: "string", maxLength: 280 },
        hashtags: { type: "array", items: { type: "string" } }
      }
    },
    scheduled_at: { type: "string", format: "date-time" },
    brand_safety_score: { type: "number", minimum: 0, maximum: 100 },
    approved: { type: "boolean", default: false },
    rejection_reason: { type: "string" }
  }
};

const BRAND_SAFETY_SCHEMA = {
  type: "object",
  required: ["score", "passed", "issues", "ipo_risk_flags"],
  properties: {
    score: { type: "number", minimum: 0, maximum: 100 },
    passed: { type: "boolean" },
    issues: { type: "array", items: { type: "string" } },
    ipo_risk_flags: { type: "array", items: { type: "string" } },
    recommendation: { type: "string" }
  }
};

const PLATFORM_MATRIX_SCHEMA = {
  type: "object",
  required: ["platforms"],
  properties: {
    platforms: {
      type: "array",
      items: {
        type: "object",
        required: ["name", "api_name", "can_post", "rate_limit", "approval_days", "cost", "gotchas"],
        properties: {
          name: { type: "string" },
          api_name: { type: "string" },
          can_post: { type: "boolean" },
          rate_limit: { type: "string" },
          approval_days: { type: "string" },
          cost: { type: "string" },
          gotchas: { type: "array", items: { type: "string" } },
          recommended_tier: { type: "string" }
        }
      }
    }
  }
};

module.exports = { CONTENT_SCHEMA, BRAND_SAFETY_SCHEMA, PLATFORM_MATRIX_SCHEMA };
