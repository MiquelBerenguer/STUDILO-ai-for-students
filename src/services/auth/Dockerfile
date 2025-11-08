FROM node:18-alpine

ENV NODE_ENV=production

WORKDIR /app

COPY --chown=node:node package*.json ./

RUN npm install --omit=dev && npm cache clean --force

COPY --chown=node:node . .

# 🔒 FIX CRÍTICO R#10
USER node

EXPOSE 3001

CMD ["node", "server.js"]