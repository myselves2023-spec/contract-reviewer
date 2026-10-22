FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 只复制运行必需的文件：不把 .env、eval/、docs/ 打进镜像
COPY app ./app
COPY data ./data
COPY web ./web
COPY samples ./samples
COPY main.py ./

EXPOSE 8000

# 用 exec 形式，保证 Ctrl+C / 平台下发的 SIGTERM 能直接到达 Python 进程
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
