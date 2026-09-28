FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends dnsutils curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY agent.py .
ENTRYPOINT ["python", "-u", "agent.py"]
