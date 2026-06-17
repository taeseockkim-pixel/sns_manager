"""
Vercel 서버리스 환경에서는 APScheduler 사용 불가.
스케줄 작업은 /cron/* HTTP 엔드포인트(src/web/routes/cron.py)로 대체되며
vercel.json의 crons 설정으로 호출된다.
"""
