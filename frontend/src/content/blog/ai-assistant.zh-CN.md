---
title: 把一句话变成一条调用链——会编排原子能力的 AI 助手
slug: ai-assistant
date: 2026-06-23
category: 架构
tags: [AI 助手, 原子能力编排, DeepSeek, 调用链, Binding, 多轮对话]
summary: 上一篇讲的流水线编排器，跑的是一条"预先排好"的固定链路。这一篇聊它的另一面——你随口说一句"把这个视频配成英文配音"，由一位 AI 助手现场把它编排成一条 分离 → 转写 → 翻译 → 合成 → 回贴 的原子能力调用链。我们把镜头拉到代码里：规划器怎么把工具目录塞给 DeepSeek、为什么模型给的 JSON 落地前要先过一道校验、产物又是靠一个"产物即文件"的关键真相自动接力的，以及它怎么记得"刚才那个结果"、和那条"只有规划上云、媒体不出本地"的底线。
cover: /blog/ai-assistant/fig-assistant-cover.svg
author: translip
readingTime: 17
---

# 把一句话变成一条调用链——会编排原子能力的 AI 助手

> 这是 **幕后 · 博客** 的一篇**架构**。上一篇[不碰算法的流水线编排器](/blog/pipeline-orchestration)，讲的是一条**预先排好**的固定链路；这一篇聊它的另一面——你随口说一句话，由 AI 助手**现场**把它编排成一条原子能力调用链。同样是"编排"，一个是套餐，一个是你点菜、它替你点单。这次我们多往代码里走几步。

## 先分清：套餐、零件、和点单的人

translip 里其实有三层"干活"的东西，容易混，先掰开。

**套餐，是流水线。** 上一篇讲的编排器跑的就是它——一条 `separation → transcription → … → render` 预先排好的固定链路，适合"标准配音"这种成熟、稳定的流程。你给一个视频，它从头跑到尾。

**零件，是原子工具。** 这是和流水线**正交**的另一套系统：十几个**各干一件小事**的独立工具，等着被自由组合。它们到底有哪些，不是写在文档里给人看的，而是有一份**机器可读的目录**——这个目录后面是主角，先记住它叫 `catalog`。

**点单的人，就是这篇的主角——AI 助手。** 它站在"原子工具"这一侧，干的事只有一件：**把你一句自然语言，编排成一条原子工具的调用链**。你说「把这个视频配成英文配音」，它知道这背后是 分离 → 转写 → 翻译 → 合成 → 回贴，五步，缺一不可——然后替你把这五步排好、串好、跑完。

它一个采样点都不处理，一行配音算法都不碰。和流水线编排器一样，它只负责**调度**；真正干活的，永远是底下那些既有的本地能力。区别只在于：流水线的链是写死的，助手的链是**临时、按你这句话现编的**。

## 第一步：把一句话，变成一份结构化的计划

你在对话框里打的那句话，发到后端的 `/plan`。规划这一步交给 DeepSeek，但喂给它的东西很讲究。

**先喂一份目录。** 规划器（`planner.py`）不会让模型"凭印象"猜有哪些工具，而是把那份机器可读的 `catalog` 作为系统提示的一部分塞进去。这份目录不是手写维护的——它是从每个原子工具的 **Pydantic 请求模型自动推导**出来的：每个工具有哪些参数、什么类型、有没有默认值、枚举可选值是什么、哪些参数是**文件输入**、它产出哪些**有名字的产物**……全是从 schema 现算的。

```python
# catalog.py —— 目录里每个工具，参数从 schema 推、产物在这儿登记
"transcription": ToolCatalogEntry(
    TranscriptionToolRequest,                       # 参数（名/类型/默认/枚举）从这个模型自动推
    {"segments_file": "转写分段 JSON（含时间轴与文本）",  # ← 下游可以 bind 的"有名字的产物"
     "srt_file":      "转写字幕 SRT"},
),
```

为什么这么较真？因为"工具有哪些参数"只有一个**真实来源**——那个请求模型。手抄一份给提示词，迟早和代码漂移。让目录从 schema 现生成，模型看到的就永远是工具**当下真实**的样子。

**再给一套规则，让它只能吐 JSON。** 系统提示里写死了几条硬规矩：只输出一个 JSON 对象、不要 markdown；文件参数（`file_id`、`*_file_id`）必须放进 `inputs` 用 binding 指定来源、其余参数放 `params`；上一步的产物用 `source="step" + step_id + output` 绑定，而 `output` **必须是那个工具目录里真实存在的产物键**。调用大模型时 `temperature: 0`、`response_format` 锁成 `json_object`——要的是**确定、可解析**，不是创意。

提示里甚至**嵌了一个真实的范例**，让模型照着学。这就是一份"计划"长什么样：

```json
// planner.py 系统提示里给模型的样例：「把视频里的日语台词转成中文字幕」
{
  "summary": "我会先分离出人声，再做日语语音转写，最后用 DeepSeek 翻译成中文字幕。",
  "steps": [
    {"id":"sep","tool_id":"separation","title":"人声分离","params":{},
     "inputs":{"file_id":{"source":"upload","upload_index":0}}},
    {"id":"asr","tool_id":"transcription","title":"日语转写","params":{"language":"ja"},
     "inputs":{"file_id":{"source":"step","step_id":"sep","output":"voice_file"}}},
    {"id":"mt","tool_id":"translation","title":"翻译为中文","params":{"source_lang":"ja","target_lang":"zh","backend":"deepseek"},
     "inputs":{"file_id":{"source":"step","step_id":"asr","output":"segments_file"}}}
  ],
  "edges": [ {"source":"sep","target":"asr"}, {"source":"asr","target":"mt"} ]
}
```

看那个 `asr` 步：它的 `file_id` 不是路径，是一条 binding——`source="step"`、来自 `sep` 这一步的 `voice_file` 产物。整条链，就是用这种 binding 把一步接一步。`edges` 把先后画成一张**有向图**（DAG）；多数时候是直链，但"既配音又烧字幕"就会分叉，用图表达比硬掰成一条线**诚实**。

![规划这一跳：把目录+历史+可用文件喂给模型，要回一个 JSON，再过校验，最后才成计划或澄清](/blog/ai-assistant/fig-plan-loop.svg)
*规划器把"从 schema 现生成的工具目录""对话历史""可用文件列表"一起喂给 DeepSeek（temperature 0、强制 JSON），模型回一个 JSON 对象；这个对象先过一道校验，才落地成一份计划，或一个澄清问题。*

## 不轻信模型：计划落地前，先过一道校验

这是我最想强调的一处工程克制：**模型给的 JSON，不是直接拿来跑的**。`parse_planner_response` 把它接住后，要先过 `_validate_plan` 一道关——你可以把它当成"对大模型输出的类型检查"：

```python
# planner.py —— 把模型输出当"不可信的草稿"严格校验
def _validate_plan(plan):
    seen = set()
    for step in plan.steps:
        if step.tool_id not in TOOL_REGISTRY:          # ① 工具必须真实存在
            raise ValueError(f"未知工具：{step.tool_id}")
        if step.id in seen:                            # ② 步骤 id 不能重复
            raise ValueError(f"步骤 id 重复：{step.id}")
        seen.add(step.id)
        valid = model_field_names(step.tool_id)        # ③ 参数/输入必须是这个工具真有的字段
        for key in step.params:
            if key not in valid or is_file_param(key):     #    且 params 里不能塞文件参数
                raise ValueError(f"{step.tool_id} 不支持参数：{key}")
        for key in step.inputs:
            if key not in valid or not is_file_param(key):  #   inputs 里只能是文件参数
                raise ValueError(f"{step.tool_id} 不支持文件输入：{key}")
        for name, binding in step.inputs.items():
            if binding.source == "step" and binding.step_id not in seen:   # ④ 只能引用"已出现的上游步骤"
                raise ValueError(f"输入 {name} 引用了未定义/靠后的步骤")
```

这一关挡住的，正是大模型最容易犯的几类错：编一个不存在的工具、把参数名拼错、让第 2 步去引用第 5 步的产物（一个还没跑的东西）。第 ④ 条尤其关键——它顺手保证了**步骤顺序在拓扑上成立**：你只能绑定**前面**出现过的步骤。

还有一个体贴的小动作：如果模型偷懒没给 `edges`，规划器**自己从 binding 反推**——谁的输入绑了谁的输出，就连一条边。所以那张 DAG，本质就是 binding 关系的另一种写法：

```python
# 模型没画连线？那就从"谁绑了谁"反推出来
def _derive_edges(plan):
    return [StepEdge(source=b.step_id, target=step.id)
            for step in plan.steps
            for b in step.inputs.values()
            if b.source == "step" and b.step_id]
```

把规划交给模型、把**校验**留给自己——这是整套设计里"既用 LLM、又不被 LLM 拖下水"的关键一笔。

## 一个有意思的岔路：它可能先反问你

但如果你那句话本身就**没说清**呢？「给这个视频配音」——配成哪国语言，你没讲。

提示里专门留了规则：信息不足时（需要文件却没上传、目标语言/方向不明、需求太宽泛）——**不要硬猜**，而是回一个澄清对象。于是 `/plan` 的返回，可能根本不是计划：

```ts
// /plan 的返回，可能是一份计划，也可能是一个澄清问题
interface PlanResult {
  type: 'plan' | 'clarification'
  plan?: AssistantPlan | null
  clarification?: Clarification | null  // { question: string; options: string[] }
}
```

走到 `clarification` 这条路，它回你的就是一句反问——"配成哪种语言？"——下面挂着中 / 英 / 日几个选项气泡。背后的判断很朴素：**一个会编排的助手，最怕的不是不会干，是会错意。** 你想要中文配音，它默默跑了一版英文——二十分钟、几个重模型的算力，就没了。"先问一句"虽然多一次来回，挡住的却是"自信地跑错"。

## 计划不是黑箱：它摊开给你改

第二道闸，是计划**可编辑**。

校验通过的那份计划，不是个一点就跑的黑箱，而是**摊在你面前的一排可视化卡片**：每张卡片就是一个步骤——用什么工具、吃什么输入、参数多少、为什么需要它（那句 `rationale`）。执行前，你可以逐步改参数、调顺序，甚至加一步删一步。比如它排好了配音，你临时想"再加上把字幕烧进去"，直接在尾巴上追一步。

所以这是**"AI 起草、你定稿"**：规划交给模型，但**拍板权在你**。它和"先反问"是一对——前面用澄清挡住误解，这里用可编辑计划兜住"模型偶尔排得不够好"。两道闸，都是为了让你别在跑了半天之后，才发现方向错了。

## 产物怎么接上的：Binding，和一个关键真相

回到那条链。第一步分离出人声，第二步转写要拿它当输入——这个"产物的传递"，落到运行时到底是怎么发生的？

先看计划里的表达：每一步的 `inputs`，值是一条 `Binding`，说清"我这个输入从哪来"：

```ts
interface Binding {
  source: 'upload' | 'step'  // 来自你最初的上传，或某个前置步骤的产物
  upload_index?: number      // source=upload：第几个可用文件
  step_id?: string           // source=step：来自哪一步
  output?: string            // source=step：要那一步的哪个"有名字的产物"
}
```

但真正让链能接上的，是执行器里一个**关键真相**：

> **原子工具的产物，本身就是一个有 `file_id` 的存储文件**（和你上传的文件同一种东西）。作业系统在校验/物化文件时，对"上传"和"产物"一视同仁。

所以"把上一步的输出喂给下一步"，落地后**根本没有什么特殊机制**——不过是把**上一步那个产物文件的 `file_id`**，当成下一步的 `*_file_id` 参数传进去而已。运行时解析一条 `source="step"` 的 binding，就是这么三步：

```python
# executor.py（精简）—— 把一条 step-binding 解析成一个具体的 file_id
def _resolve_step_output(self, step, binding, completed_jobs):
    job_id = completed_jobs[binding.step_id]              # 上游步骤跑出来的那个 job
    artifacts = self.job_manager.list_artifacts(job_id)  # 它产出的文件们
    target = self.job_manager.get_job_result(job_id)[binding.output]  # output 键 → 产物文件名
    for a in artifacts:
        if a.filename == target:
            return a.file_id                             # ← 下一步要的，就是这个 file_id
```

![运行时的接力：上一步的产物是带 file_id 的文件，下一步的 *_file_id 就填这个 file_id](/blog/ai-assistant/fig-binding-runtime.svg)
*一条 step-binding 在运行时被解析成一个具体的 file_id：上游步骤是一个原子任务，它的产物是带 file_id 的存储文件；执行器把这个 file_id 当作下游任务的 `*_file_id` 参数传进去。"产物即文件"这一条，让接力不需要任何额外机制。*

这层抽象最舒服的地方是：作为用户，你**全程没碰过一个文件**——中间产物叫什么、`file_id` 是什么、谁喂给谁，全被 binding 这层引线吃掉了。最后所有中间产物加最终成片，都能一键下载，一个都没丢。你只看到"目标进、成片出"。

（顺带一个细节：如果某一步只有**唯一一个产物**，binding 里连 `output` 都能省——执行器直接拿那唯一的产物；但只要它有**多个产物**，就必须显式写明要哪个，免得接错。）

## 执行：每一步是一个原子任务，且和手动任务同跑一条路

确认计划后，它发到 `/execute`，执行器（`executor.py`）按顺序一步步跑。这里有几处和流水线编排器同源的克制：

**它没有另起一套执行引擎。** 每一步就是一次普通的原子工具作业：`job_manager.create_job(tool_id, params)`，然后调**同一个**同步 worker `_execute_job_sync` 把它跑完——这正是手动点一个原子工具时走的那条路。于是助手的每一步，和你手动跑的单个工具，**共享同一套并发与"重模型串行"的闸**：两个多 GB 的模型（视觉 / 擦除 / 分离）不会同时挤上来，助手任务也不会和你手动开的任务互相踩踏。

**它把"已完成步骤 → job_id"记在手边**，下游 binding 才解析得动：

```python
# executor.py（精简）—— 顺序跑，边跑边记下每步的 job，供下游接力
completed_jobs = {}                       # step_id -> 完成的 atomic job_id
for step in plan.steps:
    if cancel_event.is_set(): ...return   # 步骤之间检查取消
    params = self._resolve_params(step, upload_file_ids, completed_jobs)  # 解析 binding
    job = self.job_manager.create_job(step.tool_id, params)
    self.job_manager._execute_job_sync(job.job_id)        # 阻塞到这步跑完
    if get_job(job.job_id).status != "completed": ...fail # 一步失败，整条运行失败/取消
    completed_jobs[step.id] = job.job_id                  # 记下，给下游绑定用
```

**取消是真的能停。** 每次运行配一个 `threading.Event`，点取消时把它一置位、再把当前在跑的那个原子 job 取消掉；循环在每步之间都查一眼这个信号。

**进度是直接读底层 job 的。** 你在界面上看到的每步进度、日志、产物，不是助手另存的一份，而是运行状态组装时**实时回查那个 job 的明细**——所以进度条是真在动，哪步错了错误信息就单独挂在哪步上，不会糊成一团。

## 多轮：它怎么记得"刚才那个结果"

你常会接着上一轮说话：「再把刚才那个结果配上字幕」「换成日语再来一份」。助手能接住，靠两样东西一起喂给规划器。

一是**对话历史**：之前每一轮的 user/assistant 消息，原样作为前文塞回去，模型据此理解指代和"在上次基础上调整"。

二是**可用文件列表**：它不只含你这一轮上传的文件，还含**本会话之前每次运行产出的产物**——它们和上传一样，都是带 `file_id` 的文件，在列表里用 `upload_index` 引用。所以"刚才那个成片"对模型来说，就是可用文件里的某一项，它照样能 `source="upload"` 绑进新计划。规划提示里专门写了这条规则：「刚才/上次/那个结果」通常指最近一次运行的产物，去可用文件里挑对应项。

于是"多轮"不是一个独立的对话系统，而是**把历史和产物池一起喂进同一个规划器**——重新规划一次而已。

## 跑完不丢：沉淀成一条「AI 任务」

每一次规划 + 执行，都会落库成一条 **AssistantRun**——也就是界面上的「AI 任务」。它和流水线任务、原子任务，是任务中心里**平级的三类记录**，只是多了一层来历："它是被一句话派生出来的"。后端给它配了完整生命周期：

```text
POST /assistant/plan              一句话 → 计划 / 或澄清问题
POST /assistant/execute           执行计划，起一次运行（后台线程）
GET  /assistant/runs              AI 任务列表（可按状态/关键词筛）
GET  /assistant/runs/{id}         实时状态（回查每步底层 job）
POST /assistant/runs/{id}/cancel  取消（置信号 + 取消在跑的 job）
POST /assistant/runs/{id}/rerun   用同一份计划再起一次运行
DELETE /assistant/runs/{id}       删记录（底层原子作业/产物归原子系统所有，保留）
```

注意 `rerun` 和 `delete` 的边界感：重跑是拿**存下来的那份计划**重新起一次；删除只删"AI 任务"这条编排记录，底层那些原子作业和产物，归原子工具系统所有，**留着不动**。聊天是入口，但每一次"聊"的背后，是一次可追溯、可复跑的运行。

## 边界与那条底线

最后说清楚它的边界——尤其有一条，关乎你的素材会不会被传走。

**第一，它要配 `DEEPSEEK_API_KEY` 才会规划**，没有离线兜底；把"一句话拆成调用链"这件事交给云端大模型，没配 key 就罢工。

**第二，也是那条底线：只有"规划"这一步会上云。** 发给 DeepSeek 的，**仅仅是你那句话、对话历史、和那份工具目录**——你的媒体内容，视频、音频，**不出本地**。所有真正干活的原子能力，分离、转写、翻译、合成、擦除、视觉感知，全在你机器上跑。云端只参与"排个计划"，一帧画面、一段声音都不经过它。

**第三，它只会编排已经存在的东西。** 校验那一关已经保证了：计划里每个工具都得在注册表里真实存在。模型不会凭空变出一个仓库没有的能力；它偶尔把计划排得不够好、或会错意——所以前面那两道闸（**先反问澄清**、**计划可编辑**）才是必需品，不是装饰。

## 几个「为什么这么做」

把这一层的取舍收拢一下：

- **目录从 schema 现生成**：工具有哪些参数只有一个真实来源（请求模型），让模型看到的永远是当下真实的样子，不和代码漂移。
- **规划交给模型、校验留给自己**：DeepSeek 出结构化 JSON，但落地前严格校验（工具存在、参数合法、只能绑前面的步骤）、缺了连线就从 binding 反推——既用 LLM，又不被它的幻觉拖下水。
- **两道闸挡住"会错意"**：信息不足先反问、计划永远可编辑，让你别跑到一半才发现方向错。
- **"产物即文件"**：原子产物本身就是带 `file_id` 的文件，接力只是把上一步的 `file_id` 当下一步的 `*_file_id`，不需要任何特殊管道；用户全程不碰文件。
- **复用既有作业系统**：每步就是一个原子作业，走同一个同步 worker、共享同一套并发与重模型串行的闸，助手任务和手动任务安全共存。
- **本地干活、只有规划上云**：媒体内容不出本地，是写进设计里的底线。

## 小结

这位 AI 助手，做的是一件很"产品"、也很"架构"的事：把一句模糊的人话，落成一条**你能看、能改、能复跑**的原子能力调用链——它把工具目录从 schema 现喂给模型、把模型的输出当不可信草稿严格校验、用"产物即文件"让步骤自动接力、再复用既有作业系统把每一步安全跑完，最后沉淀成一条带履历的 AI 任务。而它自己，始终是个不碰算法、只负责把活儿派明白的"会编排的同事"。

它和上一篇的流水线编排器，是同一种克制的两个面：一个把固定流程编排成一台可恢复的机器，一个把自由组合编排成一句话就能用的对话。下一篇，我们回到算法线，继续 **Task C：翻译**——看一段转写好的文字，是怎么被"看着画面、记着是谁说的"翻成另一种语言的。
