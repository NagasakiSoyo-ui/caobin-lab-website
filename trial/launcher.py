"""Windows-only local customer trial; separate from production startup."""
import argparse
import json
import msvcrt
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'app'
DATA = ROOT / 'data'
STATE = DATA / 'running.json'


def open_ready(url, token, browser=True):
    # Probe our instance before opening the browser, not merely an occupied port.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(60):
        try:
            with opener.open(url + '__trial__/health', timeout=1) as response:
                if response.read().decode() == token:
                    if browser:
                        webbrowser.open(url + '__trial__/')
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    # OS-backed lock releases even if the console is closed or the process crashes.
    with (DATA / 'instance.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('试用程序已在运行，正在打开界面……', flush=True)
            for _ in range(60):
                try:
                    state = json.loads(STATE.read_text('utf8'))
                except (FileNotFoundError, json.JSONDecodeError):
                    time.sleep(0.5)
                    continue
                if open_ready(state['url'], state['token'], not args.no_browser):
                    return
                break
            raise RuntimeError('已有试用程序仍在初始化或没有响应，请查看原来的启动窗口。')

        STATE.unlink(missing_ok=True)
        os.environ.update(LAB_DATA_DIR=str(DATA), LAB_ALLOWED_HOSTS='127.0.0.1,localhost',
                          DJANGO_SETTINGS_MODULE='config.settings', PYTHONUTF8='1')
        for name in ('LAB_PRODUCTION', 'DJANGO_SECRET_KEY'):
            os.environ.pop(name, None)
        sys.path.insert(0, str(APP))
        os.chdir(APP)
        print('正在准备网站和后台，首次启动请稍候……', flush=True)
        subprocess.run([sys.executable, str(APP / 'setup_local.py'), '--no-admin'], check=True)
        import django
        django.setup()
        from django.contrib.auth import get_user_model
        from django.db import transaction
        from django.core.wsgi import get_wsgi_application
        from waitress.server import create_server
        with transaction.atomic():
            users = get_user_model().objects
            # Never reset passwords or restore deleted content on later starts.
            if not users.filter(is_superuser=True).exists():
                if users.filter(username='admin').exists():
                    raise RuntimeError('admin 已存在但不是管理员，请联系制作方处理账号。')
                users.create_superuser('admin', password='admin')
        application = get_wsgi_application()
        token = secrets.token_urlsafe(32)
        welcome = (ROOT / 'welcome.html').read_bytes()

        def trial_app(environ, start_response):
            route = environ.get('PATH_INFO', '')
            if route in ('/__trial__/', '/__trial__/health'):
                body = token.encode() if route.endswith('/health') else welcome
                content_type = 'text/plain' if route.endswith('/health') else 'text/html'
                start_response('200 OK', [('Content-Type', content_type + '; charset=utf-8'),
                                         ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'),
                                         ('X-Robots-Tag', 'noindex, nofollow')])
                return [body]
            return application(environ, start_response)

        server = create_server(trial_app, host='127.0.0.1', port=0, max_request_body_size=60000000)
        url = f'http://127.0.0.1:{server.effective_port}/'
        STATE.write_text(json.dumps({'url': url, 'token': token}), 'utf8')
        print(f'\n网站：{url}\n后台：{url}manage/\n首次登录账号：admin  密码：admin', flush=True)
        print('使用期间请保留这个窗口。关闭此窗口即停止服务，修改内容自动保留。', flush=True)

        def show_browser():
            if not open_ready(url, token, not args.no_browser):
                print('未能自动打开，请复制上方地址到浏览器；若无响应请查看启动日志。', flush=True)

        threading.Thread(target=show_browser, daemon=True).start()
        try:
            server.run()
        finally:
            server.close()
            STATE.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        DATA.mkdir(exist_ok=True)
        details = traceback.format_exc()
        (DATA / 'startup-error.log').write_text(details, 'utf8')
        print(details, file=sys.stderr)
        print('启动失败。请将 data/startup-error.log 发给制作方。', file=sys.stderr)
        sys.exit(1)
