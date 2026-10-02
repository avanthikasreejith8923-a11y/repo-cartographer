FROM node:20-alpine

WORKDIR /app

# Install dependencies first for Docker caching
COPY package.json ./
RUN npm install

# Copy application source
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Run Vite dev server bound to 0.0.0.0
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
