# design-sync notes — Figment

Figment의 `frontend/`는 퍼블리시된 컴포넌트 라이브러리가 아니라 **Next.js 15 앱**이다. 그래서 표준 컨버터 경로(빌드된 `dist/` 진입점)가 없고, 아래 셋업으로 동기화한다.

## 셋업 개요 (재현 절차)

1. **의존성**: `COREPACK_ENABLE_STRICT=0 npm_config_manage_package_manager_versions=false pnpm -C frontend install --frozen-lockfile`
2. **Tailwind cssEntry 컴파일** (컴포넌트가 Tailwind className만 쓰고 정적 CSS가 없으므로 필요. **프리뷰를 추가/수정하면 재실행**):
   ```sh
   cd frontend && node_modules/.bin/tailwindcss \
     -c .ds-tailwind.config.ts -i .ds-tailwind-input.css -o .ds-bundle-styles.css
   ```
   - `frontend/.ds-tailwind.config.ts`: 앱 토큰(`tailwind.config.ts`의 theme.extend)을 그대로 쓰되 `content`에 `./.design-sync-entry.tsx` + `../.design-sync/previews/**`를 포함해 프리뷰의 레이아웃 유틸까지 컴파일.
   - `frontend/.ds-bundle-styles.css`는 생성물(gitignore). `cfg.cssEntry`가 가리킨다.
3. **컨버터 빌드** (repo 루트에서):
   ```sh
   node .ds-sync/package-build.mjs --config .design-sync/config.json \
     --node-modules frontend/node_modules --entry ./frontend/.design-sync-entry.tsx --out ./ds-bundle
   node .ds-sync/package-validate.mjs ./ds-bundle
   ```
   - `--entry`는 반드시 `frontend/` 안의 하니스를 가리켜야 한다(컨버터가 거기서 위로 걸어가 `frontend/package.json`을 PKG_DIR로 잡음). repo 루트엔 package.json이 없어 repo-루트 경로를 주면 PKG_DIR이 틀어진다.

## tokens / fonts / guidelines (claude.ai/design 출하물)

- **tokens/** ← `cfg.tokensPkg: "../.ds-tokens"` + `cfg.tokensGlob: "*.css"`. `lib/css.mjs`의 `copyTokens()`는 `tokensPkg`가 없으면 early-return하고 `join(node_modules, tokensPkg)/package.json`을 무조건 읽는다. 그래서 소스를 `frontend/.ds-tokens/`에 두고(=`frontend/node_modules/../.ds-tokens`) 거기에 더미 `package.json`을 넣었다. `tokens.css`는 `tailwind.config.ts` 브랜드 토큰을 `:root` 커스텀 프로퍼티로 미러링 — **tailwind.config.ts 변경 시 같이 갱신**(수동 미러). styles.css가 `@import "./tokens/tokens.css"`.
- **fonts/** ← `cfg.extraFonts: [".ds-fonts/inter.css"]`. Inter를 가변 woff2(normal/italic)로 self-host(`frontend/.ds-fonts/`, fontsource jsdelivr에서 다운로드). `@font-face`는 `format('woff2')`(variations 표기 아님 — 호환성). 컨버터가 woff2를 `fonts/`로 복사하고 url을 `./…`로 재작성, styles.css가 `@import "./fonts/fonts.css"`. **그래서 cssEntry input(`.ds-tailwind-input.css`)의 remote Google Fonts @import는 제거**(중복·네트워크 의존 제거) → 변경 후 Tailwind 재컴파일 필수. `cfg.runtimeFontPrefixes`는 이제 Inter가 아니라 런타임 폴백 CJK(`Apple SD Gothic Neo`, `Noto Sans KR`)를 선언해 `[FONT_MISSING]`을 억제.
- **guidelines/** ← `cfg.guidelinesGlob: "../.design-sync/guidelines/**/*.md"`. 소스는 PKG_DIR(frontend) **밖**인 `.design-sync/guidelines/`에 둔다 — `docs.mjs`의 dest 규칙상 PKG_DIR 안이면 `guidelines/.ds-guidelines/`로 점-디렉터리 중첩되고, 밖(workspaceRoot 내)이면 basename으로 평탄화되어 `guidelines/*.md`가 된다. 디자인 에이전트용 가이드 4종(브랜드/레이아웃/색·토큰/컴포넌트 사용) + 자동 생성 `index.md`. styles.css 클로저엔 포함 안 됨(문서 복사).

## 진입점 / provider 전략

- `--entry frontend/.design-sync-entry.tsx`가 번들 진입점이다(빌드된 dist가 없으므로 synth-entry 대신 명시 진입점). 8개 컴포넌트를 re-export → `window.Figment.*`.
- **editor 컴포넌트(ChatPanel/CanvasStage 등)는 의도적으로 제외** — Konva 캔버스·zustand·라이브 API에 묶여 디자인 페인에서 렌더 불가.
- `cfg.provider = DesignSyncProvider`: Next.js app-router context(`useRouter`/`<Link>`용)를 제공하고, **mock 모델 카탈로그 + mock 백엔드 fetch**를 시드해 데이터 의존 카드(ModelPill, RecentProjects)가 populated 렌더되게 한다.
- **중요**: 하니스에는 **최상위 부수효과가 없다**. 모든 모킹은 `DesignSyncProvider` 내부 `primePreviewEnv()`에서만 실행되고, 이는 **프리뷰 카드에서만**(cfg.provider) 렌더된다. 실제 디자인은 컴포넌트만 import하고 provider를 렌더하지 않으므로 mock fetch/시드가 절대 누출되지 않는다.

## 폰트

- Inter는 이제 **번들에 self-host**된다 — `cfg.extraFonts: [".ds-fonts/inter.css"]`로 가변 woff2(normal/italic)를 `fonts/`에 출하하고 styles.css가 `@import "./fonts/fonts.css"`. 앱 런타임의 Google Fonts `<link>`와 무관하게 디자인이 in-brand로 렌더된다. body font-family의 CJK 폴백(`Apple SD Gothic Neo`/`Noto Sans KR`)은 출하 대상이 아니므로 `cfg.runtimeFontPrefixes`로 선언만 해 `[FONT_MISSING]`을 억제. (이전: remote @import로 런타임 로드 → 제거함.)

## 컴포넌트별 메모

- `components/models/ModelPicker.tsx`는 `ModelPicker`가 아니라 **`ModelPill`·`ModelPillRow`**를 export한다(동기화 이름).
- **RecentProjects**: 마운트 시 `listProjects()`(GET /api/projects) fetch. DesignSyncProvider의 fetch mock으로 populated grid를 렌더한다. mock이 없으면 빈 상태("No projects yet")만 정적 렌더된다.
- **ModelPill/PromptBox**: zustand `useModelsStore`를 읽는다. mock 모델을 `loaded:true`로 시드해 `load()`가 no-op이 되고 즉시 선택 모델을 표시한다.

## Known render warns (재sync 시 새 warn 아님)

- `[FONT_REMOTE]`/`[FONT_MISSING]` — 더 이상 발생 안 함. Inter를 self-host하고 CJK 폴백을 `runtimeFontPrefixes`로 선언하면서 remote @import를 제거해 둘 다 사라졌다.
- `tokens: 57 defined, 39 referenced (1 missing, below threshold)` — 정의됐으나 1개 미참조 토큰, threshold 이하 non-blocking.
- 헤드리스 chromium에는 이모지 폰트가 없어 ProjectCard/RecentProjects의 🖼️ placeholder가 tofu 글리프로 보인다(구조는 정상; 실제 claude.ai/design 환경에선 이모지 렌더). 등급에는 영향 없음.

## Re-sync risks (다음 sync가 주시할 것)

- **mock 데이터/시드가 상류 코드와 분리**되어 있다. `frontend/lib/types.ts`(Model/Project), `lib/api.ts`(엔드포인트 URL: `/api/projects`, `/api/models/all`), `lib/models.ts`(store shape)가 바뀌면 `.design-sync/preview-harness.tsx`의 mock이 stale될 수 있다. 빌드/렌더가 깨지면 여기부터 확인.
- **Inter**는 빌드 타임에 fontsource(jsdelivr CDN)에서 받은 가변 woff2를 `frontend/.ds-fonts/`에 커밋해 self-host → 런타임 네트워크 의존 없음. 폰트 갱신이 필요하면 woff2 재다운로드.
- **tokens.css**(`frontend/.ds-tokens/tokens.css`)는 `tailwind.config.ts` 값을 **수동 미러링**한다 — 토큰 변경 시 둘 다 갱신해야 drift가 안 생긴다. `tokensPkg`는 `../.ds-tokens` 트릭(node_modules 밖)이라 그 폴더의 더미 `package.json`이 사라지면 빌드가 깨진다.
- **Tailwind cssEntry는 생성물**이라 커밋되지 않는다. 재sync 시 위 컴파일을 반드시 재실행.
- **next/* 번들**(next/link, next/navigation, app-router-context 내부 경로)은 Next 버전에 의존. Next 메이저 업그레이드 시 provider 경로/해석을 재확인.
