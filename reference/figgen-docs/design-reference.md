# 디자인 레퍼런스 — figurelabs.ai 클론 (M7 적용판)

> **M7 재테마**: figurelabs.ai(chat.figurelabs.ai)와 최대한 동일하게 전환.
> **light-blue SaaS** 톤(연블루 배경 + 화이트 카드 + 다크네이비/블루 액센트 + Inter 산세리프).
> (이전 Claude 라이트 아이보리+코럴+Newsreader는 폐기.)

## 토큰 (`frontend/css/app.css :root`)
- 배경 `--bg:#f5f8ff`(연블루 틴트), 표면 `--surface:#fff`/`--surface-2:#eef3fc`(쿨 패널)
- 잉크 `--ink:#0f1b35`(다크 네이비), `--ink-soft:#3a4a6b`, `--muted:#7488a8`
- 강조 `--accent:#3b82f6`(블루), `--accent-ink:#1e40af`(다크블루/버튼·액티브), `--accent-soft:#eff6ff`
- 보더 `--border:#e2e9f5`/`--border-strong:#cdd9ee`, 쿨틴트 그림자(`rgba(30,55,120,…)`)
- 헤딩·본문 모두 **Inter**(700/800 헤딩). `--font-head`=`--font-body`=Inter.

## 정보구조(IA) — figurelabs 매칭
- **헤더**: `✦ FigGen` 브랜드 · Home/History/Projects · 우측 `Upgrade`(다크 pill) + 크레딧 `✦ 250`
  (코스메틱 mock) + 빨강 아바타. 좌측 56px **아이콘 rail**(⌂/🕘/🗂/＋).
- **Home = 랜딩 ↔ 워크스페이스 전환**:
  - **랜딩**(`#landing`, `components/landing.js`): 풀폭 중앙 — 히어로("Scientific figures. made
    effortless.") + **2모드 토글**(Scientific Figures / Flowcharts Beta) + 프롬프트 카드 + 분야 갤러리
    + Recent Projects. `s.landing && !activeJob`일 때 표시.
  - **워크스페이스**(`#workspace`): 2-pane `clamp(360px,33%,460px) 1fr`(좌 대화 chatPanel · 우 캔버스).
    생성/대화 중 표시.
- **프롬프트 카드**: 입력모드 버튼(Enhance Figure/Sketch to Figure/Add Ref Figure) + 📎/💡(AI 강화)/🎨
  (색 팔레트) + 모델칩 `🍌 SeeDream 4.5` + 스타일·종횡비 셀렉터 + 라운드 ↑ 전송.
- **분야 갤러리**: 9분야 칩(`disc-chip`) × 6 템플릿 카드(`tpl-card`, 3-col 그리드) = 54.
  Flowcharts 모드는 7개 표준 템플릿(CONSORT/PRISMA/Fishbone/Roadmap/…). 데이터 = `frontend/data/templates.json`.
  카드 썸네일 = `/img/templates/<id>.png`(`scripts/gen_template_thumbs.py`가 실제 생성, 없으면 CSS
  그라데이션 placeholder 폴백).
- **결과/다운로드 바**: Export 드롭다운(PPTX/SVG/PNG 1K·4K·8K/JPG) + 코스메틱 비용 pill.

## 컴포넌트 맵
| 파일 | 역할 |
|---|---|
| `components/landing.js` | 풀폭 랜딩(히어로·2모드·프롬프트·분야칩·54카드·Recent) |
| `components/chatPanel.js` | 워크스페이스 좌 대화 + 컴포저 툴(스타일·종횡비·강화·provider·모델칩) |
| `components/downloads.js` | Export 드롭다운(고해상도/JPG, exportUrl) |
| `data/templates.js` | `/data/templates.json` 로더 + `templateById` |
| `js/state.js` | +`mode/discipline/landing/credits/templates`, `form.aspect/palette` |
| `js/actions.js` | +`setMode/setDiscipline/pickTemplate/enhancePrompt/setAspect/setPalette` |

## 코스메틱-only(백엔드 미연결)
크레딧 배지·Upgrade·Export 비용 pill·아바타·"Edit in Canvas ✦150" 류는 **표시 전용**. 절대 게이팅·
전송 안 함(실 결제·크레딧 미터링은 미구현).
