# Windows 客户试用包

适用 Windows 10/11 64 位；前台内容与 V3.6 医学深蓝版一致。

## 客户操作

1. 完整解压压缩包，双击 `启动试用.cmd`。
2. 自动打开的页面有“查看网站”和“进入后台管理”两个按钮。
3. 首次账号和密码都是 `admin`；后台修改保存后刷新前台即可查看。
4. 使用期间保留启动窗口。关闭后再次启动，修改仍然保留。
5. 交回修改结果时关闭程序，将整个文件夹重新压缩发回。`data` 是本次试用的数据，不能删除。

无需安装 Python、设置环境变量、安装依赖或创建账号。自动分配可用的本机端口，重复启动复用已有实例。图片和学习资料可离线查看，外部论文链接需要联网。

## 构建

在 Windows 64 位 Python 3.12 项目虚拟环境中，安装 requirements.txt，然后执行：

```powershell
.venv\Scripts\python.exe tools/build_trial.py --output E:\delivery\lab-trial
```

目标目录必须不存在。构建使用 Git 跟踪的源码、种子内容、当前解释器标准库及项目虚拟环境依赖；保留运行时和依赖许可证。不会复制维护电脑的数据库、会话、密钥、上传记录或账号。首次启动在客户电脑创建独立密钥和数据库，从相同的内容种子初始化。

Python 运行时通过 `python312._pth` 使用包内相对路径，隔离系统 Python、注册表与 PYTHONPATH。实现依据 [Python Windows 运行时文档](https://docs.python.org/3.12/using/windows.html)。服务使用项目已有的 [Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/api.html)，只绑定 127.0.0.1。

## 数据和上线

试用入口及默认账号创建仅在独立 launcher.py 中，常规 setup_local.py、正式 WSGI 和网站模板不使用它。后续启动不重置已有管理员密码。启动失败输出错误，并保存到 data/startup-error.log。

正式上线使用常规源码与部署配置，不运行试用 launcher；迁移需要保留的内容，并由客户设置独立管理员账号和密码。含试用修改的 data 可能包含账号及未公开内容，应由客户直接交还制作方，不上传公共仓库。

## V3.7 验收

2026-10-22：在含中文和空格的另一目录中，清除 PATH 中的 Python，并设置无效 PYTHONHOME / PYTHONPATH 后，包内解释器仍能独立启动。验证首次建库、重复启动复用、admin/admin 登录、后台修改并前台显示、离线导出及重启后数据和修改的密码保留。浏览器仅允许访问本机地址，未依赖外部资源。启动入口与后台截图已检查。
