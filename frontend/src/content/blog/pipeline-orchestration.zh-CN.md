---
title: 不碰算法的那一层——流水线编排器
slug: pipeline-orchestration
date: 2026-06-23
category: 架构
tags: [流水线编排, DAG, 缓存, 子进程隔离, manifest, Task F]
summary: 前三篇都在走"数据的路"——一段声音怎么被拆、被听懂、被认人。这一篇换个视角，把镜头拉远，看那台把所有站一站站跑起来的机器：流水线编排器。它一行算法都不碰，却决定了整条链能不能复用、能不能断点续跑、崩一站会不会全完。聊聊它三个有点反直觉的设计——阶段即独立命令、跑在隔离子进程里、用一把"内容寻址"的缓存。
cover: /blog/pipeline-orchestration/fig-orchestrator-cover.svg
author: translip
readingTime: 14
---

# 不碰算法的那一层——流水线编排器

> 这是 **幕后 · 博客** 的第四篇，也是第一篇**架构**视角的。前三篇我们一路走"数据的路"：[把声音拆成两半](/blog/voice-background-separation)、[听懂还要分清是谁说的](/blog/speaker-attributed-transcription)、[从临时工号到稳定身份](/blog/speaker-registry)。这一篇把镜头拉远，看那台**把这些站一站站跑起来的机器**——流水线编排器（`src/translip/orchestration/`，项目内部叫它 **Task F**）。

## 先说它不是什么

前三站都在解决一个**算法**问题：分离、转写、认人。很自然会以为，把它们串成一条流水线，无非是写个 `main()`，依次 `import` 进来、按顺序调一遍函数。

translip 偏偏没这么做。它的编排器**一行算法都不碰**——它不知道什么是声纹、什么是 atempo，也从不在自己的进程里加载任何模型。它只干三件事：

1. **算出这次要跑哪些节点、按什么顺序**（解析 DAG）；
2. **挨个问一句"这一站上次跑过、还能用吗？"**（查缓存）；
3. **要跑的，就把对应的那条命令丢进一个隔离的子进程里去跑**（shell out）。

![编排器：一个不碰算法、只做调度的瘦指挥](/blog/pipeline-orchestration/fig-thin-conductor.svg)
*编排器在中间，左手解析 DAG、中间查缓存、右手把命令丢进子进程；任务逻辑（分离 / 转写 / 翻译 / 配音）全在子进程那一侧，编排器这边一点都没有。*

这套"把调度和算法彻底分开"的设计，带来三个有点反直觉、但每一个都很实在的好处。下面一个一个看。

## 反直觉之一：每一站，都是一条独立的命令

最关键的一个决定：**流水线的每个阶段，都是一条能单独在终端里敲出来的 CLI 命令**——`translip run` / `transcribe` / `translate-script` / …。它读几个输入文件（大多是 JSON + 音频），写几个输出文件，外加一份 `*-manifest.json`，然后**进程退出**。

阶段与阶段之间**只通过磁盘上的文件通信**，没有任何共享的内存对象。上一站写下 `segments.zh.json`，下一站把它当输入读进来——仅此而已。

![每一站都是一个吃文件、吐文件 + manifest 的独立命令](/blog/pipeline-orchestration/fig-stage-as-command.svg)
*阶段之间不传内存对象，只传磁盘上的文件。每一站读上游产物、写自己的产物 + 一份 manifest，然后退出。manifest 记下"我是用什么参数、跑出了哪些产物、成没成功"——它是缓存和报告的依据。*

所以编排器要做的，不过是把一个 `PipelineRequest` 里的参数，**摊平成一条命令行的 argv**。`commands.py` 里全是这种"翻译"：

```python
# commands.py —— 把一个阶段"摊平"成一条命令行
def build_task_c_command(request):
    return [
        *_cli_prefix(), "translate-script",                          # = python -m translip translate-script
        "--segments",    str(effective_task_a_segments_path(request)),  # 读：上游 task-a 的产物
        "--profiles",    str(task_b_profiles_path(request)),            # 读：上游 task-b 的产物
        "--output-dir",  str(request.output_root / "task-c"),           # 写：自己的产物
        "--target-lang", request.target_lang,
        "--backend",     request.translation_backend,                   # 一个后端开关
        # …其余参数同理
    ]
```

这条命令，**和你自己在终端里敲的 `uv run translip translate-script ...` 是同一份阶段代码**——单独跑某一站，和让流水线跑它，是同一段逻辑的两个入口。这一个决定，顺手换来了一堆好东西：

- **可单独跑、可调试**：任何一站都能脱离流水线，单独喂文件复现问题；
- **可缓存**：产物落在磁盘上、带 manifest，下次能直接复用（下一节细说）；
- **可替换后端**：把 `--backend` 从 `local-m2m100` 换成 `deepseek`，编排器和别的站**完全不用动**；
- **契约清晰**：每一站的输入输出，就是它读写的那几个文件，一目了然。

整条流水线跑完，磁盘上是这样一棵稳定的目录树——每一站一个目录，顶上几份全局报告：

```text
output-pipeline/<task>/
├── stage1/<stem>/{voice.wav, background.wav, manifest.json}
├── task-a/voice/{segments.zh.json, task-a-manifest.json}
├── task-b/voice/{speaker_profiles.json, …, task-b-manifest.json}
├── task-c/voice/{translation.<lang>.json, task-c-manifest.json}
├── task-d/voice/<speaker_id>/…
├── task-e/voice/{dub_voice.<lang>.wav, …, task-e-manifest.json}
├── logs/<node>.log                       # 每一站的子进程日志
└── pipeline-{manifest,report,status}.json  # 全局：清单 / 报告 / 实时状态
```

## 反直觉之二：跑在隔离的子进程里，而不是函数调用

既然每一站都是一条命令，编排器要"跑"它，自然就是**起一个子进程**——而不是在自己进程里 `import` 然后调函数。

这听起来很奢侈：起子进程有开销，传参要序列化，还得收集日志。为什么不图省事，直接在一个进程里把模型都加载好、顺次调用？

因为这条流水线要连着加载 **demucs、Whisper、ECAPA、TTS** 一堆重模型。如果它们都挤在同一个长命进程里：

- **内存只增不减**：每加载一个模型就吃一大块内存/显存，一条链跑下来越堆越高，谁都不肯先松手；
- **一崩全崩**：某一站段错误、或 OOM，会把整个进程连同前面已经跑完的成果一起带走；
- **依赖打架**：不同模型常常要互相冲突的库版本，硬塞进一个进程迟早出事。

子进程把这三件事一次性解决了：

![每一站跑在自己的进程组里：模型随进程退出而释放，崩溃被沙盒挡住](/blog/pipeline-orchestration/fig-subprocess-isolation.svg)
*编排器是个长命、轻量的父进程；每一站是一个短命、吃重模型的子进程。进程一退出，操作系统把它占的内存（含模型权重、显存 / MPS 缓冲）整个收回——下一站从一张干净的内存表开始。崩溃和取消都被关在子进程这个沙盒里。*

落到代码上，关键就两点：**自成进程组**地启动，于是**取消时能整组干净地杀掉**（连同模型起的子孙进程）：

```python
# subprocess_runner.py —— 每一站跑在自己的进程组里，可整组取消
process = subprocess.Popen(
    command, stdout=PIPE, stderr=STDOUT, text=True,
    start_new_session=(os.name != "nt"),   # 自成进程组（setsid）
)
# …一边把子进程 stdout 实时抄进 <output_root>/logs/<node>.log

# 取消时：先 SIGTERM 礼貌通知，5 秒不退，再 SIGKILL 强杀整组
os.killpg(process.pid, signal.SIGTERM)
#   process.wait(timeout=5) 超时 →
os.killpg(process.pid, signal.SIGKILL)
```

于是"重模型退出即释放""一站崩溃毒不到编排器""点一下取消能真的停下来"——这三件事都不是额外写出来的特性，而是**子进程隔离白送的**。编排器自己始终是个不吃模型、跑不崩的瘦壳。

## 反直觉之三：一把"内容寻址"的缓存

流水线最常见的诉求是：**改一个小参数，别从头全量重跑**。translip 的答案是给每一站算一个**缓存键（cache key）**——它不是随便的版本号，而是这一站**所有会影响产物的东西**的指纹。

缓存键 = SHA256( **这一站在乎的参数** + **它每个上游产物文件的内容指纹** )。上游文件的指纹，就是文件字节的 SHA256：

```python
# runner.py —— 上游产物的"内容指纹"：文件字节的 sha256
def _file_fingerprint(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "exists": path.exists(), "sha256": digest}

# task-c 的缓存 payload（节选）：自己的参数 + 上游的指纹一起进哈希
payload = {
    "translation_backend": request.translation_backend,         # 自己的开关
    "condense_mode":       request.condense_mode,
    "segments":  _file_fingerprint(effective_task_a_segments_path(request)),  # 上游 task-a 指纹
    "profiles":  _file_fingerprint(task_b_profiles_path(request)),            # 上游 task-b 指纹
}
# cache_key = sha256(json.dumps(payload, sort_keys=True))
```

有了键，"能不能复用"就是一道**四关都过才算命中**的判断：

```python
# cache.py —— 命中要同时满足四个条件，缺一不可
def is_stage_cache_hit(spec):
    if not spec.manifest_path.exists():                    # ① manifest 还在
        return False
    if not all(p.exists() for p in spec.artifact_paths):   # ② 产物文件都还在
        return False
    payload = json.loads(spec.manifest_path.read_text())
    if payload.get("status") != "succeeded":               # ③ 上次确实跑成功了
        return False
    return spec.previous_cache_key == spec.cache_key        # ④ 缓存键没变
```

![缓存键：参数 + 上游指纹 → 哈希 → 四关判定 → 复用或重算](/blog/pipeline-orchestration/fig-cache-key.svg)
*把"这一站在乎的参数"和"每个上游产物的内容指纹"一起喂进 SHA256，得到缓存键。命中要四关都过：manifest 在、产物都在、上次成功、键没变。任何一关不过，就重算这一站。*

这套"内容寻址"最漂亮的地方，是**失效会自动沿着 DAG 往下传**。因为每一站的键里都嵌了上游文件的指纹，**上游产物一变，下游的键就跟着变**，无需任何人手动声明"谁依赖谁要一起重算"：

![翻一个开关，失效只精准地沿 DAG 往下传](/blog/pipeline-orchestration/fig-invalidation-cascade.svg)
*把翻译后端从 local-m2m100 换成 deepseek：只有 task-c 的缓存键变了。它的新产物 translation.json 内容指纹随之改变，于是 task-d、task-e 的键也跟着失效、自动重算；而 stage1 / task-a / task-b 的键纹丝没动，整段命中、直接复用。*

所以你只要：

```bash
# 改一个后端开关，重跑——编排器自己算出"只有 task-c 往下要重算"
uv run translip run-pipeline --input ./drama-ep01.mp4 \
  --translation-backend deepseek --reuse-existing
```

编排器会复用 stage1 / task-a / task-b 的旧产物，**只重算 task-c 及其下游**。改一个 flag 精准地只动它影响到的那几站——这正是"改个 backend 就触发选择性重算"背后的机制。（想强制重算某一站，再加 `--force-stage task-x` 即可。）

## DAG 是怎么长出来的：节点 → 模板 → 拓扑排序

那"要跑哪些节点、按什么顺序"，编排器又是怎么算出来的？分三层，每层只管一件事。

**第一层，节点声明自己依赖谁。** `nodes.py` 是一张静态依赖表——每个节点只说"我要等谁跑完"，外加一个 `sequence_hint` 用来给"同时就绪"的节点定个稳定先后：

```python
# nodes.py —— 每个节点声明依赖（不关心别人怎么用它）
"task-c": WorkflowNodeDef("task-c", "audio-spine", ("task-a", "task-b"), 50),
"task-d": WorkflowNodeDef("task-d", "audio-spine", ("task-b", "task-c"), 70),
"task-e": WorkflowNodeDef("task-e", "audio-spine", ("stage1","task-a","task-c","task-d"), 80),
```

**第二层，模板挑选要跑哪些节点。** `templates.py` 定义了几套工作流——`asr-dub-basic`（最常用的 7 节点）、`asr-dub+ocr-subs`（加硬字幕 OCR）、`asr-dub+ocr-subs+erase`（再加字幕擦除）。模板只列出"我要这些节点"，依赖会自动补全。

**第三层，把它解析成一份可执行的计划。** `graph.py` 先**递归收集传递依赖**（你选了 task-e，它替你把 stage1/a/c/d 都拉进来），再做一次**拓扑排序**，同层用 `sequence_hint` 当小顶堆的键定先后：

```python
# graph.py —— 顺着依赖把传递闭包递归收齐
def _collect_nodes(template_id, node_name, selected):
    if node_name in selected:
        return
    selected.add(node_name)
    for dep in _template_dependencies(template_id, node_name):
        _collect_nodes(template_id, dep, selected)

# 再做拓扑排序；入度为 0 的就绪节点，用 sequence_hint 定稳定先后
ready = [(NODE_REGISTRY[n].sequence_hint, n) for n, deg in indegree.items() if deg == 0]
heapq.heapify(ready)
# …Kahn 算法逐个出队；若最后排不满，说明有环 → 直接报错
```

![一张静态依赖图，三套模板各点亮其中一个子图](/blog/pipeline-orchestration/fig-dag-resolve.svg)
*同一张节点依赖图，模板决定点亮哪些节点；graph 递归补全传递依赖、再拓扑排序，输出一条线性的执行顺序。换模板，只是点亮不同的子图——节点定义和依赖一行都不用改。*

注意这三层**各自只懂一件事**：节点不知道自己会被哪个模板选中，模板不关心依赖怎么补全，graph 不关心节点具体干什么。加一个新阶段，通常就是往 `nodes.py` 添一行依赖、往某个模板的节点表里加个名字——编排主循环一个字都不用改。

## 把它们串起来：编排主循环

三层 DAG 解析 + 一把缓存 + 子进程隔离，最后汇成 `runner.py` 里一段**朴素得有点意外**的主循环：

```python
# runner.py —— 编排器的全部"智能"，就这一段
for node_name in node_names:                 # 已拓扑排好序
    cache_spec = _node_cache_spec(request, node_name, previous_cache_keys)

    if request.reuse_existing and node_name not in force_stages and _is_node_cache_hit(cache_spec):
        monitor.complete_stage(node_name, status="cached")   # 命中：整站跳过
        continue

    monitor.start_stage(node_name)
    result = execute_node(node_name, request, monitor=monitor)   # 未命中：shell 到子进程
    monitor.complete_stage(node_name, status="succeeded")
```

`execute_node` 做的，就是前面说的：`build_*_command(request)` 拼出 argv，交给 `run_stage_command` 起子进程跑。**查缓存 → 命中跳过 / 未命中起子进程 → 记状态**，循环到底。编排器的"聪明"全在缓存键和 DAG 解析里，主循环本身直白得能一眼看完。

## 看得见的进度，与断点续跑

最后两件工程上的体面事。

**进度是加权的。** 各阶段轻重差很多——TTS（task-d）是最重的一站，分离、转写则轻得多。所以整体进度不是"跑完几站除以总站数"，而是**按权重加权求和**（权重在 `stages.py`）：

| 阶段 | stage1 | task-a | task-b | task-c | task-d | task-e |
| --- | --- | --- | --- | --- | --- | --- |
| 权重 | 0.10 | 0.10 | 0.10 | 0.15 | **0.35** | 0.20 |

```python
# monitor.py —— 整体进度 = 各阶段进度 × 各自权重，求和
def _overall_progress(self):
    total = 0.0
    for stage in self._item_order:
        st = self._stages.get(stage)
        if st:
            total += self._item_weights[stage] * (st.progress_percent / 100.0)
    return total * 100.0
```

这个加权进度，连同每一站的状态，被**心跳式地写进 `pipeline-status.json`**——前面几篇你在管理界面上看到的那条进度条、那个"当前在跑 task-d"，读的就是这份文件：

```json
{ "status": "running", "overall_progress_percent": 62.5, "current_stage": "task-d",
  "stages": [ {"stage_name": "stage1", "status": "succeeded", "progress_percent": 100},
              {"stage_name": "task-d", "status": "running",   "progress_percent": 40} ] }
```

**断点续跑，是缓存的免费副产品。** "续跑"不需要单独的机制：开了 `--reuse-existing`，编排器就从上一次的 manifest 里读回各站的缓存键，跑到哪、哪些还能复用，全凭缓存判定。中途崩在第 5 站，修好再跑，前 4 站直接命中，从第 5 站接着来：

```python
# runner.py —— 续跑：从上次的 manifest 读回缓存键；force_stages 强制重算
previous_cache_keys = _previous_stage_cache_keys(request.output_root) if request.reuse_existing else {}
force_stages = set(request.force_stages or [])
```

还有个细节照顾到了**非关键节点**：像字幕擦除这种"锦上添花"的站，即便失败也不该让整条链报废。所以 `required=False` 的节点崩了，编排器记一笔 `optional_failures`、把整体状态标成 **partial_success**，继续往下跑——而关键站（分离 / 转写 / 配音）一旦失败则立刻中止，绝不带病出片。

## 几个"为什么这么做"

把这一层的取舍收拢一下：

- **阶段做成独立命令、只走磁盘**：换来可单独跑、可缓存、可调试、可替换后端；阶段间的契约就是那几个文件，清清楚楚。
- **跑在隔离子进程里**：重模型退出即释放、一站崩溃毒不到编排器、点取消能真的停——三件事都是隔离白送的，不是额外写的。
- **缓存用"内容寻址"**：键里嵌上游文件指纹，失效自动沿 DAG 下传；改哪一站的参数，就精准只重算它下游，跨 run 复用。
- **DAG 分三层、各懂一件事**：节点声明依赖、模板挑节点、graph 解析顺序；加一站基本不动主循环。
- **编排器不碰算法**：调度和算法彻底解耦——算法怎么演进，编排不用动；编排怎么演进，算法也不用动。

## 小结

这一层不处理一个采样点、不认识一条声纹，却决定了整条流水线**作为一个工程产品**好不好用：能不能改个参数就增量重跑、崩一站会不会全完、跑到一半能不能续上、那条进度条准不准。它把前三篇讲的算法，组织成了一台可重复、可恢复、可调试的机器——而它自己，始终是个不碰算法的瘦指挥。

说完了这台机器在**命令行**世界里怎么转，下一篇架构我们把它搬进**控制面**：FastAPI 怎么用两个守护线程把一次 `run-pipeline` 包成一个后台任务、把 `pipeline-status.json` 的心跳通过 SSE 实时推到浏览器，以及那套和流水线正交的 atomic-tools 作业系统。之后，我们再回到算法线，继续 **Task C：翻译**。
