# ---- 构建阶段 ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
# 用国内 npm 镜像，避免境外超时
RUN npm config set registry https://registry.npmmirror.com && npm install
COPY . .
RUN npm run build

# ---- 运行阶段（nginx 托管静态文件 + 反代 /api）----
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
