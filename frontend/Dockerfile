# cfo-web (dev server). Owner: Dev 2 / Dev 3.
FROM node:20-slim
WORKDIR /srv
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--host"]
