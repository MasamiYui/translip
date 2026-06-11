"""Prompt templates for the vision tasks (zh/en), JSON-output convention.

Perception prompts ask for a single JSON object/array and nothing else; parsing
tolerance for chatty model output lives in :mod:`translip.vision.schema`.
"""
from __future__ import annotations

_SCENE_ZH = (
    "你是视频画面分析助手。这些帧按时间顺序来自同一段视频片段。"
    "只输出一个 JSON 对象，不要任何其它文字。字段："
    '{"scene": "一句话场景描述（地点+人物+动作+气氛）", '
    '"people_visible": 画面中的人数(整数), '
    '"setting": "地点类型的简短英文短语，如 car_interior/office/street", '
    '"mood": "气氛的英文单词，如 tense/relaxed/joyful", '
    '"confidence": 0到1之间的小数}'
)

_SCENE_EN = (
    "You are a video frame analyst. These frames come from one clip, in order. "
    "Output exactly one JSON object and nothing else, with fields: "
    '{"scene": "one-sentence description (location + people + action + mood)", '
    '"people_visible": integer count of visible people, '
    '"setting": "short location slug like car_interior/office/street", '
    '"mood": "one-word mood like tense/relaxed/joyful", '
    '"confidence": number between 0 and 1}'
)

_ERASE_QC_ZH = (
    "这一帧来自字幕擦除后的视频，原本此处有字幕。请检查画面下方等区域是否仍有"
    "残留文字或修复涂抹痕迹（模糊块/色块/鬼影）。只输出一个 JSON 对象："
    '{"residual_text": true或false, "artifact": "无则 null，有则简短英文标签如 blur_patch/ghosting", '
    '"note": "一句话说明", "confidence": 0到1}'
)

_ERASE_QC_EN = (
    "This frame comes from a video after subtitle erasure; a subtitle used to be here. "
    "Check for leftover text or inpainting artifacts (blur patches, color smears, ghosting). "
    "Output exactly one JSON object: "
    '{"residual_text": true|false, "artifact": "null or a short label like blur_patch/ghosting", '
    '"note": "one short sentence", "confidence": number 0-1}'
)

# {text} is substituted with the OCR-recognized text of the event.
_OCR_CLASSIFY_ZH = (
    "画面中有一段 OCR 识别出的文字：「{text}」。请判断它属于哪一类，只输出一个 JSON 对象："
    '{{"kind": "subtitle|scene_text|watermark|title_card", "confidence": 0到1}}。'
    "subtitle=对白字幕（通常底部居中、与说话内容对应）；scene_text=场景内文字（路牌/店招/车牌/屏幕内容）；"
    "watermark=台标或水印；title_card=标题/片头片尾字。"
)

_OCR_CLASSIFY_EN = (
    'The frame contains OCR-recognized text: "{text}". Classify it. '
    "Output exactly one JSON object: "
    '{{"kind": "subtitle|scene_text|watermark|title_card", "confidence": number 0-1}}. '
    "subtitle = dialogue subtitle (bottom-centered, matches speech); scene_text = in-scene text "
    "(signs, plates, screens); watermark = station logo/watermark; title_card = title/credits."
)

_SPEAKER_VISUAL_ZH = (
    "这些帧按时间顺序来自同一段对话视频。判断画面人数与谁更可能正在说话。"
    "只输出一个 JSON 对象："
    '{"people_visible": 整数, "speaking_face": true/false/null（画面中能否看到说话者的脸）, '
    '"speaker_hint": "对说话者的简短描述，看不出则 null", "confidence": 0到1}'
)

_SPEAKER_VISUAL_EN = (
    "These frames come from one dialogue clip, in order. Estimate how many people are visible "
    "and who is most likely speaking. Output exactly one JSON object: "
    '{"people_visible": integer, "speaking_face": true|false|null (is the speaker\'s face visible), '
    '"speaker_hint": "short description of the speaker or null", "confidence": number 0-1}'
)

# {question} is substituted with the user's free-form question.
_FREEFORM_ZH = (
    "这些帧按时间顺序来自同一段视频。请根据画面回答问题：{question}\n"
    '只输出一个 JSON 对象：{{"answer": "回答", "confidence": 0到1}}'
)

_FREEFORM_EN = (
    "These frames come from one video clip, in order. Answer this question from the frames: {question}\n"
    'Output exactly one JSON object: {{"answer": "your answer", "confidence": number 0-1}}'
)

_TEMPLATES: dict[tuple[str, str], str] = {
    ("scene-context", "zh"): _SCENE_ZH,
    ("scene-context", "en"): _SCENE_EN,
    ("erase-qc", "zh"): _ERASE_QC_ZH,
    ("erase-qc", "en"): _ERASE_QC_EN,
    ("ocr-classify", "zh"): _OCR_CLASSIFY_ZH,
    ("ocr-classify", "en"): _OCR_CLASSIFY_EN,
    ("speaker-visual", "zh"): _SPEAKER_VISUAL_ZH,
    ("speaker-visual", "en"): _SPEAKER_VISUAL_EN,
    ("freeform", "zh"): _FREEFORM_ZH,
    ("freeform", "en"): _FREEFORM_EN,
}


def render_prompt(task: str, lang: str, **kwargs: str) -> str:
    """Render the prompt for ``task`` in ``lang`` (falls back to zh)."""
    template = _TEMPLATES.get((task, lang)) or _TEMPLATES.get((task, "zh"))
    if template is None:
        raise ValueError(f"Unsupported vision task: {task}")
    return template.format(**kwargs) if kwargs else template


__all__ = ["render_prompt"]
