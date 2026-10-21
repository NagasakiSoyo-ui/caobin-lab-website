# 曹彬课题组网站 · 医学深蓝版

七栏目研究组网站（首页、研究方向、科研课题、研究成果、研究团队、学习资料、联系与加入），配套中文内容管理后台。前台为现代医学深蓝设计：首页研究布局图、六个研究方向详情页、课题档案、可筛选的成果目录与精选成果详情页（论文原图附出处）。保留已提供的研究内容、49 位成员、成员照片和九份学习资料。

## 两种使用方式

**只看网页**：从 [Releases](https://github.com/NagasakiSoyo-ui/caobin-lab-website/releases) 下载医学深蓝离线包，完整解压，双击 `index.html`。不需要 GitHub 登录或安装软件。

**管理内容**：下载整个仓库源码，安装 Python 3.10 或更高版本，运行下面的服务端。后台需要正在运行的服务，不能在静态离线包中直接修改数据库。GitHub 仓库用于保存源码，GitHub Pages 不能运行本项目后台。

## Windows 启动

完整解压源码后，双击 `start_local.cmd`。

首次启动会创建独立环境、安装依赖、初始化数据库和现有内容，并提示设置管理员用户名和密码。密码输入时不回显，至少 12 位。项目没有预设或共用的管理员密码。

- 前台：`http://127.0.0.1:8771/`
- 后台：`http://127.0.0.1:8771/manage/`

使用期间保留启动窗口，关闭窗口即停止服务。初始化可以重复运行，已有内容和账号不会被重置。

详细操作见 [后台使用说明](docs/后台使用说明.md)。

## 手动安装与启动

```sh
python -m venv .venv
```

Windows 激活 `.venv\Scripts\activate`；macOS/Linux 激活 `source .venv/bin/activate`。然后运行：

```sh
python -m pip install -r requirements.txt
python setup_local.py
waitress-serve --listen=127.0.0.1:8771 --max-request-body-size=60000000 config.wsgi:application
```

启动后使用后台编辑内容。新增条目默认不公开；勾选「在网站公开」并保存后，前台立即显示。后台支持成员分组、照片上传、成果管理、PDF 资料更新、排序、操作记录和离线导出。

## 数据与代码

| 目录 | 用途 |
| --- | --- |
| `catalog/` | 数据模型、后台配置、渲染与导出、测试及迁移 |
| `templates/` | 前台栏目页、详情页及后台界面 |
| `static/` | 前台与后台样式、交互脚本 |
| `seed/` | 初始化内容和素材；`research-publications.json` 与 `figures/` 为首批已核验成果和原图（来源见 `figures/SOURCES.txt`） |
| `data/site.sqlite3` | 唯一的运行时内容数据库，包含账号与操作记录 |
| `data/media/` | 初始素材与新增上传文件 |
| `data/secret.key` | 每个安装实例的独立密钥 |
| `data/backups/` | 私有数据库与素材备份 |
| `exports/` | 导出的前台离线包 |

`data/`、`exports/`、虚拟环境及本机账号说明均被 Git 忽略。复制源码到新电脑会建立新的账号和数据实例；要迁移后台已经修改的内容，需要迁移私有数据库与媒体文件。

替换或删除一条内容不会立即删除原来的媒体文件，以免破坏已有引用与备份。备份包含全部媒体；前台离线导出只包含公开页面实际引用的文件。

## 升级已有安装

先备份（`python manage.py backup_site`），再更新代码并运行：

```sh
python -m pip install -r requirements.txt
python setup_local.py
```

`setup_local.py` 会执行数据库迁移（为研究方向回填固定链接名、新增「科研课题」栏目），并在首次运行时用 `seed_publications` 导入首批成果与原图。导入完成记录保存在数据库中（随备份一起迁移），之后每次启动都不会再改动内容；后台删除或清空的内容不会被恢复。已有账号、人工编辑和公开状态都会保留。

## PubMed 导入

```sh
python manage.py import_pubmed --pmid 38231624
```

结果进入后台「PubMed 候选」待审核，不会自动公开。详见后台使用说明。

## 导出与备份

后台顶部「导出离线网站」可下载当前公开内容。也可运行：

```sh
python manage.py export_site --output exports/caobin-lab-medical-blue.zip
python manage.py backup_site
```

离线包是静态快照，不含后台账号、密钥或数据库。备份则含私有管理数据，切勿放入公开仓库。

恢复备份前先停止服务、备份当前 `data/`，再将可信备份内的 `site.sqlite3` 和 `media/` 恢复到 `data/`。恢复后重新启动。更新代码前同样应先备份，再执行数据库迁移和静态资源收集。

## 验证

```sh
python manage.py check
python manage.py test catalog
python manage.py makemigrations --check --dry-run
```

测试覆盖内容导入、管理员权限、CSRF、登录锁定、上传校验、成员增删改与草稿、编辑冲突、成果链接和 HTML 转义、空数据、离线导出，以及旧数据库迁移、PubMed 重复导入与 PMID/DOI 冲突、草稿与未公开配图零泄漏、详情页与离线链接校验。

## 正式部署

本地启动仅监听回环地址，方便在交付前试用。正式上线需要具有持久磁盘的服务器、HTTPS 和进程管理，不应将 SQLite 数据和上传目录放到临时文件系统。

部署前配置：

- `LAB_PRODUCTION=1`
- `LAB_ALLOWED_HOSTS=实际域名`，多个域名用英文逗号分隔。
- `LAB_DATA_DIR=持久数据目录绝对路径`，可选；默认是仓库下的 `data/`。
- `DJANGO_SECRET_KEY`：可通过服务器环境安全提供；未设置时使用该实例的 `data/secret.key`。

正式模式启用 HTTPS 跳转、安全 Cookie 和 HSTS。Waitress 仍监听 `127.0.0.1`，由同机 Nginx/Caddy 等代理转发。代理必须覆盖客户端传入的转发头，正确设置 `X-Forwarded-Proto` 和 `X-Forwarded-For`；上传限制应至少允许 60 MB。使用以下命令，仅信任同机代理提供的协议和来源信息：

```sh
waitress-serve --listen=127.0.0.1:8771 --trusted-proxy=127.0.0.1 --trusted-proxy-count=1 --trusted-proxy-headers="x-forwarded-proto x-forwarded-for" --max-request-body-size=60000000 config.wsgi:application
```

代理架构改变时应按实际地址和链路调整，不得设置任意代理为可信，也不得直接把本地 HTTP 端口作为公网服务。

上线前执行：

```sh
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

后台入口不出现在前台导航中，并标记为不索引；保护来自服务器端的身份验证、权限及 CSRF 校验。连续五次登录失败暂时锁定 15 分钟。页面上的隐藏入口本身不是安全措施。

参考：[Django 管理后台](https://docs.djangoproject.com/en/5.2/ref/contrib/admin/) · [Django 部署检查](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)。

## 待补内容

完整论文目录（当前为代表性首批）、骨干成员照片及详细介绍仍需由课题组补充，可直接在后台录入或通过 PubMed 导入审核。现有文本依据提供的资料整理；照片、文章和 PDF 的相关权利归原权利人所有。
