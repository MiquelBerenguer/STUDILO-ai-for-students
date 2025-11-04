FROM node:18-alpine

WORKDIR /app

# Copiar archivos de dependencias
COPY package.json ./

# Instalar dependencias
RUN npm install --omit=dev

# Copiar el código fuente
COPY . .

EXPOSE 3000

# Usar el nombre correcto del archivo
CMD ["node", "serverapi.js"]
