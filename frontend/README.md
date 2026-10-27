# 当前前端入口 · Griffin 融合

> **2026-10-27 更新**：介绍页讲「先说出需求 → 找到对得上的那一期 → 看清它能帮你什么」。
> 顺序是 Hero（先说你要什么）→ 01 三步 → 02 按需求找期（`content.ts` 的 `needs`，9 条主题线各一句访客问题，
> 点开即到代表性期次）→ 03 一期给你什么（`content.ts` 的 `sampleEpisode`，EP.27 的真实三条判断 + 一句话 + 仓库）
> → 04 拆过的来源 → 05 最近几期 → 06 试听 → 结尾 CTA「说说我正琢磨的事」。
> 旧「四种入口」与「四种形式 + 预览窗」两段已从介绍页移除（工作区里照旧可用）。
> 新增数据一律回源：`node frontend/content.test.mjs` 第 13 组会把 `needs` / `sampleEpisode` 拿回
> `web/library/data/episodes.json` 与 `data.js` 逐条比对。样式只往 `web/library/griffin.css` 追加了新叙事用的布局规则。

`main.tsx → griffin-landing.tsx` 是 2026-10-25 的现役介绍页。`landing.tsx` 作为上一版源码保留。新布局只使用 `.gfn-*`，样式在 `web/library/griffin.css`，颜色在 `design-system/neon-tokens.css` 末尾的作用域 token 中。

Griffin 真源码/浏览器证据与许可边界在 `design-research/griffin-20261025/`。产品资源使用本地 OFL Instrument Serif / Noto Serif SC 子集，不含 Griffin 品牌或专有字体。既有 Sourcecast start/demo/navigate 事件与原生单音频播放器保持为业务入口。

构建 `node scripts/build_library_components.mjs`。内容回源 `node frontend/content.test.mjs`，token 同步 `python3 scripts/check_design_tokens.py`。下面是历史组件资料，不代表当前介绍页仍加载旧的动效组件。

---

# Sourcecast · SIGNAL 4.0 前端组件

入口为 `main.tsx` → `landing.tsx`。介绍页使用用户指定的 Aceternity TextHoverEffect、GoogleGeminiEffect、3DMarquee，适配源码位于 `components/`。上游原件、Registry JSON、来源 URL 与 SHA-256 保存在 `vendor/aceternity/`。共享 LWQ 的 Button、SearchField、InlineFeedback 与 useReducedMotion 保持原件复用，来源见 `vendor/lwq/provenance.json`。

当前项目规范在 `../design-system/DESIGN.md`，颜色真相源为 `../design-system/neon-tokens.css`，运行副本为 `../web/library/neon-tokens.css`，组件样式为 `../web/library/neon.css`。原 Paper & Sound 和 SplitText 仅保留历史源码，不参与当前首屏渲染；当前构建不会加载 GSAP。

Gemini 五条原始路径保留，通过真实滚动进度绘制；来源按钮进入原生创作台。3DMarquee 使用本项目原创 SVG 示意图，提供暂停/继续、离屏停止和后台暂停。减少动态时所有路径完整展示，跑马灯静止，长滚动区域改为普通区块。离开介绍页会卸载这三个效果。业务状态、笔记、导图和文件解析继续由原生脚本管理。

## 构建

项目根运行 `node scripts/build_library_components.mjs`。优先使用 `frontend/node_modules`，缺少时才复用旁边 `设计系统/` 的已安装依赖。可用 `LWQ_DESIGN_ROOT` 指定该工程。

独立源码包内，在 `frontend/` 运行 `npm ci --ignore-scripts --no-audit --no-fund`，再运行 `npm run build`。脚本自动识别工程的 `web/library/` 或源码包根目录，也支持 `SOURCECAST_WEB_DIR` 指定输出。输出是 `vendor/lwq/components.js`；构建后按真实文件 SHA-256 更新 HTML 的本地 JS/CSS 查询版本，避免预览命中旧包。

普通浏览无需 Node、CDN 或外部字体服务。PDF/EPUB 解析器、图标、字体与展示图均在本地。字体许可证见 `assets/fonts/SPACE-GROTESK-LICENSE`。当前视觉方向为本地草稿，技术验证和用户视觉认可分别记录。
