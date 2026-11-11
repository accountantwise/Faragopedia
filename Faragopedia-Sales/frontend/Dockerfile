FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Ensure the app directory is writeable by any UID (needed for Vite's temp files)
RUN chmod -R 777 /app

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]
