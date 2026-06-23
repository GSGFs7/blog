# GSGFs-blog

[![status-badge](https://woodpecker.gsgfs.sh/api/badges/1/status.svg)](https://woodpecker.gsgfs.sh/repos/1) [![Quality Gate Status](https://sonarqube.gsgfs.sh/api/project_badges/measure?project=blog&metric=alert_status&token=sqb_0d1b1441c744c4776436ce237e351a089110a9fa)](https://sonarqube.gsgfs.sh/dashboard?id=blog) [![Maintainability Rating](https://sonarqube.gsgfs.sh/api/project_badges/measure?project=blog&metric=software_quality_maintainability_rating&token=sqb_0d1b1441c744c4776436ce237e351a089110a9fa)](https://sonarqube.gsgfs.sh/dashboard?id=blog) [![Technical Debt](https://sonarqube.gsgfs.sh/api/project_badges/measure?project=blog&metric=software_quality_maintainability_remediation_effort&token=sqb_0d1b1441c744c4776436ce237e351a089110a9fa)](https://sonarqube.gsgfs.sh/dashboard?id=blog)

使用 `Django` 构建的个人网站. (新前端正在重构中)

## 运行

> [!NOTE]  
> Django 自带的后台在 `/not-admin` 而不是 `/admin`

`python`版本: `3.14`, 推荐使用 uv 作为包管理器

_Windows 用户在运行 `./xxx.py` 这类命令时可能需要在前面加上 `python`, 例如 `./manage.py runserver`
应该改为 `python ./manage.py runserver`_

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

5. 由于搜索功能依赖向量化处理, 需要下载用于生成向量的嵌入模型

    ```bash
    ./scripts/download-model.py
    ```

6. 迁移数据库

    ```bash
    ./manage.py makemigrations && ./manage.py migrate
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

## 可选依赖

- **ExifTool**: 用于清理上传图片的 EXIF 元数据. 如果系统中安装了 `exiftool`, 后端会自动调用它来处理图片以保护隐私. 如果没有,
  则使用 PIL 对图片进行重编码来去除 EXIF 信息.
    - Arch Linux: `sudo pacman -S perl-image-exiftool`
    - Debian/Ubuntu: `sudo apt install libimage-exiftool-perl`

## 目录

```text
.
├── api/            # Django app
│   ├── backends/   # Django 后端
│   ├── migrations/ # 数据库迁移
│   ├── routers/    # 路由
│   ├── tests/      # 测试
│   ├── admin.py    # Django admin 设置
│   ├── apps.py     # Django app 设置
│   ├── models.py   # Django ORM
│   ├── schemas.py  # schema 定义
│   ├── signals.py  # Django 信号处理
│   ├── task.py     # celery 任务
│   └── urls.py     # URL 汇总
├── blog/           # Django project
├── scripts/        # 辅助脚本
├── templates/      # Django 模板
└── manage.py       # Django cli
```

## 接口文档

`django-ninja` 自带 `swagger-UI`, 启动后访问 `/api/docs`

## 小工具

统一放在 `scripts` 文件夹中

- `backup-db.sh`: 一个简单备份数据库脚本(配合`cron`使用)
- `download-model.py`: 下载模型
- `export.sh`: 导出 docker 镜像
- `upload.py`: 上传文件至 R2 对象存储
- `regenerate_embeddings.py`: 重新生成文章向量

## 开源协议

MIT
