"""微软账号登录：PCL 同款授权码 + Xbox Live + Minecraft Services。"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

CLIENT_ID = "00000000402b5328"
SCOPE = "service::user.auth.xboxlive.com::MBI_SSL"
REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
AUTHORITY = "https://login.live.com/oauth20_authorize.srf"
TOKEN_URL = "https://login.live.com/oauth20_token.srf"
USER_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
MC_ENTITLEMENTS_URL = "https://api.minecraftservices.com/entitlements/mcstore"

UA = "SimpleCubeLauncher/0.2 (Minecraft launcher)"


class MicrosoftError(Exception):
    pass


def _request(url, data=None, headers=None, method=None):
    merged = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        merged.update(headers)
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        merged.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=body, headers=merged, method=method)
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        raise MicrosoftError("网络请求失败：%s" % exc)


def _json_response(status, text, action):
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        data = {}
    if status >= 400:
        message = data.get("error_description") or data.get("error") or text[:200]
        raise MicrosoftError("%s失败（HTTP %s）：%s" % (action, status, message))
    return data


def build_auth_url():
    fields = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": SCOPE,
    }
    return AUTHORITY + "?" + urllib.parse.urlencode(fields)


def extract_code(value):
    value = (value or "").strip().strip('"').strip("'")
    if not value:
        return ""
    if "code=" in value:
        try:
            query = urllib.parse.urlparse(value).query
            params = urllib.parse.parse_qs(query)
            if params.get("code"):
                return params["code"][0]
        except Exception:
            pass
        match = re.search(r"[?&]code=([^&\s]+)", value)
        if match:
            return urllib.parse.unquote(match.group(1))
    if value.startswith("M.") or (len(value) > 20 and " " not in value):
        return value
    return ""


def exchange_code(code):
    fields = {
        "client_id": CLIENT_ID,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    }
    body = urllib.parse.urlencode(fields).encode("utf-8")
    status, text = _request(TOKEN_URL, body,
                            {"Content-Type": "application/x-www-form-urlencoded"}, "POST")
    return _json_response(status, text, "获取微软令牌")


def refresh_ms_token(refresh_token):
    fields = {
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    }
    body = urllib.parse.urlencode(fields).encode("utf-8")
    status, text = _request(TOKEN_URL, body,
                            {"Content-Type": "application/x-www-form-urlencoded"}, "POST")
    return _json_response(status, text, "刷新微软令牌")


def _xbox_live(ms_access_token):
    status, text = _request(USER_AUTH_URL, {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": ms_access_token,
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    }, method="POST")
    if status != 200:
        raise MicrosoftError("Xbox Live 认证失败（HTTP %s）" % status)
    data = json.loads(text)
    token = data.get("Token")
    claims = (data.get("DisplayClaims") or {}).get("xui") or []
    if not token or not claims:
        raise MicrosoftError("Xbox Live 返回数据不完整。")
    return token, claims[0].get("uhs", "")


def _xsts(xbl_token):
    status, text = _request(XSTS_URL, {
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT",
    }, method="POST")
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        data = {}
    if status != 200:
        code = data.get("XErr")
        messages = {
            2148916233: "这个微软账号还没有创建 Xbox 档案，请先登录 xbox.com 创建。",
            2148916235: "当前账号所在地区不支持 Xbox Live。",
            2148916236: "需要进行成人验证。",
            2148916237: "需要进行成人验证。",
            2148916238: "未成年账号需要先加入 Microsoft 家庭组。",
        }
        raise MicrosoftError(messages.get(code, "XSTS 认证失败（HTTP %s，XErr %s）" % (status, code)))
    token = data.get("Token")
    claims = (data.get("DisplayClaims") or {}).get("xui") or []
    if not token or not claims:
        raise MicrosoftError("XSTS 返回数据不完整。")
    return token, claims[0].get("uhs", "")


def _minecraft_login(xsts_token, uhs):
    status, text = _request(MC_LOGIN_URL, {
        "identityToken": "XBL3.0 x=%s;%s" % (uhs, xsts_token),
    }, method="POST")
    data = _json_response(status, text, "Minecraft 登录")
    token = data.get("access_token")
    if not token:
        raise MicrosoftError("Minecraft 登录没有返回令牌，可能该账号没有游戏。")
    return data


def minecraft_profile(access_token):
    status, text = _request(MC_PROFILE_URL, headers={"Authorization": "Bearer " + access_token})
    if status == 404:
        raise MicrosoftError("该账号没有 Minecraft: Java Edition，或尚未创建游戏档案。")
    data = _json_response(status, text, "读取 Minecraft 档案")
    if not data.get("id") or not data.get("name"):
        raise MicrosoftError("Minecraft 档案数据不完整。")
    return data


def minecraft_entitlements(access_token):
    status, text = _request(MC_ENTITLEMENTS_URL, headers={"Authorization": "Bearer " + access_token})
    if status != 200:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return [item.get("name") for item in data.get("items") or [] if item.get("name")]


def build_account(ms_tokens):
    access_token = ms_tokens.get("access_token")
    refresh_token = ms_tokens.get("refresh_token")
    if not access_token or not refresh_token:
        raise MicrosoftError("微软登录结果缺少令牌。")
    xbl_token, _ = _xbox_live(access_token)
    xsts_token, uhs = _xsts(xbl_token)
    mc = _minecraft_login(xsts_token, uhs)
    profile = minecraft_profile(mc["access_token"])
    entitlements = minecraft_entitlements(mc["access_token"])
    return {
        "type": "msa",
        "uuid": profile["id"],
        "name": profile["name"],
        "access_token": mc["access_token"],
        "refresh_token": refresh_token,
        "expires_at": int(time.time()) + int(mc.get("expires_in") or 86400),
        "xuid": "",
        "entitlements": entitlements,
    }


def refresh_account(account):
    refresh_token = account.get("refresh_token")
    if not refresh_token:
        raise MicrosoftError("账号缺少 refresh_token，请重新登录。")
    tokens = refresh_ms_token(refresh_token)
    tokens.setdefault("refresh_token", refresh_token)
    return build_account(tokens)
