# 이투스247 이천기숙학원 · AI 챗봇 언급 모니터 (AEO/GEO)

소비자가 AI 챗봇에 **실제로 하는 질문**을 매일 다시 던져서 다음을 확인합니다.
현재 설정은 **Gemini · ChatGPT · Claude** 3개 엔진을 **무료(체험) 한도 안에서** 돌리도록 맞춰져 있습니다 (아래 '무료 한도 운영' 참고).

1. **얼마나 언급되나**: 이투스247 이천기숙학원이 답변에 나온 비율, 답변 안에서 몇 번째로 나왔는지, 긍정/부정 맥락
2. **출처는 어디인가**: AI가 근거로 쓴 URL을 사이트 유형별로 분류 (공식 홈페이지 / 자사 앱 / 커뮤니티 / 블로그 / 언론 / 제3자 학원정보 / 경쟁사 등)
3. **왜 언급됐고, 왜 안 됐나**: 답변마다 원인 코드를 붙임 (예: "경쟁 학원만 언급됨", "'이투스247'만 나오고 이천캠퍼스는 빠짐", "이천캠퍼스를 다룬 출처가 없음")
4. **무엇을 보완해야 하나**: 원인 빈도를 근거로 AEO/GEO 개선과제 우선순위를 매김
5. **경쟁 학원과 비교**: 같은 질문에서 퀘타·러셀·청솔·시대인재 등이 얼마나 언급되는지, 그리고 학원명만 바꾼 동일 질문 비교

매일 **07:30(KST)** 에 측정하고, **09:00(KST)** 에 요약을 GitHub 이슈(앱 푸시/메일) · Slack · 이메일로 받아봅니다.

## 질문은 어디서 오나

`config/questions.yaml` 은 업로드한 조사 엑셀(`이투스247_이천기숙학원 … TOP10.xlsx`)에서 자동 추출했습니다.

| 출처 | 내용 | 수 |
|---|---|---|
| 2번·4번 시트 | 카테고리별 상위 게시글 + 조회수 TOP30 게시글 제목 원문 (중복 제거) | 54 |
| 3번 시트 | 카테고리별 대표 검색어 | 9 |
| 합계 | | 63 |

엑셀의 4번 시트 집계(언론 133 · 제3자 플랫폼 75 · 공식 홈페이지 0 …)는 `config/baseline.json` 에 **기준선**으로 저장되어 리포트의 출처 분석에서 함께 비교됩니다.

`config/question_templates.yaml` 은 학원명만 바꿔 똑같이 묻는 질문입니다(후기·수업·면학·시설·급식·비용·추천 7종 × 기본 8개 학원).
엑셀을 새로 받으면 `python -m aeo_monitor import-excel 새파일.xlsx` 로 질문과 기준선을 다시 만들 수 있습니다.

## 리포트 구성

`docs/reports/YYYY-MM-DD.html`(대시보드) · `.xlsx`(엑셀) · `.md`(알림용 요약). 최신본은 `docs/index.html`.

- 오늘의 핵심 (규칙 기반 요약 + Gemini가 쓴 해설)
- 핵심 지표: 이천캠퍼스 언급률(전일 대비), '이투스247'만 언급된 비율(캠퍼스 혼동), 공식 홈페이지 인용률, 평균 순위, 감성
- 최근 14회 언급률 추이
- AI 엔진별 / 브랜드 포함·일반 질문별 / 엑셀 카테고리별 언급률
- 경쟁 기숙학원 대비 언급 점유율, 학원별 동일 질문 비교
- 출처 분석: 사이트 유형 비율(전체·언급된 답변·미언급 답변·엑셀 기준선), 많이 인용된 도메인, 이천캠퍼스를 다룬 출처, 경쟁사만 나올 때의 출처
- 언급/미언급 원인 집계 → AEO/GEO 개선과제(우선순위, 실행 항목, 해당 질문 예)
- 질문별 상세: 엔진마다 ●언급(순위) / ◐브랜드만 / ○미언급, 함께 언급된 학원, 원인, 출처 링크

엑셀 파일에는 답변 원문과 모든 출처 URL이 시트별로 들어 있습니다.

## 설정 (처음 한 번)

1. **API 키 등록** — GitHub 저장소 Settings → Secrets and variables → Actions → *New repository secret*
   - `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey) (무료 등급, 카드 불필요)
   - `OPENAI_API_KEY` — [OpenAI Platform](https://platform.openai.com/api-keys)
   - `ANTHROPIC_API_KEY` — [Claude Console](https://console.anthropic.com/settings/keys)
   - 키가 없는 엔진은 자동으로 건너뜁니다.
2. **기본 브랜치** — GitHub 예약 실행(cron)은 저장소 기본 브랜치의 워크플로만 실행합니다(현재 이 브랜치가 기본 브랜치).
3. **알림 채널** (선택, 여러 개 가능)
   - GitHub 이슈: 기본 사용. 저장소를 *Watch* 하면 GitHub 앱 푸시/메일로 매일 9시에 받습니다. 끄려면 변수 `NOTIFY_GITHUB_ISSUE=0`
   - Slack: secret `SLACK_WEBHOOK_URL`
   - 이메일: secrets `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `REPORT_EMAIL_TO`(쉼표로 여러 명)
4. **웹에서 리포트 보기** (선택) — Settings → Pages → Source 를 *GitHub Actions* 로 바꾸고 변수 `ENABLE_PAGES=true` 추가.
   알림 메시지에 `https://<계정>.github.io/<저장소>/reports/날짜.html` 링크가 붙습니다(다른 주소면 변수 `REPORT_SITE_URL`).
5. **공식 도메인 확인** — `config/brands.yaml` 의 `domains` 는 추정값입니다. 이천캠퍼스 공식 홈페이지와 경쟁사 홈페이지의 실제 도메인으로 바꿔야 '공식 홈페이지 인용률'이 정확해집니다.

수동 실행: Actions → *Daily AI mention check* → *Run workflow* (mode: both / collect / notify).

## 로컬 실행

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=... OPENAI_API_KEY=... ANTHROPIC_API_KEY=...
python -m aeo_monitor run               # 측정 + 리포트 (오늘 질문 10개)
python -m aeo_monitor run --daily 0     # 63개 전체 (무료 한도 초과 주의)
python -m aeo_monitor run --limit 5 --no-templates   # 소량 시험
python -m aeo_monitor run --engines mock  # 키 없이 데모 (DEMO 표시, 공개 리포트는 덮어쓰지 않음)
python -m aeo_monitor report             # 저장된 측정으로 리포트만 재생성
python -m aeo_monitor notify             # 오늘 요약 발송
python -m pytest -q
```

## 조정 포인트

| 파일 | 용도 |
|---|---|
| `config/brands.yaml` | 대상·경쟁 학원, 별칭(언급 판정), 공식 도메인 |
| `config/questions.yaml` | 측정 질문 (추가/수정, `enabled: false` 로 제외) |
| `config/question_templates.yaml` | 학원별 동일 질문, 비교할 학원 목록 (`brands: all` 이면 전체) |
| `config/sources.yaml` | 출처 URL → 사이트 유형 분류 규칙 |
| `config/settings.yaml` | 엔진·모델, 하루 질문 수, 고정 질문, 누적 기간, 동시 실행 수 |

## 무료 한도 운영

| 엔진 | 모델 | 무료 여부 | 하루 호출 |
|---|---|---|---|
| Gemini | gemini-2.5-flash | 무료 등급 있음 (구글 검색 그라운딩 포함) | 질문 10 + 해설 1 |
| ChatGPT | gpt-5-mini | 상시 무료 API 없음 — 가입/체험 크레딧 범위에서만 | 질문 10 |
| Claude | claude-haiku-4-5 | 상시 무료 API 없음 — 가입/체험 크레딧 범위에서만 | 질문 10 |

- **하루 10개 질문**(`daily_questions`) = 매일 같은 **고정 질문 4개**(`panel_questions`: 브랜드 질문 2 + 일반 질문 2) + 나머지 59개 중 **6개씩 날짜별 순환**.
  10일이면 63개 질문을 모두 한 번씩 측정합니다.
- **추이·전일 대비**는 매일 같은 고정 질문 기준, **누적 지표**(엔진별·카테고리별·경쟁사·출처·원인·개선과제)는 최근 10일 동안 질문·엔진별 최신 답변 기준입니다.
- 학원별 동일 질문(템플릿)은 호출이 많아 꺼 두었습니다(`include_templates: false`). 경쟁 학원 비교는 같은 63개 질문에서 함께 언급된 학원으로 계산됩니다.
- **한도 소진 시 자동 중단**: 일일 무료 한도 초과나 크레딧 소진 응답을 받으면 그 엔진은 그날 남은 질문을 건너뛰고, 리포트 상단에 표시합니다. 다른 엔진은 계속 측정합니다.
- 해설 문단은 무료인 Gemini가 작성합니다(`insight_engine`).
- 무료 등급 한도(분당/일일)는 계정마다 다르고 수시로 바뀝니다. 실제 한도는 Google AI Studio, OpenAI·Anthropic 콘솔의 Limits/Billing 화면에서 확인하고
  `daily_questions` 를 조정하세요. ChatGPT·Claude 의 웹검색은 검색 1회당 별도 과금되므로 체험 크레딧이 끝나면 결제 없이는 측정되지 않습니다.
- 모델 이름이 폐기되면 `settings.yaml` 의 `models` 만 최신 모델로 바꾸면 됩니다.

## 판정 방식과 한계

- **언급 판정**: `brands.yaml` 별칭 + "이투스"와 "이천"이 가까이(12자) 함께 나오는 경우. "이천청솔"처럼 다른 학원의 "이천"은 제외합니다.
  '이투스247'만 있고 캠퍼스가 불분명하면 '브랜드만 언급'으로 따로 셉니다.
- **감성**: 언급 주변 문장의 키워드(추천·장점 / 단점·불만 등) 기반이라 참고용입니다.
- **출처**: 각 AI가 API로 돌려준 검색·인용 URL 기준입니다(Gemini는 구글 검색 근거, ChatGPT·Claude는 웹검색 인용). 소비자용 앱 화면(ChatGPT 앱, 네이버 AI 브리핑 등)과 완전히 같지는 않습니다.
  네이버 AI 브리핑(Cue:)은 공개 API가 없어 포함되지 않습니다.
- **엑셀 기준선과의 비교**: 엑셀은 "웹검색 상위 9건 노출" 기준, 이 프로그램은 "AI 답변이 사용한 출처" 기준이므로 추세 참고용입니다.
