# 기숙학원 모니터링 (무료 버전)

이투스247 이천기숙학원을 위한 **매일 확인하는 인사이트 대시보드**입니다. 비용 없이 쓰도록 **GitHub Actions(매일 자동 실행) + Cloudflare Pages(화면) + Cloudflare Access(이메일 로그인)** 로 구성합니다.

| 하는 일 | 내용 |
|---|---|
| **경쟁사 콘텐츠 모니터링** | 우리·경쟁 학원의 블로그, 유튜브, 홈페이지 새 게시물을 매일 수집해 회사별·주제별로 정리하고 요약합니다. |
| **AI 챗봇 언급 측정** | 소비자가 AI 챗봇(Gemini·ChatGPT·Claude)에 실제로 하는 질문을 매일 던져, 이투스247 이천이 얼마나·왜 언급되는지, 어떤 출처를 근거로 하는지, AEO/GEO로 무엇을 보완해야 하는지 보여줍니다. |

## 어떻게 동작하나

```
매일 07:00  GitHub Actions 가 채널 수집 + AI 측정 → 대시보드 파일 생성 → Cloudflare Pages 에 배포
매일 09:00  GitHub 이슈(앱 알림) · Slack · 이메일로 요약 알림
언제든      Cloudflare 주소로 접속 → 이메일로 받은 코드로 로그인 → 대시보드
```

- 서버가 없습니다. 수집한 데이터는 저장소의 `data-store` 브랜치에 파일 하나로 보관됩니다.
- **화면은 보기 전용**입니다. 회사·채널 주소·질문은 `config/monitor.yaml` 파일을 GitHub에서 고치면(저장하면 몇 분 안에 자동 반영) 바뀝니다.
- 비용: GitHub 무료 플랜(비공개 저장소도 Actions 월 2,000분, 이 프로그램은 하루 10~20분 사용), Cloudflare 무료 플랜(Pages, Access 50명까지). AI는 Gemini 무료 등급을 기본으로 쓰고, ChatGPT·Claude 는 상시 무료 API가 없어 체험 크레딧 안에서만 동작합니다.

## 화면

| 탭 | 내용 |
|---|---|
| 리서치 캘린더 | 일간·주간·월간. 업체별 동향 카드(중심 이슈, 요약, 핵심 요약, 새 게시물과 원문 링크), 회사별 비교 |
| 리서치 통계 | 기간별 게시물 수, 블로그·유튜브·홈페이지 구분, 회사별 활동 그래프, 주제 분포 |
| 근거 자료 | 수집한 원문 목록. 회사·주제·기간·검색 필터, CSV 내려받기 |
| 수집 관리 | 회사·채널 상태(정상/로그인 필요/오류), AI 질문 목록, 설정 파일 바로 열기 |
| AI 분석 | 이번 주·이번 달(매일 갱신)과 지난 기간 보고서 |
| AI 언급 | 언급률·추이, 경쟁 학원 비교, 출처 분석, 질문별 결과(왜 언급됐나/안 됐나), 개선과제, 엑셀 |

## 설정 순서 (처음 한 번, 약 30분)

### 1. 저장소를 비공개로 바꾸기
수집한 데이터와 경쟁 학원 목록이 공개되지 않게 합니다.
저장소 → **Settings** → 맨 아래 **Danger Zone** → **Change repository visibility** → **Make private**.

### 2. AI 키를 Secrets 에 넣기
저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| 이름 | 값 |
|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) 에서 발급(무료) |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | 쓰는 경우에만 (체험 크레딧이 끝나면 멈춥니다) |

키가 없는 AI는 자동으로 건너뜁니다. 키는 Secrets 에만 있고 화면·데이터 파일에는 나오지 않습니다.

### 3. 수집할 채널 주소 넣기
저장소에서 `config/monitor.yaml` 을 열고 연필(✏️) 아이콘 → `channels:` 아래 예시 줄의 맨 앞 `#` 를 지우고 실제 주소로 바꾼 뒤 **Commit changes**.
네이버 블로그(`https://blog.naver.com/아이디`), 유튜브(`https://www.youtube.com/@채널이름`), 홈페이지 주소를 쓸 수 있습니다. 새 학원은 같은 파일의 `companies:` 에 추가합니다(예시가 파일 안에 있습니다).

### 4. Cloudflare 연결 (화면 배포)
1. https://dash.cloudflare.com 에서 무료 가입합니다.
2. **Account ID** 를 복사합니다 (Workers & Pages 화면 오른쪽에 표시).
3. 오른쪽 위 프로필 → **My Profile** → **API Tokens** → **Create Token** → **Create Custom Token** → 권한 *Account → Cloudflare Pages → Edit* → 만들어진 토큰을 복사합니다 (한 번만 보입니다).
4. GitHub Secrets 에 `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` 두 개를 추가합니다.
5. 저장소 **Actions** 탭 → **Monitor** → **Run workflow** → **Run workflow**. 10~20분 뒤 끝나면 `https://academy-monitor.pages.dev` 가 생깁니다. 이름이 이미 사용 중이면 저장소 Variables 에 `CF_PAGES_PROJECT` 로 다른 이름을 넣고 다시 실행하세요.

### 5. 로그인 걸기 (Cloudflare Access)
1. Cloudflare 왼쪽 메뉴 **Zero Trust** (처음이면 팀 이름을 정하고 **Free** 플랜을 선택합니다. 결제 수단 입력을 요구할 수 있지만 무료 플랜은 청구되지 않습니다).
2. **Access → Applications → Add an application → Self-hosted**
3. Application domain 에 `academy-monitor.pages.dev` 를 입력하고, 정책(Policy)은 **Allow**, 대상은 **Emails** 에 본인(그리고 함께 볼 사람) 이메일을 넣어 저장합니다. 로그인 방식은 기본인 One-time PIN(메일로 받는 코드)이면 충분합니다.
4. 이 주소를 열어 이메일을 입력하고, 메일로 온 코드를 넣으면 대시보드가 열립니다. 휴대폰 홈 화면에 추가해 앱처럼 쓸 수 있습니다.

> 로그인을 걸지 않으면 주소를 아는 누구나 대시보드를 볼 수 있습니다. 5번까지 끝낸 뒤 사용하세요. (Cloudflare 메뉴 이름은 바뀔 수 있습니다.)

### 6. 알림 받기 (선택)
- GitHub 이슈 요약: 저장소 오른쪽 위 **Watch → All activity** 를 켜면 매일 09:00 요약이 GitHub 앱 푸시/메일로 옵니다. Variables 에 `SITE_URL`(대시보드 주소)을 넣으면 요약에 링크가 붙습니다.
- Slack: Secrets `SLACK_WEBHOOK_URL`. 이메일: `SMTP_HOST` `SMTP_PORT` `SMTP_USER` `SMTP_PASSWORD` `SMTP_FROM` `REPORT_EMAIL_TO`.

## 매일 쓰는 방법

- **보기**: 대시보드 주소로 접속합니다.
- **수정**: GitHub → `config/monitor.yaml`(채널 주소·질문·확정 리서치 문구), `config/brands.yaml`(학원 목록·AI 판정 표기), `config/settings.yaml`(AI 종류·하루 질문 수) 를 고치고 Commit changes → 자동으로 다시 수집·배포됩니다. 설정에 오류가 있으면 Actions 가 실패하고 이메일이 옵니다(화면 위쪽에도 경고가 표시됩니다).
- **지금 실행**: Actions → Monitor → Run workflow (mode: `collect` = 수집 후 배포, `rebuild` = 수집 없이 화면만 다시 만들기, `notify` = 알림만).

### 선택 기능: 화면의 'AI 챗봇'·'지금 실행' 버튼
기본으로는 안내 창이 뜹니다. 버튼이 바로 동작하게 하려면 Cloudflare Pages 프로젝트 → **Settings → Variables and Secrets** 에 다음을 추가하고 워크플로를 한 번 더 실행하세요. 모두 Access 로그인 토큰을 검증하므로 로그인한 사람만 쓸 수 있습니다.

| 이름 | 값 |
|---|---|
| `ACCESS_TEAM_DOMAIN` | 예: `myteam.cloudflareaccess.com` (Zero Trust 팀 도메인) |
| `ACCESS_AUD` | 5번에서 만든 Access 앱의 *Application Audience (AUD) Tag* |
| `GEMINI_API_KEY` | AI 챗봇용 (무료 키) |
| `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH` | 지금 실행용. 토큰은 GitHub → Settings → Developer settings → Fine-grained tokens 에서 **이 저장소만**, 권한 *Actions: Read and write* 로 만듭니다. `GITHUB_REPO` 는 `계정/저장소`, `GITHUB_BRANCH` 는 기본 브랜치 이름 |

## 수집 방식과 한계

| 채널 | 방식 |
|---|---|
| 네이버 블로그 | `rss.blog.naver.com/<아이디>.xml` (주소에서 아이디를 자동 인식) |
| 티스토리·RSS/Atom | 피드를 직접 읽음 |
| 유튜브 | 채널 주소에서 채널 ID를 찾아 공식 피드를 읽음 |
| 그 밖의 홈페이지 | 페이지에 RSS 링크가 있으면 사용, 없으면 페이지 링크 목록의 변화를 추적(처음 읽은 링크는 '기존 글'로 간주) |

- 로그인이 필요하거나 자바스크립트로 그려지는 페이지, 수집을 막아 둔 사이트는 **로그인 필요/확인 필요**로 표시됩니다(우회하지 않습니다). 홈페이지 방식은 블로그·유튜브보다 정확도가 낮고, 게시일을 모르면 수집한 날짜를 씁니다.
- 주제 분류와 감성 판정은 키워드 규칙이라 참고용입니다. 각 사이트의 이용약관을 확인하고 쓰세요. 공개 게시물의 제목·요약·원문 링크만 저장합니다.
- 화면에서 볼 수 있는 기간은 최근 약 6개월(캘린더·통계), 근거 자료는 최근 1년입니다.

## AI 챗봇 언급 측정

- 하루 **질문 10개**(기본): 매일 같은 **고정 질문 4개**(추이·전일 대비용) + 나머지를 **6개씩 순환**(10일이면 63개 전체). 질문 추가·제외는 `monitor.yaml`, 하루 질문 수와 AI 종류는 `settings.yaml` 에서 바꿉니다.
- 모델: Gemini `gemini-2.5-flash`, ChatGPT `gpt-5-mini`, Claude `claude-haiku-4-5` (웹검색 포함, 가장 저렴한 모델). 일일 한도·크레딧이 소진되면 그 AI는 그날 건너뛰고 화면에 표시합니다.
- 언급 판정은 등록된 표기와 "이투스+이천 근접" 규칙으로 하며, AI 답변은 실행마다 달라질 수 있습니다.

## 한계 (무료 방식의 대가)

- 화면에서 직접 고칠 수 없습니다(설정 파일 수정). '지금 실행'은 선택 기능을 설정하면 버튼으로, 아니면 GitHub Actions 에서 합니다.
- GitHub 예약 실행은 정확히 07:00 이 아니라 몇 분~1시간 늦을 수 있습니다.
- Actions 무료 시간은 월 2,000분입니다. 하루 20분이면 월 600분 안팎입니다.
- 데이터는 `data-store` 브랜치의 파일 하나(이력 없이 덮어씀)와 실행마다 7일 보관되는 사이트 파일이 전부입니다. 중요한 데이터라면 가끔 `data-store` 브랜치의 `aeo.db` 를 내려받아 두세요.

## 보안

- Cloudflare Access 로그인 뒤에서만 화면과 데이터가 열립니다. 로그인 없이 쓰면 공개됩니다.
- 'AI 챗봇'·'지금 실행' 함수는 Access 로그인 토큰의 서명·만료·대상을 검증하고, 변경 요청에는 전용 헤더가 있어야 합니다.
- 수집기는 사용자가 정한 주소를 읽으므로 http/https 만 허용하고 내부망 주소는 막습니다. 화면에 나오는 외부 텍스트는 모두 이스케이프하고, CSV는 엑셀 수식 주입을 막습니다.

## 고급: 직접 서버로 운영하기

화면에서 회사·채널을 바로 추가·수정하고 '지금 실행'을 누르는 **로그인형 웹 서비스** 버전도 들어 있습니다. 항상 켜져 있는 서버와 영구 디스크가 필요해 무료로는 어렵습니다.
`docker compose up -d`(`.env.example` 참고) 또는 Render 의 `render.yaml` 로 배포합니다. 환경변수 `APP_PASSWORD`, `SECRET_KEY` 가 필요합니다. 이 방식은 화면에서 모든 설정을 바꾸고 `config/` 파일은 첫 실행 때 한 번만 읽습니다.

## 개발

```bash
pip install -r requirements-dev.txt
python -m pytest -q                                   # 테스트 (Functions 테스트는 node 필요)
AEO_DATA_DIR=/tmp/preview python -m aeo_monitor demo-seed          # 미리보기용 가짜 데이터
AEO_DATA_DIR=/tmp/preview python -m aeo_monitor build-site --out /tmp/site --no-sync --skip-collect
python -m http.server 8000 --directory /tmp/site      # 정적 사이트 미리보기
python -m aeo_monitor build-site --out site            # 실제 수집 + 사이트 생성 (Actions 가 하는 일)
```

구조: `aeo_monitor/content/`(채널 수집·분류·통계·AI 요약), `aeo_monitor/engines/`(Gemini·ChatGPT·Claude·Perplexity), `aeo_monitor/staticsite.py`(정적 사이트 생성), `aeo_monitor/server/`(서버 버전), `web/`(화면), `functions/`(Cloudflare 선택 기능), `.github/workflows/monitor.yml`(매일 실행).
