---
title: 从临时工号到稳定身份——声纹画像与说话人注册表
slug: speaker-registry
date: 2026-06-16
category: 算法
tags: [说话人识别, 声纹, ECAPA, 注册表, 在线学习, 流水线]
summary: 上一篇给每句话标了 SPEAKER_00 / 01，但那只是本片段内的临时编号——它不知道"01 号"在下一集是谁。这一站要把这些临时工号，变成跨片段、跨整部作品都稳定的身份：给每个人画一张声纹像，在一本会"记事"的注册表里认人，让同一个角色自始至终是同一个人。
cover: /blog/speaker-registry/fig-voiceprint-space.png
author: translip
readingTime: 14
---

# 从临时工号到稳定身份——声纹画像与说话人注册表

> 这是 **幕后 · 博客** 的第三篇。[上一篇](/blog/speaker-attributed-transcription) 我们让每句话都带上了 `SPEAKER_00` / `SPEAKER_01` 的标注；这一篇顺着这些标号往下走，到流水线的第三站：**说话人注册表**（`speaker-registry` / CLI 的 `build-speaker-registry`）。

## 临时工号的问题

上一站的 `SPEAKER_00` / `SPEAKER_01` 解决了"这句和那句是不是同一个人"——但它是**本片段内的相对编号**。换一个片段、换一集，编号会**重新洗牌**：

- 第 1 集里男主角可能是 `SPEAKER_00`，第 2 集里他也许成了 `SPEAKER_02`；
- 把一部剧切成很多段并行处理，每段的 `SPEAKER_00` 互不相干；
- 甚至同一段里，如果重跑一次、聚类顺序变了，编号也可能不一样。

可下游偏偏需要**绝对身份**。配音（Task D）要给"男主角"始终分配**同一个音色**——如果他每集换一把嗓子，成片就毁了。所以这一站要回答的不再是"谁，在这一段里"，而是：

> **这个声音，在整部作品、跨所有片段里，到底是哪一位？**

这是一个**身份**问题，第一次和信号处理无关。translip 的答案分三步：给每个人**画一张声纹像**、在一本**注册表**里**认人**、并让这本注册表**越用越准**。

![声纹在向量空间里按人聚成簇](/blog/speaker-registry/fig-voiceprint-space.png)
*把每段语音用 ECAPA 编码成一个向量，同一个人的向量自然聚成一簇、不同人分得开。"认人"就是把一簇新声纹，匹配到注册表里已有的某个人（图中的 ✕ 是各人的原型）。（示意：高维向量的二维投影）*

最终落到磁盘上的，是一本注册表 `speaker_registry.json`，核心是一个 `speakers` 数组，每个人长这样：

```json
{
  "speaker_id": "spk_0000",
  "display_name": "spk_0000",
  "status": "confirmed",
  "aliases": [],
  "prototype_embedding": [ /* 192 维归一化声纹（原型） */ ],
  "exemplar_embeddings": [ [...], [...] ],
  "reference_clips": ["registry_clips/spk_0000/clip_0001.wav"],
  "created_at": "…", "updated_at": "…"
}
```

`spk_0000` 这种 ID 是**全局稳定**的——它不属于任何一个片段，而属于这本注册表。

## 第一步：给每个人画一张"声纹像"

Task B 吃两样东西：上一站的 `segments.zh.json`（带 `SPEAKER_xx` 标注）和那条干净的 `voice.wav`。第一件事，是把每个本地标号变成一张稳定的声纹画像。

![从分散的句子到一张鲁棒的声纹原型](/blog/speaker-registry/fig-profile-prototype.svg)
*按本地标号归集句子 → 挑出几段最干净的参考语音 → 各提一个 ECAPA 声纹 → 聚成一个抗污染的"原型"。*

**1. 挑参考片段。** 不是这个人的每句话都适合做声纹样本——太短的不稳、太长的没必要。所以先把相邻的句子（间隔 ≤0.6s）并成组，只留 **1.5–15 秒**的，再**按"时长 + 响度"排序取前 5 段**：

```python
# reference.py —— 优先长而清晰的片段当声纹样本
MIN_REFERENCE_SEC, MAX_REFERENCE_SEC, MAX_REFERENCE_CLIPS = 1.5, 15.0, 5
ranked = sorted(candidates, key=lambda c: (c.duration, c.rms), reverse=True)
return ranked[:MAX_REFERENCE_CLIPS]
```

**2. 各提一个 ECAPA 声纹。** 用的还是上一篇说话人分离同款的 speechbrain `spkrec-ecapa-voxceleb`，把每段参考语音编码成一个 192 维归一化向量。

**3. 聚成一个"原型"——但不是简单平均。** 这是这一步最关键的设计。如果某段参考片段里混进了噪声、或聚类时把别人的话误并了进来，**裸平均**会被这一条带偏。所以 translip 用一个**抗污染的中心**：先找到与其他最像的那一条当"中心"，**剔除掉和它余弦相似度 < 0.6 的离群**，再对留下的求平均：

```python
# profile.py —— 原型 = 中心 + 剔除离群 + 再归一化平均
sims = matrix @ matrix.T
center = matrix[int(np.argmax(sims.mean(axis=1)))]      # 与其余最像的那条 = 中心
keep = [e for e in matrix if np.dot(center, e) >= 0.6]  # 丢掉离群（可能是噪声/串音）
prototype = normalize_embedding(np.stack(keep).mean(axis=0))
```

一个人因此被压缩成一组**范例（exemplars）**加一个**原型（prototype）**——既保留了他声音的多样性，又有一个稳定的代表点。

## 第二步：在注册表里"认人"

有了画像，就去注册表里对号入座。这本质是一个 **1:N 识别**问题：把这张新画像，和注册表里 N 个已知的人逐一比对，看它最像谁、有多像。

![把画像匹配到注册表：得分 + 与次优的间距 → 三种判决](/blog/speaker-registry/fig-matching-decision.svg)
*每个画像对注册表里每个人算一个相似度，再按"是否够像最优 + 是否明显比次优更像"落进三个去向之一。*

**一个人 = 一组范例，匹配取最大。** 比对时不是只看原型，而是和这个人的原型**以及每一条范例**都算余弦，**取最大**——只要和他"任何一种状态"够像，就算像。这样能容忍同一个人不同情绪、不同语速下的声音变化：

```python
# registry.py —— 和原型或任一范例够像，就算像
def _speaker_score(profile_embedding, speaker):
    scores = [_cosine(profile_embedding, speaker["prototype_embedding"])]
    scores += [_cosine(profile_embedding, ex) for ex in speaker["exemplar_embeddings"]]
    return max(scores)
```

**判决要过两道关。** 光"够像最优"还不够——如果注册表里有两个人都挺像，认成谁都很危险。所以还要求最优**明显比次优更像**（间距 ≥ 0.05），否则只标"待复核"：

```python
# registry.py —— 不只要够像最优，还要明显甩开次优
decision = (
    "matched"     if best >= matched_threshold and (best - second) >= 0.05
    else "review" if best >= review_threshold
    else "new_speaker"
)
```

三种判决：**matched**（认领成功）、**review**（像、但不够有把握，留给人工复核）、**new_speaker**（谁都不像，是个新人）。

> **自适应阈值：注册表越拥挤，门槛抬得越高。** 0.55 / 0.35 只是地板价。如果注册表里已有的人**彼此就很像**（声音接近、容易混），固定阈值就太松了。所以 translip 先算一遍"已有原型两两之间的最大相似度"当 `floor`，再把门槛抬到 `floor + 0.15`——**已知声音越挤，认领越谨慎**，避免把张三误认成李四。

```python
# registry.py —— 用注册表自身的"拥挤度"动态抬高门槛
def _decision_thresholds(speakers):
    floor = _registry_similarity_floor(speakers)   # 已有原型两两最大相似度
    return max(0.55, floor + 0.15), max(0.35, floor + 0.05)   # matched, review
```

## 第三步：让注册表"记住"，并越用越准

匹配本身是只读的——加不加 `--update-registry`，决定这本注册表是"一次性比对"还是"会成长的记忆"。开启后：

- **认领成功**：把这条新声纹**并进**那个人的范例里（上限 12 条，只留最近的），**原型重算**。于是注册表每见这个人一次，画像就更准一点——这是一种朴素的**在线学习**。
- **是个新人**：铸一个新的 `spk_NNNN`，把画像和参考片段存进去，纳入注册表。

```python
# registry.py —— 认领成功后并入新范例，原型重算（范例上限 12）
exemplars.append(new_embedding)
exemplars = exemplars[-MAX_EXEMPLARS:]                       # 只保留最近 12 条
prototype = normalize_embedding(np.stack(exemplars).mean(axis=0))
```

![注册表是唯一跨 run 持久、且越用越准的记忆](/blog/speaker-registry/fig-registry-memory.svg)
*第一次见到某人 → 铸 spk_0000；之后再遇到 → 认领并把新声纹并进去，画像随之收紧。注册表是流水线里唯一有状态、会成长的部件。*

这本注册表，是整条流水线里**唯一有状态、跨 run 持久**的部件。前面每一站都是"读文件→写文件"的纯函数，唯独它**记事**——把它指向一个固定路径（`--registry`），就能让一部剧的所有片段、甚至跨季，共享同一套人物身份。

几个边角也照顾到了：

- **冷启动**：第一次跑、注册表是空的，于是人人都是 `new_speaker`——这很正常，它就是在 bootstrap 这部作品的人物表。
- **`non_cloneable`（人在环中）**：如果你在说话人复核里手动标了某个说话人"不要克隆"（比如那其实是背景人声、或不该被配音的声音），Task B 会尊重这个决定——把它的声纹清空、不参与匹配，绝不为它建身份。
- **一个默认值差异**（和上一篇的"分离开关"异曲同工）：**完整流水线**里 `update_registry` 默认**开**（边跑边攒身份）；单独跑 `build-speaker-registry` 时默认**关**，要显式加 `--update-registry` 才会写回——避免一次试跑就污染了你精心维护的注册表。

## 一次 `build-speaker-registry` 的完整流程

串起来，一次 Task B 是这样流动的：

![Task B 端到端流程](/blog/speaker-registry/fig-task-b-flow.svg)
*从带本地标号的转写 + 干净人声，到一本带稳定身份的注册表，外加每个画像的认领结果。*

落到磁盘上的产物契约：

```text
output-speakers/example/
├── speaker_profiles.json    # 本片每个人的声纹画像 + 参考片段
├── speaker_matches.json     # 每个画像 → matched / review / new_speaker
├── speaker_registry.json    # 注册表快照（认领/更新后的状态）
├── reference_clips/         # 抠出的参考语音 WAV（profile_XXXX/clip_YYYY.wav）
└── speaker-registry-manifest.json     # 后端 / 设备 / 画像数 / 注册表人数 / 各判决计数
```

一个最小调用（吃上两站的产物，并写回一本"这部剧"的注册表）：

```bash
uv run translip build-speaker-registry \
  --segments ./output-transcribe/example/segments.zh.json \
  --audio ./output-separation/example/voice.wav \
  --registry ./my-show/speaker_registry.json \
  --update-registry --top-k 3 \
  --output-dir ./output-speakers
```

## 为什么这一步重要

身份不是为了好看——它是下游一切"角色一致性"的根。看一眼这张匹配结果如何决定判决，就明白它的分量：

![三个画像的匹配得分与判决](/blog/speaker-registry/fig-match-scores.png)
*三个画像对注册表各人的相似度：A 明显认领某人（高分 + 甩开次优）；B 两个候选咬得很近 → 落进 review；C 谁都不像 → 是新人。*

往下游看：

- **配音（Task D）强制要求 `speaker_id`**——没有稳定身份它根本不知道这句该用谁的嗓子。它按 `speaker_id` 取出该角色的所有台词，再用 Task B 攒下的**参考片段 / 声音库**去**克隆**那个人的音色。
- `build-voice-bank` 进一步把 Task B 的画像沉淀成一套**可复用的声音参考库**，让"男主角"的音色能跨集、甚至跨作品复用。

一句话：**Task B 把"谁"钉死，Task D 才能让"谁"始终用同一把嗓子说话。**

## 几个"为什么这么做"

把这一站的取舍收拢一下：

- **原型用"中心 + 剔除离群 + 再平均"而非裸平均**：一段被污染的参考片段不该带偏整张声纹像。
- **一个人 = 一组范例，匹配取最大**：容忍同一个人不同状态下的声音变化，比"压成一个点"更鲁棒。
- **判决要"甩开次优" + 自适应阈值**：宁可标 review 也不乱认；注册表越拥挤、门槛抬得越高，专防张冠李戴。
- **默认只读、显式才写回**：单独跑不污染注册表；完整流水线才边跑边攒。`non_cloneable` 把人工判断放在机器之上。
- **注册表是唯一的持久状态**：指向固定路径就能跨片段/跨季共享人物身份——这正是"同一角色同一音色"的地基。

## 小结

Task B 把上一站的临时工号，钉成了跨片段稳定的身份：给每个人一张抗污染的声纹像，在一本会成长的注册表里谨慎认人，让"男主角"无论出现在哪一段，都还是同一个 `spk_0000`。它不处理一个采样点，却决定了整部成片听起来"是不是同一拨人"。

下一篇，我们让这些**带稳定身份的句子**开口说另一种语言——聊 **Task C：翻译**，以及它要同时伺候的三件事：意思要对、术语要稳、长度还得照顾后面配音的"口型"。
