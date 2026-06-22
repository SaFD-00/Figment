# Figment

**Figures & images, made effortless.** Figment는 **FigGen**(과학 도식 파이프라인)과 **ImgGen**(로컬 이미지
스튜디오)을 하나의 제품으로 통합한 이미지 생성 스튜디오입니다. 단일 **FastAPI** 백엔드 위에 깔끔한
**Next.js** UI를 얹어, **클라우드 모델**(OpenRouter)과 **로컬 모델**(ComfyUI / Ollama)을 **생성할 때마다 UI에서
골라** 사용할 수 있습니다.

로컬 엔진은 **단일 NVIDIA H100 80GB(CUDA, GPU 0)** 를 타깃으로 하며, 실사 스택 전체(~70GB)가 한 번에
**동시 상주**하도록 구성되어 있습니다(예산 78GB). 영상(Wan 2.2)은 필요할 때 스왑인됩니다.

---

## 주요 기능

**Generate — 아이디어를 즉시 이미지/도식으로**
- **Text-to-Image / Figure** — 텍스트(또는 PDF)에서 이미지·도식 생성
- **Image-to-Image** — 스케치·사진을 일러스트/실사로 변환
- **Reference** — 레퍼런스의 스타일·구도·정체성(consent-gated)을 따라 생성

**Edit — 처음부터 다시 그리지 않고 다듬기**
- **Text Edit** — 이미지 위 라벨/지시 기반 편집(Qwen-Image-Edit)
- **Region Redraw** — 마스크로 선택한 영역만 다시 그리기(inpaint)
- **BG Remove / White BG** — 배경 제거·흰 배경 정리

**Vectorize — 완전 편집 가능한 포맷으로 내보내기**
- **편집 가능한 PPTX**, **SVG**, 그리고 **내장 캔버스**(Konva 래스터 + 마스크)
- 클라우드 이미지 모델은 **FigGen 파이프라인**을 통해 구조화된 FigureSpec → 편집 가능한 SVG/PPTX로 산출됩니다.

---

## 모델 — UI에서 직접 선택

이미지 모델과 채팅/플래너 LLM을 **컴포저의 인라인 pill picker**(홈 프롬프트 박스 + 에디터 채팅)에서 고릅니다.
Local / Cloud로 그룹화되어 표시되며, **목록은 백엔드 `/models`에서 동적으로** 받아옵니다(프론트 하드코딩 없음).

> **`.env`에는 모델 설정이 없습니다.** `.env`는 **API 키 + 서비스 URL + 폴백 기본값**만 담습니다. 모델 선택은
> 전적으로 UI에서 이뤄지고, `.env`의 모델 id는 아무것도 선택되지 않았을 때 쓰는 폴백입니다.

선택한 모델이 파이프라인 전체를 결정합니다 — 이미지 생성은 물론, **채팅/플래너 LLM도 당신의 선택을 따릅니다**(로컬
LLM은 **Ollama**, 클라우드 LLM은 **OpenRouter**에서 스트리밍). 클라우드 이미지 모델은 **FigGen 파이프라인**(구조화된
FigureSpec → 편집 가능한 SVG/PPTX)으로, 로컬 이미지 모델은 **ComfyUI**로 라우팅됩니다. API 키가 없으면 클라우드
옵션이 picker에서 비활성화되고, 앱은 로컬/mock으로 폴백해 완전히 오프라인으로 동작합니다.

### 로컬 모델 (ComfyUI / Ollama · H100)

| 용도 | id | 모델 |
|---|---|---|
| txt2img·img2img (품질) | `chroma-hd` | Chroma 1-HD (uncensored photoreal) |
| txt2img·img2img·controlnet (빠른 실사) | `lustify` | LUSTIFY! SDXL v4 |
| inpaint (지시 충실) | `flux-fill` | FLUX.1 Fill |
| inpaint (빠름) | `sdxl-inpaint` | LUSTIFY SDXL Inpainting |
| edit (지시 편집) | `qwen-edit-aio` | Qwen-Image-Edit Rapid AIO |
| edit·reference (멀티 레퍼런스) | `kontext` | FLUX.1 Kontext |
| reference (스타일) | `redux` | FLUX Redux |
| reference (얼굴 정체성, consent-gated) | `instantid` · `ip-adapter` · `pulid-flux` | InstantID · IP-Adapter FaceID · PuLID-FLUX |
| **video** (text+image→video, 경량·기본) | `wan22-ti2v` | Wan 2.2 TI2V-5B |
| **video** (text→video, MoE 품질) | `wan22-t2v` | Wan 2.2 T2V-A14B |
| **video** (image→video, MoE 품질) | `wan22-i2v` | Wan 2.2 I2V-A14B |
| 채팅/플래너 LLM | `qwen-9b-local` · `qwen-4b-local` | Qwen3.5 Uncensored (9B / 4B) |

부가: ControlNet은 xinsir ControlNet-Union ProMax 단일 파일이 canny/depth/scribble/lineart/**pose**를 모두 커버하며,
pose 전처리는 DWPose입니다. 업스케일은 RealESRGAN + Ultimate SD Upscale입니다.

### 클라우드 모델 (OpenRouter)

- **이미지**: GPT Image 2 · Nano Banana 2 · SeeDream 4.5 · FLUX.2 Max/Pro/Flex
- **LLM**: GPT-OSS 20B/120B (free) · Qwen3.7 Plus · Qwen3.6 Flash · Qwen3.6 35B-A3B

---

## 아키텍처

```
frontend/        Next.js 15 + React 19 + Tailwind + Zustand + react-konva
backend/app/     FastAPI 호스트: routers (chat·jobs·projects·assets·uploads·models)
  engines/       엔진 디스패치: local-comfy · cloud(figure pipeline) · ollama
  models_catalog/ 통합 레지스트리 (image + llm, local + cloud) — 단일 진실 공급원
  comfy/ llm/ orchestrator/ services/ db/   (로컬 엔진 + 작업 큐 + 저장)
figure_engine/   벤더링된 FigGen 패키지(`figgen`): pipeline · schema · layout · render · vectorize
AIStudio/        로컬 런타임 홈(가중치·ComfyUI·sqlite·outputs) — git-ignored
                 └ 심볼릭 링크 → /data/<user>/Figment/AIStudio  (AGENTS.md 스토리지 규약)
```

**작업(Job) 경로 vs 채팅 경로는 분리되어 있습니다.**
- **생성 작업**은 오케스트레이터 큐(`orchestrator/queue.py`)의 단일 워커가 처리합니다. 모델을 resolve한 뒤
  클라우드면 **FigGen 파이프라인**(OpenRouter, FigureSpec → SVG/PPTX), 로컬이면 **ComfyUI**(`comfy/builder.py`가
  그래프를 프로그래밍적으로 구성 → `/prompt` + `/ws` 실행, 영상은 animated webp로 저장)로 라우팅됩니다.
- **채팅**은 큐와 별개(`routers/chat.py`)로, UI에서 고른 LLM에 따라 **Ollama**(로컬) 또는 **OpenRouter**(클라우드)에서
  스트리밍됩니다. 대화에서 `GenSpec`을 추출(`llm/handoff.py`)해 생성으로 핸드오프합니다.

자세한 내용은 `docs/ARCHITECTURE.md`, `docs/MODELS.md`, `docs/WORKFLOWS.md`를 참고하세요.

---

## 빠른 시작

```bash
cp .env.example .env          # 클라우드용 OPENROUTER_API_KEY 추가, 또는 로컬 서비스 실행
```

### A. 클라우드만 사용 (서버 1개)

`OPENROUTER_API_KEY`만 있으면 ComfyUI/Ollama 없이 동작합니다. 앱(백엔드+프론트)만 띄우면 됩니다.

```bash
bash scripts/40_dev.sh        # FastAPI 백엔드 :8000 + Next.js 프론트 :3000 (한 번에)
# → http://localhost:3000
```

또는 수동으로:
```bash
cd backend  && uv sync && uv run uvicorn app.main:app --reload --port 8000
cd frontend && pnpm install && pnpm dev      # http://localhost:3000
```

### B. 로컬 풀스택 사용 — **서버 3개 필요**

로컬 모델(ComfyUI/Ollama)로 끝까지 돌리려면 **서버 3개**를 띄웁니다. `40_dev.sh`는 백엔드+프론트만 띄우고
**ComfyUI·Ollama는 이미 떠 있다고 가정**하므로, 아래 3개 런처를 각각 실행하세요(보통 별도 터미널/창에서).

| # | 서버 | 포트 | 런처 | 역할 |
|---|---|---|---|---|
| 1 | **ComfyUI** | `:8188` | `bash scripts/30_run_comfyui.sh` | 이미지·영상 디퓨전 엔진 (GPU 0, `--highvram`) |
| 2 | **Ollama** | `:11434` | `bash scripts/31_run_ollama.sh` | 채팅/플래너 LLM (idempotent — 이미 떠 있으면 그대로 둠) |
| 3 | **Figment 앱** | `:8000` + `:3000` | `bash scripts/40_dev.sh` | FastAPI 백엔드(:8000) + Next.js 프론트(:3000) |

> #3 `40_dev.sh`는 한 번에 백엔드와 프론트 **두 프로세스**를 띄웁니다(엄밀히는 총 4개 프로세스지만, 직접
> 실행하는 런처는 3개입니다). 브라우저는 `http://localhost:3000`로 접속합니다.

### 로컬 엔진 최초 설치 (순서대로)

```bash
bash scripts/00_bootstrap_dirs.sh      # 런타임 홈 생성 + /data 심볼릭 링크(AGENTS.md 규약)
bash scripts/10_install_comfyui.sh     # ComfyUI 클론 + CUDA torch(cu124) 설치 (H100)
bash scripts/12_install_custom_nodes.sh # 커스텀 노드(IPAdapter/InstantID/PuLID/controlnet_aux/USDU/GGUF/RMBG) + insightface
bash scripts/20_download_models.sh all # 가중치 다운로드 (stage: base|sdxl|edit|ref|identity|video|all)
bash scripts/21_pull_ollama_models.sh  # Ollama 채팅 LLM pull
```

다운로드 스테이지는 개별 실행도 가능합니다: `bash scripts/20_download_models.sh base`(또는 `sdxl`/`edit`/`ref`/
`identity`/`video`). `video` 스테이지(Wan 2.2)는 ~88GB로 가장 큽니다.

---

## 환경 변수 (`.env`)

`.env`는 **키 + 서비스 URL + 폴백 기본값**만 담습니다(모델 선택은 UI). 주요 키:

| 키 | 기본값 | 설명 |
|---|---|---|
| `OPENROUTER_API_KEY` | — | 클라우드 엔진 키. 없으면 안전한 `mock` 폴백(오프라인 동작) |
| `FIGGEN_PROVIDER` | `openrouter` | `openrouter \| auto \| mock` |
| `COMFY_URL` | `http://127.0.0.1:8188` | 로컬 ComfyUI 주소 (주의: `COMFYUI_URL` 아님) |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | 로컬 Ollama 주소 |
| `BACKEND_PORT` | `8000` | FastAPI 백엔드 포트 |
| `HF_TOKEN` | — | HuggingFace read 토큰(다운로드용) |
| `AISTUDIO_HOME` | `<repo>/AIStudio` | 로컬 런타임 홈. 보통 `/data/<user>/Figment/AIStudio` 심볼릭 링크 |
| `OLLAMA_MODELS` | `$AISTUDIO_HOME/ollama` | Ollama 가중치 저장 경로(/data 위) |
| `OLLAMA_LLM` / `OLLAMA_LLM_FALLBACK` | Qwen3.5 9B / 4B | 폴백 로컬 LLM 태그(UI 선택이 우선) |
| `VRAM_BUDGET_GB` / `LLM_RESIDENT_GB` | `78` / `6.5` | H100 80GB 메모리 예산(`config.py` 기본값과 일치) |

클라우드 figure 파이프라인의 폴백 모델 id(`FIGGEN_PLANNER_MODEL`, `FIGGEN_CLASSIFIER_MODEL`,
`FIGGEN_VISION_MODEL`, `FIGGEN_CHART_CODER_MODEL`, `FIGGEN_DEFAULT_IMAGER` 등)도 `.env`에 있으며, UI에서 클라우드
LLM을 고르면 작업별로 덮어씁니다. 전체 목록은 `.env.example`를 참고하세요.

---

## 검증 / 테스트

```bash
cd backend  && uv run pytest            # 헤르메틱(mock 프로바이더 — 키/GPU 불필요)
cd backend  && uv run pytest tests/test_builder.py::test_video_wan_a14b_moe   # 단일 테스트
cd backend  && uv run ruff check .      # 린트
cd frontend && pnpm typecheck && pnpm build
```

> `test_figure_engine.py`의 라이브 호출 테스트 1건은 실제 OpenRouter/OpenAI 키가 있는 환경에서만 통과합니다(환경
> 의존이며 회귀가 아님). 나머지는 모두 키 없이 통과합니다.

---

## 스토리지 규약 (`~/AGENTS.md`)

루트 볼륨(`/`)은 용량이 작아, 대용량 산출물이 쌓이면 서버 전체가 멈출 수 있습니다. 따라서 가중치·출력·로그 등
**대용량 런타임은 `/data` 볼륨**에 두고, 프로젝트 안에서는 심볼릭 링크로 연결합니다.

- `<repo>/AIStudio` → **심볼릭 링크** → `/data/<user>/Figment/AIStudio` (단일 런타임 홈: models·comfyui·outputs·db.sqlite·logs)
- `scripts/00_bootstrap_dirs.sh`가 링크를 생성하며, `.gitignore`로 무시됩니다(절대 커밋되지 않음)
- 대안: 링크 대신 `.env`의 `AISTUDIO_HOME`을 직접 `/data` 경로로 지정

로컬 ComfyUI는 GPU 0에 고정(`CUDA_VISIBLE_DEVICES=0`, `--highvram`)되어 멀티 모델 스택이 한 H100에 동시 상주합니다.

---

## 콘텐츠 범위

합법적인 **성인 합의** NSFW 생성만 전제로 합니다. 얼굴 정체성 도구(InstantID / IP-Adapter FaceID / PuLID-FLUX)는
**동의한 성인 / 합성 얼굴 한정**으로 게이트됩니다. 미성년 콘텐츠(CSAM)나 실존 인물에 대한 비합의 딥페이크는 범위
밖이며 지원하지 않습니다.
