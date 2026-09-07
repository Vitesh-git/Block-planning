FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173
# Dev server (bound to 0.0.0.0 so it's reachable from the host)
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
