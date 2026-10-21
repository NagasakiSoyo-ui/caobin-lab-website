"""Initialize a local installation without a shared/default administrator password."""
import argparse
import os
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--no-admin", action="store_true", help="Initialize content only; create an admin separately.")
args = parser.parse_args()
root = Path(__file__).resolve().parent
data = Path(os.environ.get("LAB_DATA_DIR", root / "data")).resolve()
data.mkdir(parents=True, exist_ok=True)
key = data / "secret.key"
if not key.exists():
    with key.open("x", encoding="utf-8") as file:
        file.write(secrets.token_urlsafe(64))
    key.chmod(0o600)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
call_command("migrate", interactive=False)
call_command("seed_site")
call_command("seed_publications")
call_command("collectstatic", interactive=False, verbosity=0)
if not args.no_admin and not get_user_model().objects.filter(is_superuser=True).exists():
    print("请设置管理员账号和密码。密码输入时不回显，至少 12 位。")
    call_command("createsuperuser")
print("初始化完成。后台入口 /manage/；前台不显示此入口。")
