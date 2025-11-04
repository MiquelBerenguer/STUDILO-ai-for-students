FROM node:18-alpine

WORKDIR /app

# Copiar archivos de dependencias
COPY package*.json ./

# Instalar dependencias (usando npm install en vez de npm ci)
RUN npm install --omit=dev

# Copiar el código fuente
COPY . .

EXPOSE 3001

CMD ["node", "server.js"]
