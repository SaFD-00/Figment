# FigGen 설계 계약 (구현 단일 진실 소스)

> 원본 상세 설계(533줄)의 핵심 발췌. 모듈 필드·시그니처의 기준.

## 고정 계약 (변경 시 관련 모듈 동시 수정)

1. **단위**: 내부 좌표 전부 **mm float**, 폰트만 pt. 변환은 `figgen/units.py` 단일 모듈
   (`mm_to_emu`=×36000, `mm_to_px(dpi)`, `pt_to_mm`, `mm_to_pt`, `mm_to_inch`, `pt_to_emu`=×12700).
   렌더러·엔진 내 인라인 곱셈 금지.
2. **요소 ID 3중 키**: spec `element.id` ↔ SVG `<g id="fg-{id}" data-fg-id="{id}" data-fg-kind="{kind}">`
   ↔ PPTX `shape.name="fg-{id}"`. 재생성 시 미변경 요소는 동일 id 유지.
3. **렌더러 입력 = `ResolvedFigure`** (mm, 사전 줄바꿈 `lines[]` 확정, asset_id 바인딩).
   PPTX/SVG 렌더러는 좌표·스타일·줄바꿈 계산 없는 **결정론적 그리기 전용**.
   `Resolver`가 `spec + ResolvedLayout + StyleSheet`를 병합해 생성한다.
4. **`PipelineRunner.run(job, progress_cb)`** Protocol + Stage enum
   `PLANNING → STYLING → ASSETS → RENDERING → CRITIC → FINALIZING`.
   Orchestrator가 구현, 웹앱은 Protocol만 의존.
5. **수정 = `parent_job_id`를 가진 새 job**. 부분 재생성은
   `EditDirective.target_element_ids: list[str]` 스코프 제한 패치.
   `figure_type` 리터럴은 `method_diagram|concept|chart|graphical_abstract|scientific_illustration`로 전 계층 통일.

## FigureSpec 스키마 (`schema/figure_spec.py`)

- 공통: `MM = float`; `ElementId = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,40}$')]`;
  `HexColor = ^#[0-9A-Fa-f]{6}$`; 전 모델 `extra='forbid'`.
- `SizeHint{width_mm,height_mm,min_width_mm,min_height_mm: MM|None, aspect: float|None}`
- `ElementBase{id, z:int=0, style: StyleOverride|None=None, size_hint: SizeHint|None=None, weight:float=1.0}`
- **리프 4종**:
  - `BoxElement{type='box', label/sublabel: str|None, shape∈{rect,rounded,ellipse,diamond,cylinder,parallelogram,hexagon}='rounded', role∈{input,output,process,model,data,decision,loss,note}|None, icon_asset: str|None}`
  - `TextElement{type='text', text, text_role∈{title,heading,body,caption,annotation}='body', h_align, max_width_mm: MM|None}`
  - `ImageElement{type='image', alt, gen_prompt: str|None, asset_id: str|None(래스터 PNG), svg_asset_id: str|None(벡터화 변형 — SVG 인라인), needs_transparency:bool=True, provider_hint∈{openai}|None}`
  - `ChartElement{type='chart', chart_kind∈{line,bar,grouped_bar,scatter,heatmap,box,violin,custom}, brief, data_ref: str|None, code_asset_id/svg_asset_id: str|None}`
- **컨테이너**: `ContainerBase{gap_mm:MM=4.0, padding_mm:MM=0.0, align∈{start,center,end,stretch}='center', justify∈{start,center,end,space_between}='center'}`
  - `Row/Column{children: list[Node]}`, `Grid{columns:int 1..8, children}`,
    `Group{label:str|None, direction∈{row,column}='column', role∈{module,stage,legend,panel}|None, children}`,
    `Free{items: list[FreeItem]}` — `FreeItem{node: Node, x_frac/y_frac: 0..1, w_frac/h_frac: float|None, anchor∈{top_left,center}='center'}`
- `Node = Annotated[Union[Row,Column,Grid,Group,Free,BoxElement,TextElement,ImageElement,ChartElement], Field(discriminator='type')]`
- `Connector{id, source/target: ElementId, source_side/target_side∈{auto,left,right,top,bottom}='auto', label:str|None, arrow∈{end,start,both,none}='end', routing∈{straight,elbow,curve}='elbow', line_role∈{flow,feedback,reference}='flow', style: Stroke|None}` — 트리 밖 flat 리스트
- `Canvas{width_mm:MM=180.0, height_mm:MM|None=None(자동 산출), background:HexColor='#FFFFFF'}`
- `FigureSpec{spec_version='1', figure_type, title:str|None, canvas:Canvas, stylesheet:StyleSheet|None=None(Planner는 항상 None, Stylist가 주입), root:Node, connectors:list[Connector]=[]}`
- validator(mode='after'): ① id 전역 유일성 ② connector source/target 존재 ③ 중첩 깊이 ≤6.
  헬퍼: `iter_elements()`(경로 포함 순회), `find(id) -> Node|None`.

## 스타일 (`schema/style.py`)
- `Stroke{color='#333333', width_pt=1.0, dash∈{solid,dash,dot}='solid'}`
- `Font{family='Arial', size_pt=8.0, weight∈{regular,medium,bold}='regular', italic=False, color='#222222'}`
- `StyleOverride{fill,fill_opacity,stroke,font,corner_radius_mm: 전부 Optional}`
- `StyleSheet{name, palette:list[HexColor], role_styles:dict[str,StyleOverride](키 'box.process' 형식), font_family, base_font_pt, title_font_pt, stroke_width_pt, corner_radius_mm, connector:Stroke, arrowhead_scale=1.0, background, chart_rc:dict}` + `chart_rcparams()` 메서드(`svg.fonttype='none'` 포함)
- `resolve_style(element, stylesheet) -> ResolvedStyle`: 우선순위 **element.style > role_styles[f'{type}.{role}'] > stylesheet 기본값**.

## 레이아웃 (`layout/`)
- `text_metrics.py`: `FontProvider`(TTF 해석 + 폴백 체인 Arial→Helvetica→Liberation Sans→DejaVu Sans, lru_cache),
  `measure_text(text, font, max_width_mm) -> TextMetrics{width_mm,height_mm,lines[],line_height_mm}`(PIL getbbox 단어 greedy wrap, line_height=1.25×pt, **SAFETY=1.08** 폭 보정), `fit_font_size(text, box, font, min_pt=5.0)`(이진 탐색).
- `engine.py`: 2-pass. bottom-up `_measure(node, avail_w) -> Size`(텍스트 실측, 박스 min 22×10mm, 차트 60×45mm),
  top-down `_arrange(node, rect)`(main축 weight 비례 분배, 폭 초과 시 (pref−min) 비례 축소 후 overflow warning, cross축 align).
  캔버스 폭 고정, height None이면 root preferred(상한 280mm). `layout(spec) -> ResolvedLayout{rects, z_order, connector_paths, canvas_w_mm/h_mm, warnings}`.
- `connectors.py`: `route_connectors(spec, rects) -> dict[id, ConnectorPath{points,label_anchor,arrow_at, src_side,tgt_side}]`.
  auto side=중심벡터 지배축, straight=면중점 직결, elbow=맨해튼 3/5세그, curve=베지어(법선 12mm), 평행 3mm 오프셋.
- `diagnostics.py`: `LayoutWarning{kind∈{overlap,overflow,text_clipping,canvas_exceeded,connector_crossing,tiny_text,empty_content}, element_ids, detail, severity∈{critical,major,minor}}`,
  `detect_overlaps`(비형제 AABB 교차율>5%, **image↔text 오버레이는 제외**), `check_text_fit`,
  `check_connectors`(라우팅에서 생략된 커넥터→`connector_crossing`), `check_content`(콘텐츠 leaf 없음→`empty_content` critical), `nudge_free_items`.
- **견고화(M4.0)**: 빈/내용없는 `Free`는 `_measure_free`에서 0크기로 붕괴(빈 free 남용 방지);
  height None & root>280mm면 자연 높이 배치 후 `_rescale_rects`로 균일 축소(자식 음수좌표/캔버스 밖 방지);
  `route_connectors`는 과대 변(>0.6×캔버스) 부착점을 중앙 밴드(0.3~0.7)로 클램프하고 코드>1.3×대각선 커넥터는 생략.

## 렌더 (`render/`)
- `resolved.py`: `ResolvedFigure{width_mm,height_mm,background,layers:list[Layer]}`.
  `Resolved* = discriminated union`: `ResolvedShape{shape_kind,x,y,w,h(mm),fill,fill_alpha,stroke,stroke_width_pt,dash,corner_radius_mm,label:ResolvedText|None}`,
  `ResolvedConnector{routing,points,head/tail∈{none,triangle,open,diamond}, from_id/to_id, src_side/tgt_side}`,
  `ResolvedText{x,y,w,h,lines:list[str],font:FontSpec,align,valign,color}`,
  `ResolvedImage{asset_id,x,y,w,h}`, `ResolvedChart{chart_id,x,y,w,h}`, `ResolvedGroup{children, group_id, label}`.
  각 요소는 `id`/`kind`를 보존(3중 키).
- `resolver.py`: `resolve(spec, layout, stylesheet) -> ResolvedFigure`. 스타일 병합 + lines[] 확정 + z-order 평탄화 + asset 바인딩.
- `svg_renderer.py`: `SvgRenderer(asset_store, embed_images=True)`; ElementTree 직접; layer별 `<g id="layer-..">`;
  color별 `<marker>`; `<g id="fg-{id}" data-fg-id data-fg-kind>`; `<text>`+`<tspan>` per line; `debug=True`면 id 오버레이.
- `pptx_renderer.py`: python-pptx 1.0.2. SHAPE_MAP/CONNECTOR_MAP; `add_connector`+`begin_connect/end_connect`;
  `shape.name="fg-{id}"`; word_wrap=False, auto_size=NONE; `pptx_xml`로 화살촉/알파/대시/베지어.
- `pptx_xml.py`: lxml 핵 — `set_line_arrowheads(headEnd/tailEnd)`, `set_fill_alpha(a:alpha)`, `set_dash(prstDash)`, `add_bezier_shape(custGeom cubicBezTo)`.
- `preview.py`: `svg_to_png(svg, dpi=192)`(cairosvg, resvg 교체 가능 Protocol). critic·미리보기·썸네일 공용.
- `exporter.py`: `export_figure(...) -> ExportBundle{pptx:bytes, svg:str(임베드), preview_svg:str(href), preview_png:bytes, chart_svgs:dict}`.

## Rich Scene Illustration Mode (M4.1~M4.4 — FigureLabs식)

- **분류(공격적)**: `pipeline/prompts/classify.md`는 상→하 평가로 chart→method_diagram→graphical_abstract를
  먼저 가르고, 그 외 전부 기본값 `scientific_illustration`. `concept`은 분류기 기본에서 제외(명시적 `--type`만).
- **장면 흐름**(`pipeline/scene.py:generate_scene_spec`, cli_gen·orchestrator 공유): `Planner.plan_scene`이
  `SceneBrief{scene_prompt(글자 없는 단일 응집 장면), title, aspect, labels:list[LabelProposal]}` 1콜 생성 →
  `fullimage.generate_base_image`(텍스트 금지 suffix) → `AssetStore.put(kind='illustration')` →
  (선택) `fullimage/vectorize.py:vectorize_png`(vtracer, kind='illustration_svg') →
  `fullimage.build_overlay_spec(figure_type='scientific_illustration', base_svg_asset_id=...)`로 Free 루트 spec.
  결과는 `connectors=[]`라 커넥터 엔진을 우회하고 표준 STYLING→RENDERING→CRITIC 꼬리를 그대로 통과.
- **렌더 분리**(FigureLabs와 동일 모델): 장면 아트는 래스터지만 `svg_asset_id`가 있으면 SVG에 벡터 `<path>`로
  인라인(`svg_renderer._image`가 `_inline_chart_svg` 재사용, `_strip_ns`로 `<ns0:path>`→`<path>`)되어 Illustrator
  편집 가능. PPTX는 벡터 path 임포트 불가 → 래스터 `add_picture`로 둔다(차트와 동일 한계). 라벨/제목은 항상 벡터 텍스트.
- **장면 크리틱**(`critic.py`): figure_type이 scientific_illustration이면 `_DIAGNOSE_SCENE`/`_PATCH_SCENE` 선택 —
  각 라벨이 올바른 영역에 놓였는지 검증하고 FreeItem `x_frac/y_frac/text` `set`만 허용(아트는 불변).
- **프롬프트 빌더**(`assets/prompts.py`): `build_scene_prompt`는 `_COMMON_SUFFIX`("single isolated subject")를
  **생략**(장면용), `build_icon_prompt`는 유지(아이콘용). 둘 다 'no text'로 이미지 내 글자 차단.
- **박스 일러스트(M4.3, opt-in)**: `settings.diagram_box_icons`(기본 False, `--box-icons`/`FIGGEN_DIAGRAM_BOX_ICONS`)
  켜면 `pipeline/diagram_icons.py`가 method_diagram 각 박스 라벨로 투명 아이콘 생성→`BoxElement.icon_asset`.
  렌더러는 박스 상단 `units.BOX_ICON_MM`(12mm) 영역에 아이콘, 라벨은 그 아래. decision/loss/note role 제외, 최대 12개.

## 충돌 해소 (요지)
C1 단위 mm 통일(폰트 pt) · C2 `LayoutEngine.layout`→`Resolver.resolve`→렌더러 3단 · C3 `data-fg-id` 표준 ·
C4 `method_diagram` 리터럴 · C5 job 기반 부분 재생성 · C6 AssetStore(버전체인)+AssetCache(전역 sha256) 2계층 ·
C7 provider/ 한 곳 · C8 StyleSheet 단일(Theme 폐지) · C9 SVG→PNG 단일경로 · C10 단일 Stage enum ·
C11 graphical abstract = root=Free FigureSpec · C12 SVG embed/href 이원화(동일 렌더러 플래그) ·
C13 src 레이아웃+통합 Settings · C14 캔버스=프리셋 귀속, 폰트=Arial, critic 기본 2라운드 ·
C15 컨테이너/과대노드 커넥터는 라우팅에서 중앙 클램프·degenerate 생략 + 오버플로는 클램프 아닌 균일 rescale(레이아웃 붕괴 차단) ·
C16 scientific_illustration = 래스터 장면 아트(`svg_asset_id`로 SVG 벡터 인라인) + 벡터 라벨 오버레이, 커넥터 엔진 우회.

## 모델 ID (M7: OpenRouter 기본 + OpenAI 폴백, 전부 .env 오버라이드)
planner/classifier/critic(VLM)·sketch 비전(`FIGGEN_VISION_MODEL`)/chart_coder/research = 멀티모달(VL)
`google/gemini-2.5-flash`, image default = `google/gemini-3.1-flash-image`(폴백 `openai/gpt-5.4-image-2`).
provider 기본 `openrouter`(`OPENROUTER_API_KEY`, `FIGGEN_OPENROUTER_BASE_URL`), 키 없으면 mock 폴백.
`auto`→openrouter→openai→mock.
SDK: LLM은 `openai`(OpenRouter `base_url` 오버라이드로 호환 — `OpenRouterClient(OpenAIClient)`), 이미지는
`httpx`로 `/chat/completions` + `modalities:["image"]`(응답 data URL → PNG 정규화), 웹검색은 `:online` 변종.
주의: 이 이미지 생성 경로는 **투명·mask 인페인트 미지원**(has_alpha=False, Region Redraw degrade); LLM 역할
기본값이 전부 멀티모달이라 비전 경로(critic/sketch)는 항상 가능.

## 대화형 단일 생성 플로우 (C19, M6)
생성 진입은 **하나** — 좌측 Claude풍 대화로 계획을 확정한 뒤 생성. 백엔드 one-shot 잡 구조는 불변.
- **대화 레이어**(`planner.converse`, 프롬프트 `prompts/plan_chat.md`): `ChatMessage[]` 트랜스크립트를
  1블록으로 평탄화해 `complete_structured(PlanTurn)` 1콜. `PlanTurn{reply, ready, plan: PlanBrief|None}`.
  정보 부족 시 1~2개 짧은 질문(`ready=false`), 충분하면 `ready=true`+`PlanBrief`. **stateless**(프론트가 히스토리 보유).
- **`PlanBrief`** = 그대로 JobRequest로 흐르는 계획: `{task, figure_type, description(보강 프롬프트),
  summary(한국어 카드), style_preset, refine_modes, reference_role∈{style,sketch,refine,none}}`.
  이미지 첨부 시 대화가 용도를 물어 task(generate/sketch/refine/vectorize)를 정함.
- **엔드포인트** `POST /api/projects/{pid}/plan`(`server/routes/plan.py`) — 동기, 잡 아님. 확정 후 프론트가
  PlanBrief로 기존 `POST /jobs` 호출. **orchestrator 변경 없음**(명시 figure_type이 `classify()`를 단락).
- 프론트(`frontend/js/components/chatPanel.js`): 2-pane 좌측 대화. 생성 후 같은 대화가 편집 지시도 겸함
  (요소 선택+메시지=요소편집, 미선택=전체편집; 래스터 op는 캔버스 툴바). 네비 Home/History/Projects.

## task 디스크리미네이터 & 인-캔버스 편집 (C17)
`JobRequest.task∈{generate,edit,sketch,refine,vectorize}` + `canvas_op`/`refine_modes`. orchestrator가 task로
분기(sketch=`pipeline/sketch.py`, refine/vectorize=래스터→`build_overlay_spec` 풀블리드, edit=부모 spec+에셋 복사).
`CanvasOp{kind∈region_redraw|text_edit|white_bg|upscale,...}` — text_edit는 결정론 `SpecPatch set`, 나머지는
`pipeline/image_ops.py`(OpenAI `images.edit` 마스크/배경/업스케일). 에셋은 `AssetStore.put(parent_id=...)` 버전체인.

## research 그라운딩 (PLANNING 하위 스텝, Stage enum 불변)
`req.research and provider!=mock`일 때 classify 후·plan 전 1회 `web_research()`(Responses `web_search`) →
`research_ctx`를 planner.plan/plan_scene 프롬프트에 append. 실패 시 빈 문자열로 진행(job 실패 안 함).

## 하이브리드 라우팅 (C18, `pipeline/routing.py`)
`IMAGE_FIRST_TYPES={scientific_illustration,graphical_abstract}` → `route()`가 image-first(베이스 래스터+편집 라벨+
벡터화) vs structured(FigureSpec) 결정. `classify.md`는 "그림 vs 라벨된 구조" 프레임. `--type` 오버라이드 우선.
scientific_illustration 장면 이미지는 `get_image_client(transparent=False)` → gpt-image-1.5(landscape 1536×1024). 벡터화는 `vtracer`(MIT, 결정론적; `fullimage/vectorize.py`).
