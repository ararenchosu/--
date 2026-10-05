import base64
import hashlib
import json
import random
import re
import time
import zlib
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, parse_qs
from Crypto.Cipher import AES
import requests
from discord.ext import commands

# ============================================================================
# 定数設定
# ============================================================================
AESK = bytes.fromhex('a865d7e5e2458f8ce1b5ecd087e54594')
K = b'0bk2kvtFE2'
APKEY = 'a-zrhgm09pgcgjc1iv9cxvpk3xm9b0ynyo4u00sny6bjq10nrx3up2yrhjnq2lhg'
SIGNATURE = ('s4X9CoyxGma3kGuAp5woThgvBX3dCi77Slh5RcOo6ybmMTt0J4CGiZwyiCsil7P3'
             'MVgjiVt+kGE1MqvttCXLB+hlOpyTkJp5a78TXthBNVw=')
GS = 'https://gameserver.yw-p.com'
L5 = 'https://api.level5-id.com'
MODEL = 'GA00747-UK'
OSVER = '9'
APPVER = '4.175.0'
BATTERY = {'level': 100, 'state': 3, 'technology': 'Li-poly', 'temperature': 261, 'voltage': 4300}
UA = 'Dalvik/2.1.0 (Linux; U; Android %s; %s Build/PI) com.Level5.YWP/%s' % (OSVER, MODEL, APPVER)
HDR = {'Accept-Encoding': 'identity', 'User-Agent': UA, 'Accept': 'application/json',
       'Content-Type': 'application/json', 'Connection': 'Keep-Alive'}
RC = {
    0: 'OK',
    -1: 'IPブロック/復号不可',
    20: 'appVerかマスタ版が古い',
    30: '署名の不整合',
    32: 'tokenズレ',
    37: 'チュートリアル未完了',
    101: 'マスタ版が現行と違う',
    202: 'BAN'
}
YPOINT_ITEM_ID = 80102
HITODAMA_ITEM_ID = 1001  # ひとだまアイテムID
SAVE_PREFIX = 'ywp_user_'

# アイテム名マッピング：必要に応じて追加・修正してください
ITEM_NAMES = {
    1001: 'ひとだま',
    80102: 'Yポイント',
    2001: 'けいけんちだま',
    3001: 'まもりのたま',
    # ↓ ここに追加： アイテムID: 'アイテム名',
}

GAME_CONST = [
    {"constType": 5, "mstKey": "blockComboAdjustNumA", "mstValue": "0.051800"},
    {"constType": 5, "mstKey": "blockComboAdjustNumB", "mstValue": "0.995500"},
    {"constType": 5, "mstKey": "blockSizeAdjustA", "mstValue": "0.000800"},
    {"constType": 5, "mstKey": "blockSizeAdjustB", "mstValue": "0.077000"},
    {"constType": 5, "mstKey": "blockSizeAdjustC", "mstValue": "-0.058500"},
    {"constType": 5, "mstKey": "blockSizeAdjustSkillA", "mstValue": "5.780200"},
    {"constType": 5, "mstKey": "blockSizeAdjustSkillB", "mstValue": "-2.201000"},
    {"constType": 5, "mstKey": "blockSizeAdjustSkillC", "mstValue": "1.000000"},
    {"constType": 5, "mstKey": "blockSizeRate1", "mstValue": "0.019300"},
    {"constType": 5, "mstKey": "blockSizeRate2", "mstValue": "0.058600"},
    {"constType": 5, "mstKey": "blockSizeRate3", "mstValue": "0.137900"},
    {"constType": 5, "mstKey": "comboEnableSec", "mstValue": "3.000000"},
    {"constType": 5, "mstKey": "comboEnableSize", "mstValue": "2"},
    {"constType": 5, "mstKey": "damageSwitchSize", "mstValue": "3"},
    {"constType": 5, "mstKey": "feverDamageAdjustNum", "mstValue": "0.100000"},
    {"constType": 5, "mstKey": "feverScoreAdjustNum", "mstValue": "0.100000"},
    {"constType": 5, "mstKey": "saBlockSizeAdjustSubA", "mstValue": "0.006200"},
    {"constType": 5, "mstKey": "saBlockSizeAdjustSubB", "mstValue": "-0.024500"},
    {"constType": 5, "mstKey": "saBlockSizeAdjustSubC", "mstValue": "0.416900"},
    {"constType": 5, "mstKey": "scoreAdjustNumA", "mstValue": "11.223000"},
    {"constType": 5, "mstKey": "scoreAdjustNumB", "mstValue": "0.047700"},
    {"constType": 5, "mstKey": "skillGaugeIncrementSize1", "mstValue": "0.100000"},
    {"constType": 5, "mstKey": "skillGaugeIncrementSize2", "mstValue": "1.200000"},
    {"constType": 5, "mstKey": "skillGaugeIncrementSize3", "mstValue": "2.400000"},
]

# ============================================================================
# 状態管理クラス
# ============================================================================
class AutoStatus:
    def __init__(self):
        self.running = False
        self.start_time = None
        self.current_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.current_stage = None
        self.last_error = None
        self._lock = False
        self.next_battle_at = None
        self.ypoint = None
        self.ymoney = None
        self.hitodama = None
        self.notify_user = None
        self.drops = {}  # ドロップアイテム記録: {item_id: count}

    def start(self, stage_name: str, notify_user=None):
        self.running = True
        self.start_time = time.time()
        self.current_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.current_stage = stage_name
        self.last_error = None
        self._lock = True
        self.notify_user = notify_user
        self.drops = {}  # 開始時にリセット

    def stop(self):
        self.running = False
        self._lock = False

    def increment_success(self):
        self.current_count += 1
        self.success_count += 1
        self.last_error = None

    def increment_fail(self, error_msg: str = None):
        self.current_count += 1
        self.fail_count += 1
        self.last_error = error_msg

    def add_drop(self, item_id, count=1):
        """ドロップアイテムを追加"""
        if item_id:
            self.drops[item_id] = self.drops.get(item_id, 0) + count

    def get_drop_text(self):
        """ドロップ表示用文字列作成"""
        if not self.drops:
            return "なし"
        lines = []
        for item_id, cnt in sorted(self.drops.items(), key=lambda x: (-x[1], x[0])):
            name = ITEM_NAMES.get(item_id, f"アイテム{item_id}")
            lines.append(f"・{name} ×{cnt}")
        return "\n".join(lines)

    def update_currency(self, client):
        cur = client.currency()
        items = client.items()
        self.ypoint = cur.get('ypoint')
        self.ymoney = cur.get('ymoney')
        self.hitodama = items.get(HITODAMA_ITEM_ID, 0)

    def set_next_wait(self, seconds: float):
        self.next_battle_at = datetime.utcnow() + timedelta(seconds=seconds)

    def get_next_remaining(self):
        if not self.next_battle_at:
            return "計算中..."
        rem = (self.next_battle_at - datetime.utcnow()).total_seconds()
        if rem <= 0:
            return "まもなく開始"
        return f"約{rem:.1f}秒"

    def get_elapsed_str(self):
        if not self.start_time:
            return "00:00:00"
        return str(timedelta(seconds=int(time.time() - self.start_time)))

    def get_status_text(self):
        status_emoji = "🟢 実行中" if self.running else "🔴 停止中"
        elapsed = self.get_elapsed_str()
        rate = (self.success_count / self.current_count * 100) if self.current_count > 0 else 0.0
        count_display = f"{self.current_count}/∞" if self.running else f"{self.current_count}"

        text = f"""**📊 代行状況**
状態: {status_emoji}
対象: {self.current_stage or "未設定"}
経過時間: {elapsed}
実行回数: {count_display}
✅ 成功: {self.success_count} 回
❌ 失敗: {self.fail_count} 回
成功率: {rate:.1f}%
⏳ 次のバトルまで: {self.get_next_remaining()}
💰 Yポイント: {self.ypoint or "取得中"}
💎 Yマネー: {self.ymoney or "取得中"}
🫧 ひとだま: {self.hitodama if self.hitodama is not None else "取得中"}

🎁 ドロップ累計
{self.get_drop_text()}
"""
        if self.last_error:
            text += f"\n⚠️ 最新エラー: {self.last_error}"
        return text

STATUS = AutoStatus()

# ============================================================================
# 暗号化・復号化
# ============================================================================
def salt20(body):
    return hashlib.sha1(K + hashlib.sha1(K + b' ' + body).digest()).digest()
def enc(body):
    pt = salt20(body) + body
    p = 16 - len(pt) % 16
    pt += bytes([p]) * p
    return base64.urlsafe_b64encode(AES.new(AESK, AES.MODE_ECB).encrypt(pt)).decode().rstrip('=')
def dec(s):
    s = s.strip()
    ct = base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
    pt = AES.new(AESK, AES.MODE_ECB).decrypt(ct)
    rest = pt[20:]
    g = rest.find(b'\x1f\x8b')
    if g >= 0:
        try:
            return zlib.decompress(rest[g:], 47)
        except Exception:
            pass
    try:
        rest = rest[:-pt[-1]]
    except Exception:
        pass
    e = max(rest.rfind(b'}'), rest.rfind(b']'))
    return rest[:e + 1] if e >= 0 else rest
def jbody(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

# ============================================================================
# API通信
# ============================================================================
def post_nhn(name, obj, timeout=30, retry=3):
    for attempt in range(1, retry + 1):
        try:
            r = requests.post('%s/%s' % (GS, name), data=enc(jbody(obj)),
                              headers={**HDR, 'Host': 'gameserver.yw-p.com'}, timeout=timeout)
            if r.status_code != 200:
                if attempt < retry:
                    time.sleep(2 ** attempt)
                    continue
                return r.status_code, {'resultCode': -1, '_error': f'HTTP{r.status_code}'}
            try:
                out = dec(r.text)
            except Exception:
                if attempt < retry:
                    time.sleep(2 ** attempt)
                    continue
                return r.status_code, {'resultCode': -1, '_raw': (r.text or '')[:200]}
            try:
                return r.status_code, json.loads(out)
            except Exception:
                if attempt < retry:
                    time.sleep(2 ** attempt)
                    continue
                return r.status_code, {'_raw': out[:300].decode('utf-8', 'replace')}
        except requests.exceptions.Timeout:
            if attempt < retry:
                time.sleep(3 * attempt)
                continue
            return None, {'resultCode': -1, '_error': 'Timeout'}
        except requests.exceptions.ConnectionError:
            if attempt < retry:
                time.sleep(3 * attempt)
                continue
            return None, {'resultCode': -1, '_error': 'ConnectionError'}
    return None, {'resultCode': -1, '_error': 'Max retries exceeded'}
def active(udkey=None, timeout=30):
    p = {'apkey': APKEY, 'device_cd': '%s_%s' % (MODEL, OSVER), 'device_type_cd': 'Android',
         'sign': 'true', 'version': APPVER}
    if udkey:
        p['udkey'] = udkey
    return requests.get('%s/api/v1/active/' % L5, params=p,
                        headers={'User-Agent': UA}, timeout=timeout).json()
def new_udkey():
    return active()['udkey']['value']
def create_gdkey(udkey, timeout=30):
    r = requests.get('%s/api/v1/create_gdkey' % L5,
                     params={'apkey': APKEY, 'udkey': udkey,
                             'device_cd': '%s_%s' % (MODEL, OSVER), 'device_type_cd': 'Android',
                             'version': APPVER, 'sign': 'true'},
                     headers={'User-Agent': UA}, timeout=timeout).json()
    if not r.get('result'):
        raise RuntimeError('create_gdkey失敗: %s' % r)
    return r['gdkey']['value']
def _parse_forms(html):
    out = []
    for fm in re.finditer(r'<form\b[^>]*>(.*?)</form>', html, re.S | re.I):
        block = fm.group(0)
        am = re.search(r'action="([^"]*)"', block, re.I)
        inputs = {}
        for im in re.finditer(r'<input\b[^>]*>', block, re.I):
            nm = re.search(r'name="([^"]*)"', im.group(0), re.I)
            vm = re.search(r'value="([^"]*)"', im.group(0), re.I)
            if nm:
                inputs[nm.group(1)] = vm.group(1) if vm else ''
        out.append({'action': am.group(1) if am else '', 'inputs': inputs})
    return out
def link_email(udkey, email, pw, timeout=25):
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
                      'Accept-Language': 'ja'})
    r = s.get('%s/api/v1/link_account' % L5, params={'apkey': APKEY, 'udkey': udkey},
              allow_redirects=True, timeout=timeout)
    lf = [x for x in _parse_forms(r.text) if any('email' in k.lower() for k in x['inputs'])]
    if not lf:
        raise RuntimeError('ログイン画面が出ない')
    inp = dict(lf[0]['inputs'])
    inp['form[email]'] = email
    inp['form[password]'] = pw
    r = s.post(urljoin(r.url, lf[0]['action']), data=inp, allow_redirects=True, timeout=timeout)
    ap = [x for x in _parse_forms(r.text) if 'client_id' in x['inputs'] and x['inputs'].get('_method', '') != 'delete']
    if not ap:
        raise RuntimeError('認可画面が出ない')
    inp = dict(ap[0]['inputs'])
    inp.setdefault('commit', 'Authorize')
    r2 = s.post(urljoin(r.url, ap[0]['action']), data=inp, allow_redirects=False, timeout=timeout)
    code = (parse_qs(urlparse(r2.headers.get('Location', '')).query).get('code') or [None])[0]
    if not code:
        raise RuntimeError('認可コードが取れない')
    fin = s.get('%s/api/v1/link_account' % L5,
                params={'code': code, 'apkey': APKEY, 'udkey': udkey,
                        'device_cd': '%s_%s' % (MODEL, OSVER), 'device_type_cd': 'Android'},
                timeout=timeout).json()
    if not fin.get('result'):
        raise RuntimeError('連携失敗: %s' % fin)
    return fin
def rows(s):
    if isinstance(s, str):
        s = json.loads(s) if s.startswith('{') else s
    return [r.split('|') for r in (s or '').split('*') if r] if isinstance(s, str) else (s.get('rows') if isinstance(s, dict) else (s or []))
def parse_item_rows(s):
    out = {}
    if not s:
        return out
    for r in str(s).split('*'):
        if not r: continue
        c = r.split('|')
        if len(c) < 2: continue
        try: out[int(c[0])] = int(c[1])
        except ValueError: pass
    return out
def parse_user_data(d):
    if isinstance(d, str):
        try: d = json.loads(d)
        except Exception: return {}
    return d if isinstance(d, dict) else {}

# ============================================================================
# Clientクラス
# ============================================================================
class Client:
    def __init__(self, udkey):
        self.udkey = udkey
        self.gdkey = None
        self.userId = None
        self.token = '0'
        self.mst = 16897
        self.save = {}

    def _active_with_gdkeys(self, retries=6):
        a = active(self.udkey)
        for _ in range(retries):
            if a.get('gdkeys'): break
            time.sleep(1.2)
            a = active(self.udkey)
        if not a.get('gdkeys'):
            raise RuntimeError('gdkeyが無い')
        return a

    def _enum(self, a):
        gds = a['gdkeys']
        pl = []
        for _ in range(5):
            rc, j = post_nhn('getGdkeyAccounts.nhn', {
                'appVer': APPVER, 'deviceId': self.udkey,
                'gdkeys': [{'gdkey': g['value']} for g in gds],
                'level5UserId': '0', 'mstVersionVer': self.mst, 'osType': 2,
                'userId': '0', 'ywpToken': '0'})
            pl = j.get('udkeyPlayerList') or []
            if len(pl) >= len(gds): break
            time.sleep(1.2)
        by_g = {str(p.get('gdkey')): p for p in pl if p.get('gdkey')}
        out = []
        for i, g in enumerate(gds):
            p = by_g.get(g['value'], {})
            out.append({'idx': i, 'userId': p.get('userId'), 'playerName': p.get('playerName'),
                        'gdkey': g['value'], 'gdsig': g['signature']})
        return out

    def init_nhn(self):
        rc, j = post_nhn('init.nhn', {
            'appGuardDeviceId': hashlib.sha256(self.udkey.encode()).hexdigest(),
            'appVer': APPVER, 'deviceId': self.udkey, 'level5UserId': '0',
            'mstVersionVer': self.mst, 'osType': 2, 'signature': SIGNATURE,
            'userId': '0', 'ywpToken': '0'})
        v = j.get('mstVersionMaster')
        if isinstance(v, int) and v > 0: self.mst = v
        return j

    def login(self, userId=None):
        self.init_nhn()
        a = self._active_with_gdkeys()
        accs = self._enum(a)
        sel = None
        if userId is not None:
            sel = next((x for x in accs if str(x['userId']) == str(userId)), None)
            if sel is None: raise RuntimeError('userIdが見つからない')
        if sel is None: sel = accs[0]
        rc, j = post_nhn('login.nhn', {
            'appVer': APPVER, 'batteryInfo': BATTERY, 'deviceId': self.udkey,
            'deviceName': MODEL, 'gdkeySignature': sel['gdsig'], 'gdkeyValue': sel['gdkey'],
            'isL5IDLinked': 1, 'level5UserId': sel['gdkey'],
            'modelName': MODEL, 'mstVersionVer': self.mst, 'osType': 2, 'osVersion': OSVER,
            'signNonce': a['sign_nonce'], 'signTimestamp': str(a['sign_timestamp']),
            'signature': SIGNATURE, 'udkeySignature': a['udkey']['signature'],
            'udkeyValue': self.udkey, 'userId': sel['userId'], 'ywpToken': '0'})
        if j.get('resultCode') != 0:
            code = j.get('resultCode')
            raise RuntimeError(f'login失敗: rc={code} ({RC.get(code, "不明")})')
        self.gdkey, self.userId, self.token = sel['gdkey'], sel['userId'], j.get('token')
        self.save = j
        return j

    def call(self, name, extra=None):
        if not self.token or self.token == '0':
            raise RuntimeError('先にloginしてください')
        body = {'activeDeckId': 1, 'appVer': APPVER, 'deviceId': self.udkey,
                'level5UserId': self.gdkey, 'mstVersionVer': self.mst, 'osType': 2,
                'token': self.token, 'userId': str(self.userId), 'ywpToken': '0'}
        if extra: body.update(extra)
        rc, j = post_nhn(name, body)
        t = j.get('token')
        if t and t != 'null': self.token = t
        self.merge_save(j)
        return rc, j

    def merge_save(self, j):
        if not isinstance(j, dict) or j.get('resultCode') != 0: return False
        for k, v in j.items():
            if k.startswith(SAVE_PREFIX) and v is not None: self.save[k] = v
        return True

    def currency(self):
        d = parse_user_data(self.save.get('ywp_user_data'))
        items = parse_item_rows(self.save.get('ywp_user_item'))
        ymoney = d.get('ymoney')
        return {
            'ypoint': items.get(YPOINT_ITEM_ID),
            'ymoney': int(ymoney) if str(ymoney).lstrip('-').isdigit() else None,
        }

    def items(self):
        return parse_item_rows(self.save.get('ywp_user_item'))

    def build_game_end(self, stageId, battleType, start, clear_time_sec=None):
        reqId = start.get('requestId')
        yk = start.get('userYoukaiList') or []
        en = start.get('enemyYoukaiList') or []
        total_hp = sum(e.get('hp', 0) for e in en) or 50000
        dmg = total_hp + random.randint(int(total_hp*0.05), int(total_hp*0.15))
        score = dmg
        if clear_time_sec is None:
            clear_time_sec = round(random.uniform(5.0, 7.0), 1)
        clear_time_int = int(round(clear_time_sec))
        erase_num = random.randint(20, 80)
        combo_max = random.randint(max(5, erase_num//5), min(30, erase_num//2))
        erase_size_max = random.randint(100, 112)
        users = []
        for i, y in enumerate(yk):
            is_first = i == 0
            users.append({
                'damageTotal': dmg if is_first else 0,
                'eraseNum': max(1, erase_num//2) if is_first else 0,
                'eraseSizeMax': erase_size_max if is_first else 0,
                'linkSizeMax': random.randint(2, 5) if is_first else 0,
                'recoveryActual': 0, 'skillUseNum': 0,
                'youkaiId': y.get('youkaiId'),
            })
        enemies = []
        for i, e in enumerate(en):
            enemies.append({
                'deadEndOrder': i+1, 'enemyId': e.get('enemyId'),
                'dropItemFlg': 0, 'dropYoukaiFlg': 0,
            })
        return {
            'stageId': stageId, 'battleType': battleType, 'requestId': str(reqId),
            'damageTotal': dmg, 'score': score,
            'userYoukaiResultList': users, 'enemyYoukaiResultList': enemies,
            'clearTimeSec': clear_time_int, 'comboMax': combo_max,
            'eraseNumTotal': erase_num, 'eraseSizeMax': erase_size_max,
            'resultYoukaiHP': random.randint(600, 800),
            'ywp_mst_game_const': GAME_CONST,
        }

    def battle(self, stageId, battleType=None):
        if battleType is None:
            battleType = 6 if str(stageId).startswith(('28805','28904','29008','29304')) else 1
        rc, js = self.call('gameStart.nhn', {'stageId': stageId, 'battleType': battleType, 'battleCode':'', 'retryFlg':0})
        if js.get('resultCode') != 0:
            return js.get('resultCode'), js
        wait = round(random.uniform(5.0, 7.0), 1)  # バトル内待機 5～7秒
        time.sleep(wait)
        ge = self.build_game_end(stageId, battleType, js, clear_time_sec=wait)
        rc, result = self.call('gameEnd.nhn', ge)
        return rc, result

# ============================================================================
# ログイン関数
# ============================================================================
def login_email(email, pw, userId=None):
    udkey = new_udkey()
    link_email(udkey, email, pw)
    time.sleep(3)
    c = Client(udkey)
    c.login(userId=userId)
    return c

# ============================================================================
# Cog本体
# ============================================================================
class YWPAuto(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = None

    async def send_dm(self, user_id, title, message):
        """共通DM送信"""
        try:
            u = await self.bot.fetch_user(user_id)
            await u.send(f"""{title}

{message}""")
        except Exception as e:
            print(f"DM送信失敗: {e}")

    async def start_loop(self, ctx, client: Client, stage_id: str, count: int,
                         delay_min: float, delay_max: float, notify_user_id=None):
        if STATUS._lock:
            await ctx.send("⚠️ 既に実行中です")
            return

        STATUS.start(stage_id, notify_user=ctx.author)
        STATUS.update_currency(client)
        mode = "♾️ 無限" if count <= 0 else f"✅ 計{count}回"
        await ctx.send(f"{mode}周回開始: 対象={stage_id}")

        try:
            loop_count = 0
            while STATUS.running:
                if count > 0 and loop_count >= count: break

                # ひとだまチェック：0なら停止
                if STATUS.hitodama == 0:
                    STATUS.stop()
                    STATUS.update_currency(client)
                    msg_title = "🫧 ひとだま不足"
                    msg_body = f"""周回を停止しました。

💰 Yポイント: {STATUS.ypoint}
💎 Yマネー: {STATUS.ymoney}
🫧 ひとだま: 0

※ひとだまを補充後、再度 /start で開始してください。
{STATUS.get_drop_text()}"""
                    await ctx.send(f"{msg_title}により停止しました\n{STATUS.get_status_text()}")
                    if notify_user_id:
                        await self.send_dm(notify_user_id, "🫧 ひとだま不足により周回停止", msg_body)
                    return

                # バトル実行
                try:
                    rc, result = client.battle(stage_id)
                    code = result.get('resultCode', -1)

                    # BAN検知
                    if code == 202:
                        STATUS.stop()
                        STATUS.update_currency(client)
                        msg_body = f"""アカウントがBANされました。

💰 Yポイント: {STATUS.ypoint}
💎 Yマネー: {STATUS.ymoney}
🫧 ひとだま: {STATUS.hitodama}

※これ以上周回できません。新規アカウントで再ログインしてください。
{STATUS.get_drop_text()}"""
                        await ctx.send(f"🚨 BAN検知！周回停止しました\n{STATUS.get_status_text()}")
                        if notify_user_id:
                            await self.send_dm(notify_user_id, "🚨 アカウントBANにより周回停止", msg_body)
                        return

                    if code != 0:
                        raise Exception(f"エラーコード: {code}")

                    STATUS.increment_success()
                    # ドロップ情報を記録 — gameEnd結果からアイテムを抽出
                    drop_items = result.get('dropItemList') or result.get('dropItem') or []
                    for item in drop_items:
                        if isinstance(item, dict):
                            iid = item.get('itemId') or item.get('mstItemId')
                            num = item.get('itemNum') or item.get('count') or 1
                            if iid: STATUS.add_drop(iid, num)
                    STATUS.update_currency(client)

                except Exception as e:
                    STATUS.increment_fail(str(e))

                loop_count += 1
                if count > 0 and loop_count >= count: break
                if not STATUS.running: break

                # 休憩時間：合計10～15秒になるよう調整
                wait = random.uniform(delay_min, delay_max)
                STATUS.set_next_wait(wait)
                await discord.utils.sleep_until(
                    discord.utils.utcnow() + discord.utils.timedelta(seconds=wait)
                )

        finally:
            STATUS.stop()
            await ctx.send(f"🏁 周回終了\n{STATUS.get_status_text()}")

    async def stop_loop(self):
        STATUS.stop()


async def setup(bot):
    await bot.add_cog(YWPAuto(bot))
