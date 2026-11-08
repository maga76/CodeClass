"""CodeClass для Windows.

Два режима, выбираются при первом запуске:
  • Учитель — программа сама запускает сервер на этом компьютере (Django + waitress),
    ученики подключаются к нему по локальной сети;
  • Ученик — программа открывает сервер учителя (или сайт в интернете) по адресу.

Настройки и база данных хранятся в %APPDATA%\\CodeClass.
Эта же программа запускает решения учеников на Python: CodeClass.exe --run-python файл.py
"""
import sys


def run_student_python(path):
    """Режим «интерпретатор Python» для проверки решений (в программе нет отдельного python.exe)."""
    import os
    import runpy
    import traceback

    # У программы без консоли стандартных потоков нет — открываем те, что передал проверяющий процесс
    sys.stdin = open(0, encoding='utf-8', closefd=False)
    sys.stdout = open(1, 'w', encoding='utf-8', closefd=False)
    sys.stderr = open(2, 'w', encoding='utf-8', closefd=False)
    sys.argv = [path]
    code = 0
    try:
        runpy.run_path(path, run_name='__main__')
    except SystemExit as exit_:
        code = exit_.code if isinstance(exit_.code, int) else (0 if exit_.code is None else 1)
        if not isinstance(exit_.code, (int, type(None))):
            print(exit_.code, file=sys.stderr)
    except BaseException:
        # Как в обычном Python: трассировка без строк самой программы-запускателя
        etype, value, tb = sys.exc_info()
        while tb is not None and tb.tb_frame.f_code.co_filename != path:
            tb = tb.tb_next
        traceback.print_exception(etype, value, tb)
        code = 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
    os._exit(code)


if len(sys.argv) >= 3 and sys.argv[1] == '--run-python':
    run_student_python(sys.argv[2])

# ---------- Обычный запуск программы ----------
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import secrets  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from pathlib import Path  # noqa: E402

import webview  # noqa: E402

if not getattr(sys, 'frozen', False):
    # Запуск из исходников (pythonw desktoppp.py): сайт лежит в папке выше
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(os.environ.get('APPDATA', Path.home())) / 'CodeClass'
CONFIG_FILE = DATA_DIR / 'config.json'
DEFAULT_PORT = 8001
log = logging.getLogger('codeclass')

PAGE_STYLE = '''
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
         font-family: "Segoe UI", sans-serif; color: #f1f5f9; background: #0a0e17;
         background-image: radial-gradient(at 15% 0%, rgba(0,212,255,.18) 0, transparent 45%),
                           radial-gradient(at 90% 5%, rgba(255,107,74,.14) 0, transparent 45%); }
  .card { width: 100%; max-width: 640px; padding: 36px; border-radius: 24px; text-align: center;
          background: rgba(17,24,39,.75); border: 1px solid rgba(255,255,255,.08); }
  .logo { display: inline-grid; place-items: center; width: 60px; height: 60px; border-radius: 18px; margin-bottom: 18px;
          font: 800 24px Consolas, monospace; color: #04121a; background: linear-gradient(135deg, #00d4ff, #ff6b4a);
          box-shadow: 0 0 40px -10px rgba(0,212,255,.6); }
  h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: -.02em; }
  p { color: #94a3b8; line-height: 1.55; margin: 0 0 22px; }
  .choices { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; text-align: left; }
  .choice { padding: 20px; border-radius: 18px; cursor: pointer; border: 1px solid rgba(255,255,255,.14);
            background: rgba(255,255,255,.03); color: inherit; font: inherit; text-align: left; transition: .15s; }
  .choice:hover { border-color: #00d4ff; background: rgba(0,212,255,.07); transform: translateY(-2px); }
  .choice b { display: block; font-size: 18px; margin: 10px 0 4px; }
  .choice span { color: #94a3b8; font-size: 14px; line-height: 1.45; }
  .choice .emoji { font-size: 30px; line-height: 1; }
  input { width: 100%; padding: 13px 15px; border-radius: 12px; font: 16px Consolas, monospace; color: #f1f5f9;
          background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.16); outline: none; margin-bottom: 12px; }
  input:focus { border-color: #00d4ff; box-shadow: 0 0 0 4px rgba(0,212,255,.15); }
  .btn { display: inline-block; padding: 13px 22px; border-radius: 12px; border: 0; cursor: pointer; font: 700 15px "Segoe UI";
         color: #04121a; background: linear-gradient(135deg, #00d4ff, #00a8cc); }
  .btn.secondary { color: #f1f5f9; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.14); }
  .row { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }
  .error { color: #f87171; min-height: 22px; margin: 4px 0 10px; font-size: 14px; }
  .hint { font-size: 13px; color: #64748b; margin: 18px 0 0; }
  code { color: #4de3ff; }
  @media (max-width: 560px) { .choices { grid-template-columns: 1fr; } }
'''

SETUP_PAGE = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>{style}</style></head><body>
<div class="card" id="choose">
  <div class="logo">&lt;/&gt;</div>
  <h1>Добро пожаловать в CodeClass</h1>
  <p>Выберите, как вы будете пользоваться программой. Это можно поменять позже кнопкой ⚙ в правом верхнем углу.</p>
  <div class="choices">
    <button class="choice" onclick="pywebview.api.choose_host()">
      <span class="emoji">👩‍🏫</span><b>Я учитель</b>
      <span>Сервер запустится на этом компьютере. Ученики подключатся к нему по сети класса.</span>
    </button>
    <button class="choice" onclick="showClient()">
      <span class="emoji">🧑‍🎓</span><b>Я ученик</b>
      <span>Подключиться к компьютеру учителя или к сайту CodeClass по адресу.</span>
    </button>
  </div>
  <p class="hint">Учителю: если Windows спросит про брандмауэр, нажмите «Разрешить доступ» — иначе ученики не подключатся.</p>
</div>
<div class="card" id="client" hidden>
  <div class="logo">&lt;/&gt;</div>
  <h1>Адрес сервера</h1>
  <p>Учитель видит адрес на главной странице своей программы, например <code>http://192.168.1.10:8001</code></p>
  <input id="url" placeholder="http://192.168.1.10:8001" value="{saved_url}" autofocus
         onkeydown="if (event.key === 'Enter') connect()">
  <div class="error" id="error"></div>
  <div class="row">
    <button class="btn secondary" onclick="showChoose()">Назад</button>
    <button class="btn" id="connect" onclick="connect()">Подключиться</button>
  </div>
</div>
<script>
  function showClient() {{ choose.hidden = true; client.hidden = false; url.focus(); }}
  function showChoose() {{ client.hidden = true; choose.hidden = false; }}
  async function connect() {{
    connectBtn.disabled = true; connectBtn.textContent = 'Проверяю…'; error.textContent = '';
    const message = await pywebview.api.choose_client(url.value);
    if (message) {{ error.textContent = message; connectBtn.disabled = false; connectBtn.textContent = 'Подключиться'; }}
  }}
  const connectBtn = document.getElementById('connect');
  {start_script}
</script>
</body></html>'''

MESSAGE_PAGE = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>{style}</style></head><body>
<div class="card">
  <div class="logo">&lt;/&gt;</div>
  <h1>{title}</h1>
  <p>{text}</p>
  <div class="row">{buttons}</div>
</div></body></html>'''


SETTINGS_PAGE = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>{style}
  .info {{ text-align: left; padding: 14px 16px; border-radius: 14px; margin-bottom: 18px;
           background: rgba(0,212,255,.06); border: 1px solid rgba(0,212,255,.22); color: #cbd5e1; font-size: 14px; }}
  .info b {{ color: #f1f5f9; }}
  .actions {{ display: grid; gap: 10px; }}
  .actions .btn {{ width: 100%; }}
</style></head><body>
<div class="card">
  <div class="logo">⚙</div>
  <h1>Настройки программы</h1>
  <p>CodeClass для Windows</p>
  <div class="info">{info}</div>
  <div class="actions">
    <button class="btn" onclick="pywebview.api.back()">← Вернуться</button>
    <button class="btn secondary" onclick="pywebview.api.change_mode()">Сменить режим (учитель / ученик)</button>
    <button class="btn secondary" onclick="pywebview.api.change_server()">Изменить адрес сервера</button>
  </div>
  <p class="hint">Данные программы: <code>{data_dir}</code></p>
</div></body></html>'''


# ---------- Настройки ----------

def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_config(config):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')


def normalize_url(url):
    url = url.strip().rstrip('/')
    if url and '://' not in url:
        url = 'http://' + url
    return url + '/' if url else ''


def is_reachable(url):
    try:
        urllib.request.urlopen(url, timeout=5)
        return True
    except urllib.error.HTTPError:
        return True  # сервер ответил, пусть даже ошибкой — значит, он доступен
    except (urllib.error.URLError, OSError, ValueError):
        return False


# ---------- Встроенный сервер (режим учителя) ----------

def lan_addresses():
    """IP-адреса этого компьютера в локальной сети."""
    addresses = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(('10.255.255.255', 1))  # пакет не отправляется, только выбирается сетевая карта
            addresses.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for address in socket.gethostbyname_ex(socket.gethostname())[2]:
            if address not in addresses:
                addresses.append(address)
    except OSError:
        pass
    return [a for a in addresses if not a.startswith(('127.', '169.254.'))]


def local_time_zone():
    """Часовой пояс Windows в виде, понятном Django: UTC+5 → Etc/GMT-5 (знак в таких именах обратный)."""
    offset = -(time.altzone if time.daylight and time.localtime().tm_isdst else time.timezone)
    hours, rest = divmod(offset, 3600)
    if rest:
        return 'UTC'
    return 'UTC' if hours == 0 else f'Etc/GMT{-hours:+d}'


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test:
        return test.connect_ex(('127.0.0.1', port)) != 0


def choose_port(config):
    preferred = config.get('port', DEFAULT_PORT)
    for port in [preferred, *range(DEFAULT_PORT, DEFAULT_PORT + 20)]:
        if port_is_free(port):
            return port
    raise RuntimeError('Не нашёлся свободный порт для сервера')


def warm_up_judge():
    """Первый запуск интерпретатора после включения компьютера занимает секунды —
    делаем его заранее, чтобы первое решение ученика не получило «Превышено время»."""
    from classroom.judge import _execute
    try:
        _execute('python', 'pass', [''])
    except Exception:  # noqa: BLE001 — прогрев необязателен
        pass


class LocalServer:
    def __init__(self):
        self.port = None
        self.error = None

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}/'

    def start(self, config):
        if self.port:
            return
        self.port = choose_port(config)
        config['port'] = self.port
        config.setdefault('secret_key', secrets.token_urlsafe(50))
        save_config(config)

        os.environ.update({
            'DJANGO_SETTINGS_MODULE': 'config.settings',
            'DJANGO_DEBUG': '0',
            'DJANGO_HTTPS': '0',
            'DJANGO_STATIC_MANIFEST': '0',
            'DJANGO_ALLOWED_HOSTS': '*',
            'DJANGO_SECRET_KEY': config['secret_key'],
            'DJANGO_DB_PATH': str(DATA_DIR / 'db.sqlite3'),
            'DJANGO_TIME_ZONE': config.get('time_zone') or local_time_zone(),
            'CODECLASS_PUBLIC_URLS': ','.join(f'http://{ip}:{self.port}' for ip in lan_addresses()),
        })
        import django
        from django.core.management import call_command
        django.setup()
        call_command('migrate', interactive=False, verbosity=0)

        from waitress import serve
        from config.wsgi import application
        threading.Thread(target=self._serve, args=(serve, application), daemon=True).start()
        threading.Thread(target=warm_up_judge, daemon=True).start()
        for _ in range(100):
            if self.error:
                raise RuntimeError(self.error)
            if is_reachable(self.url):
                return
            time.sleep(0.1)
        raise RuntimeError('Сервер не запустился')

    def _serve(self, serve, application):
        try:
            serve(application, host='0.0.0.0', port=self.port, threads=16, ident='CodeClass')
        except Exception as error:  # noqa: BLE001 — показываем любую причину пользователю
            log.exception('Ошибка сервера')
            self.error = str(error)


# ---------- Окно ----------

class App:
    """Публичные методы вызывает JavaScript служебных страниц (pywebview js_api), остальное — с «_»."""

    def __init__(self):
        self._config = load_config()
        self._server = LocalServer()
        self._window = None

    def _html(self, page, **values):
        return page.format(style=PAGE_STYLE, **values)

    def _message(self, title, text, buttons):
        self._window.load_html(self._html(MESSAGE_PAGE, title=title, text=text, buttons=buttons))

    def _open(self):
        # Сначала дожидаемся, пока окно догрузит стартовую страницу, иначе она затрёт нашу
        self._window.events.loaded.wait(15)
        try:
            self._route()
        except Exception:
            log.exception('Ошибка при открытии')
            self._message('Что-то пошло не так', f'Подробности в файле <code>{DATA_DIR / "codeclass.log"}</code>',
                          '<button class="btn" onclick="pywebview.api.retry()">Повторить</button>')

    def _route(self):
        mode = self._config.get('mode')
        if mode == 'host':
            self._open_host()
        elif mode == 'client' and self._config.get('server_url'):
            self._open_client()
        else:
            self._show_setup()

    def _show_setup(self, client=False):
        self._window.load_html(self._html(
            SETUP_PAGE, saved_url=self._config.get('server_url', '').rstrip('/'),
            start_script='showClient();' if client else '',
        ))

    def _open_host(self):
        self._message('Запуск сервера…', 'Подготавливаю базу данных и запускаю сервер. Это занимает несколько секунд.', '')
        try:
            self._server.start(self._config)
        except Exception as error:  # noqa: BLE001
            log.exception('Сервер не запустился')
            self._message('Не удалось запустить сервер', str(error),
                          '<button class="btn" onclick="pywebview.api.retry()">Повторить</button>'
                          '<button class="btn secondary" onclick="pywebview.api.change_mode()">Сменить режим</button>')
            return
        self._window.set_title('CodeClass — учитель (сервер работает)')
        self._window.load_url(self._server.url)

    def _open_client(self):
        url = self._config['server_url']
        if is_reachable(url):
            self._window.set_title('CodeClass')
            self._window.load_url(url)
        else:
            self._message('Нет связи с сервером',
                          f'Не удалось открыть <code>{url}</code>. Проверьте, что программа учителя запущена '
                          'и компьютеры в одной сети.',
                          '<button class="btn" onclick="pywebview.api.retry()">Повторить</button>'
                          '<button class="btn secondary" onclick="pywebview.api.change_server()">Изменить адрес</button>')

    def choose_host(self):
        self._config['mode'] = 'host'
        save_config(self._config)
        self._open_host()

    def choose_client(self, url):
        url = normalize_url(url)
        if not url:
            return 'Введите адрес'
        if not is_reachable(url):
            return 'Сервер не отвечает. Проверьте адрес и что программа учителя запущена.'
        self._config.update(mode='client', server_url=url)
        save_config(self._config)
        self._open_client()
        return ''

    def retry(self):
        self._route()

    def back(self):
        self._route()

    def open_settings(self):
        if self._config.get('mode') == 'host':
            info = ('Режим: <b>учитель</b> — сервер работает на этом компьютере.<br>Адреса для учеников: '
                    + (', '.join(f'<b>http://{ip}:{self._server.port}</b>' for ip in lan_addresses())
                       if self._server.port else 'сервер не запущен'))
        elif self._config.get('mode') == 'client':
            info = f'Режим: <b>ученик</b><br>Сервер: <b>{self._config.get("server_url", "")}</b>'
        else:
            info = 'Режим ещё не выбран'
        self._window.load_html(self._html(SETTINGS_PAGE, info=info, data_dir=DATA_DIR))

    def change_mode(self):
        self._show_setup()

    def change_server(self):
        self._show_setup(client=True)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=DATA_DIR / 'codeclass.log', level=logging.WARNING, encoding='utf-8',
                        format='%(asctime)s %(levelname)s %(message)s')
    app = App()
    app._window = webview.create_window(
        'CodeClass', html=app._html(MESSAGE_PAGE, title='CodeClass', text='Загрузка…', buttons=''),
        js_api=app, width=1280, height=820, min_size=(900, 600), background_color='#0a0e17',
        text_select=True,
    )
    webview.start(
        app._open, private_mode=False, storage_path=str(DATA_DIR / 'browser'),
        localization={
            'global.quitConfirmation': 'Закрыть CodeClass?',
            'global.ok': 'OK', 'global.quit': 'Выйти', 'global.cancel': 'Отмена',
        },
    )


if __name__ == '__main__':
    main()
