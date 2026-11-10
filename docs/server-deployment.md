# IP 访问部署

公网入口为 `https://47.119.153.171/`，管理入口为 `/manage/`。HTTP 自动跳转 HTTPS。服务器使用独立后台密码，桌面试用账号不变。账号、密钥、数据库及备份不进入 Git。

## 服务结构

- Ubuntu 24.04，Nginx 接收 80/443，Waitress 仅监听 `127.0.0.1:8771`。
- 站点专用用户 `caobinlab`；服务配置见 `deploy/`。
- `/srv/caobin-lab/releases/` 保存源码，`current` 指向正在使用的版本。
- `/srv/caobin-lab/data/` 保存数据库、媒体、独立密钥及备份，更新代码不覆盖此目录。
- `/etc/caobin-lab/environment` 保存生产配置，只允许 root 读取，由 systemd 注入服务。
- 媒体请求仍由 Django 检查公开状态和权限，不将整个媒体目录直接暴露给 Nginx。
- 成员列表通过 `?width=640` 加载等比例 WebP 预览，原始照片不覆盖。预览保存在私有 `data/image-cache/`，源文件更新后自动使用新缓存；新上传照片无需手工处理。离线导出会包含实际使用的预览文件。
- 图片使用 `private, no-cache` 与 ETag：浏览器可以保留图片字节，但每次复用必须先检查权限与版本，未变化返回 304。撤下或删除内容后不会因长效缓存继续公开。PDF 仍按原有权限和下载规则处理。

## 维护

```sh
systemctl status caobin-lab nginx
journalctl -u caobin-lab -n 100
systemctl list-timers caobin-cert-renew.timer caobin-backup.timer
systemctl start caobin-backup
```

IP 证书采用 Let's Encrypt 短期证书；每六小时检查续期，成功后重载 Nginx。首次部署应执行 Certbot 续期演练并检查定时器，不能只检查首次签发。

每天北京时间 04:10 运行现有 `backup_site` 命令，备份数据库与全部媒体到私有 `data/backups/`。定期将备份复制到另一台机器；同服务器备份不能防止整机或磁盘丢失。监控磁盘使用，备份不会自动删除。

更新前运行备份，将新代码放入新的 releases 目录，在同一数据目录执行 `manage.py migrate`、`collectstatic --noinput` 和 `check --deploy`，切换 current 后重启 caobin-lab。若有数据库结构变更，回退代码前先核对迁移兼容性，必要时使用升级前数据备份。

未来绑定域名时，同时更新 Nginx 的 server_name、证书以及 LAB_ALLOWED_HOSTS，再检查 HTTPS 登录、CSRF、媒体权限及续期任务。

证书方式依据 [Let's Encrypt 的 Certbot IP 证书说明](https://letsencrypt.org/2026/03/11/shorter-certs-certbot.html)。
