# Immutable production image: Node serves Next.js and supervises the colocated FastAPI process.
FROM nikolaik/python-nodejs:python3.11-nodejs22

WORKDIR /app

COPY package.json ./
RUN npm install

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
CMD ["npm", "run", "start"]
