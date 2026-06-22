# FigureLabs (figurelabs.ai) — 제품/UX 조사 및 FigGen 매핑

> 이 프로젝트는 **figurelabs.ai의 프레임워크·기능·UI를 클론**하는 것을 목표로 한다. **M7**에서 디자인을
> figurelabs.ai와 최대한 동일하게(light-blue SaaS + 2모드/54템플릿, [[design-reference]]) 맞추고,
> 모델을 **OpenRouter**(LLM은 멀티모달(VL) `google/gemini-2.5-flash`, 이미지 `google/gemini-3.1-flash-image`)로 교체했다.
> 멀티모델 스위처는 미채택(단일 provider 교체). 엔진은 FigGen의 구조적 FigureSpec→편집가능 PPTX/SVG +
> **하이브리드 자동 라우팅**을 유지한다([[architecture]]).

## 1. 제품 정체성
- 슬로건: **"The World's First AI Agent for Scientific Illustration"** — 연구자가 디자인이 아닌
  발견에 집중하도록 출판 품질 과학 figure를 자동 생성.
- 핵심 차별점(원문): *"Most AI tools give you a flat image. We give you Vectors. ... fully
  editable, layered scientific figures."* → **편집 가능한 벡터 출력**이 본질.
- 워크스페이스는 챗/에이전트형(`chat.figurelabs.ai`, Next.js). 대상: 생명·의학 중심 연구자.

## 2. 4대 기능 (→ FigGen surface 매핑)
| FigureLabs | 설명 | FigGen 구현 |
|---|---|---|
| **Text-to-Figure** | 텍스트·논문·PDF→figure | `task="generate"` (분류→이미지-우선/구조 라우팅) |
| **Sketch-to-Figure** | 손그림/화이트보드→정제 다이어그램 | `task="sketch"` (`pipeline/sketch.py`: gpt-image edit로 정제 + plan_scene 라벨 + 벡터화) |
| **Figure Refiner** | 업스케일/색보정/노이즈제거 | `task="refine"` (`pipeline/image_ops.refine_asset`) |
| **Image Vectorization** | PNG/JPG→SVG/EPS | `task="vectorize"` (`fullimage/vectorize.py` vtracer) + SVG Editor 뷰 |

## 3. 인-캔버스 편집 도구 (→ canvas_op)
FigureLabs는 생성 후 캔버스에서 부분 편집을 제공한다. FigGen은 `JobRequest.canvas_op`
(`task="edit"`, `parent_job_id` 필요)로 매핑:
- **Region Redraw** → `image_ops.region_redraw` (마스크 인페인트, OpenAI `images.edit`)
- **Text Edit** → 결정론적 `SpecPatch set`(label/text), LLM 없음 (캔버스 라벨 더블클릭)
- **White BG** → `image_ops.white_background`
- **Upscale** → `image_ops.refine_asset(["upscale"])`
모든 편집은 부모 spec+에셋을 자식 job으로 복사 후 적용 → `AssetStore.put(parent_id=...)` 버전 체인
(비파괴·undo). 자세한 데이터 흐름은 [[architecture]].

## 4. 앱 IA (네비) — 그대로 채택
Home / History / Projects / **SVG Converter** / **SVG Editor** + 입력 모드 탭
**By Text / By Sketch / By Image**. FigGen 프론트엔드(`frontend/`)가 동일 IA로 재구성됨([[design-reference]]).

## 5. 출력/익스포트
PNG·SVG·**PPTX**(편집 가능) — FigGen은 이미 PPTX+SVG(임베드)+preview를 산출. 벡터 편집은
SVG/PNG에서, PPTX는 래스터 그림으로 임포트되는 한계(vtracer path 미지원)는 동일.

## 6. 멀티모델 → OpenRouter 단일 provider 교체 (M7)
FigureLabs는 Nano Banana/GPT Image/Sora/SeeDream/Flux 스위칭을 제공하지만, 본 프로젝트는 스위처 없이
**OpenRouter 단일 provider**로 교체했다: LLM은 멀티모달(VL) 전용 `google/gemini-2.5-flash`(planner/classifier/
critic-vision/chart/research), 이미지 default **`google/gemini-3.1-flash-image`**(폴백 `openai/gpt-5.4-image-2`).
OpenRouter는 OpenAI 호환이라 LLM은 `base_url` 오버라이드로 기존 SDK 재사용, 이미지는
chat-completions+`modalities:["image"]`(httpx). 웹검색 그라운딩은 OpenRouter `:online` 변종으로 구현.
주의: 이 이미지 생성 경로는 **투명·mask 인페인트 미지원**.

## 출처(요약)
PRNewswire 런칭 기사, SciDraw/FigPad 비교글, 공식 소셜(@FigureLabs_AI) 카피, 가격/크레딧 페이지
인덱싱 스니펫. 직접 페이지는 Next.js SPA라 본문 추출이 제한적 — 검색·소셜 카피로 보강.
