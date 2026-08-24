FROM node:22-bookworm-slim

ARG CODEX_CLI_VERSION=0.147.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates python3 tini \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global "@openai/codex@${CODEX_CLI_VERSION}" \
    && npm cache clean --force

WORKDIR /app
COPY . .

RUN python3 -B build.py \
    && python3 -B -m unittest discover -s tests -t .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NRI_HOST=0.0.0.0

EXPOSE 8080

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/scripts/start-production.sh"]
