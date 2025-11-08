FROM node:18-alpine

# Buena práctica: definir entorno de producción explícitamente
ENV NODE_ENV=production

WORKDIR /app

# Cambiamos el propietario de los archivos AL COPIARLOS.
# Esto evita tener que ejecutar 'chown -R' después, que duplica capas y aumenta el tamaño de la imagen.
COPY --chown=node:node package*.json ./

# Instalamos dependencias y limpiamos la caché en la misma capa
RUN npm install --omit=dev && npm cache clean --force

# Copiamos el resto del código con los permisos correctos
COPY --chown=node:node . .

# 🔒 FIX CRÍTICO R#10: Cambiar a usuario sin privilegios
USER node

EXPOSE 3000

CMD ["node", "serverapi.js"]