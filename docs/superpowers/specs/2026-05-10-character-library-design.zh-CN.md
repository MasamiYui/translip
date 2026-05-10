# 角色库（Character Library）设计方案

- 文档日期：2026-05-10
- 适用版本：translip vNext
- 关联模块：`speaker_review` / `speakers` / `dubbing/voice_bank` / `characters/ledger`
- 关联前端：`frontend/src/components/speaker-review/SpeakerReviewDrawer.tsx`、新增 `CharacterLibraryPage.tsx`
- 状态：草案（Proposal）

---

## 0. TL;DR

> **不要新建一个"角色库"模块，而要把项目里已经存在但被低估的 `speaker_review/global_personas.py` 长成完整形态。**

- 项目里已有「全局人物库」雏形：存储在 `~/.translip/personas.json`，已支持新增、删除、导入、智能匹配，并已通过 `/api/global-personas` 暴露给前端。
- 真正缺的是：**演员（actor）字段、头像文件、参考音频、与 voice_bank 的双向绑定、前端的入口与可视化**。
- 落点采用**"双入口"**：
  - 入口 A：侧栏一级导航「角色库」管理页 —— 资产维护
  - 入口 B：「说话人核对抽屉」内嵌智能匹配卡片 —— 现场调用
- 数据物理位置保持 `~/.translip/`（用户级、跨任务），不进入 `tasks/{task_id}/` 目录。

---

## 1. 背景与现状

### 1.1 用户痛点

当前「说话人核对」页面（见产品截图）右侧只能看到 `SPEAKER_00 / 改昵称 / 中风险` + 一行台词。
用户必须靠"听 + 猜"完成识别，存在三个核心问题：

1. **跨集 / 跨任务无复用**：电视剧/电影连续作品里，"哪吒""敖丙"会反复出现，每次都得重新认一遍。
2. **决策上下文太薄**：没有头像、没有演员信息、没有历史参考音，决策质量依赖人脑记忆。
3. **配音环节断链**：核对决策后，TTS 阶段又要重新选音色。"哪吒永远用同一个音色"无法被持久化。

### 1.2 既有资产盘点

| 模块 | 文件 | 既有能力 |
|---|---|---|
| 全局人物库后端 | `src/translip/speaker_review/global_personas.py` | load/save/add_or_update/remove/list/smart_match/export_from_task |
| 任务级人物 | `src/translip/speaker_review/personas.py` | Persona dataclass，含 bindings/aliases/color/avatar_emoji/gender/age_hint/note/role/tts_voice_id |
| 角色台账 | `src/translip/characters/ledger.py` | character_ledger.json，含 voice_signature / risk_flags / review_status |
| 配音音色库 | `src/translip/dubbing/voice_bank.py` | 管理 TTS 可用音色资源 |
| 说话人画像 | `src/translip/speakers/profile.py`、`registry.py` | reference_clips 与 embedding |
| HTTP 路由 | `src/translip/server/routes/speaker_review.py:844` | `GET/POST/DELETE /api/global-personas`、`POST /api/global-personas/import`、`POST .../speaker-review/global-personas/export-from-task` |
| 前端 | `frontend/src/components/speaker-review/SpeakerReviewDrawer.tsx` | 任务内说话人 / persona 编辑 |

**结论**：地基已搭好 50%，需要的是补字段、加入口、连环节。

### 1.3 目标与非目标

#### 目标

- G1：让用户能够在一个独立页面集中维护"角色 + 演员 + 头像 + 参考音色"档案。
- G2：让「说话人核对」可以一键智能匹配到角色库中的角色，绑定后自动回填名称、颜色、头像、TTS 音色。
- G3：让角色库的 `tts_voice_id` 与 `dubbing/voice_bank.py` 联动，做到"角色 → 固定音色"在全项目持久化。
- G4：让角色台账（character ledger）的质量数据可以反哺到角色库（如"在 3 部作品里出现过、平均风险等级"）。

#### 非目标（本期不做）

- N1：演员（actor）的独立档案表 —— 本期把演员姓名作为字段挂在角色上，N:M 关系延后做。
- N2：跨用户、多端云同步 —— 仅本机文件存储，导入/导出走手动。
- N3：肖像版权审查 —— 本期仅提供"仅本地"提示，不做自动审查。

---

## 2. 信息架构

### 2.1 概念边界

```
Actor（演员，未来）  ─── 1:N ───  Character（角色 / 全局 persona）
                                       │
                                       │  match
                                       ▼
Task Persona（任务内 persona） ──── bind ──→  SPEAKER_xx 标签
                                       │
                                       │  produces
                                       ▼
                              Voice Profile（dubbing voice）
```

### 2.2 角色（Character）数据字段（扩展后）

在 `global_personas.py` 的 `_strip_for_global` 的 `kept_keys` 中新增字段：

| 字段 | 类型 | 含义 | 备注 |
|---|---|---|---|
| `id` | str | 全局唯一 ID | 已有 |
| `name` | str | 角色名（如"哪吒"） | 已有，作为主显示名 |
| `aliases` | list[str] | 别名（"小哪吒"等） | 已有 |
| `color` | str | 颜色 | 已有，与时间轴卡片配色一致 |
| `avatar_emoji` | str | emoji 头像 | 已有，作为兜底 |
| `avatar_path` | str | **新增** 头像文件相对路径 | `assets/{id}/avatar.png` |
| `gender` | str | 性别 | 已有 |
| `age_hint` | str | 年龄段提示 | 已有 |
| `note` | str | 备注 | 已有 |
| `role` | str | 角色类型（主角/配角…） | 已有 |
| `actor_name` | str | **新增** 演员姓名 | 你提的"演员" |
| `actor_aliases` | list[str] | **新增** 演员别名 | 可选 |
| `character_alias_in_work` | str | **新增** 在某作品中的特定称谓 | 可选 |
| `tts_voice_id` | str | TTS 默认音色 ID | 已有，与 voice_bank 联动 |
| `tts_skip` | bool | 是否跳过该角色 TTS | 已有 |
| `reference_clip_paths` | list[str] | **新增** 参考音频相对路径列表 | `assets/{id}/refs/*.wav` |
| `voice_signature` | dict | **新增** 缓存的声纹签名 | 来自 `quality/audio_signature.py` |
| `tags` | list[str] | **新增** 自由标签 | 例：`["主角","少年","男声"]` |
| `project_refs` | list[dict] | **新增** 出现过的任务/作品 | `[{task_id, work_name, episode, last_seen}]` |
| `confidence` | float | 置信度 | 已有 |
| `created_at` / `updated_at` | str | 时间戳 | 已有 |

### 2.3 物理存储

```
~/.translip/                              ← 用户级根，可被 TRANSLIP_GLOBAL_PERSONAS_DIR 覆盖
├── personas.json                         ← 主清单（JSON）
├── personas.history.jsonl                ← 操作日志（追加式）
└── assets/
    └── {persona_id}/
        ├── avatar.png                    ← 头像
        └── refs/
            ├── 001.wav                   ← 参考音频
            ├── 001.json                  ← 对应声纹签名
            └── ...
```

理由：
- 与既有 `speaker_review/personas.py` 的 history/snapshot 机制保持同构；
- 二进制资源单独目录，便于备份与迁移；
- 可被环境变量整体覆盖（已经支持 `TRANSLIP_GLOBAL_PERSONAS_DIR`）。

---

## 3. 后端设计

### 3.1 模块组织（不新增顶层模块）

仍然以 `src/translip/speaker_review/global_personas.py` 为入口，必要时拆分成包：

```
src/translip/speaker_review/global_personas/
├── __init__.py            ← 公共导出（保持向后兼容旧 import 路径）
├── store.py               ← load/save/path/_strip_for_global
├── matching.py            ← smart_match_global 及未来更复杂匹配
├── assets.py              ← 头像 / 参考音频文件 IO
└── voice_link.py          ← 与 dubbing/voice_bank.py 的桥
```

> 若不希望立即拆包，第 1 阶段保持单文件，仅在文件内分小节即可。

### 3.2 关键 API（在 `server/routes/speaker_review.py` 的 `global_personas_router` 上新增）

| Method | 路径 | 作用 | 返回 |
|---|---|---|---|
| GET | `/api/global-personas` | 列出全部（已有） | `{path, personas[], total}` |
| GET | `/api/global-personas/{id}` | **新增** 详情 | `{persona, signed_avatar_url}` |
| POST | `/api/global-personas` | **新增** 创建/更新单条 | `{persona}` |
| POST | `/api/global-personas/import` | 批量导入（已有） | `{ok, total, personas}` |
| DELETE | `/api/global-personas/{id}` | 删除（已有） | `{ok, personas}` |
| POST | `/api/global-personas/{id}/avatar` | **新增** 上传头像（multipart） | `{avatar_path}` |
| POST | `/api/global-personas/{id}/reference-clip` | **新增** 上传/绑定参考音频 | `{clip_id, voice_signature}` |
| DELETE | `/api/global-personas/{id}/reference-clip/{clip_id}` | **新增** 删除参考音频 | `{ok}` |
| POST | `/api/global-personas/{id}/voice-link` | **新增** 绑定到 voice_bank 的 voice_id | `{tts_voice_id}` |
| POST | `/api/tasks/{task_id}/speaker-review/global-personas/match` | **新增** 主动拉取智能匹配候选 | `[{speaker_label, candidates[]}]` |
| POST | `/api/tasks/{task_id}/speaker-review/global-personas/bind` | **新增** 把全局 persona 绑定到任务 SPEAKER 标签 | `{task_persona}` |
| POST | `/api/tasks/{task_id}/speaker-review/global-personas/export-from-task` | 任务回灌（已有） | `{exported, skipped, total}` |

### 3.3 文件上传与签名声纹

- 头像上传：限制 `image/png`、`image/jpeg`，最大 2MB，自动生成 256×256 缩略图。
- 参考音频上传：限制 `audio/wav`、`audio/mp3`、`audio/x-m4a`，最大 30MB，单条 ≤ 30s；
  上传后立即调用 `quality.audio_signature.voice_signature` 计算并缓存声纹（pitch_class、rms、duration）。
- 声纹缓存写入同名 `.json`，便于后续 `smart_match` 直接读取。

### 3.4 与 voice_bank 的双向绑定

- **方向 A（角色 → 音色）**：persona.tts_voice_id 写入后，`dubbing/voice_bank.py` 在 lookup 时优先返回该 voice。
- **方向 B（音色 → 角色）**：`voice_bank` 新增 `linked_persona_id` 反向引用，便于在音色库页面看到"该音色被哪个角色长期使用"。
- 失效保护：voice_bank 删除音色时，扫描 personas，自动把 `tts_voice_id` 置空并记录降级日志。

### 3.5 与 character_ledger 的反哺

`characters/ledger.py` 在生成 `character_ledger.{lang}.json` 时，新增一段 `linked_persona_id` 字段。
未来可在角色库管理页里展示「该角色历史风险趋势」（来自多份 ledger 聚合）。

---

## 4. 前端设计

### 4.1 双入口策略

#### 入口 A：独立管理页 `/personas`

- 在 `frontend/src/components/layout/Sidebar.tsx` 增加一级菜单「角色库」，图标使用 `icons.svg` 中已有的人物图标。
- 新建 `frontend/src/pages/CharacterLibraryPage.tsx`，路由 `/personas`：
  - **顶部条**：搜索框（按角色名/演员名/标签）、性别筛选、来源任务筛选、新增按钮、批量导入按钮。
  - **主体网格**：卡片瀑布流，每张卡片：头像 + 角色名 + 演员名 + 标签条 + 颜色条 + 出现作品数。
  - **详情抽屉**（右侧滑出）：
    - Tab 1 基本信息：name / aliases / color / actor_name / role / gender / age_hint / note / tags
    - Tab 2 参考音频：列表 + 播放器 + 上传按钮 + 声纹（pitch_class、duration）
    - Tab 3 TTS 绑定：当前 `tts_voice_id`，可以从 voice_bank 选择
    - Tab 4 出现记录：`project_refs` 列表，可点击跳转任务详情
    - Tab 5 历史：来自 `personas.history.jsonl` 的操作记录（只读）
  - **批量操作**：导出 JSON、批量删除、批量打标签。

#### 入口 B：说话人核对抽屉内嵌（高频核心场景）

改造 `frontend/src/components/speaker-review/SpeakerReviewDrawer.tsx`：

```
┌─ SPEAKER_00 ──────────────────  [改昵称] [中风险] ┐
│ 0:42.5 - 0:45.9                  [循环 (L)]        │
│  全陈塘关都得陪葬                                  │
│                                                    │
│  ┌─ 🎯 角色库匹配 ────────────────────────────┐   │ ← 新增卡片
│  │ ① 哪吒（陈浩饰）  匹配度 0.9  性别+台词     │   │
│  │   [试听参考音] [绑定]                        │   │
│  │ ② 敖丙（王雷饰）  匹配度 0.6  音色相近       │   │
│  │   [试听参考音] [绑定]                        │   │
│  │ ③ 哪吒之父（赵飞饰）匹配度 0.4 …             │   │
│  │ ─────────────────────────────────────────── │   │
│  │ [搜索角色库] [创建新角色]                    │   │
│  └────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

- 抽屉打开时调用 `POST /api/tasks/{task_id}/speaker-review/global-personas/match`，把 top-3 候选缓存到 `speakerReviewStore.ts`。
- 选择一个候选后调用 `.../bind`，自动回填该 SPEAKER 的 name、color、avatar_emoji、tts_voice_id；时间轴上的色条立即更新。
- 顶部菜单加一个**「另存为新角色 / 回灌到角色库」**按钮：调用既有 `export-from-task`，把当前任务里改过名的 persona 推回全局。

### 4.2 状态管理

- 在 `speakerReviewStore.ts` 中新增切片：
  - `globalPersonaCandidates: Record<speakerLabel, Candidate[]>`
  - `globalPersonaBindings: Record<speakerLabel, persona_id>`
  - `globalPersonaCache: Record<persona_id, Persona>` —— 减少重复请求
- 新建独立 store `frontend/src/stores/characterLibraryStore.ts`，供管理页使用，与上面的缓存共享。

### 4.3 i18n

字段加入 `frontend/src/i18n/messages.ts`：

| key | zh | en |
|---|---|---|
| `characterLibrary.title` | 角色库 | Character Library |
| `characterLibrary.character` | 角色 | Character |
| `characterLibrary.actor` | 演员 | Actor |
| `characterLibrary.avatar` | 头像 | Avatar |
| `characterLibrary.refClips` | 参考音频 | Reference clips |
| `characterLibrary.match.cta` | 匹配角色库 | Match library |
| `characterLibrary.bind` | 绑定 | Bind |
| `characterLibrary.exportFromTask` | 回灌到角色库 | Export to library |

### 4.4 视觉规范

- 颜色沿用 persona.color，与时间轴说话人色条统一。
- 头像缺省态：圆形 + emoji（avatar_emoji），确保即使没上传头像也有视觉锚点。
- 风险条：当 persona.tts_voice_id 失效时显示橙色"音色已失效"标签。

---

## 5. 关键交互流程

### 5.1 首次使用某 IP（冷启动）

```
1. 用户在「说话人核对」抽屉里手动改 SPEAKER_00 → "哪吒"，颜色橙色
2. 点击右上角「回灌到角色库」
3. 后端 export_task_personas_to_global 执行
4. 角色库页面自动出现"哪吒"卡片（无头像）
5. 用户进入角色库页 → 上传头像、填写演员、上传参考音频
6. 后端为参考音频计算声纹签名并写入
```

### 5.2 后续作品复用（热复用）

```
1. 新任务 ASR + diarization 完成，进入「说话人核对」
2. 抽屉打开时自动 POST /global-personas/match
3. SPEAKER_00 收到 top-3 候选，"哪吒"匹配度 0.9（性别 + role）
4. 用户点击"绑定" → 一键回填名称/颜色/头像/tts_voice_id
5. 时间轴色条立即变橙
6. 后续 TTS 阶段读取 tts_voice_id 自动用回原音色
```

### 5.3 音色失效降级

```
1. 用户在 voice_bank 删除某音色 voice_xyz
2. voice_bank 删除钩子扫描 personas，发现"哪吒"使用该音色
3. 自动置空 tts_voice_id 并写入 history（reason="voice_deleted"）
4. 角色库页面卡片显示橙色"音色已失效"
5. 下次说话人核对时若仍能匹配到"哪吒"，会提示"请先重选音色"
```

---

## 6. 实施路线图

按"先打通价值，再补丰富度"的节奏，不需要一口吃成胖子。

### 阶段 1：最高 ROI（约 1 周，纯前端）

- [ ] 在 `SpeakerReviewDrawer.tsx` 内嵌"角色库匹配"卡片
- [ ] 接入既有 `smart_match_global`，展示 top-3 候选
- [ ] 实现"绑定" → 调用既有 export/import API 回填 task persona
- [ ] 在抽屉顶部加"回灌到角色库"按钮
- ✅ 收益：核对效率立即提升，**0 行后端代码改动**

### 阶段 2：管理页 + 资产字段（约 2 周）

- [ ] 后端：扩展 `_strip_for_global` 的 kept_keys，加入 actor_name / avatar_path / reference_clip_paths / tags / project_refs
- [ ] 后端：实现 `/avatar` 与 `/reference-clip` 上传接口
- [ ] 前端：新增 Sidebar 菜单 + `CharacterLibraryPage.tsx` + 详情抽屉
- [ ] 前端：i18n 词条接入
- [ ] e2e：补 `tests/e2e/character-library.spec.ts`
- ✅ 收益：用户拥有"IP 资产中心"

### 阶段 3：voice_bank 双向绑定（约 1 周）

- [ ] 在 `dubbing/voice_bank.py` 增加 `linked_persona_id`
- [ ] 写删除钩子，自动清理失效引用
- [ ] 前端在角色库详情 Tab 3 显示音色试听 + 切换
- ✅ 收益："角色固定音色"在全项目持久化

### 阶段 4：character_ledger 反哺（约 1 周）

- [ ] `characters/ledger.py` 的 character payload 增加 `linked_persona_id`
- [ ] 前端：详情 Tab 5 增加"历史风险趋势"图
- ✅ 收益：质量数据闭环

### 阶段 5（可选，未来）：演员独立档案

- [ ] 引入 `actors.json` 与 N:M 关系
- [ ] 支持"同一演员的不同角色""同一角色不同演员版本"

---

## 7. 兼容性与迁移

- 既有 `~/.translip/personas.json` 文件**直接兼容**：未填充的新字段读出来为 None / 空数组。
- 既有 `/api/global-personas` 接口签名**保持不变**：新接口走新路径，不改旧路径返回结构。
- 历史数据迁移：第 2 阶段上线时执行一次 `migrate_v1_to_v2`，仅补默认值，不删字段。
- 老版本前端访问新后端：忽略未识别字段即可，不会崩溃。

---

## 8. 风险与对策

| 风险 | 等级 | 对策 |
|---|---|---|
| 头像 / 演员姓名涉及肖像权 | 中 | UI 顶部提示"仅本地存储"；导出 JSON 提供"脱敏模式"剥离 actor_name 与 avatar_path |
| 参考音频体积膨胀 | 中 | 单条 ≤ 30s、单角色 ≤ 5 条；管理页提供"清理未使用资源"按钮 |
| smart_match 误匹配 | 中 | top-3 默认不自动绑定，必须手动确认；显示匹配理由便于人审 |
| voice_bank 与 persona 双向引用形成孤儿 | 低 | 启动期一次性扫描，写一致性日志；删除均走钩子 |
| 跨设备同步 | 低（非目标） | 第 5 阶段后再考虑接 WebDAV / Git 同步 |
| 文件名冲突 | 低 | persona_id 为 uuid4；assets 目录以 id 作为子目录 |

---

## 9. 验收标准

- A1：用户能在 `/personas` 页面看到 ≥ 1 个角色，并完成新增、编辑、删除全流程。
- A2：在「说话人核对」抽屉里，每个 SPEAKER 都能看到 0–3 个候选；点击"绑定"后，时间轴色条与名称同步更新。
- A3：上传头像 / 参考音频后，刷新页面仍可见，文件物理存在于 `~/.translip/assets/{id}/`。
- A4：persona 关联的 `tts_voice_id` 在新任务的 TTS 阶段被自动选中，无需手动指定。
- A5：删除 voice_bank 中某音色后，受影响的 persona 自动置空 tts_voice_id 并出现降级提示。
- A6：导出/导入 JSON 闭环可用，导入会按 fingerprint 去重。
- A7：i18n 中英文切换无文案缺失。
- A8：playwright e2e `character-library.spec.ts` 全部通过。

---

## 10. 决策记录（ADR 摘要）

- **ADR-1**：复用 `global_personas.py` 而非新建 `character_library` 模块 —— 避免双源、降低迁移成本。
- **ADR-2**：物理存储继续使用 `~/.translip/`，不下沉到任务目录 —— 角色库本质是跨任务资产。
- **ADR-3**：演员（actor）字段先扁平化为 persona 的属性，N:M 关系延后 —— 第 1 期不引入新实体表。
- **ADR-4**：双入口（侧栏管理页 + 抽屉内嵌） —— 兼顾"主动维护"与"现场调用"两种使用动线。
- **ADR-5**：top-3 智能匹配默认手动确认 —— 错绑代价高于轻微的多点击成本。

---

## 11. 一句话收尾

> 我们不是"引入"一个角色库，而是把项目里已经存在的全局人物库**长成它该有的样子**：
> 后端补齐字段 + 资产 IO + voice_bank/ledger 双向连接，前端做"管理页 + 抽屉内嵌"双入口。
> 第 1 阶段几乎零后端改动就能立刻拿下"核对智能匹配"这个最高 ROI 场景，
> 后续阶段把它逐步抚养成贯穿"识别 → 配音 → 质检"全链路的核心资产。

---

# v3 增订：「作品（Work）+ 标签（Tag）」二级模型

- 增订日期：2026-05-10
- 状态：实施中（按 PR 拆分推进）
- 上下文：阶段 1（抽屉内嵌匹配 + 回灌入口）✅ + 阶段 2（独立管理页 + 演员/标签字段）✅ 已完成；本节落地"打通全环节"的中长期方案。

## V3.1 为什么要再升一级

当前角色库是**扁平名册**：所有 persona 平铺在一张大表里。这在 50 人以下没问题，但出现两个真实场景就会失效：

1. **同名歧义**：两部不同剧里都有"小青"，按姓名匹配会撞车。
2. **同演员多剧**：Anne Hathaway 在不同电影里饰演不同角色，扁平表很难总览"她演过的角色"。

要解决，但又不能简单地"按剧名硬分文件夹"——那会强迫每条角色都归属一部作品，提高使用门槛。

**结论**：引入 **Work**（作品）作为结构化的一等公民 + 保留 **Tag** 作为自由的二等公民，二者互补不互斥。

## V3.2 数据模型

### V3.2.1 文件布局

```
~/.translip/
├── personas.json           # 已存在，保留；persona 上增加可选 work_id 等字段
└── works.json              # 新增：作品花名册
```

### V3.2.2 Work 实体（works.json）

```jsonc
{
  "version": 1,
  "updated_at": "...",
  "works": [
    {
      "id": "work_<base32>_<hash>",
      "title": "老友记",
      "type": "tv",                       // 见 V3.2.4 类型枚举
      "year": 1994,
      "aliases": ["Friends", "六人行"],
      "cover_emoji": "☕️",
      "color": "#7c3aed",
      "note": "Sitcom，10 季 236 集",
      "tags": ["美剧", "情景喜剧"],          // 作品自身的 tag
      "default_tts_voice_map": { ... },    // 可选，作品级默认音色映射
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### V3.2.3 Persona 扩展（向后兼容）

每条 persona 增加 4 个**可选**字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `work_id` | `string \| null` | 主作品归属。null 表示"通用/未归属" |
| `guest_work_ids` | `string[]` | 客串/兼职过的其他作品 |
| `episodes` | `string[]` | 出现过的具体集，如 `["S01E03"]` |
| `external_refs` | `{ tmdb_id?, imdb_id? }` | 占位，未来对接外部库 |

### V3.2.4 作品类型枚举（内置 + 用户可扩展）

由用户决策：**内置常用类型，并允许手动添加自定义类型**。

**内置类型**（保留中英显示名，存盘存英文 key）：

| key | 中文 | 英文 |
|---|---|---|
| `tv` | 电视剧 | TV Series |
| `movie` | 电影 | Movie |
| `anime` | 动漫 | Anime |
| `documentary` | 纪录片 | Documentary |
| `short` | 短片 | Short |
| `variety` | 综艺 | Variety |
| `audiobook` | 有声书 | Audiobook |
| `game` | 游戏 | Game |
| `other` | 其他 | Other |

**自定义类型**：作品创建/编辑时，"类型"下拉框最后一项是「+ 自定义」，点击后弹出输入框；用户输入的自定义类型 key 落到 `~/.translip/work_types.json` 单独文件保存（避免污染主数据），全 UI 共享。

`work_types.json` 结构：

```json
{
  "version": 1,
  "custom_types": [
    { "key": "podcast", "label_zh": "播客", "label_en": "Podcast" }
  ]
}
```

约束：
- key 只允许小写字母 + 数字 + `_`
- 不允许与内置 key 冲突
- 删除自定义类型时，作品中已使用的 key 会保留为字符串，但下拉框不再展示该选项

### V3.2.5 Task 扩展

`Task` 表增加 2 列（Alembic add column with default null，幂等可回滚）：

| 列 | 类型 | 含义 |
|---|---|---|
| `work_id` | `VARCHAR(64) NULL` | 任务关联的作品 |
| `episode_label` | `VARCHAR(64) NULL` | 集数标签（"S01E01"、"第 3 集"） |

> **本次确认**：保留 `episode_label` 字段，让推断算法更聪明、UI 更直观。

## V3.3 后端 API

### V3.3.1 Works 端点（新增）

| Method | Path | 说明 |
|---|---|---|
| `GET` | `/api/works` | 列表，支持 `?q=` 搜索 title/alias |
| `POST` | `/api/works` | 创建（body: `{ title, type, year?, aliases?, ... }`） |
| `PATCH` | `/api/works/{work_id}` | 局部更新 |
| `DELETE` | `/api/works/{work_id}` | 删除（带 `?reassign_to=null \| <work_id>`） |
| `GET` | `/api/works/{work_id}/personas` | 该作品下角色 |
| `POST` | `/api/works/{work_id}/personas/move` | 批量移动 personas |
| `POST` | `/api/works/infer-from-task/{task_id}` | 启发式推断作品候选 top-3 |
| `GET` | `/api/work-types` | 内置 + 自定义类型列表 |
| `POST` | `/api/work-types` | 添加自定义类型 |
| `DELETE` | `/api/work-types/{key}` | 删除自定义类型（不影响存量数据） |

### V3.3.2 既有 personas 端点扩展

| 端点 | 改动 |
|---|---|
| `GET /api/global-personas` | 新增 `?work_id=`、`?tags=`、`?q=` 过滤 |
| `POST /api/global-personas/import` | body 可带 `work_id` 字段 |
| `POST /api/tasks/{id}/speaker-review/personas/suggest-from-global` | 当 task 关联了 work_id 时，**优先**在 work 内匹配并加权；不足再降级到 cross-work；返回 `match_scope` |

### V3.3.3 Task 端点扩展

| 端点 | 改动 |
|---|---|
| `PATCH /api/tasks/{task_id}` | 新增 `work_id`、`episode_label` 可写字段 |
| `GET /api/tasks/{task_id}` | 返回值增加 `work` 内嵌对象 |
| `POST /api/tasks/{task_id}/work/auto-bind` | 服务端推断 + 自动落库 |

### V3.3.4 删除策略（用户已确认）

**默认行为**：删除 Work 时**保留旗下 personas 为"未归属"**（清空它们的 `work_id`）。

提供三种模式（前端弹窗选择，后端通过 `?reassign_to=` 表达）：

1. **保留旗下角色为"未归属"**（默认；`reassign_to=null` 或省略）
2. **批量改归到另一个 Work**（`reassign_to=<other_work_id>`）
3. **连同旗下角色一起删除**（`?cascade=true`，需二次确认 + 输入作品名）

## V3.4 启发式推断 `infer_work_from_task`

按以下顺序打分，返回 top-3：

1. 任务名/源文件名包含**已存在 Work 的 title 或 alias**（最高分 0.9）
2. 任务名与**已存在 Work 的 title 编辑距离 ≤2** 或子串重合 ≥70%（0.6）
3. 文件名通用模式抽取：`<标题>.S\d+E\d+.*`、`<标题>\.\d{4}.*`，把抽出的"标题"再去 1/2 比对（0.5）

返回结构：

```jsonc
[
  { "work_id": "work_lyj", "title": "老友记", "score": 0.9, "reason": "title alias matched: Friends", "episode_label": "S01E01" },
  { "work_id": null, "suggest_create": { "title": "Friends", "year": null }, "score": 0.6, "reason": "filename pattern S01E01" }
]
```

UI 阈值：
- `>= 0.85` → 自动绑定 + Toast 通知「已自动关联到：老友记 S01E01，可撤销」
- `0.5 ~ 0.85` → 顶部 banner「为你识别到 ...，是否关联？[确认] [换一个] [关闭]」
- `< 0.5` → 不打扰，仅在用户主动点"自动识别"时返回候选

## V3.5 前端架构

| 页面 | 改动 |
|---|---|
| `/character-library` | 改造成**双栏**：左侧 Works（含"全部 / 未归属"虚拟项 + 搜索），右侧角色表 |
| `/character-library/works/:workId` | 单个作品详情 + 旗下角色 |
| `TaskDetailPage` | 顶部新增"关联作品" chip + "自动识别"按钮 |
| `SpeakerReviewDrawer` | 候选卡片显示 *本作品 N 个 · 全局 M 个*，可切 scope |

新增组件：`WorksSidebar` / `WorkEditorDrawer` / `WorkChip`（Compact/Detailed）/ `WorkInferenceBanner` / `WorkTypeSelect`（含自定义入口）。

## V3.6 智能匹配的 scope 切换

```python
def smart_match_with_work(task_speakers, task_work_id, global_payload):
    for sp in task_speakers:
        in_work = match(sp, scope=work_personas(task_work_id))
        cross   = match(sp, scope=all_personas, exclude=in_work)
        in_work = boost(in_work, +0.3)             # 同 work 加权
        ranked  = (in_work + cross)[:5]
    return { speaker_label: { "scope": "work" if task_work_id else "global", "candidates": ranked } }
```

要点：
- `task_work_id` 为空时退化成阶段 1（保持兼容）
- 同作品候选始终排在 cross-work 之前
- UI 标记每个候选 `from_work_id` 是否等于当前任务

## V3.7 Work 与 Tag 的关系

- 每个 Work 自动派生只读虚拟 tag（`__work__:work_lyj`），仅 UI 内部使用，不写盘
- 用户在 persona 编辑器输入 tag 时，模糊匹配 Works 列表，命中则提示「检测到这是作品名，要把它升格为关联作品吗？」
- 反向：Work 重命名时，自动重写所有把旧 title 当 tag 的 personas（dry-run 报告 → 用户确认 → 写盘）

## V3.8 测试矩阵

### 后端 pytest

| 测试 | 覆盖点 |
|---|---|
| `test_works_routes.py::test_create_list_update_delete` | CRUD 基本流 |
| `test_works_routes.py::test_delete_with_reassign` | 三种删除模式 |
| `test_works_routes.py::test_infer_from_task_filename_pattern` | S01E01 抽取 + alias 命中 |
| `test_work_types_routes.py::test_custom_types_crud` | 自定义类型 CRUD |
| `test_speaker_review_routes.py::test_suggest_with_work_scope` | scope=work 优先 |
| `test_speaker_review_routes.py::test_suggest_falls_back_to_global` | 同 work 不足时降级 |

### 前端 vitest

| 测试 | 覆盖点 |
|---|---|
| `WorksSidebar.test.tsx` | 渲染、计数、搜索过滤、点击切换 |
| `WorkEditorDrawer.test.tsx` | 创建/编辑/别名编辑 |
| `WorkTypeSelect.test.tsx` | 内置类型 + 自定义类型添加 |
| `CharacterLibraryPage.test.tsx`（升级） | 双栏交互、按 Work 过滤、未归属虚拟项 |

### Playwright e2e

| spec | 流程 |
|---|---|
| `tests/e2e/works.spec.ts` | 新建作品 → 创建角色挂到该作品 → 左栏切换 |
| `tests/e2e/works-task-binding.spec.ts` | 任务详情页"自动识别" → 接受推荐 → 进入说话人核对 |
| `tests/e2e/works-rename-cascade.spec.ts` | 重命名作品 → tags 自动 sweep |

每个 e2e 严格沿用阶段 2 已验证的 LIFO + `route.fallback()` 模式。

## V3.9 实施排期（按 PR 拆分）

| PR | 内容 | 预估 |
|---|---|---|
| **PR-1** 数据底座 | works.json IO + Work CRUD + Persona/Task 扩展 + 后端 pytest | 0.5d |
| **PR-2** 推断引擎 | infer_work_from_task + 接口 + 单测 | 0.5d |
| **PR-3** 角色库双栏 UI | WorksSidebar + WorkEditorDrawer + 升级 CharacterLibraryPage + 自定义类型 + vitest + e2e | 1d |
| **PR-4** 任务详情页关联 | WorkChip + 自动识别 banner + e2e | 0.5d |
| **PR-5** Speaker Review work scope | smart_match_with_work + 抽屉 scope 切换 + e2e | 0.5d |
| **PR-6** Tag 升格通道 | 输入检测同名 Work + 一键升格 + 重命名 sweep | 0.5d |
| **PR-7** Onboarding & 迁移 | 高频 tag 升格引导 + 文档更新 | 0.5d |

## V3.10 用户已确认项（2026-05-10）

1. **作品类型**：内置常用枚举（tv/movie/anime/documentary/short/variety/audiobook/game/other），并支持用户在 UI 添加自定义类型
2. **Work 删除时旗下 personas**：默认保留为"未归属"
3. **集数字段**：保留 `episode_label`，让推断算法更聪明、UI 更直观

## V3.11 风险与对策

| 风险 | 对策 |
|---|---|
| 用户已有几百条无归属 personas，左栏首屏"未归属"很大 | 提供"批量归属"模式：勾选多个角色 → 选择目标 Work，单次写盘 |
| 启发式推断把同名不同剧绑错 | 置信度 < 0.85 时**只 banner 提示**；提供"换一个候选" |
| Work 删除后僵尸引用 | list/get personas 时做"work 不存在则视为 unassigned"容错 |
| Tag 字符串和 Work title 撞名 | UI 上以图标区分（🏷 vs 🎬） |
| 大库性能（>1万角色） | MVP in-memory；后续 `personas-by-work/` 分片 + 索引（已在文件布局预留） |

## V3.12 一句话收尾

> Work 给"角色库"装上骨架，Tag 给它装上自由的肌肉；二者各司其职，老数据无缝过渡，从此"角色库"才真正贯穿"任务 → 说话人核对 → 资产复用"全链路。

## V3.13 实施踩坑记录（2026-05-10 PR-3 阶段）

### 1. Playwright `page.route` glob 误匹配 Vite 源模块

- **现象**：测试启动后浏览器报 `Failed to load module script: Expected a JavaScript-or-Wasm module script but the server responded with a MIME type of "application/json"`，React 卡在 `Loading…` 没挂载，`getByTestId('works-sidebar')` 永远找不到。
- **根因**：在 `setupRoutes` 里写 `page.route('**/api/works**', ...)` 时，glob 中的 `**` 匹配任意字符（包括 `.ts?t=...`），于是 Vite 的 `/src/api/works.ts?t=xxx` 模块请求也被这条规则拦下来，被强制返回了 `application/json` 的 mock JSON，导致 ESM 模块加载失败。
- **修复**：所有 `**/api/works**`、`**/api/work-types**` 一律改为正则 `/\/api\/works(\?|$)/`、`/\/api\/works\/[^/?#]+(\?|$)/`、`/\/api\/work-types(\?|$)/` 等明确收口的 pattern，避免吞掉 Vite dev server 的源码请求。
- **教训**：Playwright 的 `page.route` 用 glob 时一定要确认 `**` 不会跨越 `?` / `.` 边界；只要前端 API 文件名（`api/<name>.ts`）和后端路由名（`/api/<name>`）撞名，就一定要切到正则。

### 2. Playwright `baseURL` 与 Vite `--host` 主机名不一致

- **现象**：`scripts/dev.sh` 里 Vite 通过 `--host 127.0.0.1` 启动，而 `playwright.config.ts` 里 `baseURL: 'http://localhost:5173'`，部分 macOS / Chromium 上下文会把 `localhost` 解析到 IPv6 `::1`，导致请求 `ERR_ABORTED`。
- **修复**：`playwright.config.ts` 与 `dev.sh` 对齐为 `http://127.0.0.1:5173`，保证 IPv4 一致解析。
- **教训**：dev 服务器和测试 baseURL 必须用同一个主机名字符串，避免 IPv4/IPv6 解析分裂。

### 3. React 19 `react-hooks/set-state-in-effect` 新规

- **现象**：`WorkEditorDrawer` 里用 `useEffect(() => setForm(toFormState(work)), [open, work])` 重置表单，被 ESLint 报 `react-hooks/set-state-in-effect` 错误。改用 `useRef + 渲染期赋值` 又触发"Cannot access refs during render"。
- **最终修复**：采用"render 中按 reset key 派生状态"模式：

  ```tsx
  const resetKey = open ? `${work?.id ?? 'new'}` : '__closed__'
  const [lastResetKey, setLastResetKey] = useState<string>('__closed__')
  if (lastResetKey !== resetKey) {
    setLastResetKey(resetKey)
    if (open) {
      setForm(work ? toFormState(work) : EMPTY_FORM)
      // 重置自定义类型 inline 表单
      setCustomOpen(false)
    }
  }
  ```

  这是 React 官方推荐的"在 render 阶段同步派生状态"写法，单次 re-render 就能完成 reset，不会引发死循环。

