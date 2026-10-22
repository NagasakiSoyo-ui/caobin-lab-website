"""Build a relocatable Windows trial from tracked source and local dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True, type=Path, help='New package directory; must not exist.')
args = parser.parse_args()
if sys.platform != 'win32' or sys.version_info[:2] != (3, 12):
    parser.error('Build with Windows 64-bit Python 3.12 and the project virtual environment.')
root = Path(__file__).resolve().parents[1]
dest = args.output.resolve()
dest.mkdir(parents=True, exist_ok=False)
app = dest / 'app'; app.mkdir()
tracked = subprocess.check_output(['git','ls-files','-z'], cwd=root).decode('utf8').split('\0')
for name in filter(None, tracked):
    source = root / name
    if source.is_file() and Path(name).parts[0] not in ('trial','tools'):
        target = app / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
runtime = dest / 'runtime'; runtime.mkdir()
base = Path(sys.base_prefix)
for name in ('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):
    shutil.copy2(base / name, runtime / name)
ignore = shutil.ignore_patterns('__pycache__','*.pyc','*.pdb')
shutil.copytree(base / 'DLLs', runtime / 'DLLs', ignore=ignore)
shutil.copytree(base / 'Lib', runtime / 'Lib', ignore=shutil.ignore_patterns('site-packages','__pycache__','*.pyc','test','tests','ensurepip','idlelib','tkinter','turtledemo'))
shutil.copytree(root / '.venv/Lib/site-packages', runtime / 'Lib/site-packages',
                ignore=shutil.ignore_patterns('__pycache__','*.pyc','pip','pip-*.dist-info'))
# Isolate imports from the client's installed Python, registry and environment.
(runtime / 'python312._pth').write_text('.\nDLLs\nLib\nLib/site-packages\n../app\nimport site\n', 'utf8')
for name in ('launcher.py','welcome.html'):
    shutil.copy2(root / 'trial' / name, dest / name)
(dest / '启动试用.cmd').write_bytes((root / 'trial/start.cmd').read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
(dest / '先看这里.txt').write_text('曹彬课题组网站 · Windows 客户试用包\n\n1. 将压缩包完整解压到普通文件夹（不要在压缩软件里直接运行）。\n2. 双击“启动试用.cmd”，等待浏览器自动打开。无需安装 Python 或下载依赖。\n3. 点击“查看网站”或“进入后台管理”。首次账号：admin，密码：admin。\n4. 后台修改后保存，再刷新网站即可看到效果。使用期间保留启动窗口。\n5. 关闭启动窗口即停止服务。再次双击启动，已有修改会保留。\n6. 交回修改结果：先关闭启动窗口，将整个文件夹重新压缩发回。不要删除 data 文件夹。\n\n适用 Windows 10/11 64 位电脑。研究图片和资料可离线查看，论文外部链接需要联网。\n本包用于本地客户试用；正式上线由制作方部署，并设置独立管理员账号与密码。\n', 'utf-8-sig')
archive = dest.parent / (dest.name + '.zip')
with ZipFile(archive, 'x', ZIP_DEFLATED) as z:
    for file in sorted(dest.rglob('*')):
        if file.is_file():z.write(file, dest.name+'/'+file.relative_to(dest).as_posix())
print(json.dumps({'folder':str(dest),'zip':str(archive),'size':archive.stat().st_size,
                  'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()},ensure_ascii=False))
