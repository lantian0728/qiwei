FROM python:3.12-slim

WORKDIR /app

# 先装依赖（利用构建缓存）。用国内镜像源，避免境外 PyPI 超时
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 5 \
    -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 再拷代码
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
