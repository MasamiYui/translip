"""Subtitle merger module - handles text deduplication and time merging"""

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

import numpy as np

from translip.ocr.models.domain import DetectedText, Subtitle
from translip.ocr.utils.geometry import box_to_polygon, merge_polygons, polygon_to_rotated_box

logger = logging.getLogger(__name__)

_COMMON_VARIANT_TRANSLATION = str.maketrans({
    "萬": "万",
    "專": "专",
    "與": "与",
    "東": "东",
    "絲": "丝",
    "個": "个",
    "麼": "么",
    "為": "为",
    "麗": "丽",
    "舉": "举",
    "樂": "乐",
    "習": "习",
    "書": "书",
    "買": "买",
    "亂": "乱",
    "乾": "干",
    "了": "了",
    "亂": "乱",
    "亞": "亚",
    "親": "亲",
    "億": "亿",
    "從": "从",
    "倆": "俩",
    "兒": "儿",
    "兩": "两",
    "冊": "册",
    "冪": "幂",
    "凍": "冻",
    "劇": "剧",
    "動": "动",
    "勁": "劲",
    "勞": "劳",
    "勢": "势",
    "區": "区",
    "醫": "医",
    "華": "华",
    "協": "协",
    "單": "单",
    "厲": "厉",
    "參": "参",
    "雙": "双",
    "變": "变",
    "変": "变",
    "發": "发",
    "臺": "台",
    "號": "号",
    "葉": "叶",
    "嗎": "吗",
    "聽": "听",
    "啟": "启",
    "國": "国",
    "圖": "图",
    "圍": "围",
    "場": "场",
    "壞": "坏",
    "聲": "声",
    "處": "处",
    "備": "备",
    "夠": "够",
    "夢": "梦",
    "學": "学",
    "實": "实",
    "寫": "写",
    "寧": "宁",
    "對": "对",
    "導": "导",
    "將": "将",
    "專": "专",
    "尋": "寻",
    "對": "对",
    "寶": "宝",
    "將": "将",
    "屆": "届",
    "屬": "属",
    "岡": "冈",
    "嶽": "岳",
    "島": "岛",
    "峯": "峰",
    "崙": "仑",
    "幣": "币",
    "幹": "干",
    "庫": "库",
    "應": "应",
    "廠": "厂",
    "廣": "广",
    "廳": "厅",
    "張": "张",
    "強": "强",
    "當": "当",
    "錄": "录",
    "彈": "弹",
    "後": "后",
    "徵": "征",
    "德": "德",
    "恆": "恒",
    "愛": "爱",
    "慘": "惨",
    "應": "应",
    "戶": "户",
    "戰": "战",
    "戲": "戏",
    "戶": "户",
    "拋": "抛",
    "挾": "挟",
    "捨": "舍",
    "據": "据",
    "擇": "择",
    "擔": "担",
    "擴": "扩",
    "攝": "摄",
    "攔": "拦",
    "敵": "敌",
    "數": "数",
    "斂": "敛",
    "斷": "断",
    "於": "于",
    "時": "时",
    "晉": "晋",
    "暈": "晕",
    "曉": "晓",
    "曆": "历",
    "會": "会",
    "術": "术",
    "條": "条",
    "來": "来",
    "樣": "样",
    "機": "机",
    "權": "权",
    "條": "条",
    "樂": "乐",
    "歡": "欢",
    "歲": "岁",
    "歷": "历",
    "歸": "归",
    "殘": "残",
    "殿": "殿",
    "氣": "气",
    "沒": "没",
    "湯": "汤",
    "為": "为",
    "灣": "湾",
    "無": "无",
    "煙": "烟",
    "燈": "灯",
    "燉": "炖",
    "營": "营",
    "獎": "奖",
    "環": "环",
    "產": "产",
    "畫": "画",
    "當": "当",
    "瘋": "疯",
    "發": "发",
    "盜": "盗",
    "監": "监",
    "盤": "盘",
    "著": "着",
    "眾": "众",
    "瞭": "了",
    "矚": "瞩",
    "禮": "礼",
    "稅": "税",
    "種": "种",
    "稱": "称",
    "緝": "缉",
    "窩": "窝",
    "競": "竞",
    "筆": "笔",
    "節": "节",
    "簽": "签",
    "續": "续",
    "總": "总",
    "綜": "综",
    "網": "网",
    "罷": "罢",
    "羅": "罗",
    "習": "习",
    "聲": "声",
    "聖": "圣",
    "聰": "聪",
    "肅": "肃",
    "腦": "脑",
    "臺": "台",
    "舉": "举",
    "艦": "舰",
    "艙": "舱",
    "藝": "艺",
    "藥": "药",
    "處": "处",
    "蘭": "兰",
    "虧": "亏",
    "蝦": "虾",
    "衛": "卫",
    "裝": "装",
    "裏": "里",
    "裡": "里",
    "註": "注",
    "製": "制",
    "複": "复",
    "見": "见",
    "悅": "悦",
    "規": "规",
    "覺": "觉",
    "視": "视",
    "詞": "词",
    "試": "试",
    "說": "说",
    "請": "请",
    "讀": "读",
    "謝": "谢",
    "識": "识",
    "證": "证",
    "讓": "让",
    "豐": "丰",
    "貝": "贝",
    "貓": "猫",
    "貴": "贵",
    "賀": "贺",
    "資": "资",
    "賓": "宾",
    "賞": "赏",
    "賴": "赖",
    "贊": "赞",
    "趕": "赶",
    "躍": "跃",
    "轉": "转",
    "辦": "办",
    "邊": "边",
    "這": "这",
    "連": "连",
    "進": "进",
    "運": "运",
    "過": "过",
    "還": "还",
    "這": "这",
    "這": "这",
    "適": "适",
    "選": "选",
    "鄉": "乡",
    "釀": "酿",
    "醫": "医",
    "針": "针",
    "鈞": "钧",
    "鈴": "铃",
    "鈣": "钙",
    "鉅": "巨",
    "銀": "银",
    "銅": "铜",
    "銷": "销",
    "鋒": "锋",
    "錄": "录",
    "錢": "钱",
    "鍋": "锅",
    "鍵": "键",
    "鏡": "镜",
    "鐘": "钟",
    "鐵": "铁",
    "鑑": "鉴",
    "長": "长",
    "開": "开",
    "關": "关",
    "隊": "队",
    "陽": "阳",
    "際": "际",
    "難": "难",
    "電": "电",
    "霧": "雾",
    "靈": "灵",
    "靜": "静",
    "響": "响",
    "頁": "页",
    "頂": "顶",
    "項": "项",
    "順": "顺",
    "頒": "颁",
    "領": "领",
    "頭": "头",
    "顏": "颜",
    "類": "类",
    "風": "风",
    "飛": "飞",
    "館": "馆",
    "馬": "马",
    "駐": "驻",
    "驗": "验",
    "體": "体",
    "髮": "发",
    "鬥": "斗",
    "魯": "鲁",
    "鴻": "鸿",
    "黃": "黄",
    "點": "点",
})


class SubtitleMerger:
    """
    Subtitle merger - handles text deduplication and time merging

    Strategy:
    1. Sort by timestamp
    2. Merge consecutive similar texts
    3. Handle text change boundaries
    4. Generate final subtitle list
    """

    def __init__(
        self,
        similarity_threshold: float = 0.8,
        time_tolerance: float = 0.5,
        min_duration: float = 0.5,
        attach_short_prefixes: bool = False,
    ):
        """
        Initialize subtitle merger

        Args:
            similarity_threshold: Text similarity threshold for merging
            time_tolerance: Time tolerance for consecutive detections
            min_duration: Minimum subtitle duration in seconds
            attach_short_prefixes: Whether to stitch very short prefix subtitles into the following subtitle
        """
        self.similarity_threshold = similarity_threshold
        self.time_tolerance = time_tolerance
        self.min_duration = min_duration
        self.attach_short_prefixes = attach_short_prefixes

    def merge_detected_texts(
        self,
        detections: List[DetectedText]
    ) -> List[Subtitle]:
        """
        Merge detected texts into subtitles

        Strategy:
        1. Sort by time
        2. Merge consecutive identical or similar texts
        3. Handle text change boundaries
        4. Generate final subtitle list

        Args:
            detections: List of detected texts (time-ordered)

        Returns:
            Merged subtitle list
        """
        if not detections:
            return []

        # Sort by timestamp
        sorted_dets = sorted(detections, key=lambda d: d.timestamp)

        # Merge consecutive similar texts
        merged = []
        current_group = [sorted_dets[0]]

        for i in range(1, len(sorted_dets)):
            current = sorted_dets[i]
            prev = current_group[-1]

            # Check if should merge
            if self._should_merge(current, prev):
                current_group.append(current)
            else:
                # End current group, start new one
                merged.append(self._create_subtitle_from_group(current_group))
                current_group = [current]

        # Handle last group
        if current_group:
            merged.append(self._create_subtitle_from_group(current_group))

        # Post-process: adjust time boundaries
        subtitles = self._adjust_time_boundaries(merged)

        logger.info(f"Merged {len(detections)} detections into {len(subtitles)} subtitles")
        return subtitles

    def _should_merge(self, current: DetectedText, prev: DetectedText) -> bool:
        """
        Determine if two detections should be merged

        Args:
            current: Current detection
            prev: Previous detection

        Returns:
            True if should merge
        """
        # Check time gap
        time_gap = current.timestamp - prev.timestamp
        if time_gap > self.time_tolerance * 2:  # More than 2x time tolerance
            return False

        # Check text similarity
        similarity = self._text_similarity(current.text, prev.text)
        return similarity >= self.similarity_threshold

    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate text similarity

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0-1)
        """
        norm1 = self._normalize_text(text1)
        norm2 = self._normalize_text(text2)
        if not norm1 or not norm2:
            return 0.0
        return SequenceMatcher(None, norm1, norm2).ratio()

    def _create_subtitle_from_group(self, group: List[DetectedText]) -> Subtitle:
        """
        Create subtitle from a group of detections

        Args:
            group: List of detections in same group

        Returns:
            Subtitle object
        """
        start_time = group[0].timestamp
        end_time = group[-1].timestamp

        best_text = self._select_representative_text(group)
        best_text_detections = [
            det for det in group
            if self._clean_output_text(det.text) == best_text
        ]
        box_source_detections = best_text_detections if best_text_detections else group
        stable_box, stable_polygon, stable_rotated_box, debug_info = self._compute_stable_geometry(box_source_detections)

        # Calculate average confidence
        avg_confidence = np.mean([d.confidence for d in group])

        # Estimate end time (considering sampling interval)
        # If single frame, need to estimate reasonable end time
        if len(group) == 1:
            end_time = start_time + self.min_duration

        return Subtitle(
            index=0,  # Assigned later
            start_time=start_time,
            end_time=end_time,
            text=best_text,
            confidence=avg_confidence,
            box=stable_box,
            polygon=stable_polygon,
            rotated_box=stable_rotated_box,
            debug_info=debug_info
        )

    def _select_representative_text(self, group: List[DetectedText]) -> str:
        if not group:
            return ""
        if len(group) == 1:
            return group[0].text

        text_groups: Dict[str, List[Tuple[DetectedText, str]]] = {}
        fallback_text = self._clean_output_text(group[0].text) or group[0].text
        for det in group:
            cleaned_text = self._clean_output_text(det.text) or det.text.strip()
            normalized_key = self._normalize_text(cleaned_text) or cleaned_text
            text_groups.setdefault(normalized_key, []).append((det, cleaned_text))

        best_text = fallback_text
        best_score = float("-inf")
        group_size = max(1, len(group))

        for detections in text_groups.values():
            candidate_text = self._select_best_text_variant(detections)
            frequency_score = len(detections) / group_size
            avg_confidence = float(np.mean([det.confidence for det, _ in detections])) if detections else 0.0
            normalized_text = self._normalize_text(candidate_text)
            length_score = min(1.0, len(normalized_text) / 12.0)
            quality_score = self._text_quality_score(candidate_text)
            similarity_score = float(np.mean([
                self._text_similarity(candidate_text, other.text)
                for other in group
            ])) if group else 0.0

            score = (
                0.34 * frequency_score
                + 0.20 * avg_confidence
                + 0.18 * similarity_score
                + 0.12 * length_score
                + 0.16 * quality_score
            )
            if score > best_score:
                best_score = score
                best_text = candidate_text

        return best_text

    def _compute_stable_geometry(self, detections: List[DetectedText]) -> Tuple[Tuple[int, int, int, int], List[Tuple[float, float]] | None, dict | None, dict]:
        # Collect raw data for debugging
        raw_data = []
        for det in detections:
            raw_data.append({
                "box": det.box,
                "polygon": det.polygon,
                "rotated_box": det.rotated_box,
                "recognition_region": det.recognition_region,
                "recognition_executed": det.recognition_executed,
                "sample_debug": det.sample_debug,
                "confidence": det.confidence,
                "timestamp": det.timestamp,
                "text": det.text
            })

        if len(detections) == 1:
            box = detections[0].box
            # Apply padding even for single detection
            width = max(1.0, box[2] - box[0])
            height = max(1.0, box[3] - box[1])
            pad_x = max(5.0, width * 0.08)
            pad_y = max(4.0, height * 0.3)
            
            x1 = int(round(box[0] - pad_x))
            y1 = int(round(box[1] - pad_y))
            x2 = int(round(box[2] + pad_x))
            y2 = int(round(box[3] + pad_y))
            
            if x2 <= x1: x2 = x1 + 1
            if y2 <= y1: y2 = y1 + 1

            stable_box = (x1, y1, x2, y2)
            polygon = detections[0].polygon or box_to_polygon(box)
            rotated_box = detections[0].rotated_box or polygon_to_rotated_box(polygon)

            return stable_box, polygon, rotated_box, {
                "raw_detections": raw_data,
                "method": "single",
                "padding": {"x": pad_x, "y": pad_y},
            }

        boxes = np.array([det.box for det in detections], dtype=np.float64)
        confidence = np.array([max(0.01, det.confidence) for det in detections], dtype=np.float64)
        top_conf = float(np.max(confidence))
        mask = confidence >= top_conf * 0.8
        selected = boxes[mask]
        if selected.shape[0] == 0:
            selected = boxes
            selected_detections = detections
        else:
            selected_detections = [det for det, keep in zip(detections, mask.tolist()) if keep]

        med = np.median(selected, axis=0)
        width = max(1.0, med[2] - med[0])
        height = max(1.0, med[3] - med[1])
        
        # Increased padding
        pad_x = max(5.0, width * 0.08)
        pad_y = max(4.0, height * 0.3)

        x1 = int(round(med[0] - pad_x))
        y1 = int(round(med[1] - pad_y))
        x2 = int(round(med[2] + pad_x))
        y2 = int(round(med[3] + pad_y))
        if x2 <= x1:
            x2 = x1 + 1
        if y2 <= y1:
            y2 = y1 + 1

        stable_box = (x1, y1, x2, y2)
        polygon_candidates = [det.polygon or box_to_polygon(det.box) for det in selected_detections]
        stable_polygon = merge_polygons(polygon_candidates, target_box=stable_box) or box_to_polygon(stable_box)
        stable_rotated_box = polygon_to_rotated_box(stable_polygon)

        return stable_box, stable_polygon, stable_rotated_box, {
            "raw_detections": raw_data,
            "method": "median_stable",
            "median_box": med.tolist(),
            "padding": {"x": pad_x, "y": pad_y},
            "selected_count": len(selected),
        }

    def _adjust_time_boundaries(self, subtitles: List[Subtitle]) -> List[Subtitle]:
        """
        Adjust subtitle time boundaries

        Ensures no overlap and minimum duration.

        Args:
            subtitles: List of subtitles

        Returns:
            Adjusted subtitles
        """
        if not subtitles:
            return []

        adjusted = []

        for i, sub in enumerate(subtitles):
            if i > 0:
                prev = adjusted[-1]
                if sub.start_time <= prev.start_time:
                    sub.start_time = prev.start_time + 0.01
                if sub.start_time < prev.end_time:
                    gap = min(0.01, self.min_duration * 0.2)
                    prev.end_time = max(prev.start_time + 0.05, sub.start_time - gap)

            if sub.end_time <= sub.start_time:
                sub.end_time = sub.start_time + self.min_duration

            duration = sub.end_time - sub.start_time
            if duration < self.min_duration:
                sub.end_time = sub.start_time + self.min_duration

            sub.index = i + 1
            adjusted.append(sub)

        return adjusted

    def filter_low_confidence(
        self,
        subtitles: List[Subtitle],
        min_confidence: float = 0.7
    ) -> List[Subtitle]:
        """
        Filter low confidence subtitles

        Args:
            subtitles: List of subtitles
            min_confidence: Minimum confidence threshold

        Returns:
            Filtered subtitles
        """
        filtered = [s for s in subtitles if s.confidence >= min_confidence]

        # Re-index
        for i, sub in enumerate(filtered):
            sub.index = i + 1

        return filtered

    def deduplicate_similar(
        self,
        subtitles: List[Subtitle]
    ) -> List[Subtitle]:
        """
        Remove duplicate content subtitles

        Args:
            subtitles: List of subtitles

        Returns:
            Deduplicated subtitles
        """
        if len(subtitles) <= 1:
            return subtitles

        deduped = [self._normalize_subtitle_output(subtitles[0])]

        for raw_current in subtitles[1:]:
            current = self._normalize_subtitle_output(raw_current)
            if not current.text:
                continue
            prev = deduped[-1]
            gap = current.start_time - prev.end_time
            similar = self._text_similarity(current.text, prev.text)
            contain = self._is_text_contained(current.text, prev.text)
            short_variant_match = self._is_short_text_variant_match(current, prev)
            minor_variation_match = self._is_minor_text_variation(current.text, prev.text)

            if ((similar > 0.92 and gap < self.time_tolerance and minor_variation_match) or
                (contain and gap < self.time_tolerance * 1.2) or
                short_variant_match):
                prev.end_time = current.end_time
                prev.text = self._choose_better_subtitle_text(prev, current)
                if current.box and (not prev.box or current.confidence >= prev.confidence):
                    prev.box = current.box
                    prev.polygon = current.polygon
                    prev.rotated_box = current.rotated_box
                prev.confidence = max(prev.confidence, current.confidence)
            elif current.text:
                deduped.append(current)

        if self.attach_short_prefixes:
            deduped = self._merge_short_contextual_subtitles(deduped)

        # Re-index
        for i, sub in enumerate(deduped):
            sub.index = i + 1

        return deduped

    def merge_nearby(
        self,
        subtitles: List[Subtitle],
        max_gap: float = 1.0
    ) -> List[Subtitle]:
        """
        Merge nearby subtitles with same content

        Args:
            subtitles: List of subtitles
            max_gap: Maximum gap to merge (seconds)

        Returns:
            Merged subtitles
        """
        if len(subtitles) <= 1:
            return subtitles

        merged = [subtitles[0]]

        for current in subtitles[1:]:
            prev = merged[-1]
            gap = current.start_time - prev.end_time

            # If same text and small gap, merge
            if (self._text_similarity(current.text, prev.text) > 0.95 and
                gap <= max_gap):
                prev.end_time = current.end_time
            else:
                merged.append(current)

        # Re-index
        for i, sub in enumerate(merged):
            sub.index = i + 1

        return merged

    def _normalize_text(self, text: str) -> str:
        text = self._apply_common_variant_map(text).strip().lower()
        text = re.sub(r"\s+", "", text)
        text = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3]", "", text)
        return text

    def _apply_common_variant_map(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text or "")
        return normalized.translate(_COMMON_VARIANT_TRANSLATION)

    def _select_best_text_variant(self, detections: List[Tuple[DetectedText, str]]) -> str:
        best_text = detections[0][1]
        best_score = float("-inf")
        for det, text in detections:
            score = 0.58 * det.confidence + 0.42 * self._text_quality_score(text)
            if score > best_score:
                best_score = score
                best_text = text
        return best_text

    def _text_quality_score(self, text: str) -> float:
        lines = [line for line in self._split_clean_lines(text) if line]
        if not lines:
            return 0.0

        total_length = 0
        total_cjk = 0
        total_latin = 0
        short_noise_lines = 0
        for line in lines:
            normalized = self._normalize_text(line)
            total_length += len(normalized)
            total_cjk += sum(1 for ch in normalized if '\u4e00' <= ch <= '\u9fff')
            total_latin += sum(1 for ch in normalized if ch.isascii() and ch.isalpha())
            if self._looks_like_noise_line(line, has_strong_cjk_sibling=True):
                short_noise_lines += 1

        length_score = min(1.0, total_length / 14.0)
        cjk_ratio = total_cjk / max(1, total_length)
        latin_ratio = total_latin / max(1, total_length)
        noise_penalty = min(1.0, short_noise_lines / max(1, len(lines)))

        return max(
            0.0,
            min(
                1.0,
                0.42 * length_score
                + 0.36 * cjk_ratio
                + 0.16 * (1.0 - min(1.0, latin_ratio))
                + 0.06 * (1.0 - noise_penalty),
            ),
        )

    def _split_clean_lines(self, text: str) -> List[str]:
        normalized = self._apply_common_variant_map(text)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        return [re.sub(r"\s+", " ", line).strip() for line in normalized.split("\n") if line.strip()]

    def _clean_output_text(self, text: str) -> str:
        lines = self._split_clean_lines(text)
        if not lines:
            return ""

        has_strong_cjk_line = any(
            sum(1 for ch in self._normalize_text(line) if '\u4e00' <= ch <= '\u9fff') >= 2
            for line in lines
        )

        cleaned_lines: List[str] = []
        for line in lines:
            stripped = self._strip_leading_noise_token(line)
            if self._looks_like_noise_line(stripped, has_strong_cjk_sibling=has_strong_cjk_line):
                continue
            cleaned_lines.append(stripped)

        if not cleaned_lines:
            cleaned_lines = [self._strip_leading_noise_token(line) for line in lines]

        deduped_lines: List[str] = []
        for line in cleaned_lines:
            if not deduped_lines:
                deduped_lines.append(line)
                continue
            previous = deduped_lines[-1]
            if self._text_similarity(previous, line) >= 0.88 or self._is_text_contained(previous, line):
                deduped_lines[-1] = self._choose_better_text(previous, line)
            else:
                deduped_lines.append(line)

        return "\n".join(line for line in deduped_lines if line).strip()

    def _strip_leading_noise_token(self, text: str) -> str:
        stripped = re.sub(r"\s+", " ", self._apply_common_variant_map(text)).strip()
        if re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3]", stripped):
            stripped = re.sub(
                r"^(?:[@#]?[A-Za-z][A-Za-z0-9_-]{0,7}\s+)+(?=[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3])",
                "",
                stripped,
            )
        return stripped.strip()

    def _looks_like_noise_line(self, text: str, *, has_strong_cjk_sibling: bool) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return True

        cjk_count = sum(1 for ch in normalized if '\u4e00' <= ch <= '\u9fff')
        latin_count = sum(1 for ch in normalized if ch.isascii() and ch.isalpha())
        digit_count = sum(1 for ch in normalized if ch.isdigit())

        if not has_strong_cjk_sibling:
            return False

        if cjk_count == 0 and len(normalized) <= 10 and latin_count >= min(3, len(normalized)):
            return True
        if cjk_count <= 1 and len(normalized) <= 4 and latin_count + digit_count >= max(2, len(normalized) - 1):
            return True
        return False

    def _normalize_subtitle_output(self, subtitle: Subtitle) -> Subtitle:
        subtitle.text = self._clean_output_text(subtitle.text)
        return subtitle

    def _choose_better_text(self, text1: str, text2: str) -> str:
        cleaned1 = self._clean_output_text(text1)
        cleaned2 = self._clean_output_text(text2)
        if not cleaned1:
            return cleaned2
        if not cleaned2:
            return cleaned1

        score1 = self._text_quality_score(cleaned1)
        score2 = self._text_quality_score(cleaned2)
        if score2 > score1 + 1e-6:
            return cleaned2
        if score1 > score2 + 1e-6:
            return cleaned1
        return cleaned2 if len(self._normalize_text(cleaned2)) > len(self._normalize_text(cleaned1)) else cleaned1

    def _choose_better_subtitle_text(self, prev: Subtitle, current: Subtitle) -> str:
        cleaned_prev = self._clean_output_text(prev.text)
        cleaned_current = self._clean_output_text(current.text)
        score_prev = self._text_quality_score(cleaned_prev)
        score_current = self._text_quality_score(cleaned_current)
        if abs(score_current - score_prev) <= 0.02:
            return cleaned_current if current.confidence >= prev.confidence else cleaned_prev
        return cleaned_current if score_current > score_prev else cleaned_prev

    def _is_short_text_variant_match(self, current: Subtitle, prev: Subtitle) -> bool:
        if current.box is None or prev.box is None:
            return False

        gap = current.start_time - prev.end_time
        if gap > max(0.18, self.time_tolerance * 0.5):
            return False

        n1 = self._normalize_text(current.text)
        n2 = self._normalize_text(prev.text)
        max_len = max(len(n1), len(n2))
        if max_len == 0 or max_len > 8:
            return False

        if self._box_overlap_ratio(current.box, prev.box) < 0.7:
            return False

        return self._edit_distance(n1, n2) <= 1

    def _is_minor_text_variation(self, text1: str, text2: str) -> bool:
        n1 = self._normalize_text(text1)
        n2 = self._normalize_text(text2)
        if not n1 or not n2:
            return False
        if n1 in n2 or n2 in n1:
            return True

        max_len = max(len(n1), len(n2))
        distance = self._edit_distance(n1, n2)
        if max_len <= 8:
            return distance <= 1
        if max_len <= 16:
            return distance <= 2
        return distance <= 1

    def _edit_distance(self, text1: str, text2: str) -> int:
        if text1 == text2:
            return 0
        if not text1:
            return len(text2)
        if not text2:
            return len(text1)

        previous = list(range(len(text2) + 1))
        for i, left in enumerate(text1, start=1):
            current = [i]
            for j, right in enumerate(text2, start=1):
                substitution = previous[j - 1] + (0 if left == right else 1)
                deletion = previous[j] + 1
                insertion = current[j - 1] + 1
                current.append(min(substitution, deletion, insertion))
            previous = current
        return previous[-1]

    def _box_overlap_ratio(self, box1: Tuple[int, int, int, int], box2: Tuple[int, int, int, int]) -> float:
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        if x2 <= x1 or y2 <= y1:
            return 0.0

        intersection = float((x2 - x1) * (y2 - y1))
        area1 = float(max(1, box1[2] - box1[0]) * max(1, box1[3] - box1[1]))
        area2 = float(max(1, box2[2] - box2[0]) * max(1, box2[3] - box2[1]))
        return intersection / max(1.0, min(area1, area2))

    def _merge_short_contextual_subtitles(self, subtitles: List[Subtitle]) -> List[Subtitle]:
        if len(subtitles) <= 1:
            return subtitles

        merged: List[Subtitle] = []
        items = list(subtitles)
        index = 0
        while index < len(items):
            current = items[index]
            if index + 1 < len(items) and self._should_attach_short_prefix(current, items[index + 1]):
                next_subtitle = items[index + 1]
                next_subtitle.start_time = current.start_time
                next_subtitle.text = self._concat_subtitle_texts(current.text, next_subtitle.text)
                next_subtitle.confidence = max(current.confidence, next_subtitle.confidence)
                index += 1
                continue

            merged.append(current)
            index += 1

        return merged

    def _should_attach_short_prefix(self, current: Subtitle, next_subtitle: Subtitle) -> bool:
        if current.box is None or next_subtitle.box is None:
            return False

        current_norm = self._normalize_text(current.text)
        next_norm = self._normalize_text(next_subtitle.text)
        if not current_norm or not next_norm:
            return False
        if len(current_norm) > 4 or len(next_norm) < 6:
            return False
        if "\n" in current.text:
            return False

        gap = next_subtitle.start_time - current.end_time
        if gap < -0.05 or gap > max(0.7, self.time_tolerance * 0.45):
            return False
        if self._box_overlap_ratio(current.box, next_subtitle.box) < 0.5:
            return False
        return True

    def _concat_subtitle_texts(self, left: str, right: str) -> str:
        left_clean = self._clean_output_text(left)
        right_clean = self._clean_output_text(right)
        if not left_clean:
            return right_clean
        if not right_clean:
            return left_clean

        needs_space = (
            left_clean[-1].isalnum()
            and right_clean[0].isalnum()
            and left_clean[-1].isascii()
            and right_clean[0].isascii()
        )
        return f"{left_clean}{' ' if needs_space else ''}{right_clean}"

    def _is_text_contained(self, text1: str, text2: str) -> bool:
        n1 = self._normalize_text(text1)
        n2 = self._normalize_text(text2)
        if not n1 or not n2:
            return False
        return n1 in n2 or n2 in n1
