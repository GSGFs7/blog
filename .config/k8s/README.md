# 使用 k3s 部署的配置

## 开发环境

需要用到 `containers/*.Dockerfile` 这些文件来构建镜像

步骤:

0. 安装并配置 k3s

1. 配置环境变量

    ```bash
    # 复制 .env 并填写相关内容
    cp .env.example .env

    # 从 .env 文件创建 secret
    kubectl create secret generic blog-secrets --from-env-file=.env -n blog
    ```

2. 构建镜像并导入到 k3s

    ```bash
    ./scripts/k3s-build.sh
    ```

    这将得到这些镜像:
    - `localhost/blog-app:latest`
    - `localhost/blog-backup:latest`
    - `localhost/blog-model-downloader:latest`
    - `localhost/blog-pgbouncer:latest`

3. 部署到 k3s

    ```bash
    ./scripts/k3s-deploy.sh
    # 或者使用开发环境配置
    ./scripts/k3s-deploy.sh dev
    ```

    Django 和 Celery 会通过 `blog-pgbouncer:6432` 访问数据库

## 生产环境

生产环境通过 Woodpecker CI + Argo CD 来实现自动化 CI/CD pipeline

具体配置见 `.woodpecker/` 和 `scripts/argo-app-config.sh`

`blog-secret` 这个 k8s secret 可以使用 `scripts/k3s-sync-secrets.sh` 自动生成

---

其他:

生产环境需要安装 cert-manager 来管理 TLS 证书:

```bash
# 安装 cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.19.4/cert-manager.yaml

# 部署 ClusterIssuer（用于 Let's Encrypt 证书）
envsubst < .config/k8s/cluster-issuer.yaml | kubectl apply -f -
```

关于私有 Registry 镜像的拉取, 需要在 k3s 节点上创建 `/etc/rancher/k3s/registries.yaml`, 并进行配置
