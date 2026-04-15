# 常用命令：安装依赖、启动后端/前端（需本机已安装 Python 3.11+ 与 Node18+）
PYTHON ?= python3.11

.PHONY: install install-backend install-frontend dev-backend dev-frontend upload-api upload-binary-api

install: install-backend install-frontend

install-backend:
	cd backend && (test -d .venv || $(PYTHON) -m venv .venv) && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

install-frontend:
	cd frontend && npm install

dev-backend:
	cd backend && PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

# 正确调用上传接口（需 Vite 5173 与后端 8000 已启动）。勿用浏览器「复制为 cURL」里带 --data-raw 的空正文命令。
# 用法：make upload-api FILE=/绝对路径/你的.pdf
upload-api:
	@test -n "$(FILE)" || (echo '用法: make upload-api FILE=/path/to/文档.pdf'; exit 1)
	curl -sS -F "file=@$(FILE)" "http://localhost:5173/api/upload?replace=true"

# 原始 body 上传（无需 multipart），filename 用查询参数指定（文件名含 & 时请改用 curl 手写 URL）
upload-binary-api:
	@test -n "$(FILE)" || (echo '用法: make upload-binary-api FILE=/path/to/文档.pdf'; exit 1)
	curl -sS --data-binary "@$(FILE)" "http://localhost:5173/api/upload/binary?filename=$(notdir $(FILE))&replace=true"
