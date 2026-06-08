#!/usr/bin/env bash
# 一键部署脚本（轻量/SQLite，适配 2G 内存服务器）
# 用法（在 /opt/qiwei 目录）：NEXTSLS_TOKEN=xxx WX_ARCHIVE_SECRET=yyy bash deploy.sh
set -e
cd "$(dirname "$0")"

echo "==> 1/4 检查 swap（2G内存build需要）"
if [ "$(free -m | awk '/Swap/{print $2}')" = "0" ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "    已添加 2G swap"
else
  echo "    已有 swap，跳过"
fi

echo "==> 2/4 生成 .env"
if [ ! -f .env ]; then
  cat > .env <<EOF
SECRET_KEY=$(openssl rand -hex 32)
DEMO_MODE=${DEMO_MODE:-true}
HTTP_PORT=${HTTP_PORT:-8090}
CORS_ORIGINS=*
WX_CORP_ID=${WX_CORP_ID:-}
NEXTSLS_TOKEN=${NEXTSLS_TOKEN:-}
NEXTSLS_BASE_URL=https://zjyxgj.nextsls.com/mpapi/v5
DOUBAO_API_KEY=${DOUBAO_API_KEY:-}
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-pro-32k
WX_ARCHIVE_SECRET=${WX_ARCHIVE_SECRET:-}
EOF
  echo "    .env 已生成"
else
  echo "    .env 已存在，保留不动"
fi

echo "==> 3/4 构建并启动容器（首次较慢，请耐心等）"
mkdir -p data
docker compose -f docker-compose.lite.yml up -d --build

echo "==> 4/4 状态"
docker compose -f docker-compose.lite.yml ps
IP=$(curl -s --max-time 5 ifconfig.me || echo "你的公网IP")
echo ""
echo "============================================"
echo "  部署完成！浏览器访问： http://$IP:${HTTP_PORT:-8090}"
echo "  (需在腾讯云安全组放行 ${HTTP_PORT:-8090} 端口)"
echo "============================================"
