# GSGFs-blog

[![status-badge](https://woodpecker.gsgfs.sh/api/badges/2/status.svg)](https://woodpecker.gsgfs.sh/repos/2)

使用 `Django` 构建的个人网站.

## 运行

`python`版本: `3.14`, 启动后访问 `localhost:8000`.

1. 安装所需依赖

    ```bash
    uv sync
    pnpm i
    ```

2. 激活 Python 虚拟环境 (以 `Linux` 为例)

    ```bash
    source .venv/bin/activate
    ```

3. 将 `.env.example` 复制一份为 `.env` 并填写需要的环境变量

    尖括号中的内容是必填项, 可以使用 `openssl rand -hex 40` 生成所需的随机字符

4. 启动数据库和 Redis

    ```bash
    docker compose up -d "blog-postgres" "blog-redis"
    ```

5. (可选) 由于搜索功能依赖向量化处理, 需要下载用于生成向量的嵌入模型

    ```bash
    ./scripts/download-model.py
    ```

6. 迁移数据库

    ```bash
    ./manage.py migrate
    ```

7. 创建一个管理员用户 (用于登陆后台)

    ```bash
    ./manage.py createsuperuser
    ```

8. 运行开发服务器

    ```bash
    # 运行 vite
    ./manage.py vite # 或者 pnpm run dev
    # 新开一个终端, 运行 Django ASGI 开发服务器
    ./manage.py runasgi
    ```

## 目录

```text
.
├── accounts/           # 认证与账号管理 app
├── api/                # 后端 app
│   ├── backends/       # 外部服务后端
│   ├── management/     # 管理命令
│   ├── markdown/       # Markdown 渲染集成
│   ├── middleware/     # 中间件
│   ├── models/         # ORM 模型
│   ├── routers/        # Ninja 路由
│   ├── schemas/        # Schema 定义
│   ├── services/       # 业务服务
│   └── tests/          # 测试
├── blog/               # Django 配置
├── core/               # 共享内容
├── media_service/      # 媒体 app
├── native/             # 原生扩展
│   ├── crc64nvme/      # CRC64-NVMe (C)
│   └── markdown/       # Markdown 渲染器 (Rust)
├── web/                # 前端 app
│   ├── views/          # 页面视图
│   ├── templates/      # 页面模板
│   ├── templatetags/   # 模板标签
│   ├── typescript/     # 前端源码
│   ├── e2e/            # e2e测试
│   └── tests/          # 视图测试
├── templates/          # 共享与 Admin 模板
├── scripts/            # 运维与构建脚本
├── compose.yml         # 本地容器编排
└── manage.py           # Django CLI
```

## 接口文档

`django-ninja` 自带 `swagger-UI`, 启动后访问 `/api/docs`

## 开源协议

MIT
