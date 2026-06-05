# PoC 실행 가이드 (Runbook)

> **담당자**: taeseock.kim@cimon.com | **대상 채널**: X (Twitter)

## 사전 준비

### 1. 환경 설정
```bash
cd D:\업무\agent\sns_management
cp config/.env.example config/.env
# .env 파일에 API 키 입력
```

### 2. 의존성 설치
```bash
pip install requests requests-oauthlib python-dotenv
```

### 3. DB 초기화
```bash
python src/db/queue.py
```

---

## 워크플로우 실행 순서

### Day 1-2: 플랫폼 매트릭스 생성
```bash
claude --workflow .claude/workflows/01_research_platforms.js
# 결과를 deliverables/platform_matrix.md에 복사
```

### Day 4: 톤매뉴얼 생성
```bash
claude --workflow .claude/workflows/02_tone_manual.js
# 결과를 deliverables/tone_manual.md에 복사
```

### Day 6-7: 콘텐츠 생성 테스트
```bash
# 주제를 args로 전달
claude --workflow .claude/workflows/03_generate_content.js \
  --args '{"topic": "CIMON 스마트팩토리 솔루션 소개", "platform": "x"}'
```

### Day 7: 브랜드 안전 검사
```bash
# 03 출력 결과를 args로 전달
claude --workflow .claude/workflows/04_brand_safety.js \
  --args '<03번 출력 JSON>'
```

### Day 8-9: 승인 게이트
```bash
# 04 출력 결과를 args로 전달
claude --workflow .claude/workflows/05_approval_gate.js \
  --args '<04번 출력 JSON>'

# 대기 목록 확인
python src/db/queue.py list

# 승인 (H-01: 사람이 직접 실행)
python src/db/queue.py approve 1

# 반려
python src/db/queue.py reject 1 "톤이 너무 홍보성임"
```

### Day 10: 게시
```bash
# 05 출력 결과를 args로 전달 (approved: true인 경우만)
claude --workflow .claude/workflows/06_publish.js \
  --args '<05번 출력 JSON>'
```

---

## 하네스 규칙 요약 (H-01~H-05)

| 규칙 | 내용 |
|------|------|
| **H-01** | approved: true 없이는 절대 게시 불가 |
| **H-02** | 모든 생성 에이전트는 CONTENT_SCHEMA 사용 |
| **H-03** | brand_safety_score < 80이면 자동 반려 |
| **H-04** | API 실패 시 재시도 없이 즉시 알림 |
| **H-05** | X, Meta, LinkedIn 에이전트 독립 실행 |

---

## 긴급 대응

### 잘못된 게시물 삭제
```python
from src.api.x_client import delete_tweet
delete_tweet("TWEET_ID")
```

### 모니터링 시작
```bash
python src/monitor/comment_monitor.py
```
