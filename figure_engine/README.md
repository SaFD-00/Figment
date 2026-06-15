# FigGen — 논문용 figure 생성 프레임워크

자연어 설명·논문 메서드·CSV·참조 이미지를 입력하면, LLM이 **의미·구조만** 담은 중간 JSON(`FigureSpec`)을 만들고
결정론적 Python 렌더러가 **PowerPoint/Illustrator에서 후편집 가능한 PPTX+SVG**를 동시에 산출한다.

> 핵심 원칙 — **"LLM은 의미·구조만, 좌표·색은 코드가."** LLM에 절대좌표를 요구하지 않아 raw SVG 좌표 환각을 피한다.

## 지원 figure 5종
- `scientific_illustration` — **FigureLabs식 풍부한 단일 장면 일러스트**(쥐·조직·세포 등). 이미지 모델이
  글자 없는 응집 장면을 그리고, 라벨·제목은 편집 가능 벡터 텍스트로 오버레이 + 장면 아트는 벡터화(SVG 편집).
- `method_diagram` — 방법론/아키텍처 다이어그램 (`--box-icons`로 박스마다 일러스트 삽입 가능)
- `concept` — 개념도/일러스트 (명시적 `--type concept`로만 선택)
- `chart` — 데이터 차트 (실데이터 직접 전달 → 수치 환각 차단)
- `graphical_abstract` — 풀이미지 베이스 + 편집 가능 라벨 오버레이

> 자동 분류는 **공격적 기본값**으로 동작한다: 명백한 아키텍처/파이프라인(`method_diagram`)·데이터 플롯(`chart`)·
> 명시적 graphical_abstract가 아니면 `scientific_illustration`(풍부한 장면 일러스트)으로 라우팅한다. `--type`으로 강제 지정 가능.

## 설치

### 사전 요구사항
| 항목 | 요구 | 비고 |
|---|---|---|
| Python | 3.11+ (본 환경 3.12) | `pyproject.toml` `requires-python = ">=3.11"` |
| [uv](https://docs.astral.sh/uv/) | 권장 | 표준 `python -m venv` + `pip`로도 가능 |
| Homebrew `cairo` | macOS 필수 | SVG→PNG 래스터화(cairosvg). `brew install cairo` |
| API 키 | 선택 | 없으면 `mock` provider로 전 기능 오프라인 구동 |

> ⚠️ **이 프로젝트는 Google Drive 동기화 폴더 안에 있다.** venv도 프로젝트 안 `.venv`에 둔다(`.gitignore`에 포함).
> 잦은 파일 쓰기의 동기화 충돌을 피하려면 **Drive 앱 설정에서 `.venv/`·`outputs/` 폴더를 동기화 제외**하는 것을 권장한다.
> (venv는 절대경로·플랫폼 의존 바이너리를 담으므로 다른 기기로 동기화돼도 그대로 쓰지 못한다 — 기기마다 재생성한다.)

### 설치 단계
```bash
# 0) (macOS) SVG→PNG 래스터화용 cairo
brew install cairo

# 1) venv (프로젝트 안 .venv)
uv venv .venv --python 3.12

# 2) 의존성 + 패키지 (editable, dev 도구 포함)
uv pip install --python .venv/bin/python -e ".[dev]"

# 3) API 키 (없어도 mock provider로 오프라인 동작) — OpenRouter
cp .env.example .env   # OPENROUTER_API_KEY 입력 (선택; SeeDream 4.5 + MiniMax M3)
```

설치가 끝나면 `figgen` 실행 파일은 `.venv/bin/figgen`에 생긴다. 아래 예시는 모두 이 경로를 쓴다.
`source .venv/bin/activate` 후에는 그냥 `figgen ...`으로 호출해도 된다.

```bash
.venv/bin/figgen --version    # 설치 확인
.venv/bin/figgen --help       # 전체 서브커맨드 도움말 (render / gen / serve)
```

> **macOS / cairosvg 내부 동작** — uv/pyenv Python은 `/opt/homebrew/lib`를 dlopen 경로에 두지 않으므로,
> `figgen`은 `import` 시 `figgen._native`가 검색 경로를 자동 보강한다(별도 환경변수 불필요).
> `cairo` 미설치 시 PNG 미리보기 단계에서 에러가 난다 — `brew install cairo`로 해결.

## 실행 방법

`figgen`은 서브커맨드 3개로 동작한다. **`serve`(웹 앱)**가 critic 보정·에셋 생성까지 도는 풀 파이프라인이고,
**`gen`/`render`**는 같은 코어를 쓰는 단발 CLI 경로다.

| 커맨드 | 용도 | API 키 |
|---|---|---|
| `figgen serve` | 로컬 웹 앱(프로젝트/버전 관리·실시간 진행·편집 UI). 풀 파이프라인 | 선택(mock 가능) |
| `figgen gen "<설명>"` | 설명→`FigureSpec`→산출물 단발 생성 | 선택(mock 가능) |
| `figgen render <spec.json>` | 기존 `spec.json`만 결정론 렌더 | **불필요** |

### 1. `figgen serve` — 웹 앱 (권장)
브라우저 UI에서 입력(텍스트·CSV·참조 이미지)→생성→미리보기→부분 재생성·편집까지 한 흐름으로 처리한다.

```bash
.venv/bin/figgen serve            # http://127.0.0.1:8736 자동 오픈
```
기동 시 콘솔에 서버 URL·`outputs` 경로·가용 provider 목록을 출력한다. `/api/health`가 200을 반환하면 브라우저가 자동으로 열린다.

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--host HOST` | `127.0.0.1` | 바인드 호스트 (`FIGGEN_HOST`) |
| `--port PORT` | `8736` | 포트. **사용 중이면 +1씩 최대 20회 자동 탐색** (`FIGGEN_PORT`) |
| `--no-browser` | off | 브라우저 자동 오픈 비활성 |
| `--outputs DIR` | `./outputs` | 산출물 루트 (`FIGGEN_OUTPUTS`) |
| `--reload` | off | 개발용 코드 자동 리로드(이때 브라우저 자동 오픈 생략) |

```bash
# 외부 접속 허용 + 포트 지정 + 브라우저 비오픈 + 산출물 위치 변경
.venv/bin/figgen serve --host 0.0.0.0 --port 9000 --no-browser --outputs ~/.figgen/outputs
```

### 2. `figgen gen` — 설명에서 단발 생성
```bash
.venv/bin/figgen gen "Transformer encoder-decoder" --type method_diagram --provider mock -o out/
```

| 인자/옵션 | 기본값 | 설명 |
|---|---|---|
| `description` (위치 인자) | — | figure 설명 또는 논문 메서드 텍스트 |
| `--type TYPE` | 자동 분류 | `method_diagram` · `concept` · `chart` · `graphical_abstract` · `scientific_illustration` |
| `--style NAME` | `nature_minimal` | 스타일 프리셋 (아래 목록) |
| `--provider P` | `mock`* | `mock` · `openrouter` · `openai` · `auto` (`FIGGEN_PROVIDER`) |
| `--dpi N` | `192` | PNG/JPG 래스터 DPI |
| `--format F` | `png` | 래스터 포맷 (`png` · `jpg`) |
| `--box-icons` | off | `method_diagram` 각 박스에 작은 일러스트 생성(박스당 이미지 1콜, 비용↑) |
| `-o, --out DIR` | `figgen_out` | 출력 디렉토리 |

\* `--provider` 미지정 시 `.env`의 `FIGGEN_PROVIDER`(기본 `mock`)를 따른다. `auto`는 키가 있으면 OpenRouter→OpenAI, 없으면 `mock`으로 안전 폴백한다.

```bash
# FigureLabs식 풍부한 장면 일러스트 (이미지 모델 필요 → --provider openrouter)
.venv/bin/figgen gen "상처 치유: 손상→치료→회복 단계의 마우스, 조직 단면과 면역세포" \
    --type scientific_illustration --provider openrouter -o out/
# → out/figure.svg : 장면 아트가 편집 가능 벡터 path + 라벨/제목은 벡터 텍스트(Illustrator/Inkscape 편집)
#    out/figure.pptx: 장면은 이동 가능 그림, 각 라벨은 편집 가능 텍스트 박스
```
완료 시 선택된 `figure_type`·요소 수·캔버스 크기와 레이아웃 경고(`connector_crossing`/`empty_content` 등)를 콘솔에 출력한다.
> 참고: `gen` 단발 경로는 planner→stylist→렌더(+`scientific_illustration` 장면 생성, `--box-icons` 박스 에셋)까지 돈다.
> **VLM critic 보정 루프는 웹 앱(`serve`)의 오케스트레이터에서 동작**한다.

### 3. `figgen render` — spec만 렌더 (API 불필요)
이미 만들어진 `spec.json`(예: `gen`/웹 앱 산출물)을 결정론적으로 다시 렌더한다. 스타일만 바꿔 재출력할 때 유용하다.

```bash
.venv/bin/figgen render out/spec.json -o out2/                 # 그대로 렌더
.venv/bin/figgen render out/spec.json --style science_bold -o out2/   # 스타일 교체 재렌더
```

| 인자/옵션 | 기본값 | 설명 |
|---|---|---|
| `spec` (위치 인자) | — | `FigureSpec` JSON 경로 |
| `--style NAME` | spec의 값 유지 | 지정 시 spec의 스타일시트를 덮어씀 |
| `-o, --out DIR` | `figgen_out` | 출력 디렉토리 |
| `--no-pptx` | off | PPTX 생략 |
| `--no-png` | off | 미리보기 PNG 생략 |

## provider 모드 (OpenRouter 기본)
- `mock`(기본/키없음 폴백) — 키 불필요. 타입별 캔드 `FigureSpec` + PIL placeholder 에셋으로 오프라인 구동.
- `openrouter` — `.env`에 `OPENROUTER_API_KEY` 입력 후 사용. LLM `minimax/minimax-m3`(planner·classifier·critic(비전)·chart·research), 이미지 **`bytedance-seed/seedream-4.5`**(SeeDream 4.5). 키 없으면 `mock` 폴백.
- `openai` — 선택적 폴백. `.env`에 `OPENAI_API_KEY` 입력 시 `gpt-image`/`gpt-5.x` 사용.
- `auto` — 키가 있으면 OpenRouter→OpenAI, 없으면 `mock`.

> 모든 모델 ID는 `FIGGEN_*` 환경변수로 오버라이드 가능. **주의**: SeeDream은 투명·mask 인페인트 미지원
> (Region Redraw degrade); critic/sketch/참조분석의 `FIGGEN_VISION_MODEL`은 비전 가능 OpenRouter 모델 권장.

## figurelabs 디자인 클론 & 웹 앱 네비
웹 앱(`serve`)은 **figurelabs.ai와 최대한 동일한 UI**(light-blue SaaS + Inter)로, 헤더에 Upgrade/크레딧/
아바타·좌측 아이콘 rail을 둔다. Home은 **랜딩(갤러리) ↔ 워크스페이스(2-pane)** 전환: 랜딩에는 히어로 +
**2모드 토글(Scientific Figures / Flowcharts)** + 프롬프트 카드 + **9분야×6 템플릿 갤러리(54)** + Recent.
템플릿 썸네일은 `scripts/gen_template_thumbs.py --provider openrouter`로 실제 생성한다.

**figure 생성 방법은 하나 — 대화로 계획을 확정한 뒤 생성한다.**
1. 왼쪽 대화에 만들 figure를 설명한다. 필요하면 **데이터 파일(CSV/JSON · 차트용)**·**참조 스타일 이미지**를 첨부한다.
2. 어시스턴트가 부족한 정보만 짧게 되묻고(필요시), 충분하면 **계획 카드**를 제시한다. (`POST /api/projects/{pid}/plan`, 동기·stateless)
3. **‘✨ 이 계획으로 생성’**을 누르면 합의된 계획으로 생성된다(기존 `/jobs` 재사용).
- **이미지 첨부 = 대화가 용도를 묻는다**: 스타일 참조 / 손스케치(→정제 figure) / 기존 figure 정제(업스케일·색보정·노이즈) / 벡터화(PNG→SVG)를 대화로 정해 해당 task로 라우팅.
- **생성 후 편집**: 캔버스에서 요소를 클릭해 좌측 대화로 수정 지시(요소 선택 시 해당 요소만), 또는 상단 인-캔버스 도구(Region Redraw·Text Edit·White BG·Upscale).
- **소형 UX(figurelabs 매칭)**: 💡 AI 프롬프트 강화(`/enhance-prompt`), 🎨 수동 색 팔레트, 종횡비(Auto/square/tall) 셀렉터, `flat` 스타일 프리셋.
- **웹 리서치 그라운딩 토글** — 생성 전 OpenRouter `:online` 웹검색으로 과학적 맥락을 수집해 정확도 보강(기본 OFF).
- **고해상도/JPG export** — 다운로드 시 `?res=1k|4k|8k&format=png|jpg`로 `figure.svg`에서 지연 렌더.

### 스타일 프리셋
`--style`(`gen`) / `--style`(`render`) / 웹 앱에서 선택:

| id | 설명 |
|---|---|
| `nature_minimal` | 기본값. Nature풍 미니멀 |
| `neurips_pastel` | NeurIPS풍 파스텔 |
| `ieee_classic` | IEEE 클래식 |
| `science_bold` | Science풍 볼드 |
| `grayscale_print` | 흑백 인쇄용 |
| `flat` | figurelabs 'Flat' — 굵은 솔리드 면·그라데이션 없음·둥근 모서리 |

### 환경변수 (`.env`)
`.env.example`을 복사해 채운다. 전부 선택이며, 비우면 표의 기본값을 쓴다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `OPENROUTER_API_KEY` | — | OpenRouter 키(비우면 mock 폴백) |
| `OPENAI_API_KEY` | — | (선택) OpenAI 폴백 키 |
| `FIGGEN_PROVIDER` | `openrouter` | 기본 provider (`mock`·`openrouter`·`openai`·`auto`) |
| `FIGGEN_OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter 베이스 URL |
| `FIGGEN_PLANNER_MODEL` | `minimax/minimax-m3` | planner 모델 |
| `FIGGEN_CLASSIFIER_MODEL` | `minimax/minimax-m3` | 분류기 모델 |
| `FIGGEN_VISION_MODEL` | `minimax/minimax-m3` | critic(VLM)·sketch 비전 모델 (비전 가능 모델 권장) |
| `FIGGEN_CHART_CODER_MODEL` | `minimax/minimax-m3` | 차트 코드 생성 모델 |
| `FIGGEN_DEFAULT_IMAGER` | `bytedance-seed/seedream-4.5` | 이미지(생성·edit) 모델 |
| `FIGGEN_RESEARCH_ENABLED` | `false` | 웹검색 그라운딩 기본값 |
| `FIGGEN_RESEARCH_MODEL` | `minimax/minimax-m3` | research(`:online`) 모델 |
| `FIGGEN_RESEARCH_MAX_CHARS` | `4000` | 리서치 컨텍스트 최대 길이 |
| `FIGGEN_CRITIC_ENABLED` | `true` | critic 보정 루프 on/off |
| `FIGGEN_MAX_CRITIC_ITERS` | `2` | critic 최대 반복 |
| `FIGGEN_SCENE_VECTORIZE` | `true` | 장면 아트 vtracer 벡터화 |
| `FIGGEN_DIAGRAM_BOX_ICONS` | `false` | method_diagram 박스 일러스트(=`--box-icons`) |
| `FIGGEN_HOST` | `127.0.0.1` | 서버 호스트 |
| `FIGGEN_PORT` | `8736` | 서버 포트 |
| `FIGGEN_MAX_CONCURRENT_JOBS` | `2` | 동시 job 수(웹 앱) |
| `FIGGEN_OUTPUTS` | `./outputs` | 산출물 루트 |
| `FIGGEN_ASSET_CACHE` | `~/.figgen/assets_cache` | 전역 에셋 캐시(홈, 비동기화) |

## 산출물 레이아웃
**웹 앱(`serve`)** — 프로젝트/버전 단위로 누적:
```
outputs/projects/{project_id}/
  project.json
  inputs/{file_id}_{name}
  jobs/{job_id}/
    job.json  spec.json  figure.pptx  figure.svg  preview.svg  preview.png  assets/*.png
```
**`gen`/`render`** — `-o`로 지정한 디렉토리에 평평하게:
```
out/
  spec.json  figure.svg  preview.svg  figure.pptx  preview.png  assets/*.png   # render는 --no-pptx/--no-png로 일부 생략
```
`FIGGEN_OUTPUTS`로 웹 앱 산출물 위치 변경 가능(예: `~/.figgen/outputs`). 전역 에셋 캐시는 `~/.figgen/assets_cache`(홈, 비동기화).

## 개발
```bash
.venv/bin/python -m pytest      # 테스트
.venv/bin/ruff check src tests  # 린트
```

## 라이브 API 검증 (키 확보 후)
```bash
.venv/bin/python scripts/smoke_structured.py   # 재귀 FigureSpec 구조적 출력 성공률 측정
.venv/bin/python scripts/smoke_image.py        # gpt-image 투명 PNG alpha 채널 확인
```

## 트러블슈팅
- **`OSError: cannot load library 'libcairo...'` / PNG 생성 실패** → macOS는 `brew install cairo`. 그래도 안 되면 venv 재생성.
- **`--provider openai`인데 결과가 placeholder** → `.env`의 `OPENAI_API_KEY`가 비어 있어 `mock`으로 폴백된 것. 키 입력 후 재실행(서버는 재기동).
- **포트 8736 충돌** → `serve`는 자동으로 +1씩 최대 20회 빈 포트를 찾는다. 콘솔에 출력된 실제 URL을 확인하거나 `--port`로 지정.
- **Drive 동기화 충돌/느림** → Drive 앱에서 `.venv/`·`outputs/` 동기화 제외, 또는 `FIGGEN_OUTPUTS=~/.figgen/outputs`로 산출물을 홈으로 분리.
- **다른 기기에서 venv가 안 됨** → venv는 플랫폼 의존이라 동기화로 공유 불가. 기기마다 `uv venv` + `uv pip install`로 재생성.

## 아키텍처
```
입력 → 분류(공격적 기본값)
   ├─ scientific_illustration → Planner.plan_scene(LLM 장면 브리프)
   │     → generate_base_image(글자 없는 응집 장면) → vtracer 벡터화
   │     → build_overlay_spec(Free 루트: 벡터 장면 + 편집 라벨)   ─┐
   └─ 그 외 → Planner(LLM, 구조적 출력) → FigureSpec(JSON)         │
     → Stylist(저널 프리셋, role→스타일 결정론적 주입)  ←──────────┘
     → AssetGen(아이콘/일러스트 병렬 + 차트 트랙; method_diagram은 --box-icons로 박스 일러스트)
     → LayoutEngine(2-pass measure/arrange, mm 단위) → ResolvedLayout
     → Resolver(스타일 병합 + 사전 줄바꿈 확정) → ResolvedFigure
     → SvgRenderer + PptxRenderer (결정론적 그리기 전용; 장면 벡터는 SVG에 <path> 인라인)
     → Critic(VLM + 레이아웃 경고 → 제한된 PatchOp, best-snapshot; 장면은 라벨 위치 검증)
```
**레이아웃 견고화**: 빈 `free` 노드는 0크기로 붕괴, 캔버스 초과 시 균일 축소, 과대 변의 커넥터 부착점은
중앙 클램프 — `method_diagram`이 빈 박스/거대 노드로 캔버스를 뒤덮으며 깨지던 문제를 차단하고 `connector_crossing`·
`empty_content` 경고를 CLI에 노출한다. 설계 상세는 `docs/DESIGN.md` 참조.
