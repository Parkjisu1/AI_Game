# NewPlay gateway — node-pty 로 docker exec PTY 를 열어 웹소켓으로 중계. docker CLI 필요(docker.sock 마운트).
FROM node:20-bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 make g++ curl ca-certificates gnupg \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update -qq && apt-get install -y -qq --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY server.js ./
EXPOSE 3001
CMD ["node", "server.js"]
