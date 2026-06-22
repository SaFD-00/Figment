# FigGen 아키텍처 (M7: figurelabs 디자인 클론 + OpenRouter)

> figurelabs 프레임워크([[figurelabs-research]]) 기반. **M7**에서 UI를 **figurelabs.ai와 최대한 동일하게**
> 재테마(light-blue SaaS + Inter, 2모드 토글·54 템플릿 갤러리·셀렉터, [[design-reference]])하고,
> 모델을 **GPT(OpenAI) → OpenRouter**로 교체(LLM은 멀티모달(VL) `google/gemini-2.5-flash`, 이미지 default
> `google/gemini-3.1-flash-image`(폴백 `openai/gpt-5.4-image-2`) = 품질 1순위 동인). + Tier0 버그 5개(§7)
> 수정 + 소형 UX(프롬프트 강화·색 팔레트·Flat 프리셋·종횡비)
> + 고해상도/JPG export. mock은 오프라인 폴백 유지.

## 0. 대화형 단일 생성 플로우 (M6 — 최상위 진입)
- 생성 방법은 **하나**: 좌측 Claude풍 대화로 계획 확정 → `✨ 이 계획으로 생성`.
- `POST /api/projects/{pid}/plan`(`routes/plan.py`, 동기·stateless) → `Planner.converse`(프롬프트
  `prompts/plan_chat.md`) → `PlanTurn{reply, ready, plan: PlanBrief|None}`. 정보 부족 시 1~2개 질문.
- `PlanBrief{task, figure_type, description, summary, style_preset, refine_modes, reference_role}` →
  프론트가 그대로 기존 `POST /jobs`로 전송. **orchestrator 무변경**(명시 figure_type이 classify 단락).
- 이미지 첨부 시 대화가 용도(스타일참조/스케치/정제/벡터화)를 물어 task 라우팅. 데이터파일(CSV/JSON)·
  참조 스타일 이미지는 첨부로 유지. 생성 후 같은 대화가 편집 지시도 겸함(요소선택=요소편집).
- **스타일 참조 반영(M6.1)**: generate 경로에 참조 이미지가 첨부되면(=reference_role="style")
  orchestrator `_describe_reference`가 `planner.describe_reference`(비전)로 RefStyleReport(palette/density/
  layout/font)를 뽑아 → scene 경로는 `build_scene_prompt(palette=…)`로 이미지 프롬프트에, structured 경로는
  `_with_style`로 planner.plan 입력에 스타일 가이드를 주입. 베스트-에포트(실패해도 job 진행), 첨부 있을 때만 1콜.
- 프론트 `chatPanel.js`(2-pane 좌). 네비 **Home/History/Projects**(SVG Converter/Editor 제거 — 대화로 흡수).

## 1. Provider (OpenRouter 기본 + OpenAI 폴백 + mock)
- `providers/registry.py` 단일 라우팅 병목. 역할 모델 속성: planner/editor=`planner_model`,
  classifier=`classifier_model`, **critic=`vision_model`**(비전 필요), chart_coder=`chart_coder_model`,
  research=`research_model`. LLM 역할 기본값 전부 멀티모달(VL) `google/gemini-2.5-flash`(env 오버라이드).
- `_resolve_provider`: `auto`→openrouter(키 보유)→openai→mock. 명시 provider도 키 없으면 mock 폴백.
- **OpenRouter**(`providers/openrouter_client.py`): OpenAI 호환(`base_url=…/api/v1`)이라 LLM은
  `OpenRouterClient(OpenAIClient)`로 SDK 재사용(`OpenAIClient`에 `base_url/extra_headers/omit_temp` 추가).
  `web_research`는 `:online` 변종(Responses API 미지원 대체). 이미지는 OpenAI Images API가 아니라
  **`POST /chat/completions` + `modalities:["image"]`**(httpx) → `choices[0].message.images[0].image_url.url`
  (data URL) → PNG 정규화. 종횡비/해상도는 `image_config.aspect_ratio`("16:9"/"1:1"/"9:16")·`image_size`
  ("1K"/"2K"/"4K"). 이 이미지 생성 경로는 **투명·mask 인페인트 미지원** → has_alpha=False, Region Redraw degrade.
- 이미지: `get_image_client` → `OpenRouterImageClient`(gemini-3.1-flash-image) / `OpenAIImageClient`(gpt-5.4-image-2, 폴백) / mock.
- `config.py`: `OPENROUTER_API_KEY`·`FIGGEN_OPENROUTER_BASE_URL`·모델 ID 전부 `FIGGEN_*` env 오버라이드.
  `image_model`(구 `image_model_openai`, alias 호환). **비전 필요 경로(critic/sketch/참조분석)는
  `vision_model`을 비전 가능 OpenRouter 모델로 둔다**(LLM 역할 기본값이 모두 멀티모달이라 critic 항상 가능).

## 2. 파이프라인 (orchestrator.run, task 분기)
```
PLANNING ─ task별 분기
  vectorize → _vectorize_spec (업로드 PNG → vtracer SVG 풀블리드)
  refine    → _refine_spec    (업로드 PNG → image_ops.refine_asset)
  sketch    → research → sketch_to_spec (gpt-image edit 정제 + plan_scene 라벨 + 벡터화)
  edit(parent) → _edit_spec  (부모 에셋 복사 → canvas_op 또는 PartialEditor)
  generate  → classify → research → route(image_first|structured)
                image_first → scene.generate_scene_spec (sci_illust·graphical_abstract)
                structured  → planner.plan (method_diagram·chart·concept)
STYLING → ASSETS → RENDERING → CRITIC(generate·sketch만) → FINALIZING
```
- **research(웹검색 그라운딩)**: classify 후·plan 전 1회. `req.research and provider!="mock"`일 때
  `get_llm("research").web_research()`(OpenAI Responses `web_search`) → `research_ctx`를
  planner.plan/plan_scene 프롬프트에 "Researched scientific context"로 append. 실패 시 빈 문자열로
  진행(절대 job 실패 안 함). 이것은 PLANNING의 **하위 스텝**(Stage enum 불변).

## 3. 하이브리드 라우팅 (`pipeline/routing.py`)
- `IMAGE_FIRST_TYPES = {scientific_illustration, graphical_abstract}`.
- `route(figure_type)` → image-first(베이스 래스터 1장 + 편집 라벨 + 벡터화) vs structured
  (FigureSpec 박스/플롯). `classify.md`가 "그림 vs 라벨된 구조" 프레임으로 결정. `--type`/요청
  `figure_type` 오버라이드 우선.

## 4. 신규 surface & 인-캔버스 (task 디스크리미네이터)
- `JobRequest.task ∈ {generate, edit, sketch, refine, vectorize}`, `canvas_op`, `refine_modes`.
- `CanvasOp{kind∈region_redraw|text_edit|white_bg|upscale, target_element_id, instruction, text, region}`.
  - text_edit는 결정론(LLM 없음). 나머지는 `pipeline/image_ops.py`(OpenAI `images.edit`).
- 에셋 비파괴 버전 체인: `AssetStore.put(parent_id=...)`. 자식 job 렌더는 부모 에셋을 자식
  에셋 스토어로 복사(`_seed_assets`) 후 진행(임베드 SVG가 해석되도록).

## 5. 서버/프론트
- 통합 엔드포인트 `POST /api/projects/{pid}/jobs`(JobRequest)로 4 surface + 편집 전부 처리. SSE 진행 스트림.
  JobRequest/GenerationRequest에 **`palette`(수동 색)·`aspect`(종횡비)** 추가.
- `/plan`: `PlanChatRequest.paper_text`(논문 method ContentPlan 분해) + `research` 시 `research_context()`로
  웹검색 그라운딩을 `converse`에 전달(§7-A/C). **`POST /enhance-prompt`**: AI 프롬프트 강화(§7 UX).
- `/jobs/{jid}/files/{name}`: `?res=1k|4k|8k&format=png|jpg` — 저장 `figure.svg`에서 지연 고해상도 렌더
  (`svg_to_png(dpi)` canvas-aware + `png_to_jpg`). CLI `render`/`gen`에 `--dpi`/`--format`.
- 프론트엔드(figurelabs IA, [[design-reference]]): **랜딩(갤러리) ↔ 워크스페이스(2-pane)** 전환,
  2모드 토글, 9분야×6 템플릿 갤러리(`data/templates.json` + `gen_template_thumbs.py` 실제 썸네일),
  컴포저 셀렉터(스타일/종횡비/강화/팔레트/provider/모델칩), Export 드롭다운(고해상도/JPG), 헤더 크레딧·rail
  (코스메틱).

## 6. 의존성(API-by-SDK)
`openai>=1.30` — LLM은 OpenAI 호환 chat-completions(OpenRouter는 `base_url` 오버라이드로 재사용).
이미지는 `httpx`로 OpenRouter chat-completions(modalities). `google-genai` 미사용. vtracer(벡터화),
cairosvg(PNG), Pillow(JPG/정규화), python-pptx.

## 7. M7 Tier0 버그 수정 + 소형 UX
- **A** `converse(paper_text=…)` + `_paper_digest`(ContentPlan 분해); `/plan`이 전달.
- **B** `plan_scene(figure_type=…)` → graphical_abstract면 `prompts/graphical_abstract_scene.md`(SceneBrief형)
  로드; `scene.generate_scene_spec`이 figure_type 전달.
- **C** `/plan`이 `research` 시 `research_context()`(orchestrator 자유함수)로 그라운딩 → `converse`.
- **D** sketch 잡에 2번째 첨부 이미지가 있으면 `_describe_style_ref_2nd`로 style_ref 산출 →
  `sketch_to_spec(style_ref=…)` → `plan_scene`/`build_scene_prompt(palette=…)`.
- **E** STYLING에서 `_apply_style`: 우선순위 **수동 팔레트 > 참조 스타일(`Stylist.from_report`: palette/
  font_feel/density 실반영) > 프리셋**.
- **UX**: `Planner.enhance_prompt`(`prompts/enhance.md`), 수동 팔레트(JobRequest.palette→custom StyleSheet),
  Flat 프리셋(`styles/presets.py _flat` + `assets/prompts.py "flat"`), 종횡비 오버라이드(scene `_ASPECT`).

## 검증
mock-우선: `pytest`(114 green; +OpenRouter 클라이언트·버그A~E·enhance·palette·flat·aspect·hi-res 테스트) +
`figgen gen --provider mock` 전 타입 + `figgen serve` UI. 라이브: OpenRouter 키로 `gen --provider openrouter`,
`scripts/gen_template_thumbs.py --provider openrouter`(실제 gemini-3.1-flash-image 썸네일).
