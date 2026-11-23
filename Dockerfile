# Immutable production image: Node serves Next.js and supervises the colocated FastAPI process.
FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN python3 -m pip install --no-cache-dir --target backend/.pylibs -r backend/requirements.txt
RUN npm run build

RUN useradd --system --uid 10001 --create-home flowforge \
    && chown -R flowforge:flowforge /app
USER flowforge

ENV NODE_ENV=production
ENV APP_ENV=production
ENV COOKIE_SECURE=1
ENV FF_SEED=0

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["npm", "run", "start"]
