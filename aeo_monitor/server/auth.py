"""단일 비밀번호 로그인 + 서명된 세션 쿠키."""
from __future__ import annotations

import hmac
import os
import time
from collections import defaultdict

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE = "aeo_session"
MAX_AGE = 14 * 24 * 3600
FAIL_LIMIT, LOCK_SECONDS = 5, 15 * 60


class Auth:
    def __init__(self):
        self.password = os.environ.get("APP_PASSWORD", "")
        self.secret = os.environ.get("SECRET_KEY", "")
        self.no_auth = os.environ.get("APP_ALLOW_NO_AUTH") == "1"
        if not self.no_auth:
            if len(self.password) < 8:
                raise RuntimeError("환경변수 APP_PASSWORD(8자 이상)를 설정하세요. (로컬 시험용: APP_ALLOW_NO_AUTH=1)")
            if len(self.secret) < 16:
                raise RuntimeError("환경변수 SECRET_KEY(16자 이상 무작위 문자열)를 설정하세요.")
        self.ser = URLSafeTimedSerializer(self.secret or "dev-secret-not-for-production", salt="aeo-session")
        self._fails: dict[str, list[float]] = defaultdict(list)

    @staticmethod
    def client_ip(request: Request) -> str:
        if os.environ.get("TRUST_PROXY") == "1":
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def locked(self, ip: str) -> int:
        now = time.time()
        self._fails[ip] = [t for t in self._fails[ip] if now - t < LOCK_SECONDS]
        if len(self._fails[ip]) >= FAIL_LIMIT:
            return int(LOCK_SECONDS - (now - self._fails[ip][0]))
        return 0

    def check_password(self, ip: str, password: str) -> str | None:
        """맞으면 세션 토큰. 틀리면 None (실패 기록)."""
        if self.no_auth:
            return self.ser.dumps({"u": "admin"})
        ok = hmac.compare_digest(password.encode(), self.password.encode())
        if not ok:
            self._fails[ip].append(time.time())
            return None
        self._fails.pop(ip, None)
        return self.ser.dumps({"u": "admin"})

    def valid(self, token: str | None) -> bool:
        if self.no_auth:
            return True
        if not token:
            return False
        try:
            self.ser.loads(token, max_age=MAX_AGE)
            return True
        except (BadSignature, SignatureExpired):
            return False


def require_auth(request: Request) -> None:
    auth: Auth = request.app.state.auth
    if not auth.valid(request.cookies.get(COOKIE)):
        raise HTTPException(401, "로그인이 필요합니다.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with") != "aeo-app":
        raise HTTPException(403, "잘못된 요청입니다.")  # CSRF: 브라우저 교차 사이트 요청은 이 헤더를 붙일 수 없음
