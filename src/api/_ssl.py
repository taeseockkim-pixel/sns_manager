"""
SSL 검증 설정 헬퍼.
회사 프록시(SSL 인터셉션) 환경 대응:
  - REQUESTS_CA_BUNDLE: 회사 CA 인증서 .pem 경로 (권장)
  - SSL_VERIFY_DISABLED=true: 검증 완전 비활성화 (개발 임시용)
"""
import os
import warnings


def ssl_verify():
    if os.environ.get("SSL_VERIFY_DISABLED", "").lower() == "true":
        warnings.warn(
            "SSL 검증이 비활성화되어 있습니다 (SSL_VERIFY_DISABLED=true). 운영 환경에서는 사용하지 마세요.",
            stacklevel=2,
        )
        return False
    ca = os.environ.get("REQUESTS_CA_BUNDLE")
    return ca if ca else True
