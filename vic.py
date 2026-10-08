"""
Victor's Company Farmer — Single File Python (Chromium version)

Commands:
  python vic.py              → Auto farmer (initData → get pass → mining → loop)
  python vic.py --add        → Tambah akun baru via login Telegram
  python vic.py pass <acc>   → Get pass manual untuk 1 akun
  python vic.py pass-all     → Get pass manual semua akun
  python vic.py help         → Bantuan
"""

import asyncio
import json
import logging
import random
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import parse_qs, quote

import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich import box
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.messages import RequestWebViewRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import KeyboardButtonWebView


# =====================================================================
# PATH
# =====================================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SESSIONS_DIR = BASE_DIR / "sessions"
DATA_DIR = BASE_DIR / "data"
LOG_PATH = BASE_DIR / "error.log"
BROWSER_PROFILES_DIR = BASE_DIR / "chromium-profiles"

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
BROWSER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================================
# LOGGER
# =====================================================================

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("vic")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = RotatingFileHandler(
        LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


LOGGER = setup_logger()
LOGGER.info("=" * 70)
LOGGER.info("Victor's Company Farmer (Chromium) dimulai")


def log_info(account_id: str, message: str):
    LOGGER.info(f"[{account_id}] {message}")


def log_warn(account_id: str, message: str):
    LOGGER.warning(f"[{account_id}] {message}")


def log_error(account_id: str, context: str, error: Exception):
    LOGGER.error(f"[{account_id}] {context}: {type(error).__name__}: {error}")
    LOGGER.error(f"[{account_id}] Traceback:\n{traceback.format_exc()}")


# =====================================================================
# DEFAULT CONFIG
# =====================================================================

DEFAULT_CONFIG = {
    "telegram": {"api_id": 224069, "api_hash": "f2ddfd53867f28a3b6b98e80fa010e9d"},
    "bot": {
        "username": "VictorsCompanybot",
        "app_url": "https://app.victors.company/",
        "api_url": "https://server.victors.company/api",
    },
    "turnstile": {
        "site_key": "0x4AAAAAAFD0KRgPRFVwDvgn",
        "page_url": "https://app.victors.company/",
        "headless": False,
        # Pilihan perilaku window Chrome:
        #   "normal"    → Chrome tampil di layar (default, paling stabil)
        #   "minimize"  → Chrome tampil sebentar lalu minimize otomatis (via API)
        #   "offscreen" → Chrome diposisikan di luar layar (kadang Cloudflare curiga)
        "window_mode": "offscreen",
        "timeout": 60,
        "skip_if_fails": True,
        "max_concurrent": 1,
    },
    "human_pass": {
        "required_code": "HUMAN_REQUIRED",
        "expiry_margin_seconds": 600,
        "auto_refresh_threshold_hours": 3,
    },
    "mining": {
        "minimum_claimable": 1.0,
        "claim_retry_max": 5,
        "claim_retry_delay_min": 30,
        "claim_retry_delay_max": 90,
    },
    "tasks": {"dwell_seconds_min": 11, "dwell_seconds_max": 15},
    "withdrawal": {
        "minimum_default": 1000,
        "fee_default": 70,
        "buffer": 75,
        "history_limit": 20,
        "pending_statuses": ["Pending", "Approved", "Processing"],
    },
    "cycle": {
        "interval_seconds": 21600,
        "request_timeout": 30,
        "retry_count": 3,
        "stagger_seconds": 3,
    },
    "miner_curve": {
        "maximum_level": 1000,
        "base_speed_ths": 0.2,
        "mid_speed_level": 203,
        "mid_speed_ths": 7.56,
        "maximum_speed_ths": 5000,
        "daily_output_per_ths": 25,
        "level_one_daily_output": 5,
    },
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("=" * 80)
        print("config.json belum ada — sudah dibuat otomatis.")
        print(f"Lokasi: {CONFIG_PATH}")
        print("=" * 80)
        sys.exit(0)
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"config.json tidak valid: {e}")
        sys.exit(1)

    def merge(target, defaults):
        for k, v in defaults.items():
            if k not in target:
                target[k] = v
            elif isinstance(v, dict) and isinstance(target[k], dict):
                merge(target[k], v)

    merge(cfg, DEFAULT_CONFIG)
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return cfg


CFG = load_config()


# =====================================================================
# CONFIG VARIABLES
# =====================================================================

API_ID = int(CFG["telegram"]["api_id"])
API_HASH = str(CFG["telegram"]["api_hash"])

if not API_ID or not API_HASH:
    print("=" * 80)
    print("⚠️  telegram.api_id dan telegram.api_hash belum diisi di config.json")
    print("=" * 80)
    sys.exit(1)

BOT_USERNAME = str(CFG["bot"]["username"]).lstrip("@")
APP_URL = str(CFG["bot"]["app_url"]).rstrip("/")
API_URL = str(CFG["bot"]["api_url"]).rstrip("/")

TURNSTILE_SITE_KEY = CFG["turnstile"]["site_key"]
TURNSTILE_PAGE_URL = CFG["turnstile"]["page_url"]
TURNSTILE_HEADLESS = bool(CFG["turnstile"]["headless"])
TURNSTILE_WINDOW_MODE = str(CFG["turnstile"].get("window_mode", "normal")).lower()
TURNSTILE_TIMEOUT = int(CFG["turnstile"]["timeout"])
TURNSTILE_SKIP_IF_FAILS = bool(CFG["turnstile"].get("skip_if_fails", True))
TURNSTILE_MAX_CONCURRENT = int(CFG["turnstile"].get("max_concurrent", 1))

HUMAN_REQUIRED_CODE = CFG["human_pass"]["required_code"]
HUMAN_PASS_EXPIRY_MARGIN = int(CFG["human_pass"]["expiry_margin_seconds"])
HUMAN_PASS_AUTO_REFRESH_HOURS = float(
    CFG["human_pass"].get("auto_refresh_threshold_hours", 3)
)

MINIMUM_CLAIMABLE_MINING = float(CFG["mining"]["minimum_claimable"])
MINING_CLAIM_RETRY_MAX = int(CFG["mining"].get("claim_retry_max", 5))
MINING_CLAIM_RETRY_DELAY_MIN = int(CFG["mining"].get("claim_retry_delay_min", 30))
MINING_CLAIM_RETRY_DELAY_MAX = int(CFG["mining"].get("claim_retry_delay_max", 90))

TASK_DWELL_MIN = float(CFG["tasks"]["dwell_seconds_min"])
TASK_DWELL_MAX = float(CFG["tasks"]["dwell_seconds_max"])

WD_MIN_DEFAULT = float(CFG["withdrawal"]["minimum_default"])
WD_FEE_DEFAULT = float(CFG["withdrawal"]["fee_default"])
WD_BUFFER = float(CFG["withdrawal"]["buffer"])
WD_HISTORY_LIMIT = int(CFG["withdrawal"]["history_limit"])
WD_PENDING_STATUSES = list(CFG["withdrawal"]["pending_statuses"])

CYCLE_INTERVAL = int(CFG["cycle"]["interval_seconds"])
REQUEST_TIMEOUT = int(CFG["cycle"]["request_timeout"])
RETRY_COUNT = int(CFG["cycle"]["retry_count"])
STAGGER_SECONDS = int(CFG["cycle"].get("stagger_seconds", 3))

MC = CFG["miner_curve"]
MAX_MINER_LEVEL = int(MC["maximum_level"])
BASE_SPEED_THS = float(MC["base_speed_ths"])
MID_SPEED_LEVEL = int(MC["mid_speed_level"])
MID_SPEED_THS = float(MC["mid_speed_ths"])
MAXIMUM_SPEED_THS = float(MC["maximum_speed_ths"])
DAILY_OUTPUT_PER_THS = float(MC["daily_output_per_ths"])
LEVEL_ONE_DAILY_OUTPUT = float(MC["level_one_daily_output"])

_TURNSTILE_SEM: asyncio.Semaphore | None = None


def get_turnstile_semaphore() -> asyncio.Semaphore:
    global _TURNSTILE_SEM
    if _TURNSTILE_SEM is None:
        _TURNSTILE_SEM = asyncio.Semaphore(TURNSTILE_MAX_CONCURRENT)
    return _TURNSTILE_SEM


# =====================================================================
# WINDOW CONTROL + TASK RESET
# =====================================================================

def find_next_task_reset(result_tasks: dict) -> int:
    if not isinstance(result_tasks, dict):
        return 0
    tasks = result_tasks.get("tasks", [])
    if not tasks:
        return 0
    now = time.time()
    earliest = None
    for task in tasks:
        available = task.get("availableAt")
        if not available:
            continue
        try:
            dt = datetime.fromisoformat(available.replace("Z", "+00:00"))
            ts = dt.timestamp()
            if ts > now:
                if earliest is None or ts < earliest:
                    earliest = ts
        except Exception:
            continue
    return int(earliest) if earliest else 0


def _initdata_age_minutes(init_data: str) -> int:
    for p in SESSIONS_DIR.glob("*.initdata"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("initData") == init_data:
                fetched_at = int(data.get("fetchedAt", 0))
                if fetched_at:
                    return int((time.time() - fetched_at) / 60)
        except Exception:
            continue
    return 0


def minimize_windows_browser(keyword: str = "victors") -> bool:
    import platform
    if platform.system() != "Windows":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
        )
        found = {"hwnd": None}

        def callback(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            if keyword.lower() in title.lower() and user32.IsWindowVisible(hwnd):
                found["hwnd"] = hwnd
                return False
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)

        if found["hwnd"]:
            SW_MINIMIZE = 6
            user32.ShowWindow(found["hwnd"], SW_MINIMIZE)
            return True
    except Exception:
        pass
    return False


def get_launch_args() -> list:
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if TURNSTILE_WINDOW_MODE == "offscreen":
        args.extend([
            "--window-position=-3000,-3000",
            "--window-size=500,900",
        ])
    return args


# =====================================================================
# DEVICE PROFILES
# =====================================================================

DEVICES = [
    ("Samsung Galaxy S22", "SM-S908B", "Android 13", "Chrome/120.0.0.0"),
    ("Samsung Galaxy S23", "SM-S916B", "Android 14", "Chrome/121.0.0.0"),
    ("Google Pixel 7", "Pixel 7", "Android 14", "Chrome/119.0.0.0"),
    ("OnePlus 11", "CPH2451", "Android 13", "Chrome/120.0.0.0"),
    ("Xiaomi 13", "2211133G", "Android 14", "Chrome/121.0.0.0"),
    ("Samsung Galaxy A54", "SM-A546B", "Android 13", "Chrome/118.0.0.0"),
]


def get_device(account_id: str):
    try:
        num = int(account_id.split("_")[-1])
    except Exception:
        num = 0
    return DEVICES[num % len(DEVICES)]


def get_user_agent(account_id: str) -> str:
    _, code, android, chrome = get_device(account_id)
    return (
        f"Mozilla/5.0 (Linux; {android}; {code}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"{chrome} Mobile Safari/537.36"
    )


# =====================================================================
# MINER CURVE
# =====================================================================

def get_miner_speed(level: int) -> Decimal:
    if level <= 0:
        return Decimal(0)
    if level >= MAX_MINER_LEVEL:
        return Decimal(str(MAXIMUM_SPEED_THS))
    if level <= MID_SPEED_LEVEL:
        step = (MID_SPEED_THS - BASE_SPEED_THS) / (MID_SPEED_LEVEL - 1)
        return Decimal(f"{BASE_SPEED_THS + (level - 1) * step:.2f}")
    progress = (level - MID_SPEED_LEVEL) / (MAX_MINER_LEVEL - MID_SPEED_LEVEL)
    val = MID_SPEED_THS + (MAXIMUM_SPEED_THS - MID_SPEED_THS) * (progress ** 2.1)
    return Decimal(f"{val:.2f}")


def get_miner_daily_output(level: int) -> Decimal:
    if level <= 0:
        return Decimal(0)
    if level == 1:
        return Decimal(str(LEVEL_ONE_DAILY_OUTPUT))
    return Decimal(f"{float(get_miner_speed(level)) * DAILY_OUTPUT_PER_THS:.2f}")


def get_miner_required_holding(level: int) -> Decimal:
    if level <= 0:
        return Decimal(0)
    if level == 1:
        return Decimal(100)
    if level >= MAX_MINER_LEVEL:
        return Decimal(3875968992)
    if level <= 203:
        return Decimal(round(100 + 9900 * ((level - 1) / 202) ** 1.8))
    if level <= 450:
        return Decimal(round(1e4 + 24e4 * ((level - 203) / 247) ** 2))
    if level <= 650:
        return Decimal(round(25e4 + 26881780 * ((level - 450) / 200) ** 2.2))
    if level <= 850:
        return Decimal(round(27131780 + 321705420 * ((level - 650) / 200) ** 2.5))
    return Decimal(round(
        348837200 + 3527131792 * ((level - 850) / (MAX_MINER_LEVEL - 850)) ** 2.6
    ))


def find_miner_level_for_holding(holding, wallet_connected: bool = True) -> int:
    amount = float(holding or 0)
    if not wallet_connected and amount <= 0:
        return 0
    if amount < float(get_miner_required_holding(1)):
        return 1 if wallet_connected else 0
    lo, hi, reachable = 1, MAX_MINER_LEVEL, 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if amount >= float(get_miner_required_holding(mid)):
            reachable = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return reachable


# =====================================================================
# DASHBOARD
# =====================================================================

SLOTS = ["ACCOUNT", "AUTH", "MINING", "TASK", "SQUAD", "WITHDRAW"]

STATUS_STYLES = {
    "SUCCESS": "bold green", "SUCCESSFUL": "bold green",
    "READY": "bold green", "OK": "bold green",
    "JOINED": "bold green", "DONE": "bold green",
    "START": "bold yellow", "RUNNING": "bold yellow",
    "REQUEST": "yellow", "RESPONSE": "green",
    "WAIT": "bold yellow", "SKIP": "dim yellow",
    "CACHE": "cyan", "FETCH": "cyan", "SAVED": "cyan",
    "MISS": "yellow", "RETRY": "bold magenta", "BUSY": "bold magenta",
    "INPUT": "bold yellow", "CLAIM": "bold yellow",
    "REFRESH": "cyan", "FAILED": "bold red",
    "ERROR": "bold red", "INVALID": "bold red",
}


class Dashboard:
    def __init__(self):
        self.accounts: list = []
        self.data: dict = {}
        self.lock = asyncio.Lock()
        self._console = Console()
        self._live = None
        self._started = False

    def register(self, account_id):
        if account_id not in self.data:
            self.data[account_id] = {
                slot: {"status": "WAIT", "detail": "Menunggu..."}
                for slot in SLOTS
            }

    def start(self):
        if self._started:
            return
        self._live = Live(
            self.build_layout(),
            console=self._console,
            refresh_per_second=4,
            screen=True,
            transient=False,
        )
        self._live.start(refresh=True)
        self._started = True

    def stop(self):
        if self._live is not None:
            try:
                self._live.stop()
            finally:
                self._live = None
                self._started = False

    async def update(self, account_id, slot, status, detail):
        async with self.lock:
            self.register(account_id)
            slot_key = str(slot).upper()
            if slot_key not in SLOTS:
                slot_key = "ACCOUNT"
            self.data[account_id][slot_key] = {
                "status": str(status).upper(),
                "detail": str(detail),
            }
            self.render()

    def build_table(self) -> Table:
        table = Table(
            title="👷 Victor's Company Farmer",
            box=box.ROUNDED,
            border_style="bright_blue",
            header_style="bold white on blue",
            expand=True,
            show_lines=False,
        )
        table.add_column("ACCOUNT", style="bold cyan", min_width=10, no_wrap=True)
        table.add_column("SLOT", style="bold magenta", min_width=10, no_wrap=True)
        table.add_column("DETAIL", ratio=1, overflow="fold")

        for idx, acc in enumerate(self.accounts):
            if idx > 0:
                table.add_section()
            account_rows = self.data.get(acc, {})
            for slot_idx, slot in enumerate(SLOTS):
                row = account_rows.get(slot, {"status": "WAIT", "detail": "-"})
                status = str(row.get("status", "-")).upper()
                detail = str(row.get("detail", "-")).replace("\n", " ").strip()
                if len(detail) > 110:
                    detail = detail[:107] + "..."
                style = STATUS_STYLES.get(status, "white")
                acc_display = acc if slot_idx == 0 else ""
                table.add_row(
                    acc_display,
                    slot,
                    f"[{style}]{status}[/{style}] · {detail}",
                )
        return table

    def build_layout(self):
        if not self.accounts:
            return Panel("Menunggu akun...", title="👷 Victor's Company Farmer")
        return self.build_table()

    def render(self):
        if not self._started or self._live is None:
            return
        self._live.update(self.build_layout(), refresh=True)


DASHBOARD = Dashboard()


async def activity(account_id, slot, status, detail):
    await DASHBOARD.update(account_id, slot, status, detail)


# =====================================================================
# STATE
# =====================================================================

@dataclass
class AccountState:
    account_id: str
    last_balance: float = 0.0
    last_level: int = 0
    cycles_run: int = 0
    last_run_ts: int = 0


class StateManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def load(self, account_id: str) -> AccountState:
        path = self.base_dir / f"{account_id}.json"
        if path.exists():
            try:
                return AccountState(**json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return AccountState(account_id=account_id)

    def save(self, state: AccountState):
        path = self.base_dir / f"{state.account_id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(asdict(state), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)


# =====================================================================
# TURNSTILE SOLVER — Chromium bundled
# =====================================================================

class TurnstileSolver:
    def __init__(self, account_id, site_key, page_url, init_data,
                 headless=False, timeout=60):
        self.account_id = account_id
        self.site_key = site_key
        self.page_url = page_url
        self.init_data = init_data
        self.headless = headless
        self.timeout = timeout

    async def _load_playwright(self):
        try:
            from patchright.async_api import async_playwright
            return async_playwright, "patchright"
        except ImportError:
            pass
        try:
            from playwright.async_api import async_playwright
            return async_playwright, "playwright"
        except ImportError:
            raise RuntimeError(
                "Install: pip install patchright && python -m patchright install chromium"
            )

    async def solve(self):
        sem = get_turnstile_semaphore()
        async with sem:
            log_info(self.account_id, "Turnstile slot didapat")
            return await self._solve_inner()

    async def _solve_inner(self):
        try:
            async_playwright, lib_name = await self._load_playwright()
        except RuntimeError as e:
            log_error(self.account_id, "Load playwright gagal", e)
            raise

        profile_dir = BROWSER_PROFILES_DIR / f"{self.account_id}_farmer"
        profile_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=self.headless,
                    args=get_launch_args(),
                )
                browser = None
            except Exception as e:
                log_error(self.account_id, "Launch browser gagal", e)
                raise

            page = await context.new_page()

            if TURNSTILE_WINDOW_MODE == "minimize" and not self.headless:
                await asyncio.sleep(1.5)
                minimize_windows_browser()
                minimize_windows_browser("victors")
                minimize_windows_browser("chromium")

            captured = {"human_pass": None}

            async def on_request(request):
                if captured["human_pass"]:
                    return
                try:
                    if "server.victors.company" not in request.url:
                        return
                    headers = request.headers
                    hp = headers.get("x-human-pass") or headers.get("X-Human-Pass")
                    if hp and hp.count(".") >= 2:
                        captured["human_pass"] = hp
                except Exception:
                    pass

            page.on("request", lambda r: asyncio.create_task(on_request(r)))

            webapp_url = (
                f"{self.page_url.rstrip('/')}/"
                f"#tgWebAppData={quote(self.init_data, safe='')}"
                f"&tgWebAppVersion=7.0&tgWebAppPlatform=android"
            )

            try:
                await page.goto(webapp_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                log_warn(self.account_id, f"Goto gagal: {e}")

            if TURNSTILE_WINDOW_MODE == "minimize" and not self.headless:
                await asyncio.sleep(1)
                minimize_windows_browser("app.victors.company")
                minimize_windows_browser("victors")
                minimize_windows_browser("chromium")

            start = time.time()
            while time.time() - start < 40:
                if captured["human_pass"]:
                    break
                try:
                    done = await page.evaluate("""
                        () => {
                            const c = !!document.querySelector('canvas');
                            const w = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                            return c && !w;
                        }
                    """)
                    if done:
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)

            if not captured["human_pass"]:
                positions = [
                    (206, 850), (206, 800), (100, 850),
                    (310, 850), (150, 200), (250, 200), (206, 500),
                ]
                for _ in range(3):
                    if captured["human_pass"]:
                        break
                    for x, y in positions:
                        if captured["human_pass"]:
                            break
                        try:
                            await page.mouse.click(x, y)
                        except Exception:
                            pass
                        await asyncio.sleep(1)

            try:
                await context.close()
            except Exception:
                pass
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

            if captured["human_pass"]:
                log_info(self.account_id, "Human pass dari network")
                return captured["human_pass"]

            log_warn(self.account_id, "Human pass tidak dapat")
            return None


# =====================================================================
# API CLIENT
# =====================================================================

class ApiClient:
    def __init__(self, init_data: str, account_id: str):
        self.init_data = init_data
        self.account_id = account_id
        self.human_pass = None
        self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)

    async def close(self):
        await self._client.aclose()

    def _headers(self, url: str) -> dict:
        headers = {
            "User-Agent": get_user_agent(self.account_id),
            "Accept": "application/json, text/plain, */*",
            "Origin": APP_URL,
            "Referer": APP_URL + "/",
        }
        if url.startswith(API_URL):
            headers["Authorization"] = f"tma {self.init_data}"
            if self.human_pass:
                headers["x-human-pass"] = self.human_pass
        return headers

    async def call(self, method, path, data=None, retry_human=True, human_solver=None):
        url = f"{API_URL}{path}"
        last_error = None
        payload = {}
        for attempt in range(RETRY_COUNT):
            try:
                response = await self._client.request(
                    method=method.upper(),
                    url=url,
                    json=data if method.lower() == "post" else None,
                    headers=self._headers(url),
                )
                payload = response.json() if response.content else {}
                if response.status_code >= 400:
                    log_warn(self.account_id,
                             f"HTTP {response.status_code} {method.upper()} {path}")
                break
            except Exception as e:
                last_error = e
                if attempt < RETRY_COUNT - 1:
                    await asyncio.sleep(2 * (attempt + 1))
        else:
            return {"success": False, "error": f"HTTP error: {last_error}"}

        if payload.get("code") == HUMAN_REQUIRED_CODE and retry_human and human_solver:
            await human_solver()
            return await self.call(method, path, data, retry_human=False)
        return payload

    async def get(self, path, human_solver=None):
        result = await self.call("get", path, human_solver=human_solver)
        if result.get("success") is False:
            raise RuntimeError(result.get("error") or f"Gagal baca {path}")
        return result

    async def post(self, path, data=None, human_solver=None):
        return await self.call("post", path, data or {}, human_solver=human_solver)


# =====================================================================
# VICTOR'S CLIENT
# =====================================================================

class VictorsClient:
    def __init__(self, account_id: str):
        self.account_id = account_id
        self.tg: TelegramClient | None = None
        self.api: ApiClient | None = None
        self.init_data_raw: str | None = None
        self.user_obj: dict | None = None
        self.tg_id: int | None = None
        self.state: dict = {}
        self.state_read_at: float = 0
        self._joined_channels = set()

    def _pass_cache_path(self) -> Path:
        return SESSIONS_DIR / f"{self.account_id}.pass"

    def _initdata_cache_path(self) -> Path:
        return SESSIONS_DIR / f"{self.account_id}.initdata"

    def _load_cached_initdata(self) -> str | None:
        p = self._initdata_cache_path()
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                init_data = data.get("initData")
                fetched_at = int(data.get("fetchedAt", 0))
                if not init_data:
                    return None
                if time.time() - fetched_at > 50 * 60:
                    return None
                return init_data
            return None
        except Exception:
            return None

    def _load_cached_pass(self) -> str | None:
        p = self._pass_cache_path()
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            token = data.get("humanPass")
            expires_at = int(data.get("expiresAt", 0))
            if not token or expires_at - time.time() < HUMAN_PASS_EXPIRY_MARGIN:
                return None
            return token
        except Exception:
            return None

    def _save_cached_pass(self, token: str):
        try:
            _, expires_at = self._parse_human_pass(token)
            self._pass_cache_path().write_text(
                json.dumps({"humanPass": token, "expiresAt": expires_at}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log_warn(self.account_id, f"Gagal cache pass: {e}")

    def _clear_cached_pass(self):
        try:
            p = self._pass_cache_path()
            if p.exists():
                p.unlink()
        except Exception:
            pass

    async def connect(self, require_login=True) -> bool:
        model, code, android, _ = get_device(self.account_id)
        self.tg = TelegramClient(
            str(SESSIONS_DIR / self.account_id),
            API_ID, API_HASH,
            device_model=model, system_version=android,
            app_version="10.5.2", lang_code="en", system_lang_code="en-US",
        )
        last_error = None
        for attempt in range(RETRY_COUNT):
            try:
                await self.tg.connect()
                last_error = None
                break
            except Exception as e:
                last_error = e
                await asyncio.sleep(2 + attempt * 2)

        if last_error:
            raise RuntimeError(f"Telegram connect failed: {last_error}")

        if not await self.tg.is_user_authorized():
            if not require_login:
                return False
            await activity(self.account_id, "AUTH", "INPUT",
                           "Session belum ada — login Telegram")
            await self.tg.disconnect()
            await self.login_new_telegram()
            return True

        me = await self.tg.get_me()
        await activity(self.account_id, "AUTH", "OK",
                       f"@{me.username or '-'} | ID={me.id}")
        return True

    async def login_new_telegram(self):
        model, code, android, _ = get_device(self.account_id)
        self.tg = TelegramClient(
            str(SESSIONS_DIR / self.account_id),
            API_ID, API_HASH,
            device_model=model, system_version=android,
            app_version="10.5.2", lang_code="en", system_lang_code="en-US",
        )
        await self.tg.connect()
        phone = input(f"\nNomor Telegram untuk {self.account_id}: ").strip()
        if not phone:
            raise RuntimeError("Nomor kosong")
        await self.tg.send_code_request(phone)
        code_input = input("Kode OTP: ").strip()
        try:
            await self.tg.sign_in(phone=phone, code=code_input)
        except SessionPasswordNeededError:
            password = input("Password 2FA: ")
            await self.tg.sign_in(password=password)

        me = await self.tg.get_me()
        await activity(self.account_id, "AUTH", "SUCCESS",
                       f"@{me.username or '-'} | ID={me.id}")

    async def close(self):
        if self.api:
            try:
                await self.api.close()
            except Exception:
                pass
            self.api = None
        if self.tg:
            try:
                await self.tg.disconnect()
            except Exception:
                pass
            self.tg = None

    async def fetch_webapp_query(self) -> str:
        if not self.tg:
            raise RuntimeError("Telegram belum connect")
        bot = await self.tg.get_entity(BOT_USERNAME)

        def find_button_url(messages):
            for msg in messages:
                if not msg.reply_markup:
                    continue
                rows = getattr(msg.reply_markup, "rows", None) or []
                for row in rows:
                    for button in row.buttons:
                        if isinstance(button, KeyboardButtonWebView):
                            return button.url
                        url = getattr(button, "url", None)
                        if url and ("t.me" in url or "victors" in url or "app." in url):
                            return url
            return None

        await activity(self.account_id, "AUTH", "FETCH", "Buka WebApp bot...")

        messages = await self.tg.get_messages(bot, limit=20)
        button_url = find_button_url(messages)

        if not button_url:
            try:
                result = await self.tg(RequestWebViewRequest(
                    peer=bot, bot=bot, platform="android",
                    from_bot_menu=True,
                    url=f"https://t.me/{BOT_USERNAME}/app",
                ))
                if result.url and "#" in result.url:
                    return self._extract_init_data_from_url(result.url)
            except Exception:
                pass

        if button_url:
            result = await self.tg(RequestWebViewRequest(
                peer=bot, bot=bot, platform="android",
                from_bot_menu=False, url=button_url,
            ))
            return self._extract_init_data_from_url(result.url)

        raise RuntimeError(f"WebApp URL tidak ditemukan di @{BOT_USERNAME}")

    def _extract_init_data_from_url(self, url: str) -> str:
        if "#" not in url:
            raise RuntimeError("URL tidak memiliki fragment")
        fragment = url.split("#", 1)[1]
        params = parse_qs(fragment)
        if "tgWebAppData" not in params:
            raise RuntimeError("tgWebAppData tidak ada")
        raw = params["tgWebAppData"][0]
        qs = parse_qs(raw)
        if "user" not in qs:
            raise RuntimeError("Data user tidak ada")
        try:
            user_obj = json.loads(qs["user"][0])
        except Exception as e:
            raise RuntimeError(f"JSON user tidak valid: {e}")
        if not isinstance(user_obj, dict) or not user_obj.get("id"):
            raise RuntimeError("Data user tidak valid")

        self.init_data_raw = raw
        self.user_obj = user_obj
        self.tg_id = int(user_obj["id"])

        try:
            init_meta = {
                "initData": raw,
                "fetchedAt": int(time.time()),
                "userId": self.tg_id,
            }
            (SESSIONS_DIR / f"{self.account_id}.initdata").write_text(
                json.dumps(init_meta, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            log_warn(self.account_id, f"Gagal simpan initData: {e}")

        log_info(self.account_id, f"initData OK ({len(raw)} chars)")
        return raw

    # ------------------------------------------------------------------
    # AUTO JOIN TELEGRAM CHANNEL
    # ------------------------------------------------------------------
    async def join_telegram_channel(self, channel_url: str) -> bool:
        if not self.tg:
            return False

        try:
            path = channel_url.rstrip("/").split("/")
            username = None
            for part in path:
                if part and part != "t.me" and not part.startswith("http") and not part.startswith("?"):
                    username = part
                    break
            if not username or username.startswith("+"):
                return False
        except Exception:
            return False

        if username in self._joined_channels:
            return True

        try:
            entity = await self.tg.get_entity(username)
            await self.tg(JoinChannelRequest(entity))
            self._joined_channels.add(username)
            log_info(self.account_id, f"Joined @{username}")
            await asyncio.sleep(2)
            return True
        except Exception as e:
            err = str(e).lower()
            if "already" in err or "participant" in err or "user already" in err:
                self._joined_channels.add(username)
                log_info(self.account_id, f"Sudah join @{username}")
                return True
            log_warn(self.account_id, f"Gagal join @{username}: {e}")
            return False

    # ------------------------------------------------------------------
    # HUMAN PASS
    # ------------------------------------------------------------------
    def _parse_human_pass(self, token: str):
        parts = str(token or "").split(".")
        if len(parts) < 2:
            return "", 0
        try:
            return parts[0], int(parts[1])
        except ValueError:
            return parts[0], 0

    async def obtain_human_pass(self):
        cached = self._load_cached_pass()
        if cached:
            self.api.human_pass = cached
            await activity(self.account_id, "AUTH", "OK", "Pass dari cache")
            return

        await activity(self.account_id, "AUTH", "RUNNING", "Auto get pass...")

        try:
            await get_pass_mode(self.account_id)
        except SystemExit:
            raise RuntimeError("Get pass gagal (SystemExit)")
        except Exception as e:
            log_error(self.account_id, "Get pass gagal", e)
            raise

        cached = self._load_cached_pass()
        if cached:
            self.api.human_pass = cached
            await activity(self.account_id, "AUTH", "SUCCESS", "Pass OK")
        else:
            raise RuntimeError("Pass tidak tersimpan setelah get_pass_mode")

    async def login(self):
        raw = await self.fetch_webapp_query()
        await activity(self.account_id, "AUTH", "SAVED",
                       f"initData OK ({len(raw)} chars)")

        self.api = ApiClient(self.init_data_raw, self.account_id)
        await self.obtain_human_pass()

    async def load_state(self):
        try:
            result = await self.api.get("/me", human_solver=self.obtain_human_pass)
            self._apply_result(result)
        except RuntimeError as e:
            if HUMAN_REQUIRED_CODE in str(e):
                self._clear_cached_pass()
            raise

    def _apply_result(self, result: dict):
        if result.get("state"):
            self.state = result["state"]
            self.state_read_at = datetime.now().timestamp()

    def user(self): return self.state.get("user", {})
    def mining(self): return self.state.get("mining", {})
    def verify(self): return self.state.get("verify", {})
    def config(self): return self.state.get("config", {})
    def referral(self): return self.state.get("referral", {})

    def get_mined_amount(self) -> Decimal:
        mining = self.mining()
        accrued = Decimal(str(mining.get("accrued", 0)))
        server_time = self.state.get("serverTime")
        ends_at = mining.get("sessionEndsAt")
        if not server_time or not ends_at:
            return accrued
        try:
            server_ts = datetime.fromisoformat(server_time.replace("Z", "+00:00")).timestamp()
            ends_ts = datetime.fromisoformat(ends_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            return accrued
        now = datetime.now().timestamp()
        elapsed_ms = max(0, min((now - self.state_read_at) * 1000, (ends_ts - server_ts) * 1000))
        daily = Decimal(str(mining.get("accrualDaily") or mining.get("dailyOutput") or 0))
        return accrued + daily * Decimal(elapsed_ms) / Decimal(86400 * 1000)

    # ------------------------------------------------------------------
    # MINING CLAIM — dengan retry 503
    # ------------------------------------------------------------------
    async def claim_mining(self):
        level = int(self.mining().get("level") or 0)
        if level <= 0:
            await activity(self.account_id, "MINING", "SKIP", "Wallet belum terhubung")
            return

        pending = self.get_mined_amount()
        if pending < Decimal(str(MINIMUM_CLAIMABLE_MINING)):
            await activity(self.account_id, "MINING", "SKIP",
                           f"Pending {pending:.4f} < {MINIMUM_CLAIMABLE_MINING}")
            return

        await activity(self.account_id, "MINING", "CLAIM", f"Pending={pending:.4f} VIC")

        # Retry loop untuk handle HTTP 503 (on-chain verify sementara gagal)
        for attempt in range(1, MINING_CLAIM_RETRY_MAX + 1):
            result = await self.api.post(
                "/mining/claim",
                human_solver=self.obtain_human_pass,
            )

            if result.get("success") is not False:
                # Sukses
                self._apply_result(result)
                claimed = result.get("claimed", pending)
                log_info(self.account_id,
                         f"Claim mining SUKSES +{claimed} VIC (attempt {attempt})")
                await activity(self.account_id, "MINING", "SUCCESS",
                               f"+{claimed} VIC")
                return

            err = str(result.get("error") or "").lower()

            # Cek apakah error sementara
            is_transient = (
                "could not verify" in err
                or "try again" in err
                or "temporarily" in err
                or "503" in err
                or "service unavailable" in err
                or "on-chain holding" in err
            )

            if not is_transient:
                # Error permanen — skip
                log_warn(self.account_id,
                         f"Claim mining gagal (non-transient): {err[:80]}")
                await activity(self.account_id, "MINING", "FAILED", err[:60])
                return

            # Error sementara — retry dengan delay random
            if attempt < MINING_CLAIM_RETRY_MAX:
                delay = random.uniform(
                    MINING_CLAIM_RETRY_DELAY_MIN,
                    MINING_CLAIM_RETRY_DELAY_MAX,
                )
                log_warn(self.account_id,
                         f"Claim mining 503 (attempt {attempt}/{MINING_CLAIM_RETRY_MAX}), "
                         f"retry in {delay:.0f}s: {err[:60]}")
                await activity(self.account_id, "MINING", "RETRY",
                               f"attempt {attempt}/{MINING_CLAIM_RETRY_MAX} | wait {delay:.0f}s")

                # Countdown di dashboard
                remaining = int(delay)
                while remaining > 0:
                    await asyncio.sleep(min(5, remaining))
                    remaining -= 5

        # Semua retry habis
        log_warn(self.account_id,
                 f"Claim mining GAGAL setelah {MINING_CLAIM_RETRY_MAX} percobaan")
        await activity(self.account_id, "MINING", "FAILED",
                       f"Gagal setelah {MINING_CLAIM_RETRY_MAX} percobaan")

    async def complete_tutorial(self):
        if self.user().get("tutorialDone"):
            return
        result = await self.api.post("/me/tutorial", human_solver=self.obtain_human_pass)
        if result.get("success") is False:
            return
        self._apply_result(result)

    async def check_in(self):
        if self.state.get("checkIn", {}).get("claimedToday"):
            await activity(self.account_id, "TASK", "SKIP", "Check-in: sudah")
            return
        result = await self.api.post("/checkin", human_solver=self.obtain_human_pass)
        if result.get("success") is False:
            await activity(self.account_id, "TASK", "FAILED",
                           f"Check-in: {str(result.get('error'))[:50]}")
            return
        self._apply_result(result)
        await activity(self.account_id, "TASK", "SUCCESS",
                       f"Check-in Day {result.get('streak')} +{result.get('reward')} VIC")

    def _is_task_qualified(self, task: dict) -> bool:
        user = self.user()
        kind = task.get("kind")
        if kind == "wallet_connect":
            return bool(user.get("walletAddress"))
        if kind == "onchain_hold":
            return (bool(user.get("walletAddress")) and
                    float(user.get("walletBalance") or 0) >= float(task.get("minHolding") or 0))
        if kind == "invite_friends":
            return int(self.referral().get("walletReferralsCount") or 0) >= int(task.get("minReferrals") or 0)
        if kind == "reach_level":
            return int(self.mining().get("level") or 0) >= int(task.get("minLevel") or 0)
        return True

    async def complete_tasks(self) -> int:
        result = await self.api.get("/tasks", human_solver=self.obtain_human_pass)
        tasks_data = result
        all_tasks = result.get("tasks", [])
        tasks = [t for t in all_tasks
                 if t.get("status") == "open" and self._is_task_qualified(t)]

        next_reset = find_next_task_reset(tasks_data)

        log_info(self.account_id, f"Task board: {len(all_tasks)} task total")
        for t in all_tasks:
            status = t.get("status", "?")
            title = t.get("title", "?").strip()
            reward = t.get("reward", 0)
            available = t.get("availableAt") or "-"
            log_info(self.account_id,
                     f"  [{status:9}] {title} (+{reward} VIC) reset={available}")

        if not tasks:
            log_info(self.account_id, "Tidak ada task open, skip klaim")
            await activity(self.account_id, "TASK", "SKIP", "Tidak ada task open")
            return next_reset

        log_info(self.account_id, f"Akan klaim {len(tasks)} task open")
        total_reward = 0

        for task in tasks:
            title = task.get("title", "").strip()
            reward = task.get("reward", 0)
            kind = task.get("kind")
            url = task.get("url", "")
            log_info(self.account_id, f"Mulai klaim: '{title}' (+{reward} VIC)")

            # Auto-join Telegram channel
            if kind == "telegram_channel" and url:
                log_info(self.account_id, f"Auto-join channel: {url}")
                await activity(self.account_id, "TASK", "RUNNING",
                               f"Join {url[:35]}...")
                await self.join_telegram_channel(url)
                await asyncio.sleep(3)

            # Dwell time
            if kind in ("link_visit", "telegram_channel"):
                dwell = random.uniform(TASK_DWELL_MIN, TASK_DWELL_MAX)
                for remaining in range(int(dwell), 0, -1):
                    await activity(self.account_id, "TASK", "WAIT",
                                   f"{title[:35]} | dwell {remaining:02d}s")
                    await asyncio.sleep(1)

            result = await self.api.post("/tasks/claim", {"taskId": task["taskId"]},
                                          human_solver=self.obtain_human_pass)
            if result.get("success") is False:
                err = str(result.get('error'))[:80]
                log_warn(self.account_id, f"Task '{title}' GAGAL: {err}")
                await activity(self.account_id, "TASK", "FAILED",
                               f"{title[:35]} | {err[:35]}")
            else:
                self._apply_result(result)
                reward_val = float(task.get("reward") or 0)
                total_reward += reward_val
                log_info(self.account_id, f"Task '{title}' SUKSES +{reward_val} VIC")
                await activity(self.account_id, "TASK", "SUCCESS",
                               f"{title[:35]} +{reward_val} VIC")
            await asyncio.sleep(3)

        log_info(self.account_id,
                 f"Total task diklaim: {len(tasks)} | reward: +{total_reward:.2f} VIC")
        await activity(self.account_id, "TASK", "SUCCESS",
                       f"{len(tasks)} task | +{total_reward:.2f} VIC")
        return next_reset

    async def show_squad(self):
        result = await self.api.get("/friends", human_solver=self.obtain_human_pass)
        friends = result.get("friends", [])
        r = self.referral()
        await activity(
            self.account_id, "SQUAD", "OK",
            f"{r.get('referralsCount',0)} ref | "
            f"{r.get('walletReferralsCount',0)} wallet | "
            f"{r.get('eligibleCount',0)} qualified",
        )
        for f in friends[:3]:
            await activity(
                self.account_id, "SQUAD", "OK",
                f"{f.get('name','-')[:18]} | Lv{f.get('level')} | "
                f"wallet={'Y' if f.get('walletConnected') else 'N'}",
            )

    async def claim_squad_rewards(self):
        r = self.referral()
        claims = [
            ("hiring bonus", r.get("unclaimedBonus"), "/referral/claim-bonus"),
            ("commission", r.get("unclaimedCommission"), "/referral/claim-commission"),
        ]
        for label, amount, path in claims:
            if not amount or float(amount) <= 0:
                continue
            result = await self.api.post(path, human_solver=self.obtain_human_pass)
            if result.get("success") is False:
                await activity(self.account_id, "SQUAD", "FAILED",
                               f"{label}: {str(result.get('error'))[:40]}")
            else:
                self._apply_result(result)
                claimed = result.get('claimed', amount)
                await activity(self.account_id, "SQUAD", "SUCCESS",
                               f"{label}: +{claimed} VIC")
            await asyncio.sleep(2)

    async def get_withdrawals(self):
        result = await self.api.get(
            f"/transactions?limit={WD_HISTORY_LIMIT}",
            human_solver=self.obtain_human_pass,
        )
        return [t for t in result.get("transactions", []) if t.get("type") == "Withdraw"]

    async def get_pending_withdrawals(self):
        return [w for w in await self.get_withdrawals()
                if w.get("status") in WD_PENDING_STATUSES]

    def is_withdrawal_eligible(self) -> bool:
        v = self.verify()
        age = v.get("walletAgeDays")
        return (
            bool(v.get("verified"))
            and not v.get("underReview")
            and age is not None
            and float(age) >= float(v.get("minWalletAgeDays") or 0)
        )

    def get_minimum_withdrawal(self) -> float:
        return float(self.config().get("withdrawMin") or WD_MIN_DEFAULT)

    def get_withdrawal_fee(self) -> float:
        return float(self.config().get("withdrawFee") or WD_FEE_DEFAULT)

    async def withdraw(self):
        user = self.user()
        destination = user.get("walletAddress")
        if not destination:
            await activity(self.account_id, "WITHDRAW", "SKIP",
                           "Wallet belum terhubung")
            return
        if not self.is_withdrawal_eligible():
            v = self.verify()
            reason = (
                "belum terverifikasi" if not v.get("verified")
                else "under review" if v.get("underReview")
                else f"umur wallet < {v.get('minWalletAgeDays')} hari"
            )
            await activity(self.account_id, "WITHDRAW", "SKIP", reason)
            return
        if await self.get_pending_withdrawals():
            await activity(self.account_id, "WITHDRAW", "SKIP",
                           "Masih ada pending")
            return

        balance = Decimal(str(user.get("inAppBalance") or 0))
        minimum = Decimal(str(self.get_minimum_withdrawal()))
        required = minimum + Decimal(str(WD_BUFFER))
        if balance < required:
            await activity(self.account_id, "WITHDRAW", "SKIP",
                           f"Balance {balance} < {required}")
            return

        active_level = int(self.mining().get("level") or 0)
        holding_after = Decimal(str(self.state.get("holding") or 0)) - balance
        level_after = find_miner_level_for_holding(max(holding_after, 0), True)
        warning = ""
        if level_after < active_level:
            warning = f" | ⚠️ Lv {active_level}→{level_after}"

        amount = balance
        await activity(self.account_id, "WITHDRAW", "REQUEST",
                       f"Request {amount} VIC → {destination[:20]}...{warning}")
        result = await self.api.post("/withdraw", {"amount": float(amount)},
                                      human_solver=self.obtain_human_pass)
        if result.get("success") is False:
            await activity(self.account_id, "WITHDRAW", "FAILED",
                           str(result.get('error'))[:60])
            return
        self._apply_result(result)
        received = max(amount - Decimal(str(self.get_withdrawal_fee())), 0)
        await activity(self.account_id, "WITHDRAW", "SUCCESS",
                       f"{amount} VIC → diterima ~{received}")

    async def update_account_row(self, status="READY"):
        mining = self.mining()
        user = self.user()
        verify = self.verify()
        level = int(mining.get("level") or 0)
        speed = get_miner_speed(level)
        daily = get_miner_daily_output(level)
        pending = self.get_mined_amount()
        balance = user.get("inAppBalance", 0)
        verified = bool(verify.get("verified"))
        detail = (
            f"Lv={level} | Speed={float(speed):.2f} TH/s | "
            f"Daily={float(daily):.2f} VIC | Bal={float(balance):.4f} | "
            f"Pending={float(pending):.4f} | Verified={'Y' if verified else 'N'}"
        )
        await activity(self.account_id, "ACCOUNT", status, detail)

    async def process(self, state: AccountState) -> int:
        await self.connect(require_login=True)
        await self.login()
        await self.load_state()

        balance_before = float(self.user().get("inAppBalance") or 0)
        await self.update_account_row("READY")

        await self.complete_tutorial()
        await self.check_in()
        await self.claim_mining()

        next_task_reset = await self.complete_tasks()

        await self.show_squad()
        await self.claim_squad_rewards()
        await self.withdraw()

        await self.load_state()
        balance_after = float(self.user().get("inAppBalance") or 0)
        level_after = int(self.mining().get("level") or 0)
        gain = balance_after - balance_before

        state.last_balance = balance_after
        state.last_level = level_after
        state.cycles_run += 1
        state.last_run_ts = int(time.time())

        await self.update_account_row("READY")
        await activity(self.account_id, "ACCOUNT", "SUCCESS",
                       f"Cycle selesai | {balance_before:.4f} → {balance_after:.4f} VIC (+{gain:.4f})")

        return next_task_reset


# =====================================================================
# GET PASS MODE — Chromium bundled
# =====================================================================

async def get_pass_mode(account_id: str):
    print(f"\n🔑 Get Pass — {account_id}\n")

    init_data = None
    temp_client = VictorsClient(account_id)
    cached_init = temp_client._load_cached_initdata()

    if cached_init:
        init_data = cached_init
        sisa = _initdata_age_minutes(cached_init)
        await activity(account_id, "AUTH", "RUNNING",
                       f"Pakai initData cache ({sisa}m)")
        print(f"✅ initData cache masih fresh, skip fetch Telegram")
    else:
        await activity(account_id, "AUTH", "RUNNING", "Fetch initData baru...")
        print(f"🔄 initData expired/tidak ada, fetch ulang...")

        try:
            await temp_client.connect(require_login=True)
            init_data = await temp_client.fetch_webapp_query()
            print(f"✅ initData fresh: {len(init_data)} chars")
        except SystemExit:
            await activity(account_id, "AUTH", "FAILED", "Fetch initData gagal")
            raise RuntimeError(f"Fetch initData gagal untuk {account_id}")
        except Exception as e:
            await activity(account_id, "AUTH", "FAILED",
                           f"Fetch initData gagal: {str(e)[:40]}")
            print(f"❌ Fetch initData gagal: {e}")
            raise RuntimeError(f"Fetch initData gagal: {e}")
        finally:
            await temp_client.close()

    if not init_data:
        await activity(account_id, "AUTH", "FAILED", "initData kosong")
        print("❌ initData kosong")
        raise RuntimeError("initData kosong")

    await activity(account_id, "AUTH", "RUNNING", "Buka browser...")

    profile_dir = BROWSER_PROFILES_DIR / account_id
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        from patchright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright

    webapp_url = (
        f"{APP_URL}/"
        f"#tgWebAppData={quote(init_data, safe='')}"
        f"&tgWebAppVersion=7.0&tgWebAppPlatform=android"
    )

    captured = {"human_pass": None}

    async with async_playwright() as p:
        print(f"🚀 Buka Chromium...")

        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=get_launch_args(),
        )
        page = await context.new_page()

        if TURNSTILE_WINDOW_MODE == "minimize":
            await asyncio.sleep(1.5)
            if minimize_windows_browser():
                print("   🗕 Browser di-minimize")

        async def on_request(request):
            if captured["human_pass"]:
                return
            try:
                if "server.victors.company" not in request.url:
                    return
                hp = request.headers.get("x-human-pass") or request.headers.get("X-Human-Pass")
                if hp and hp.count(".") >= 2:
                    captured["human_pass"] = hp
                    await activity(account_id, "AUTH", "SUCCESS",
                                   "X-Human-Pass ter-intercept!")
                    print(f"\n🎯 X-Human-Pass ter-intercept!")
            except Exception:
                pass

        page.on("request", lambda r: asyncio.create_task(on_request(r)))

        print(f"🌐 Buka {APP_URL}...")
        await activity(account_id, "AUTH", "RUNNING", "Buka WebApp...")

        try:
            await page.goto(webapp_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"⚠️  Goto: {e}")

        if TURNSTILE_WINDOW_MODE == "minimize":
            await asyncio.sleep(1)
            minimize_windows_browser("app.victors.company")
            minimize_windows_browser("victors")
            minimize_windows_browser("chromium")

        await activity(account_id, "AUTH", "RUNNING",
                       "Menunggu dashboard / intercept...")

        start = time.time()
        while time.time() - start < 60:
            if captured["human_pass"]:
                break
            try:
                done = await page.evaluate("""
                    () => {
                        const c = !!document.querySelector('canvas');
                        const w = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
                        return c && !w;
                    }
                """)
                if done:
                    await activity(account_id, "AUTH", "RUNNING",
                                   "Dashboard OK, trigger request...")
                    break
            except Exception:
                pass
            elapsed = int(time.time() - start)
            await activity(account_id, "AUTH", "RUNNING",
                           f"Menunggu verifikasi... ({elapsed}s)")
            await asyncio.sleep(1)

        if not captured["human_pass"]:
            await activity(account_id, "AUTH", "RUNNING",
                           "Klik menu trigger /api/me...")
            try:
                vp = page.viewport_size or {"width": 1280, "height": 720}
                cx = vp["width"] // 2
                positions = [
                    (cx, vp["height"] - 40),
                    (vp["width"] // 4, vp["height"] - 40),
                    (vp["width"] * 3 // 4, vp["height"] - 40),
                    (cx, vp["height"] // 2),
                ]
                for _ in range(3):
                    if captured["human_pass"]:
                        break
                    for x, y in positions:
                        if captured["human_pass"]:
                            break
                        try:
                            await page.mouse.click(x, y)
                        except Exception:
                            pass
                        await asyncio.sleep(1)
            except Exception:
                pass

        human_pass = captured["human_pass"]

        try:
            await context.close()
        except Exception:
            pass

        if not human_pass:
            await activity(account_id, "AUTH", "FAILED", "humanPass tidak didapat")
            print("❌ Gagal dapat humanPass")
            raise RuntimeError("Gagal dapat humanPass")

        parts = human_pass.split(".")
        expires_at = int(parts[1]) if len(parts) > 1 else int(time.time()) + 86400

        pass_path = SESSIONS_DIR / f"{account_id}.pass"
        pass_path.write_text(json.dumps({
            "humanPass": human_pass,
            "expiresAt": expires_at - 600,
        }, indent=2), encoding="utf-8")

        sisa_jam = (expires_at - time.time()) / 3600
        await activity(account_id, "AUTH", "SUCCESS", f"Pass OK ({sisa_jam:.1f}h)")
        print(f"✅ Pass tersimpan — expires {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}")


async def get_pass_all_mode():
    accounts = sorted(p.stem for p in SESSIONS_DIR.glob("acc_*.session"))
    if not accounts:
        print("❌ Tidak ada akun")
        sys.exit(1)
    for idx, acc in enumerate(accounts, 1):
        print(f"\n[{idx}/{len(accounts)}] {acc}")
        try:
            await get_pass_mode(acc)
        except SystemExit:
            continue
        except Exception as e:
            print(f"❌ {acc}: {e}")


# =====================================================================
# ADD ACCOUNT MODE
# =====================================================================

async def add_account_mode():
    print()
    print("=" * 70)
    print("  ➕ TAMBAH AKUN BARU")
    print("=" * 70)
    print()

    existing = sorted(p.stem for p in SESSIONS_DIR.glob("acc_*.session"))
    next_num = 1
    while f"acc_{next_num:03d}" in existing:
        next_num += 1
    account_id = f"acc_{next_num:03d}"

    print(f"Akun berikutnya: {account_id}")
    print()
    confirm = input("Lanjut? (y/n): ").strip().lower()
    if confirm != "y":
        print("Dibatalkan.")
        return

    client = VictorsClient(account_id)
    try:
        await client.connect(require_login=True)
        print()
        print("📥 Fetch initData...")
        try:
            await client.fetch_webapp_query()
            print(f"✅ initData disimpan")
        except Exception as e:
            print(f"⚠️  Gagal fetch initData: {e}")
    finally:
        await client.close()

    print()
    print("🔑 Get pass untuk akun baru...")
    try:
        await get_pass_mode(account_id)
    except Exception as e:
        print(f"⚠️  Get pass gagal: {e}")

    print()
    print("=" * 70)
    print(f"  ✅ {account_id} siap")
    print("=" * 70)


# =====================================================================
# FARMER LOOP
# =====================================================================

async def run_account_cycle(account_id: str, state_mgr: StateManager) -> int:
    state = state_mgr.load(account_id)
    client = VictorsClient(account_id)
    log_info(account_id, "Cycle dimulai")
    try:
        next_reset = await client.process(state)
        return next_reset
    except Exception as e:
        log_error(account_id, "Cycle error", e)
        message = str(e).strip() or type(e).__name__
        await activity(account_id, "ACCOUNT", "ERROR", message[:70])
        return 0
    finally:
        state_mgr.save(state)
        await client.close()


async def run_account_worker(account_id: str, state_mgr: StateManager):
    """Worker per akun: get pass dulu (kalau perlu), lalu loop mining dynamic."""
    pass_path = SESSIONS_DIR / f"{account_id}.pass"
    need_pass = True

    if pass_path.exists():
        try:
            data = json.loads(pass_path.read_text(encoding="utf-8"))
            expires_at = int(data.get("expiresAt", 0))
            if expires_at - time.time() > 2 * 3600:
                sisa = (expires_at - time.time()) / 3600
                await activity(account_id, "AUTH", "OK",
                               f"Pass cache valid ({sisa:.1f}h)")
                need_pass = False
        except Exception:
            pass

    if need_pass:
        await activity(account_id, "AUTH", "REFRESH", "Get pass dulu...")
        for attempt in range(2):
            try:
                await get_pass_mode(account_id)
                break
            except SystemExit:
                await activity(account_id, "AUTH", "FAILED",
                               f"Get pass gagal (percobaan {attempt + 1}/2)")
                await asyncio.sleep(5)
            except Exception as e:
                await activity(account_id, "AUTH", "FAILED", str(e)[:50])
                log_warn(account_id, f"Get pass gagal (percobaan {attempt + 1}/2): {e}")
                await asyncio.sleep(5)
        else:
            log_warn(account_id, "Get pass gagal 2x, worker tetap jalan tanpa pass")

    while True:
        next_reset = await run_account_cycle(account_id, state_mgr)

        now = int(time.time())
        default_wait = CYCLE_INTERVAL

        if next_reset and next_reset > now:
            wait_secs = next_reset - now
            wait_secs = min(wait_secs, default_wait)
            wait_secs += 30
            log_info(account_id,
                     f"Next task reset in {wait_secs}s ({wait_secs/3600:.1f}h)")
        else:
            wait_secs = default_wait
            log_info(account_id, f"Tidak ada task reset, tunggu {wait_secs/3600:.1f}h")

        remaining = wait_secs
        while remaining > 0:
            pass_path = SESSIONS_DIR / f"{account_id}.pass"
            if pass_path.exists():
                try:
                    data = json.loads(pass_path.read_text(encoding="utf-8"))
                    expires_at = int(data.get("expiresAt", 0))
                    sisa_jam = (expires_at - time.time()) / 3600
                    if 0 < sisa_jam < HUMAN_PASS_AUTO_REFRESH_HOURS:
                        log_info(account_id,
                                 f"Pass hampir expired ({sisa_jam:.1f}h), auto refresh")
                        await activity(account_id, "AUTH", "REFRESH",
                                       f"Auto refresh ({sisa_jam:.1f}h left)")
                        try:
                            await get_pass_mode(account_id)
                        except Exception as e:
                            log_warn(account_id, f"Auto refresh gagal: {e}")
                except Exception:
                    pass

            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            await activity(account_id, "ACCOUNT", "WAIT",
                           f"Next cycle in {hours:02d}:{minutes:02d}:{seconds:02d}")
            await asyncio.sleep(60)
            remaining -= 60


async def _staggered_worker(account_id: str, state_mgr: StateManager, delay: int):
    if delay > 0:
        await asyncio.sleep(delay)
    await run_account_worker(account_id, state_mgr)


# =====================================================================
# MAIN
# =====================================================================

def get_existing_accounts() -> list[str]:
    return sorted(p.stem for p in SESSIONS_DIR.glob("acc_*.session"))


async def ensure_accounts() -> list[str]:
    accounts = get_existing_accounts()
    if accounts:
        return accounts

    print()
    print("=" * 70)
    print("  Belum ada akun. Tambah akun dulu:")
    print(f"    python {Path(sys.argv[0]).name} --add")
    print("=" * 70)
    return []


async def run_farmer():
    log_info("main", "Main loop dimulai")
    print()
    print("=" * 70)
    print("  👷 VICTOR'S COMPANY FARMER — AUTO MODE")
    print("=" * 70)
    print()

    accounts = await ensure_accounts()
    if not accounts:
        sys.exit(0)

    DASHBOARD.accounts = accounts
    for account in accounts:
        DASHBOARD.register(account)

    DASHBOARD.start()
    DASHBOARD.render()

    try:
        state_mgr = StateManager(DATA_DIR)
        tasks = []
        for idx, acc in enumerate(accounts):
            delay = idx * STAGGER_SECONDS
            tasks.append(_staggered_worker(acc, state_mgr, delay))
        await asyncio.gather(*tasks)
    except SystemExit:
        log_warn("main", "Ada worker yang exit — lanjut worker lain")
    except Exception as e:
        log_error("main", "run_farmer exception", e)
    finally:
        DASHBOARD.stop()
        log_info("main", "Main loop selesai")


def print_help():
    print(__doc__)
    print()
    print("Contoh:")
    print("  python vic.py --add          → tambah akun baru")
    print("  python vic.py                → start farmer")
    print("  python vic.py pass acc_001   → get pass 1 akun")
    print("  python vic.py pass-all       → get pass semua akun")


if __name__ == "__main__":
    try:
        args = sys.argv[1:]

        if not args:
            asyncio.run(run_farmer())
        elif args[0] in ("--add", "add"):
            asyncio.run(add_account_mode())
        elif args[0] == "pass":
            if len(args) < 2:
                print("Usage: python vic.py pass <account_id>")
                sys.exit(1)
            asyncio.run(get_pass_mode(args[1]))
        elif args[0] == "pass-all":
            asyncio.run(get_pass_all_mode())
        elif args[0] in ("-h", "--help", "help"):
            print_help()
        else:
            print(f"❌ Argumen tidak dikenal: {args[0]}")
            print_help()
            sys.exit(1)

    except KeyboardInterrupt:
        LOGGER.info("Bot dihentikan oleh user")
        print()
        print("Bot dihentikan.")
    except Exception as e:
        LOGGER.critical(f"FATAL: {type(e).__name__}: {e}")
        LOGGER.critical(traceback.format_exc())
        print(f"\n❌ Bot crash: {e}")
        print(f"Cek detail di: {LOG_PATH}")
        raise
