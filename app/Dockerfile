FROM python:3.10-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY . .

RUN mkdir -p storage/audio storage/subtitles storage/video

CMD ["uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "7860"]