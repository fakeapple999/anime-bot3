FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl fzf grep sed ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/pystardust/ani-cli /tmp/ani-cli && \
    cp /tmp/ani-cli/ani-cli /usr/local/bin/ani-cli && \
    chmod +x /usr/local/bin/ani-cli && \
    rm -rf /tmp/ani-cli

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
