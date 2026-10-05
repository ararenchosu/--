import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
import asyncio
import json
import os
import re
import time
import unicodedata
import random
from datetime import datetime, timezone, timedelta, time as dtime
from cogs.ywp_auto import Client, login_email, RC, YPOINT_ITEM_ID, parse_item_rows, parse_user_data
# ============================================================
# JST
# ============================================================
JST = timezone(timedelta(hours=9))
# ============================================================
# データ
# ============================================================
DATA_DIR = "data"
SESSION_FILE = f"{DATA_DIR}/sessions.json"
LOOP_FILE = f"{DATA_DIR}/loops.json"
PANEL_FILE = f"{DATA_DIR}/panel.json"
BENCH_FILE = f"{DATA_DIR}/bench.json"
DAILY_FILE = f"{DATA_DIR}/daily.json"
SLOT_FILE = f"{DATA_DIR}/slots.json"
QUEUE_FILE = f"{DATA_DIR}/queue.json"
DEBUG_BUY_FILE = f"{DATA_DIR}/debug_buyhitodama.json"
DEBUG_GAMEEND_FILE = f"{DATA_DIR}/debug_gameend.json"
# ============================================================
# 設定
# ============================================================
MAX_CONCURRENT_LOOPS = 10
MAX_SLOTS = 10
HITODAMA_THRESHOLD = 5
HITODAMA_RESUME_MIN = 5
AUTO_BUY_HITODAMA = True
AUTO_BUY_GOODS_ID = 1001
AUTO_BUY_GOODS_IDS = [1001]
AUTO_BUY_COST_YM = 1000
AUTO_BUY_MAX_PER_LOOP = 9999
AUTO_BUY_KEEP_YMONEY = 5000
AUTO_BUY_HITODAMA_GAIN = 2
BENCH_MAX_STAGES = 8
BENCH_MAX_SAMPLES = 10
DAILY_REPORT_ENABLED = True
DAILY_REPORT_HOUR = 23
DAILY_REPORT_MINUTE = 55
REQUEST_DELAY_MIN = 2.5
REQUEST_DELAY_MAX = 3.0
COOLDOWN_MIN = 2.5
COOLDOWN_MAX = 3.0
ODD_HOUR_REST_ENABLED = True
ODD_HOUR_REST_MIN = 29
ODD_HOUR_REST_DURATION = 300
EVENT_SKIP_CODES = (5, 100, 1303)
RETRY_CODES = (4, 32, 101, 102)
RETRY_WAITS = [4, 5, 5]
LOCKED_RC = 5
LOCKED_STAGE_LIMIT = 3
MAX_CONSECUTIVE_ERRORS = 4
_session_lock = asyncio.Lock()
_loop_lock = asyncio.Lock()
_queue_lock = asyncio.Lock()
_panel_hitodama_cache = {}
_bot_ref = None
# ============================================================
# ステージデータ
# ============================================================
STAGE_LIST = [
    # 通常ステージ
    ("通常 1-1", "100101"), ("通常 1-2", "100102"), ("通常 1-3", "100103"),
    ("通常 1-4", "100104"), ("通常 1-5", "100105"), ("通常 1-6", "100106"),
    ("通常 1-7", "100107"), ("通常 1-8", "100108"), ("通常 1-9", "100109"),
    ("通常 1-10", "100110"), ("通常 1-11", "100111"), ("通常 1-12", "100112"),
    ("通常 1-13", "100113"), ("通常 1-14", "100114"), ("通常 1-15", "100115"),
    # イベントステージ
    ("イベント 1", "2980101"), ("イベント 2", "2980102"), ("イベント 3", "2980103"),
    ("イベント 4", "2980104"), ("イベント 5", "2980105"), ("イベント 6", "2980106"),
    ("イベント 7", "2980107"), ("イベント 8", "2980108"), ("イベント 9", "2980109"),
    ("イベント 10", "2980110"), ("イベント 11", "2980111"), ("イベント 12", "2980112"),
    ("イベント 13", "2980113"), ("イベント 14", "2980201"), ("イベント 15", "2980202"),
    ("イベント 16", "2980203"), ("イベント 17", "2980204"), ("イベント 18", "2980205"),
    ("イベント 19", "2980206"), ("イベント 20", "2980207"), ("イベント 21", "2980208"),
    ("イベント 22", "2980209"), ("イベント 23", "2980210"), ("イベント 24", "2980211"),
    ("イベント 25", "2980212"), ("イベント 26", "2980213"), ("イベント 27", "2980214"),
    ("イベント 28", "2980215"), ("イベント 29", "2980301"), ("イベント 30", "2980302"),
    ("イベント 31", "2980303"), ("イベント 32", "2980304"), ("イベント 33", "2980305"),
    ("イベント 34", "2980306"), ("イベント 35", "2980307"), ("イベント 36", "2980308"),
    ("イベント 37", "2980309"), ("イベント 38", "2980310"), ("イベント 39", "2980311"),
    ("イベント 40", "2980312"), ("イベント 41", "29803013"), ("イベント 42", "29803014"),
    ("イベント 43", "2980314"),
    # ウラステージ
    ("ウラ 1-1", "2980401"), ("ウラ 1-2", "2980402"), ("ウラ 1-3", "2980403"),
    ("ウラ 1-4", "2980404"), ("ウラ 1-5", "2980405"),
    # 封印ボス
    ("封印ボス", "2980406"),
]
# ============================================================
# JSON キャッシュ
# ============================================================
_json_cache = {}
def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
def load_json(path, default=None):
    ensure_dir()
    if not os.path.exists(path):
        return default or {}
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return default or {}
    cached = _json_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return default or {}
    _json_cache[path] = (mtime, data)
    return data
def save_json(path, data):
    ensure_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        _json_cache[path] = (os.path.getmtime(path), data)
    except OSError:
        _json_cache.pop(path, None)
def load_loops() -> dict:
    return load_json(LOOP_FILE, {})
def save_loops(data):
    save_json(LOOP_FILE, data)
async def save_loops_async(data):
    async with _loop_lock:
        save_loops(data)
# ============================================================
# 複数アカウント管理
# ============================================================
def _migrate_session(sdata: dict) -> dict:
    if "accounts" in sdata:
        return sdata
    if "udkey" not in sdata:
        return {"accounts": [], "active_index": 0}
    acc = {
        "email": sdata.get("email", ""),
        "password": sdata.get("password", ""),
        "player_id": str(sdata.get("userId", "")),
        "player_name": sdata.get("playerName", "不明"),
        "udkey": sdata["udkey"],
        "gdkey": sdata["gdkey"],
        "userId": sdata["userId"],
        "token": sdata["token"],
        "mst": sdata.get("mst", 16897),
        "saved_at": sdata.get("saved_at", ""),
    }
    return {"accounts": [acc], "active_index": 0}
def load_sessions() -> dict:
    return load_json(SESSION_FILE, {})
def save_sessions(data):
    save_json(SESSION_FILE, data)
async def save_sessions_async(data):
    async with _session_lock:
        save_sessions(data)
def get_user_session(user_id: int) -> dict:
    sessions = load_sessions()
    sdata = sessions.get(str(user_id))
    if not sdata:
        return {"accounts": [], "active_index": 0}
    return _migrate_session(sdata)
def get_user_accounts(user_id: int) -> list:
    return get_user_session(user_id).get("accounts", [])
def get_active_account(user_id: int) -> dict | None:
    sess = get_user_session(user_id)
    accounts = sess.get("accounts", [])
    if not accounts:
        return None
    idx = sess.get("active_index", 0)
    if idx >= len(accounts):
        idx = 0
    return accounts[idx]
def get_active_id(user_id: int) -> str | None:
    sess = get_user_session(user_id)
    accounts = sess.get("accounts", [])
    if not accounts:
        return None
    idx = sess.get("active_index", 0)
    if idx >= len(accounts):
        idx = 0
    acc = accounts[idx]
    return str(acc.get("player_id") or acc.get("userId") or "")
def get_session(user_id: int, account_id=None) -> dict | None:
    if account_id is None:
        return get_active_account(user_id)
    accounts = get_user_accounts(user_id)
    for acc in accounts:
        if str(acc.get("player_id")) == str(account_id) or str(acc.get("userId")) == str(account_id):
            return acc
    return None
def get_accounts(user_id: int) -> dict:
    out = {}
    for acc in get_user_accounts(user_id):
        gid = str(acc.get("player_id") or acc.get("userId") or "")
        if gid:
            out[gid] = acc
    return out
def set_active_index(user_id: int, index: int):
    sessions = load_sessions()
    uid = str(user_id)
    sess = _migrate_session(sessions.get(uid, {}))
    sess["active_index"] = index
    sessions[uid] = sess
    save_sessions(sessions)
async def add_account(user_id: int, client: Client, player_name: str):
    store = load_sessions()
    uid = str(user_id)
    sess = _migrate_session(store.get(uid, {}))
    accounts = sess.get("accounts", [])
    gid = str(client.userId)
    new_acc = {
        "email": "",
        "password": "",
        "player_id": gid,
        "player_name": player_name,
        "udkey": client.udkey,
        "gdkey": client.gdkey,
        "userId": client.userId,
        "token": client.token,
        "mst": client.mst,
        "saved_at": datetime.now(JST).isoformat(),
    }
    found = None
    for i, acc in enumerate(accounts):
        if str(acc.get("player_id")) == gid:
            found = i
            break
    if found is not None:
        accounts[found] = new_acc
        sess["active_index"] = found
    else:
        accounts.append(new_acc)
        sess["active_index"] = len(accounts) - 1
    sess["accounts"] = accounts
    store[uid] = sess
    await save_sessions_async(store)
    return gid
async def set_active(user_id: int, account_id: str) -> bool:
    sessions = load_sessions()
    uid = str(user_id)
    sess = _migrate_session(sessions.get(uid, {}))
    accounts = sess.get("accounts", [])
    for i, acc in enumerate(accounts):
        if str(acc.get("player_id")) == str(account_id) or str(acc.get("userId")) == str(account_id):
            sess["active_index"] = i
            sessions[uid] = sess
            await save_sessions_async(sessions)
            return True
    return False
async def remove_account(user_id: int, account_id: str) -> bool:
    sessions = load_sessions()
    uid = str(user_id)
    sess = _migrate_session(sessions.get(uid, {}))
    accounts = sess.get("accounts", [])
    new_accounts = [
        acc for acc in accounts
        if str(acc.get("player_id")) != str(account_id)
        and str(acc.get("userId")) != str(account_id)
    ]
    if len(new_accounts) == len(accounts):
        return False
    if not new_accounts:
        sessions.pop(uid, None)
    else:
        idx = sess.get("active_index", 0)
        if idx >= len(new_accounts):
            idx = 0
        sess["accounts"] = new_accounts
        sess["active_index"] = idx
        sessions[uid] = sess
    await save_sessions_async(sessions)
    return True
async def remove_all_accounts(user_id: int) -> int:
    sessions = load_sessions()
    uid = str(user_id)
    if uid not in sessions:
        return 0
    n = len(sessions[uid].get("accounts", [])) if "accounts" in sessions[uid] else 1
    sessions.pop(uid, None)
    await save_sessions_async(sessions)
    return n
async def update_token(user_id: int, account_id: str, client: Client):
    sessions = load_sessions()
    uid = str(user_id)
    sess = _migrate_session(sessions.get(uid, {}))
    accounts = sess.get("accounts", [])
    for acc in accounts:
        if str(acc.get("player_id")) == str(account_id) or str(acc.get("userId")) == str(account_id):
            acc["token"] = client.token
            acc["mst"] = client.mst
            break
    sess["accounts"] = accounts
    sessions[uid] = sess
    await save_sessions_async(sessions)
def upsert_account(user_id: int, email: str, password: str, client: Client):
    sessions = load_sessions()
    uid = str(user_id)
    sess = _migrate_session(sessions.get(uid, {}))
    accounts = sess.get("accounts", [])
    player_id = str(client.userId)
    info = client.info()
    player_name = info.get("playerName", "不明")
    new_acc = {
        "email": email,
        "password": password,
        "player_id": player_id,
        "player_name": player_name,
        "udkey": client.udkey,
        "gdkey": client.gdkey,
        "userId": client.userId,
        "token": client.token,
        "mst": client.mst,
        "saved_at": datetime.now(JST).isoformat(),
    }
    found_idx = None
    for i, acc in enumerate(accounts):
        if acc.get("email") == email and str(acc.get("player_id")) == player_id:
            found_idx = i
            break
    if found_idx is not None:
        accounts[found_idx] = new_acc
        sess["active_index"] = found_idx
    else:
        accounts.append(new_acc)
        sess["active_index"] = len(accounts) - 1
    sess["accounts"] = accounts
    sessions[uid] = sess
    save_sessions(sessions)
    return new_acc
def build_client_from_account(acc: dict) -> Client:
    client = Client(acc["udkey"])
    client.gdkey = acc["gdkey"]
    client.userId = acc["userId"]
    client.token = acc["token"]
    client.mst = acc.get("mst", 16897)
    return client
def make_client(sdata: dict) -> Client:
    return build_client_from_account(sdata)
def update_account_tokens(user_id: int, client: Client):
    sessions = load_sessions()
    uid = str(user_id)
    sess = _migrate_session(sessions.get(uid, {}))
    accounts = sess.get("accounts", [])
    idx = sess.get("active_index", 0)
    if 0 <= idx < len(accounts):
        accounts[idx]["token"] = client.token
        accounts[idx]["mst"] = client.mst
        sess["accounts"] = accounts
        sessions[uid] = sess
        save_sessions(sessions)
def account_busy(account_id: str) -> bool:
    for data in load_loops().values():
        if data.get("status") != "running":
            continue
        if str(data.get("account_id") or "") == str(account_id):
            return True
    return False
def load_panel() -> dict:
    return load_json(PANEL_FILE, {})
def save_panel(data):
    save_json(PANEL_FILE, data)
# ============================================================
# スロット管理
# ============================================================
def set_bot_ref(bot):
    global _bot_ref
    _bot_ref = bot
def load_slots() -> dict:
    data = load_json(SLOT_FILE, {})
    if "slots" not in data:
        data["slots"] = {str(i): None for i in range(MAX_SLOTS)}
    else:
        for i in range(MAX_SLOTS):
            data["slots"].setdefault(str(i), None)
    return data
def save_slots(data):
    save_json(SLOT_FILE, data)
async def update_panel_on_change():
    if _bot_ref is None:
        return
    panel = load_panel()
    for guild_id, data in panel.items():
        try:
            ch_id = int(data["channel_id"])
            channel = _bot_ref.get_channel(ch_id)
            if not channel:
                continue
            msg = await channel.fetch_message(int(data["message_id"]))
            await msg.edit(embed=build_panel_embed(), view=PanelView())
        except Exception as e:
            print(f">>> パネル更新失敗 guild={guild_id}: {e}")
def find_free_slot() -> int | None:
    data = load_slots()
    for i in range(MAX_SLOTS):
        s = data["slots"].get(str(i))
        if not s or s.get("status") not in ("running", "paused_hitodama"):
            return i
    return None
async def assign_slot(job_key: str, user_id: int, job_type: str, stage_info: str) -> int | None:
    data = load_slots()
    for i in range(MAX_SLOTS):
        s = data["slots"].get(str(i))
        if not s or s.get("status") not in ("running", "paused_hitodama"):
            data["slots"][str(i)] = {
                "job_key": job_key,
                "user_id": user_id,
                "type": job_type,
                "stage_info": stage_info,
                "status": "running",
                "started_at": datetime.now(JST).isoformat(),
            }
            save_slots(data)
            await update_panel_on_change()
            return i
    return None
def update_slot(slot_id: int, **kwargs):
    data = load_slots()
    s = data["slots"].get(str(slot_id))
    if s:
        s.update(kwargs)
        save_slots(data)
async def release_slot(slot_id: int):
    data = load_slots()
    data["slots"][str(slot_id)] = None
    save_slots(data)
    await update_panel_on_change()
    asyncio.create_task(process_queue())
def get_slot_status() -> dict:
    data = load_slots()
    running = paused = free = 0
    for i in range(MAX_SLOTS):
        s = data["slots"].get(str(i))
        if not s:
            free += 1
        elif s.get("status") == "running":
            running += 1
        elif s.get("status") == "paused_hitodama":
            paused += 1
    return {"running": running, "paused": paused, "free": free}
# ============================================================
# 予約キュー管理
# ============================================================
def load_queue() -> list:
    data = load_json(QUEUE_FILE, {"queue": []})
    if "queue" not in data:
        data["queue"] = []
    return data["queue"]
def save_queue(queue: list):
    save_json(QUEUE_FILE, {"queue": queue})
async def save_queue_async(queue: list):
    async with _queue_lock:
        save_queue(queue)
async def add_to_queue(user_id: int, job_type: str, stage_info: str, params: dict) -> int:
    queue = load_queue()
    job_key = f"{user_id}_{int(time.time())}_{job_type}"
    entry = {
        "job_key": job_key,
        "user_id": user_id,
        "job_type": job_type,
        "stage_info": stage_info,
        "params": params,
        "created_at": datetime.now(JST).isoformat(),
    }
    queue.append(entry)
    await save_queue_async(queue)
    position = len(queue)
    print(f">>> 予約追加: user={user_id} type={job_type} 順番={position}")
    await update_panel_on_change()
    return position
async def pop_next_queue() -> dict | None:
    queue = load_queue()
    if not queue:
        return None
    entry = queue.pop(0)
    await save_queue_async(queue)
    return entry
async def remove_user_from_queue(user_id: int) -> int:
    queue = load_queue()
    before = len(queue)
    queue = [e for e in queue if e.get("user_id") != user_id]
    removed = before - len(queue)
    if removed:
        await save_queue_async(queue)
        print(f">>> 予約削除: user={user_id} {removed}件")
        await update_panel_on_change()
    return removed
def get_user_queue_position(user_id: int) -> int | None:
    queue = load_queue()
    for i, e in enumerate(queue):
        if e.get("user_id") == user_id:
            return i + 1
    return None
def queue_status() -> dict:
    queue = load_queue()
    by_user = {}
    for e in queue:
        uid = e.get("user_id")
        by_user[uid] = by_user.get(uid, 0) + 1
    return {"total": len(queue), "users": len(by_user)}
# ============================================================
# 予約キューの自動実行
# ============================================================
async def process_queue():
    while True:
        slot_id = find_free_slot()
        if slot_id is None:
            break
        entry = await pop_next_queue()
        if entry is None:
            break
        job_type = entry.get("job_type")
        user_id = entry.get("user_id")
        params = entry.get("params", {})
        print(f">>> 予約実行: user={user_id} type={job_type}")
        try:
            if job_type == "farm":
                asyncio.create_task(run_farm(
                    _bot_ref, None, None, user_id,
                    params["stage_id"], params["count"],
                    params["request_delay"], params["cooldown"],
                    params.get("end_at"),
                    params.get("use_random_rd", True),
                    params.get("use_random_cd", True),
                    params.get("account_id")
                ))
            elif job_type == "progress":
                asyncio.create_task(run_progress(
                    _bot_ref, None, None, user_id,
                    params["start_id"], params["end_id"],
                    params.get("end_at"),
                    params.get("account_id")
                ))
            elif job_type == "event":
                asyncio.create_task(run_event_progress(
                    _bot_ref, None, None, user_id,
                    params["start_id"],
                    params.get("end_at"),
                    params.get("account_id")
                ))
            elif job_type == "bench":
                asyncio.create_task(run_benchmark(
                    _bot_ref, None, None, user_id,
                    params["stage_ids"], params["samples"],
                    params.get("account_id")
                ))
        except Exception as e:
            print(f">>> 予約実行失敗: {e}")
        await asyncio.sleep(0.5)
# ============================================================
# ランダム生成
# ============================================================
def rand_request_delay() -> float:
    return random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
def rand_cooldown() -> float:
    return random.uniform(COOLDOWN_MIN, COOLDOWN_MAX)
# ============================================================
# 奇数時間休憩
# ============================================================
async def check_odd_hour_rest(loop_key=None):
    if not ODD_HOUR_REST_ENABLED:
        return False
    now = datetime.now(JST)
    if now.hour % 2 == 1 and now.minute == ODD_HOUR_REST_MIN:
        print(f">>> 奇数時間休憩開始 ({now.hour:02d}:{now.minute:02d} JST) → {ODD_HOUR_REST_DURATION}秒停止")
        await asyncio.sleep(ODD_HOUR_REST_DURATION)
        print(f">>> 奇数時間休憩終了 → 周回再開")
        return True
    return False
# ============================================================
# 日時パーサ
# ============================================================
def parse_datetime(s: str):
    s = s.strip()
    formats = [
        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    return None
# ============================================================
# 3秒対策
# ============================================================
async def safe_defer(interaction, ephemeral=True, thinking=True):
    if interaction is None:
        return False
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        return True
    except (discord.NotFound, discord.HTTPException):
        return False
async def safe_reply(interaction, **kwargs):
    if interaction is None:
        return
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(**kwargs)
        else:
            return await interaction.response.send_message(**kwargs)
    except (discord.NotFound, discord.HTTPException):
        pass
async def safe_edit_original(interaction, **kwargs):
    if interaction is None:
        return
    try:
        await interaction.edit_original_response(**kwargs)
    except Exception:
        pass
# ============================================================
# ユーザーの古いジョブを整理
# ============================================================
async def cleanup_user_loops(user_id: int):
    loops = load_loops()
    keys_to_delete = []
    for key, data in loops.items():
        if data.get("user_id") != user_id:
            continue
        if data.get("status") in ("stopped", "done", "fatal", "error"):
            keys_to_delete.append(key)
    for key in keys_to_delete:
        del loops[key]
    if keys_to_delete:
        await save_loops_async(loops)
# ============================================================
# ステージパーサ
# ============================================================
def parse_stages(stage_raw: str) -> dict:
    result = {}
    if not stage_raw:
        return result
    for row in str(stage_raw).split("*"):
        if not row:
            continue
        cols = row.split("|")
        if not cols:
            continue
        try:
            sid = int(cols[0])
            if not (1 <= sid <= 99999999):
                continue
            cleared = len(cols) >= 2 and cols[1] == "1"
            result[sid] = {"cols": cols, "cleared": cleared}
        except (ValueError, IndexError):
            pass
    return result
# ============================================================
# ステージ分類
# ============================================================
STAGE_CATEGORIES = [
    {"name": "📖 メインステージ", "pattern": lambda sid: str(sid).startswith(("1001", "1002", "1003"))},
    {"name": "📖 メイン（2章以降）", "pattern": lambda sid: str(sid).startswith("1901")},
    {"name": "🎯 サブステージ", "pattern": lambda sid: str(sid).startswith(("5001", "5002", "5003", "5004",
                                                                            "5005", "5006", "5007", "5008",
                                                                            "5009", "5010", "5011"))},
    {"name": "🎪 イベントステージ", "pattern": lambda sid: str(sid).startswith(("3167", "2970"))},
    {"name": "💪 強敵ステージ", "pattern": lambda sid: str(sid).startswith(("2880", "2890"))},
    {"name": "🌙 夜叉ステージ", "pattern": lambda sid: str(sid).startswith("2900")},
    {"name": "❓ その他", "pattern": lambda sid: True},
]
def categorize_stages(stage_ids: list) -> dict:
    result = {}
    assigned = set()
    for cat in STAGE_CATEGORIES:
        name = cat["name"]
        bucket = []
        for sid in stage_ids:
            if sid in assigned:
                continue
            try:
                if cat["pattern"](sid):
                    bucket.append(sid)
                    assigned.add(sid)
            except Exception:
                pass
        if bucket:
            result[name] = bucket
    return result
# ============================================================
# 同時実行
# ============================================================
def get_running_count() -> int:
    loops = load_loops()
    return sum(1 for data in loops.values() if data.get("status") == "running")
def can_start_loop() -> tuple:
    current = get_running_count()
    return current < MAX_CONCURRENT_LOOPS, current
# ============================================================
# 人魂
# ============================================================
def get_hitodama_detail(client: Client) -> dict:
    try:
        data = parse_user_data(client.save.get("ywp_user_data"))
        paid = int(data.get("hitodama", 0))
        free = int(data.get("freeHitodama", 0))
        return {"paid": paid, "free": free, "total": paid + free,
                "recover_sec": int(data.get("hitodamaRecoverSec", 0))}
    except Exception:
        return {"paid": 999, "free": 0, "total": 999, "recover_sec": 0}
def get_hitodama(client: Client) -> int:
    return get_hitodama_detail(client)["total"]
def get_ymoney(client: Client) -> int:
    try:
        data = client.save.get("ywp_user_data", {})
        if isinstance(data, str):
            data = json.loads(data)
        return int(data.get("ymoney", 0))
    except Exception:
        return 0
def get_items(client: Client) -> dict:
    try:
        return parse_item_rows(client.save.get("ywp_user_item"))
    except Exception:
        return {}
def get_ypoint(client: Client):
    items = get_items(client)
    if not items:
        return None
    return items.get(YPOINT_ITEM_ID, 0)
def fmt_gain(value) -> str:
    if value is None:
        return "?"
    return f"{value:+,}" if value else "0"
def event_point_name(client: Client) -> str:
    try:
        for e in (client.save.get("ywp_mst_event") or []):
            for part in str(e.get("generalStringParam12") or "").split(","):
                if part.startswith("spPointName:"):
                    name = part.split(":", 1)[1].strip()
                    if name:
                        return name
    except Exception:
        pass
    return "イベントP"
class GainTracker:
    def __init__(self, client: Client):
        self.client = client
        self.items_prev = get_items(client)
        self.money_start = get_ymoney(client)
        self.point_name = event_point_name(client)
        self.money_gain = 0
        self.exp_gain = 0
        self.event_point = 0
        self.event_sub_point = 0
        self.score_total = 0
        self.item_gain = {}
        self.last_money = None
        self.counted = 0
        self.live = None
    def _apply_items(self):
        items = get_items(self.client)
        if not items:
            return
        for iid, cnt in items.items():
            diff = cnt - self.items_prev.get(iid, 0)
            if diff:
                self.item_gain[iid] = self.item_gain.get(iid, 0) + diff
        self.items_prev = items
    async def after_battle(self, result, user_id=None):
        if not isinstance(result, dict):
            return
        game = result.get("userGameResultData") or {}
        if self.live is None:
            self.live = bool(game)
            if GAIN_DEBUG_DUMP:
                dump_gameend_debug(result)
        money = game.get("money")
        if isinstance(money, (int, float)):
            self.money_gain += int(money)
            self.last_money = int(money)
            self.counted += 1
        exp = game.get("exp")
        if isinstance(exp, (int, float)):
            self.exp_gain += int(exp)
        score = game.get("score")
        if isinstance(score, (int, float)):
            self.score_total += int(score)
        for key, attr in (("eventPoint", "event_point"), ("eventSubPoint", "event_sub_point")):
            v = result.get(key)
            if isinstance(v, (int, float)) and v:
                setattr(self, attr, getattr(self, attr) + int(v))
        self._apply_items()
    async def refresh(self, batches=None):
        try:
            await asyncio.to_thread(self.client.login, self.client.userId)
        except Exception:
            return
        self._apply_items()
    def per_stage(self):
        if not self.counted:
            return None
        return self.money_gain / self.counted
    def to_dict(self):
        return {
            "money_gain": self.money_gain,
            "money_last": self.last_money,
            "money_counted": self.counted,
            "exp_gain": self.exp_gain,
            "event_point": self.event_point,
            "point_name": self.point_name,
            "event_sub_point": self.event_sub_point,
            "score_total": self.score_total,
            "item_gain": {str(k): v for k, v in self.item_gain.items() if v},
        }
def dump_gameend_debug(result):
    try:
        if os.path.exists(DEBUG_GAMEEND_FILE):
            return
        if not isinstance(result, dict):
            return
        info = {
            "saved_at": datetime.now(JST).isoformat(),
            "top_level_keys": sorted(result.keys()),
            "ywp_user_item": str(result.get("ywp_user_item"))[:2000],
            "ywp_user_data": str(result.get("ywp_user_data"))[:2000],
        }
        save_json(DEBUG_GAMEEND_FILE, info)
    except Exception:
        pass
def apply_gain_to_loop(loop_data: dict, tracker):
    if tracker is not None:
        loop_data.update(tracker.to_dict())
def gain_fields(embed: discord.Embed, data: dict, done: bool = False):
    buy_count = data.get("buy_count")
    if buy_count:
        limit = AUTO_BUY_MAX_PER_LOOP or "∞"
        embed.add_field(
            name="💠 人魂購入",
            value=f"**{buy_count} / {limit}** 回\n-{data.get('buy_ym', 0):,} YM",
            inline=True
        )
    gain = data.get("money_gain")
    if gain is None:
        return embed
    counted = data.get("money_counted") or 0
    last = data.get("money_last")
    avg = (gain / counted) if counted else None
    value = f"**{fmt_gain(gain)}**"
    if isinstance(last, int):
        value += f"\n直近: {last:+,}"
    embed.add_field(name="💰 稼いだマネー", value=value, inline=True)
    embed.add_field(
        name="📐 1ステあたり",
        value=(f"**{avg:,.1f}** マネー" if avg is not None else "計測中..."),
        inline=True
    )
    ep = data.get("event_point") or 0
    if ep:
        sub = data.get("event_sub_point") or 0
        v = f"**{ep:,}**" + (f"\nサブ: {sub:,}" if sub else "")
        name = data.get("point_name") or "イベントP"
        embed.add_field(name=f"🎪 {name}", value=v, inline=True)
    exp = data.get("exp_gain") or 0
    if exp and done:
        embed.add_field(name="⭐ 経験値", value=f"{exp:,}", inline=True)
    drops = {k: v for k, v in (data.get("item_gain") or {}).items() if v}
    if drops and done:
        top = sorted(drops.items(), key=lambda kv: -abs(kv[1]))[:6]
        embed.add_field(
            name="🎁 アイテム増減",
            value=" / ".join(f"`{k}`: {v:+,}" for k, v in top),
            inline=False
        )
    return embed
async def auto_buy_hitodama(client: Client, goods_id: int = None):
    candidates = [goods_id] if goods_id is not None else list(AUTO_BUY_GOODS_IDS)
    attempts = []
    for gid in candidates:
        try:
            rc, result = await asyncio.to_thread(
                client.call, "buyHitodama.nhn", {"goodsId": gid}
            )
            if not isinstance(result, dict):
                result = {}
            rc_code = result.get("resultCode")
            msg = result.get("dialogMsg") or result.get("_error") or result.get("_raw") or ""
            attempts.append({"goodsId": gid, "http": rc, "resultCode": rc_code,
                             "dialogTitle": result.get("dialogTitle", ""),
                             "dialogMsg": str(msg)[:300]})
            if rc_code == 0:
                try:
                    await asyncio.to_thread(client.login, client.userId)
                except Exception:
                    pass
                return True, {"attempts": attempts}
        except Exception as e:
            attempts.append({"goodsId": gid, "error": str(e)[:200]})
    info = {
        "attempts": attempts,
        "saved_at": datetime.now(JST).isoformat(),
        "ymoney": get_ymoney(client),
        "hitodama": get_hitodama_detail(client),
        "hitodamaShopSaleList": client.save.get("hitodamaShopSaleList"),
        "ymoneyShopSaleList": client.save.get("ymoneyShopSaleList"),
        "monthlyPurchasableLeft": client.save.get("monthlyPurchasableLeft"),
    }
    try:
        save_json(DEBUG_BUY_FILE, info)
    except Exception:
        pass
    return False, info
async def try_auto_buy(client: Client, buy_count: int):
    if not AUTO_BUY_HITODAMA:
        return False, {"skipped": "自動購入が OFF"}, buy_count
    if AUTO_BUY_MAX_PER_LOOP and buy_count >= AUTO_BUY_MAX_PER_LOOP:
        return False, {"skipped": f"この周回の購入上限 {AUTO_BUY_MAX_PER_LOOP}回に到達"}, buy_count
    ym = get_ymoney(client)
    if ym - AUTO_BUY_COST_YM < AUTO_BUY_KEEP_YMONEY:
        return False, {"skipped": f"YM残 {ym:,} — 温存ライン {AUTO_BUY_KEEP_YMONEY:,} を割るため見送り"}, buy_count
    ok, info = await auto_buy_hitodama(client)
    if ok:
        buy_count += 1
    return ok, info, buy_count
def describe_buy_failure(info) -> str:
    if info and info.get("skipped"):
        return f"・購入を見送りました: {info['skipped']}"
    if not info or not info.get("attempts"):
        return "不明（レスポンスなし）"
    lines = []
    for a in info["attempts"][:4]:
        if "error" in a:
            lines.append(f"・goodsId `{a['goodsId']}` → 例外: {a['error'][:80]}")
            continue
        rc_code = a.get("resultCode")
        desc = RC.get(rc_code, "未知のコード")
        msg = a.get("dialogMsg") or ""
        line = f"・goodsId `{a['goodsId']}` → rc=`{rc_code}` ({desc})"
        if msg:
            line += f"\n　{msg[:120]}"
        lines.append(line)
    return "\n".join(lines)
# ============================================================
# イベントID遷移
# ============================================================
def next_block_start(current_id: int) -> int:
    s = str(current_id)
    if len(s) < 7:
        return current_id + 1
    block = int(s[-4])
    prefix = s[:-4]
    next_block = block + 1
    return int(f"{prefix}{next_block}001")
# ============================================================
# DM通知View
# ============================================================
class ResumeView(ui.View):
    def __init__(self, user_id, loop_key, stage_id, count, current,
                 request_delay, cooldown, end_at=None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.loop_key = loop_key
        self.stage_id = stage_id
        self.count = count
        self.current = current
        self.request_delay = request_delay
        self.cooldown = cooldown
        self.end_at = end_at
    @ui.button(label="▶️ 周回再開", style=discord.ButtonStyle.success, emoji="▶️", custom_id="hitodama_resume:resume")
    async def resume(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ あなたの通知ではありません。", ephemeral=True)
        if not await safe_defer(interaction):
            return
        acc = get_active_account(self.user_id)
        if not acc:
            return await safe_reply(interaction, content="❌ セッションがありません。", ephemeral=True)
        client = build_client_from_account(acc)
        try:
            await asyncio.to_thread(client.login, acc["userId"])
            update_account_tokens(self.user_id, client)
        except Exception as e:
            return await safe_reply(interaction, content=f"❌ ログイン失敗: `{str(e)[:200]}`", ephemeral=True)
        current_hitodama = get_hitodama(client)
        if current_hitodama < HITODAMA_RESUME_MIN:
            return await safe_reply(
                interaction,
                content=f"❌ 人魂がまだ足りません。\n**現在**: {current_hitodama} / 必要: {HITODAMA_RESUME_MIN}",
                ephemeral=True
            )
        loops = load_loops()
        if self.loop_key in loops:
            loops[self.loop_key]["status"] = "running"
            await save_loops_async(loops)
        remaining = self.count - self.current
        if remaining <= 0:
            return await safe_reply(interaction, content="✅ 周回は既に完了しています。", ephemeral=True)
        embed = discord.Embed(
            title="▶️ 周回を再開します",
            description=f"**人魂**: {current_hitodama}\n**残り回数**: {remaining}回\n**ステージ**: `{self.stage_id}`",
            color=0x00ff88
        )
        await safe_reply(interaction, embed=embed, ephemeral=False)
        asyncio.create_task(run_farm_dm(
            interaction.client, interaction, self.user_id,
            self.stage_id, self.count, self.current + 1,
            self.request_delay, self.cooldown, self.end_at
        ))
    @ui.button(label="🛑 完全停止", style=discord.ButtonStyle.danger, emoji="🛑", custom_id="hitodama_resume:stop")
    async def stop(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ あなたの通知ではありません。", ephemeral=True)
        if not await safe_defer(interaction):
            return
        loops = load_loops()
        if self.loop_key in loops:
            del loops[self.loop_key]
            await save_loops_async(loops)
        await safe_reply(interaction, content="🛑 周回を完全停止しました。", ephemeral=True)
# ============================================================
# DM通知
# ============================================================
async def send_locked_dm(bot, user_id, stage_id, player_name=None, streak=0):
    try:
        user = await bot.fetch_user(user_id)
    except Exception:
        return
    embed = discord.Embed(
        title="⛔ ステージに入れないため停止しました",
        description=(
            f"に連続 {streak} 回ステージ `{stage_id}` に入れませんでした。\n"
            f"プレイヤー: `{player_name or '不明'}`\n"
            f"しばらく時間をおいてから再開してください。"
        ),
        color=0xff4444,
        timestamp=datetime.now(JST)
    )
    try:
        await user.send(embed=embed)
    except Exception:
        pass


async def send_hitodama_pause_dm(bot, user_id, loop_key, stage_id, count, current,
                                  request_delay, cooldown, end_at=None):
    try:
        user = await bot.fetch_user(user_id)
    except Exception:
        return
    embed = discord.Embed(
        title="💤 人魂が不足したため一時停止",
        description=(
            f"ステージ: `{stage_id}`\n"
            f"進捗: {current} / {count}\n"
            f"人魂が補充されたら下のボタンから再開できます。"
        ),
        color=0xffaa00,
        timestamp=datetime.now(JST)
    )
    view = ResumeView(
        user_id=user_id,
        loop_key=loop_key,
        stage_id=stage_id,
        count=count,
        current=current,
        request_delay=request_delay,
        cooldown=cooldown,
        end_at=end_at
    )
    try:
        await user.send(embed=embed, view=view)
    except Exception:
        pass


async def send_finish_dm(bot, user_id, stage_id, count, tracker_data=None):
    try:
        user = await bot.fetch_user(user_id)
    except Exception:
        return
    embed = discord.Embed(
        title="✅ 周回完了",
        description=f"ステージ `{stage_id}` を {count} 回実行しました。",
        color=0x00ff88,
        timestamp=datetime.now(JST)
    )
    if tracker_data:
        gain_fields(embed, tracker_data, done=True)
    try:
        await user.send(embed=embed)
    except Exception:
        pass


# ============================================================
# 周回メイン処理
# ============================================================
GAIN_DEBUG_DUMP = False


async def run_farm(bot, interaction, ctx, user_id, stage_id, count,
                    request_delay, cooldown, end_at=None,
                    use_random_rd=True, use_random_cd=True, account_id=None):
    loop_key = f"{user_id}_{stage_id}_{int(time.time())}"
    loops = load_loops()
    loops[loop_key] = {
        "user_id": user_id,
        "stage_id": stage_id,
        "count": count,
        "current": 0,
        "status": "running",
        "started_at": datetime.now(JST).isoformat(),
        "account_id": account_id,
        "buy_count": 0,
        "errors": 0,
        "locked_streak": 0,
    }
    await save_loops_async(loops)

    slot_id = await assign_slot(loop_key, user_id, "farm", str(stage_id))
    if slot_id is None:
        loops = load_loops()
        loops[loop_key]["status"] = "queued"
        await save_loops_async(loops)
        position = await add_to_queue(
            user_id, "farm", str(stage_id),
            {
                "stage_id": stage_id,
                "count": count,
                "request_delay": request_delay,
                "cooldown": cooldown,
                "end_at": end_at,
                "use_random_rd": use_random_rd,
                "use_random_cd": use_random_cd,
                "account_id": account_id,
            }
        )
        if interaction:
            await safe_reply(
                interaction,
                content=f"⏳ 空きがないため予約しました。順番は {position} 番目です。",
                ephemeral=True
            )
        return

    acc = get_session(user_id, account_id)
    if not acc:
        if interaction:
            await safe_reply(interaction, content="❌ アカウントが見つかりません。", ephemeral=True)
        await release_slot(slot_id)
        return

    client = build_client_from_account(acc)
    try:
        await asyncio.to_thread(client.login, acc["userId"])
        update_account_tokens(user_id, client)
    except Exception as e:
        if interaction:
            await safe_reply(interaction, content=f"❌ ログイン失敗: `{str(e)[:200]}`", ephemeral=True)
        await release_slot(slot_id)
        return

    tracker = GainTracker(client)
    current = 0
    buy_count = 0
    locked_streak = 0
    errors = 0

    if interaction:
        await safe_reply(
            interaction,
            content=f"✅ 周回開始: `{stage_id}` / {count} 回",
            ephemeral=False
        )

    while current < count:
        loops = load_loops()
        if loop_key not in loops or loops[loop_key]["status"] != "running":
            break

        if end_at and datetime.now(JST) >= end_at:
            break

        if ODD_HOUR_REST_ENABLED:
            rested = await check_odd_hour_rest(loop_key)
            if rested:
                continue

        hitodama = get_hitodama(client)
        if hitodama < HITODAMA_THRESHOLD:
            ok, info, buy_count = await try_auto_buy(client, buy_count)
            if not ok:
                loops = load_loops()
                loops[loop_key]["status"] = "paused_hitodama"
                loops[loop_key]["buy_count"] = buy_count
                loops[loop_key]["hitodama"] = hitodama
                await save_loops_async(loops)
                await send_hitodama_pause_dm(
                    bot, user_id, loop_key, stage_id, count, current,
                    request_delay, cooldown, end_at
                )
                await release_slot(slot_id)
                return

        rd = rand_request_delay() if use_random_rd else request_delay
        cd = rand_cooldown() if use_random_cd else cooldown

        try:
            await asyncio.sleep(rd)
            rc, result = await asyncio.to_thread(
                client.call, "startStage.nhn", {"stageId": int(stage_id)}
            )

            if isinstance(result, dict):
                rc_code = result.get("resultCode", rc)
            else:
                rc_code = rc

            if rc_code in EVENT_SKIP_CODES:
                locked_streak += 1
                loops = load_loops()
                loops[loop_key]["locked_streak"] = locked_streak
                await save_loops_async(loops)
                if locked_streak >= LOCKED_STAGE_LIMIT:
                    loops = load_loops()
                    loops[loop_key]["status"] = "locked"
                    await save_loops_async(loops)
                    await send_locked_dm(
                        bot, user_id, stage_id,
                        acc.get("player_name"), locked_streak
                    )
                    break
                await asyncio.sleep(5)
                continue

            if rc_code in RETRY_CODES:
                errors += 1
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    loops = load_loops()
                    loops[loop_key]["status"] = "error"
                    await save_loops_async(loops)
                    break
                await asyncio.sleep(RETRY_WAITS[min(errors - 1, len(RETRY_WAITS) - 1)])
                continue

            errors = 0
            locked_streak = 0

            rc, game_result = await asyncio.to_thread(
                client.call, "endStage.nhn", {}
            )
            await tracker.after_battle(game_result, user_id)
            current += 1

            loops = load_loops()
            loops[loop_key]["current"] = current
            loops[loop_key]["buy_count"] = buy_count
            apply_gain_to_loop(loops[loop_key], tracker)
            await save_loops_async(loops)

            if current >= count:
                loops = load_loops()
                loops[loop_key]["status"] = "done"
                await save_loops_async(loops)
                await tracker.refresh()
                await send_finish_dm(bot, user_id, stage_id, count, tracker.to_dict())
                break

            await asyncio.sleep(cd)

        except Exception as e:
            errors += 1
            if errors >= MAX_CONSECUTIVE_ERRORS:
                loops = load_loops()
                loops[loop_key]["status"] = "fatal"
                loops[loop_key]["error"] = str(e)[:200]
                await save_loops_async(loops)
                break
            await asyncio.sleep(2)
            continue

    await release_slot(slot_id)
    await cleanup_user_loops(user_id)


async def run_farm_dm(bot, interaction, user_id, stage_id, count, start_from,
                      request_delay, cooldown, end_at=None, account_id=None):
    acc = get_session(user_id, account_id)
    if not acc:
        await safe_reply(interaction, content="❌ アカウントが見つかりません。", ephemeral=True)
        return

    client = build_client_from_account(acc)
    try:
        await asyncio.to_thread(client.login, acc["userId"])
        update_account_tokens(user_id, client)
    except Exception as e:
        await safe_reply(interaction, content=f"❌ ログイン失敗: `{str(e)[:200]}`", ephemeral=True)
        return

    tracker = GainTracker(client)
    current = start_from - 1
    buy_count = 0
    locked_streak = 0
    errors = 0
    loop_key = None

    while current < count:
        if end_at and datetime.now(JST) >= end_at:
            break

        hitodama = get_hitodama(client)
        if hitodama < HITODAMA_THRESHOLD:
            ok, info, buy_count = await try_auto_buy(client, buy_count)
            if not ok:
                break

        rd = rand_request_delay()
        cd = rand_cooldown()

        try:
            await asyncio.sleep(rd)
            rc, result = await asyncio.to_thread(
                client.call, "startStage.nhn", {"stageId": int(stage_id)}
            )
            rc_code = result.get("resultCode", rc) if isinstance(result, dict) else rc

            if rc_code in EVENT_SKIP_CODES:
                locked_streak += 1
                if locked_streak >= LOCKED_STAGE_LIMIT:
                    break
                await asyncio.sleep(5)
                continue

            if rc_code in RETRY_CODES:
                errors += 1
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    break
                await asyncio.sleep(RETRY_WAITS[min(errors - 1, len(RETRY_WAITS) - 1)])
                continue

            errors = 0
            locked_streak = 0

            rc, game_result = await asyncio.to_thread(client.call, "endStage.nhn", {})
            await tracker.after_battle(game_result, user_id)
            current += 1

            if current >= count:
                await tracker.refresh()
                await send_finish_dm(bot, user_id, stage_id, count, tracker.to_dict())
                break

            await asyncio.sleep(cd)

        except Exception as e:
            errors += 1
            if errors >= MAX_CONSECUTIVE_ERRORS:
                break
            await asyncio.sleep(2)
            continue


async def run_progress(bot, interaction, ctx, user_id, start_id, end_id,
                       end_at=None, account_id=None):
    acc = get_session(user_id, account_id)
    if not acc:
        if interaction:
            await safe_reply(interaction, content="❌ アカウントが見つかりません。", ephemeral=True)
        return

    client = build_client_from_account(acc)
    try:
        await asyncio.to_thread(client.login, acc["userId"])
        update_account_tokens(user_id, client)
    except Exception as e:
        if interaction:
            await safe_reply(interaction, content=f"❌ ログイン失敗: `{str(e)[:200]}`", ephemeral=True)
        return

    if interaction:
        await safe_reply(
            interaction,
            content=f"✅ 進行開始: `{start_id}` ～ `{end_id}`",
            ephemeral=False
        )

    tracker = GainTracker(client)
    success = 0
    failed = 0

    for sid in range(int(start_id), int(end_id) + 1):
        if end_at and datetime.now(JST) >= end_at:
            break

        hitodama = get_hitodama(client)
        if hitodama < HITODAMA_THRESHOLD:
            ok, _, _ = await try_auto_buy(client, 0)
            if not ok:
                break

        try:
            await asyncio.sleep(rand_request_delay())
            rc, result = await asyncio.to_thread(
                client.call, "startStage.nhn", {"stageId": sid}
            )
            rc_code = result.get("resultCode", rc) if isinstance(result, dict) else rc

            if rc_code in EVENT_SKIP_CODES:
                failed += 1
                await asyncio.sleep(3)
                continue

            rc, game_result = await asyncio.to_thread(client.call, "endStage.nhn", {})
            await tracker.after_battle(game_result, user_id)
            success += 1

            await asyncio.sleep(rand_cooldown())

        except Exception:
            failed += 1
            await asyncio.sleep(2)
            continue

    await tracker.refresh()
    embed = discord.Embed(
        title="✅ 進行完了",
        description=f"成功: {success} / 失敗: {failed}",
        color=0x00ff88
    )
    gain_fields(embed, tracker.to_dict(), done=True)
    if interaction:
        await safe_reply(interaction, embed=embed, ephemeral=False)


async def run_event_progress(bot, interaction, ctx, user_id, start_id,
                             end_at=None, account_id=None):
    acc = get_session(user_id, account_id)
    if not acc:
        if interaction:
            await safe_reply(interaction, content="❌ アカウントが見つかりません。", ephemeral=True)
        return

    client = build_client_from_account(acc)
    try:
        await asyncio.to_thread(client.login, acc["userId"])
        update_account_tokens(user_id, client)
    except Exception as e:
        if interaction:
            await safe_reply(interaction, content=f"❌ ログイン失敗: `{str(e)[:200]}`", ephemeral=True)
        return

    if interaction:
        await safe_reply(
            interaction,
            content=f"✅ イベント進行開始: `{start_id}` 以降",
            ephemeral=False
        )

    tracker = GainTracker(client)
    current_id = int(start_id)
    success = 0
    failed = 0
    consecutive_fail = 0

    while consecutive_fail < 5:
        if end_at and datetime.now(JST) >= end_at:
            break

        hitodama = get_hitodama(client)
        if hitodama < HITODAMA_THRESHOLD:
            ok, _, _ = await try_auto_buy(client, 0)
            if not ok:
                break

        try:
            await asyncio.sleep(rand_request_delay())
            rc, result = await asyncio.to_thread(
                client.call, "startStage.nhn", {"stageId": current_id}
            )
            rc_code = result.get("resultCode", rc) if isinstance(result, dict) else rc

            if rc_code in EVENT_SKIP_CODES:
                failed += 1
                consecutive_fail += 1
                current_id = next_block_start(current_id)
                await asyncio.sleep(3)
                continue

            consecutive_fail = 0
            rc, game_result = await asyncio.to_thread(client.call, "endStage.nhn", {})
            await tracker.after_battle(game_result, user_id)
            success += 1
            current_id += 1

            await asyncio.sleep(rand_cooldown())

        except Exception:
            failed += 1
            consecutive_fail += 1
            current_id = next_block_start(current_id)
            await asyncio.sleep(2)
            continue

    await tracker.refresh()
    embed = discord.Embed(
        title="✅ イベント進行完了",
        description=f"最後に到達したID: `{current_id}`\n成功: {success} / 失敗: {failed}",
        color=0x00ff88
    )
    gain_fields(embed, tracker.to_dict(), done=True)
    if interaction:
        await safe_reply(interaction, embed=embed, ephemeral=False)


async def run_benchmark(bot, interaction, ctx, user_id, stage_ids, samples, account_id=None):
    acc = get_session(user_id, account_id)
    if not acc:
        if interaction:
            await safe_reply(interaction, content="❌ アカウントが見つかりません。", ephemeral=True)
        return

    client = build_client_from_account(acc)
    try:
        await asyncio.to_thread(client.login, acc["userId"])
        update_account_tokens(user_id, client)
    except Exception as e:
        if interaction:
            await safe_reply(interaction, content=f"❌ ログイン失敗: `{str(e)[:200]}`", ephemeral=True)
        return

    if interaction:
        await safe_reply(
            interaction,
            content=f"✅ ベンチマーク開始: {len(stage_ids)}ステージ × {samples}回",
            ephemeral=False
        )

    results = {}
    for sid in stage_ids:
        sid = int(sid)
        tracker = GainTracker(client)
        ok_count = 0
        for _ in range(samples):
            hitodama = get_hitodama(client)
            if hitodama < HITODAMA_THRESHOLD:
                ok, _, _ = await try_auto_buy(client, 0)
                if not ok:
                    break

            try:
                await asyncio.sleep(rand_request_delay())
                rc, result = await asyncio.to_thread(
                    client.call, "startStage.nhn", {"stageId": sid}
                )
                rc_code = result.get("resultCode", rc) if isinstance(result, dict) else rc
                if rc_code in EVENT_SKIP_CODES:
                    continue

                rc, game_result = await asyncio.to_thread(client.call, "endStage.nhn", {})
                await tracker.after_battle(game_result, user_id)
                ok_count += 1
                await asyncio.sleep(rand_cooldown())
            except Exception:
                continue

        if ok_count > 0:
            data = tracker.to_dict()
            data["ok_count"] = ok_count
            data["avg_money"] = data["money_gain"] / ok_count
            results[sid] = data

    embed = discord.Embed(title="📊 ベンチマーク結果", color=0x00aaff)
    for sid, res in sorted(results.items()):
        embed.add_field(
            name=f"`{sid}`",
            value=(
                f"平均マネー: {res['avg_money']:,.1f}\n"
                f"合計: {res['money_gain']:,} / {res['ok_count']}回"
            ),
            inline=True
        )

    if interaction:
        await safe_reply(interaction, embed=embed, ephemeral=False)


# ============================================================
# パネル
# ============================================================
class PanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📋 状態更新", style=discord.ButtonStyle.secondary, custom_id="panel:refresh")
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        if not await safe_defer(interaction):
            return
        await safe_edit_original(interaction, embed=build_panel_embed())

    @ui.button(label="⏹️ 自分のジョブ停止", style=discord.ButtonStyle.danger, custom_id="panel:stop_mine")
    async def stop_mine(self, interaction: discord.Interaction, button: ui.Button):
        if not await safe_defer(interaction, ephemeral=True):
            return
        loops = load_loops()
        deleted = 0
        for k, v in list(loops.items()):
            if v.get("user_id") == interaction.user.id and v.get("status") == "running":
                del loops[k]
                deleted += 1
        await save_loops_async(loops)
        rem = await remove_user_from_queue(interaction.user.id)
        await safe_reply(
            interaction,
            content=f"🛑 実行中 {deleted}件 / 予約 {rem}件 を停止しました。",
            ephemeral=True
        )
        await update_panel_on_change()


def build_panel_embed() -> discord.Embed:
    slots = load_slots()["slots"]
    q_total = queue_status()["total"]
    running = paused = free = 0
    slot_lines = []
    for i in range(MAX_SLOTS):
        s = slots.get(str(i))
        if not s:
            free += 1
            slot_lines.append(f"#{i}: ✅ 空き")
        elif s.get("status") == "running":
            running += 1
            slot_lines.append(f"#{i}: ▶️ `{s.get('stage_info', '?')}` — <@{s.get('user_id')}>")
        elif s.get("status") == "paused_hitodama":
            paused += 1
            slot_lines.append(f"#{i}: 💤 `{s.get('stage_info', '?')}` — <@{s.get('user_id')}>")
        else:
            slot_lines.append(f"#{i}: ⏸️ その他")

    embed = discord.Embed(
        title="🏃 周回状態パネル",
        description=(
            f"**実行中**: {running} / **一時停止**: {paused} / **空き**: {free}\n"
            f"**予約キュー**: {q_total} 件"
        ),
        color=0x00ffaa,
        timestamp=datetime.now(JST)
    )
    embed.add_field(
        name="スロット一覧",
        value="\n".join(slot_lines) or "データなし",
        inline=False
    )
    return embed


# ============================================================
# コマンド定義
# ============================================================
async def setup_commands(bot):
    @bot.tree.command(name="panel", description="周回状態パネルを表示")
    @app_commands.checks.has_permissions(administrator=True)
    async def cmd_panel(interaction: discord.Interaction):
        if not await safe_defer(interaction):
            return
        embed = build_panel_embed()
        view = PanelView()
        msg = await interaction.followup.send(embed=embed, view=view)
        panel = load_panel()
        panel[str(interaction.guild_id)] = {
            "channel_id": interaction.channel_id,
            "message_id": msg.id,
        }
        save_panel(panel)

    @bot.tree.command(name="farm", description="指定ステージを周回")
    @app_commands.describe(
        stage_id="ステージID（例: 100101）",
        count="回数",
        request_delay="リクエスト間隔（秒）",
        cooldown="戦闘間隔（秒）",
        end_at="終了時刻（YYYY-MM-DD HH:MM）",
        account_id="使用するアカウントID",
    )
    async def cmd_farm(
        interaction: discord.Interaction,
        stage_id: str,
        count: app_commands.Range[int, 1, 99999] = 100,
        request_delay: float = 2.5,
        cooldown: float = 3.0,
        end_at: str | None = None,
        account_id: str | None = None,
    ):
        if not await safe_defer(interaction):
            return
        end_dt = parse_datetime(end_at) if end_at else None
        ok, current = can_start_loop()
        if not ok:
            await safe_reply(
                interaction,
                content=f"⏳ 同時実行上限 {MAX_CONCURRENT_LOOPS} に達しています。予約キューに追加します。",
                ephemeral=True
            )
            position = await add_to_queue(
                interaction.user.id, "farm", stage_id,
                {
                    "stage_id": stage_id,
                    "count": count,
                    "request_delay": request_delay,
                    "cooldown": cooldown,
                    "end_at": end_dt,
                    "account_id": account_id,
                }
            )
            await safe_reply(interaction, content=f"✅ 予約完了: {position} 番目", ephemeral=True)
            return

        asyncio.create_task(run_farm(
            bot, interaction, None, interaction.user.id,
            stage_id, count, request_delay, cooldown, end_dt,
            account_id=account_id
        ))

    @bot.tree.command(name="progress", description="ID範囲を進行")
    @app_commands.describe(
        start_id="開始ID",
        end_id="終了ID",
        account_id="アカウントID",
    )
    async def cmd_progress(
        interaction: discord.Interaction,
        start_id: str,
        end_id: str,
        account_id: str | None = None,
    ):
        if not await safe_defer(interaction):
            return
        asyncio.create_task(run_progress(
            bot, interaction, None, interaction.user.id,
            start_id, end_id, account_id=account_id
        ))

    @bot.tree.command(name="event", description="イベント自動進行")
    @app_commands.describe(
        start_id="開始ID",
        account_id="アカウントID",
    )
    async def cmd_event(
        interaction: discord.Interaction,
        start_id: str,
        account_id: str | None = None,
    ):
        if not await safe_defer(interaction):
            return
        asyncio.create_task(run_event_progress(
            bot, interaction, None, interaction.user.id,
            start_id, account_id=account_id
        ))

    @bot.tree.command(name="accounts", description="登録済みアカウント一覧")
    async def cmd_accounts(interaction: discord.Interaction):
        if not await safe_defer(interaction, ephemeral=True):
            return
        accs = get_user_accounts(interaction.user.id)
        if not accs:
            await safe_reply(interaction, content="❌ アカウントが登録されていません。", ephemeral=True)
            return
        lines = []
        for i, acc in enumerate(accs):
            active_mark = "✅" if i == get_user_session(interaction.user.id).get("active_index", 0) else ""
            lines.append(
                f"{active_mark} `{acc.get('player_id')}` — {acc.get('player_name', '不明')}"
            )
        await safe_reply(
            interaction,
            content="\n".join(lines) or "なし",
            ephemeral=True
        )

    @bot.tree.command(name="switch", description="使用アカウントを切り替え")
    @app_commands.describe(account_id="切り替え先アカウントID")
    async def cmd_switch(interaction: discord.Interaction, account_id: str):
        if not await safe_defer(interaction, ephemeral=True):
            return
        ok = await set_active(interaction.user.id, account_id)
        if ok:
            await safe_reply(interaction, content=f"✅ `{account_id}` に切り替えました。", ephemeral=True)
        else:
            await safe_reply(interaction, content=f"❌ `{account_id}` が見つかりません。", ephemeral=True)

    @bot.tree.command(name="remove_account", description="アカウントを削除")
    @app_commands.describe(account_id="削除するアカウントID")
    async def cmd_remove_account(interaction: discord.Interaction, account_id: str):
        if not await safe_defer(interaction, ephemeral=True):
            return
        ok = await remove_account(interaction.user.id, account_id)
        if ok:
            await safe_reply(interaction, content=f"✅ `{account_id}` を削除しました。", ephemeral=True)
        else:
            await safe_reply(interaction, content=f"❌ `{account_id}` が見つかりません。", ephemeral=True)

    @bot.tree.command(name="queue", description="予約キュー状態表示")
    async def cmd_queue(interaction: discord.Interaction):
        if not await safe_defer(interaction, ephemeral=True):
            return
        q = load_queue()
        pos = get_user_queue_position(interaction.user.id)
        await safe_reply(
            interaction,
            content=(
                f"全体: {len(q)} 件\n"
                f"自分の位置: {pos if pos else 'なし'}"
            ),
            ephemeral=True
        )

    @bot.tree.command(name="stop", description="自分のジョブを停止")
    async def cmd_stop(interaction: discord.Interaction):
        if not await safe_defer(interaction, ephemeral=True):
            return
        loops = load_loops()
        deleted = 0
        for k, v in list(loops.items()):
            if v.get("user_id") == interaction.user.id and v.get("status") in ("running", "paused_hitodama"):
                del loops[k]
                deleted += 1
        await save_loops_async(loops)
        rem = await remove_user_from_queue(interaction.user.id)
        await safe_reply(
            interaction,
            content=f"🛑 実行中 {deleted}件 / 予約 {rem}件 を停止しました。",
            ephemeral=True
        )
        await update_panel_on_change()


# ============================================================
# Bot セットアップ
# ============================================================
class YWPCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        set_bot_ref(bot)
        self.daily_report.start()

    async def cog_load(self):
        await setup_commands(self.bot)

    async def cog_unload(self):
        self.daily_report.stop()

    @tasks.loop(minutes=1)
    async def daily_report(self):
        if not DAILY_REPORT_ENABLED:
            return
        now = datetime.now(JST)
        if now.hour == DAILY_REPORT_HOUR and now.minute == DAILY_REPORT_MINUTE:
            pass  # 日次レポート処理をここに追加可

    @daily_report.before_loop
    async def before_daily_report(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(YWPCog(bot))
