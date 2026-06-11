FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# config/.env는 .gitignore에 포함 — 빈 파일로 생성 (실제 값은 HF Space 시크릿으로 주입)
RUN mkdir -p config && echo "" > config/.env

EXPOSE 7860

ENV PORT=7860
ENV HOST=0.0.0.0

CMD ["python", "main.py"]
