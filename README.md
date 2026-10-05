# 이투스247 이천기숙학원 · AI 챗봇 언급 모니터 (AEO/GEO)

소비자가 AI 챗봇(Claude · ChatGPT · Gemini · Perplexity)에 **실제로 하는 질문**을 매일 다시 던져서 다음을 확인합니다.

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

- 오늘의 핵심 (규칙 기반 요약 + `ANTHROPIC_API_KEY` 가 있으면 Claude 해설)
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
   - `ANTHROPIC_API_KEY` (Claude, 웹검색 포함) · `OPENAI_API_KEY` (ChatGPT) · `GEMINI_API_KEY` (Gemini) · `PERPLEXITY_API_KEY` (Perplexity)
   - 등록한 엔진만 측정합니다. 하나만 있어도 동작합니다.
2. **기본 브랜치에 병합** — GitHub 예약 실행(cron)은 저장소 기본 브랜치의 워크플로만 실행합니다.
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
export ANTHROPIC_API_KEY=...            # 필요한 엔진 키
python -m aeo_monitor run               # 측정 + 리포트
python -m aeo_monitor run --limit 5 --no-templates --engines claude   # 소량 시험
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
| `config/settings.yaml` | 엔진, 모델, 질문당 반복 횟수, 동시 실행 수 |

**비용 감각**: 기본 설정은 하루 119개 질문(실제 63 + 동일질문 56) × 엔진 수만큼 호출합니다. 웹검색 포함 호출이라
엔진 4개를 모두 켜면 하루 약 480회입니다. 비용을 줄이려면 템플릿 학원 수를 줄이거나 `include_templates: false`, 엔진 수를 줄이세요.
AI 답변은 매번 조금씩 달라지므로 `samples_per_question` 을 2~3으로 올리면 수치가 안정됩니다(비용도 비례).

## 판정 방식과 한계

- **언급 판정**: `brands.yaml` 별칭 + "이투스"와 "이천"이 가까이(12자) 함께 나오는 경우. "이천청솔"처럼 다른 학원의 "이천"은 제외합니다.
  '이투스247'만 있고 캠퍼스가 불분명하면 '브랜드만 언급'으로 따로 셉니다.
- **감성**: 언급 주변 문장의 키워드(추천·장점 / 단점·불만 등) 기반이라 참고용입니다.
- **출처**: 각 AI가 API로 돌려준 검색·인용 URL 기준입니다. 소비자용 앱 화면(ChatGPT 앱, 네이버 AI 브리핑 등)과 완전히 같지는 않습니다.
  네이버 AI 브리핑(Cue:)은 공개 API가 없어 포함되지 않습니다.
- **엑셀 기준선과의 비교**: 엑셀은 "웹검색 상위 9건 노출" 기준, 이 프로그램은 "AI 답변이 사용한 출처" 기준이므로 추세 참고용입니다.
