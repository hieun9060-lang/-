"""오전 9시 알림: Slack / 이메일 / GitHub 이슈 (설정된 채널만)."""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

import requests

log = logging.getLogger(__name__)


def notify_slack(markdown: str) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return False
    text = markdown.replace("**", "*").replace("## ", "").replace("### ", "")
    r = requests.post(url, json={"text": text}, timeout=30)
    r.raise_for_status()
    return True


def notify_email(subject: str, markdown: str) -> bool:
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("REPORT_EMAIL_TO")
    if not (host and to):
        return False
    msg = MIMEText(markdown, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", ""))
    msg["To"] = to
    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=60) as s:
        s.starttls()
        if os.environ.get("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
        s.sendmail(msg["From"], [x.strip() for x in to.split(",")], msg.as_string())
    return True


def notify_github_issue(title: str, markdown: str) -> bool:
    """GitHub Actions 안에서 실행되면 GITHUB_TOKEN 으로 이슈를 올려 앱/메일 알림을 받는다."""
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo) or os.environ.get("NOTIFY_GITHUB_ISSUE", "1") == "0":
        return False
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    body = {"title": title, "body": markdown, "labels": ["daily-ai-report"]}
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code == 422:  # 라벨 문제 등 → 라벨 없이 재시도
        body.pop("labels")
        r = requests.post(url, headers=headers, json=body, timeout=30)
    r.raise_for_status()
    return True


def send_all(title: str, markdown: str) -> list[str]:
    sent = []
    for name, fn in (("slack", lambda: notify_slack(markdown)),
                     ("email", lambda: notify_email(title, markdown)),
                     ("github_issue", lambda: notify_github_issue(title, markdown))):
        try:
            if fn():
                sent.append(name)
        except Exception as e:  # noqa: BLE001 - 한 채널 실패가 다른 채널을 막지 않도록
            log.error("%s 알림 실패: %s", name, e)
    return sent
