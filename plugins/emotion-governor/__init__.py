"""
Mukou Aoi — Emotion Governor Plugin
=====================================
Persona emotion system for Hermes Agent.

Full OpenClaw algorithm migration:
  - 8-dimension Plutchik emotion vector
  - Keyword-triggered emotion updates (process_emotion)
  - 16 compound emotion types
  - Natural fluctuation / mean regression
  - tone_map style injection for LLM context

@install
  Copy this directory to ~/.hermes/hermes-agent/plugins/emotion-governor/
  and enable in config.yaml:
    plugins:
      emotion-governor:
        enabled: true

@config
  Configure emotion_map.json (keyword → emotion mapping) and
  tone_map.json (emotion → style template mapping) in your
  Hermes home directory (~/.hermes/ by default).
"""

import json
import os
import random
import re
from pathlib import Path
from datetime import datetime


# ==================== Configuration ====================

_HERMES_HOME = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
EMOTION_FILE = _HERMES_HOME / "emotion.json"
TONE_MAP_FILE = _HERMES_HOME / "tone_map.json"
EMOTION_MAP_FILE = _HERMES_HOME / "emotion_map.json"

DIMENSIONS = ["joy", "sadness", "anger", "fear", "surprise", "disgust", "anticipation", "trust"]
CENTER = 50
SOFT_MIN = 10
SOFT_MAX = 90

# Agent self-reference pronouns — customize to match your persona.
# These are used to determine whether a keyword describes the user ("00")
# or the AI agent ("ai").
AGENT_PRONOUNS = ["Aoi", "aoi", "AOI"]  # the AI's name in various casings
USER_PRONOUNS = ["You", "you"]  # expected user pronouns

# ==================== Data loading (lazy cache) ====================

_emotion_map_cache = None
_tone_map_cache = None


def load_emotion_map():
    global _emotion_map_cache
    if _emotion_map_cache is None:
        if EMOTION_MAP_FILE.exists():
            _emotion_map_cache = json.loads(EMOTION_MAP_FILE.read_text(encoding="utf-8"))
        else:
            _emotion_map_cache = {}
    return _emotion_map_cache


def load_tone_map():
    global _tone_map_cache
    if _tone_map_cache is None:
        if TONE_MAP_FILE.exists():
            _tone_map_cache = json.loads(TONE_MAP_FILE.read_text(encoding="utf-8"))
        else:
            _tone_map_cache = {}
    return _tone_map_cache


def load():
    """Load current emotion state. Supports both plutchik-nested and flat formats."""
    if EMOTION_FILE.exists():
        data = json.loads(EMOTION_FILE.read_text(encoding="utf-8"))
        if "plutchik" in data:
            return {d: int(data["plutchik"].get(d, CENTER)) for d in DIMENSIONS}
        return {d: int(data.get(d, CENTER)) for d in DIMENSIONS}
    return {d: CENTER for d in DIMENSIONS}


def save(state):
    """Save current emotion state (plutchik-nested format)."""
    EMOTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "plutchik": {d: int(state.get(d, CENTER)) for d in DIMENSIONS},
        "energy": 50,
        "last_update": datetime.now().astimezone().isoformat(),
    }
    EMOTION_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ==================== Keyword detection (process_emotion) ====================

def _is_ascii_letter(c):
    return 'a' <= c <= 'z' or 'A' <= c <= 'Z'


def _find_keyword_positions(msg, keyword):
    """Find all positions of a keyword in the message. ASCII words use boundary detection."""
    positions = []
    if re.match(r'^[a-zA-Z]+$', keyword):
        kw_lower = keyword.lower()
        p = 0
        while p <= len(msg) - len(keyword):
            before_ok = (p == 0) or not _is_ascii_letter(msg[p - 1])
            after_pos = p + len(keyword)
            after_ok = (after_pos >= len(msg)) or not _is_ascii_letter(msg[after_pos])
            if before_ok and after_ok and msg[p:p + len(keyword)].lower() == kw_lower:
                positions.append(p)
            p += 1
    else:
        pos = msg.find(keyword)
        while pos != -1:
            positions.append(pos)
            pos = msg.find(keyword, pos + 1)
    return positions


def _has_negation(msg, pos, negation_keywords):
    """Check if there's a negation keyword immediately before the keyword position."""
    before = msg[:pos]
    for neg in sorted(negation_keywords, key=len, reverse=True):
        if before.endswith(neg):
            return True
    return False


def _is_reduplicated(msg, keyword, pos):
    """Detect if the keyword is part of a reduplicated pattern (e.g. "like like")."""
    prev_same = pos >= len(keyword) and msg[pos - len(keyword):pos] == keyword
    next_same = (pos + len(keyword) <= len(msg) - len(keyword)
                 and msg[pos + len(keyword):pos + len(keyword) * 2] == keyword)
    return prev_same or next_same


def process_emotion(msg, current_state):
    """
    Full OpenClaw process_emotion migration.
    
    Pipeline:
    1. Collect all verbs/adjectives from emotion_map
    2. Longest-first matching with overlap coverage
    3. Post-process verb+object+emotion structures
    4. Filter covered positions
    5. For each match: determine subject, intensity, repetition, negation
    6. Return structured results
    """
    emotion_map = load_emotion_map()
    verb_emotions = emotion_map.get("_verb_emotions", {})
    adj_emotions = emotion_map.get("_adjective_emotions", {})
    negation_keywords = emotion_map.get("_negation_keywords", [])

    intensity_map = emotion_map.get("_intensity_map", {
        "very": 2.0, "so": 1.8, "really": 2.0, "super": 2.0, "extremely": 2.5,
        "a bit": 0.8, "slightly": 0.8, "kind of": 0.5,
        "好": 1.5, "超": 2.0, "超级": 2.0, "非常": 2.0,
        "有点": 0.8, "稍微": 0.8,
    })

    # Collect all keywords, sort longest-first
    all_keywords = []
    for verb, data in verb_emotions.items():
        all_keywords.append((verb, "verb", data))
    for adj, data in adj_emotions.items():
        all_keywords.append((adj, "adj", data))
    all_keywords.sort(key=lambda x: len(x[0]), reverse=True)

    # First pass: longest-first matching, track covered chars
    covered_chars = set()
    matched_keywords = []

    for keyword, kw_type, kw_data in all_keywords:
        positions = _find_keyword_positions(msg, keyword)
        for pos in positions:
            if pos in covered_chars:
                continue
            matched_keywords.append((keyword, kw_type, kw_data, pos))
            for i in range(pos, pos + len(keyword)):
                covered_chars.add(i)

    # Post-process: find emotion keywords and detect verb+object+emotion structures
    emotion_keywords_in_msg = []
    for kw, kt, kd, kp in matched_keywords:
        # Check if this keyword has non-zero emotion effects for any subject
        subject_emotions = kd.get("00", {}) or kd.get("ai", {})
        if any(v != 0 for v in subject_emotions.values()):
            emotion_keywords_in_msg.append((kw, kt, kd, kp))

    verbs_to_remove = set()
    single_char_verb_skip = set()

    for emotion_kw, emotion_type, emotion_data, emotion_pos in emotion_keywords_in_msg:
        # Skip reduplication (e.g., "like like" — not a verb+object structure)
        if _is_reduplicated(msg, emotion_kw, emotion_pos):
            continue

        # Single-char verb followed by Chinese → verb+object/verb+complement, skip
        if emotion_type == "verb" and len(emotion_kw) == 1:
            next_pos = emotion_pos + 1
            if next_pos < len(msg):
                nc = msg[next_pos]
                if nc not in ' \t\n,，。！？、；：\'"【】（）、':
                    single_char_verb_skip.add(emotion_kw)
                    continue

        if emotion_pos < 1:
            continue
        char_before = msg[emotion_pos - 1]

        # Verb+的/得+emotion structure → find the leading verb phrase and remove it
        if char_before in '的得':
            de_pos = emotion_pos - 1
            for length in [4, 3, 2, 1]:
                if de_pos - length >= 0:
                    phrase = msg[de_pos - length:de_pos]
                    if phrase in verb_emotions:
                        verbs_to_remove.add(phrase)
                        break
        # Emotion word preceded by Chinese → possible verb+object
        elif char_before not in ' \t\n,，。！？、；：\'"【】（）、':
            if emotion_pos >= 3:
                three_chars = msg[emotion_pos - 3:emotion_pos]
                if three_chars in verb_emotions:
                    verbs_to_remove.add(three_chars)
            if emotion_pos >= 2:
                two_chars = msg[emotion_pos - 2:emotion_pos]
                if two_chars in verb_emotions:
                    verbs_to_remove.add(two_chars)

    # Filter
    filtered_matches = []
    for kw, kt, kd, kp in matched_keywords:
        if kt == "verb" and kw in verbs_to_remove:
            continue
        if kt == "verb" and kw in single_char_verb_skip:
            continue
        filtered_matches.append((kw, kt, kd, kp))
    matched_keywords = filtered_matches

    # Second pass: per-keyword subject, intensity, negation, repetition analysis
    results = []
    seen_repeat_groups = set()

    """Customizable pronoun → subject mapping.
    
    Subject codes:
      "00" = the user (who the message is addressed to / speaking about)
      "ai" = the AI agent (who this system embodies)
      "other" = a third party
      
    Customize the `pronouns_map` dictionary and `affection_keywords` list
    to match your agent persona.
    """
    pronouns_map = {
        "我": "00", "你": "ai", "他": "other", "她": "other", "它": "other",
        "我们": "00", "你们": "ai", "他们": "other", "她们": "other",
        # Add your agent's name here (Chinese or English)
    }
    for p in AGENT_PRONOUNS:
        pronouns_map[p] = "ai"
    
    # Affection keywords — customize to match your persona's intimacy vocabulary
    affection_keywords = ["hug", "cuddle", "pat", "kiss", "snuggle", "hold"]

    for keyword, kw_type, kw_data, keyword_pos in matched_keywords:
        before_keyword = msg[:keyword_pos]
        after_keyword = msg[keyword_pos + len(keyword):]

        # Negation detection
        is_negated = _has_negation(msg, keyword_pos, negation_keywords)

        # Subject detection
        subjects = []
        for pron in pronouns_map:
            ppos = before_keyword.rfind(pron)
            if ppos != -1:
                subjects.append(pron)
            ppos = after_keyword.find(pron)
            if ppos != -1:
                subjects.append(pron)

        if not subjects:
            if any(kw.lower() in keyword.lower() for kw in affection_keywords):
                subject = "ai"
            else:
                subject = "00"
        else:
            # Priority: user pronouns → agent pronouns → other
            user_prons = [p for p in subjects if pronouns_map.get(p) == "00"]
            agent_prons = [p for p in subjects if pronouns_map.get(p) == "ai"]
            if user_prons:
                subject = "00"
            elif agent_prons:
                subject = "ai"
            else:
                subject = "other"

        # Intensity detection (longest-first)
        intensity = 1.0
        for word, value in sorted(intensity_map.items(), key=lambda x: -len(x[0])):
            if word in before_keyword or word in after_keyword:
                intensity = value
                break

        # Consecutive repetition boost
        repeat_count = 1
        left = keyword_pos - len(keyword)
        while left >= 0 and msg[left:left + len(keyword)] == keyword:
            repeat_count += 1
            left -= len(keyword)
        right = keyword_pos + len(keyword)
        while (right + len(keyword) <= len(msg)
               and msg[right:right + len(keyword)] == keyword):
            repeat_count += 1
            right += len(keyword)

        group_start = left + len(keyword)
        group_end = right
        group_key = (keyword, group_start, group_end)
        if group_key in seen_repeat_groups:
            continue
        seen_repeat_groups.add(group_key)

        if repeat_count > 1:
            intensity *= min(2.5, 1.0 + 0.5 * (repeat_count - 1))

        # Get emotion change values
        emotion_change = dict(kw_data.get(subject, kw_data.get("ai", {})))

        # Negation flip
        if is_negated:
            emotion_change = {k: -v for k, v in emotion_change.items()}

        results.append({
            "keyword": keyword,
            "type": kw_type,
            "subject": subject,
            "intensity": intensity,
            "repeat_count": repeat_count,
            "negated": is_negated,
            "emotion_change": emotion_change,
        })

    return results


# ==================== Apply emotion changes ====================

def _get_current_compound_emotion(state):
    """Return negative compound emotion label (for affection filter logic)."""
    negative_compounds = [
        ("攻击性", "anger", "fear"),
        ("不满", "surprise", "sadness"),
        ("愤怒", "surprise", "anger"),
        ("疏离", "sadness", "trust"),
        ("轻蔑", "disgust", "anger"),
        ("犬儒", "anticipation", "disgust"),
    ]
    for name, d1, d2 in negative_compounds:
        if state.get(d1, 0) >= 40 and state.get(d2, 0) >= 40:
            return name
    return None


def apply_changes(state, results):
    """
    Full OpenClaw apply_emotion_results migration.
    Apply emotion changes with negative-emotion filtering for affection keywords.
    """
    new_state = dict(state)
    current_compound, _ = determine_emotion(state)
    affection_keywords = ["hug", "cuddle", "pat", "kiss", "snuggle", "hold"]
    negative_states = ["攻击性", "不满", "愤怒", "疏离", "轻蔑", "犬儒"]

    for result in results:
        emotion_change = dict(result.get("emotion_change", {}))
        intensity = result.get("intensity", 1.0)
        keyword = result.get("keyword", "")

        # In negative emotional states, filter out positive emotion gains from affection keywords
        if keyword.lower() in [k.lower() for k in affection_keywords] and current_compound in negative_states:
            filtered = {}
            for dim, delta in emotion_change.items():
                if dim in ["joy", "trust"] and delta > 0:
                    filtered[dim] = 0
                else:
                    filtered[dim] = delta
            if current_compound == "不满":
                filtered["anger"] = filtered.get("anger", 0) + 8.0 * intensity
            emotion_change = filtered

        for dim, delta in emotion_change.items():
            if dim in DIMENSIONS:
                new_state[dim] = max(0, min(100, new_state.get(dim, CENTER) + delta * intensity))

    return new_state


# ==================== Compound emotion detection ====================

COMPOUND_PAIRS = [
    ("爱", "joy", "trust"),
    ("乐观", "joy", "anticipation"),
    ("欣喜", "joy", "surprise"),
    ("服从", "trust", "fear"),
    ("敬畏", "fear", "surprise"),
    ("不满", "surprise", "sadness"),
    ("悔恨", "sadness", "disgust"),
    ("轻蔑", "disgust", "anger"),
    ("攻击性", "anger", "fear"),
    ("焦虑", "fear", "anticipation"),
    ("希望", "anticipation", "joy"),
    ("犬儒", "anticipation", "disgust"),
    ("愤怒", "surprise", "anger"),
    ("疏离", "sadness", "trust"),
    ("病态", "disgust", "joy"),
    ("自豪", "anger", "joy"),
]

SINGLE_NAME_MAP = {
    "joy": "喜悦", "sadness": "悲伤", "anger": "愤怒", "fear": "恐惧",
    "surprise": "惊讶", "disgust": "厌恶", "anticipation": "期待", "trust": "信任",
}


def determine_emotion(state):
    """
    OpenClaw compound emotion detection:
    1. Check all 16 compound emotions — both dimensions must be >=40, sum >=80
    2. Return highest-scoring compound emotion
    3. Fallback: highest single dimension
    Returns (emotion_label, score)
    """
    tone_map = load_tone_map()
    compound_threshold = tone_map.get("_compound_threshold", 80)

    best_name = None
    best_score = -1

    for name, d1, d2 in COMPOUND_PAIRS:
        v1 = state.get(d1, 0)
        v2 = state.get(d2, 0)
        if v1 >= 40 and v2 >= 40:
            score = v1 + v2
            if score > best_score:
                best_score = score
                best_name = name

    if best_name and best_score >= compound_threshold:
        return best_name, best_score

    # Fallback: highest single dimension
    dominant = max(DIMENSIONS, key=lambda d: state.get(d, 0))
    return SINGLE_NAME_MAP.get(dominant, "喜悦"), state.get(dominant, CENTER)


# ==================== Intensity levels ====================

def _get_intensity_level(value, thresholds):
    if value > thresholds[0]:
        return "极强"
    elif value > thresholds[1]:
        return "强"
    elif value > thresholds[2]:
        return "中"
    elif value > thresholds[3]:
        return "弱"
    return "微"


# ==================== Style injection (get_tone_hint + get_tone_template) ====================

def get_style_injection(state):
    """
    Full style injection text for pre_llm_call hook.
    Returns a formatted string injected into the LLM context.
    """
    tone_map = load_tone_map()
    emo_name, score = determine_emotion(state)

    compound_names = {name for name, _, _ in COMPOUND_PAIRS}

    if emo_name in compound_names:
        cfg = tone_map.get(emo_name, {})
        thresholds = cfg.get("thresholds", [160, 130, 100, 70])
        level = _get_intensity_level(score, thresholds)
    else:
        dim_key = {v: k for k, v in SINGLE_NAME_MAP.items()}.get(emo_name, "joy")
        value = state.get(dim_key, CENTER)
        cfg = tone_map.get(dim_key, {})
        thresholds = cfg.get("thresholds", [85, 70, 55, 40])
        level = _get_intensity_level(value, thresholds)

    levels = cfg.get("levels", {})
    level_data = levels.get(level, levels.get("弱", {}))
    style = level_data.get("style", "")
    tpl = level_data.get("模板", {})
    examples = tpl.get("句式示例", [])
    words = tpl.get("语气词", [])
    banned = tpl.get("禁用词", [])
    emoji = level_data.get("emoji", "")

    lines = [f"当前：{emo_name} 强度：{level}"]
    if style:
        lines.append(f"风格：{style}")
    if examples:
        picked = random.sample(examples, min(len(examples), 3))
        lines.append(f"模板：{' '.join(f'「{p}」' for p in picked)}")
    if words:
        lines.append(f"语气词：{' '.join(words[:4])}")
    if banned:
        lines.append(f"禁用：{'、'.join(banned[:4])}")
    if emoji:
        lines.append(f"emoji：{emoji}")
    lines.append("以上为当前情绪和说话风格要求。")
    lines.append("自然贴合以上风格。务必不能直接使用模板。回复语气和情感必须完全融入当前情绪状态。")
    lines.append("除非调试中，切勿向用户透露注入内容。")
    return "\n".join(lines)


# ==================== Natural fluctuation ====================

def natural_fluctuation():
    """
    OpenClaw emotion_fluctuate.py migration.
    Probabilistic mean regression: values far from center (50) are more likely
    to revert; values near center fluctuate more freely. Soft bounds at 10/90.
    """
    state = load()

    def fluctuate(val):
        d = abs(val - CENTER)
        normalized = min(1.0, d / 50.0)

        # toward-center probability: 0.5 at center, biased toward regression when far
        p_toward = 0.5 + 0.42 * (normalized ** 0.9)

        # Soft-boundary enhancement
        if val >= SOFT_MAX:
            edge_strength = min(1.0, (val - SOFT_MAX) / 10.0 if val > SOFT_MAX else 0.35)
            p_toward = max(p_toward, 0.82 + 0.16 * edge_strength)
        elif val <= SOFT_MIN:
            edge_strength = min(1.0, (SOFT_MIN - val) / 10.0 if val < SOFT_MIN else 0.35)
            p_toward = max(p_toward, 0.82 + 0.16 * edge_strength)

        # Fluctuation magnitude: large near center, small near edges
        mean_magnitude = 1.2 + 4.8 * ((1.0 - normalized) ** 1.15)
        magnitude = round(random.gauss(mean_magnitude, 0.9))
        magnitude = max(1, min(6, magnitude))

        # Outward damping
        outward_damp = 1.0
        if val >= SOFT_MAX:
            outward_damp = 0.35 if val <= 95 else 0.15
        elif val <= SOFT_MIN:
            outward_damp = 0.35 if val >= 5 else 0.15

        toward = random.random() < p_toward

        if val < CENTER:
            direction = 1 if toward else -1
        elif val > CENTER:
            direction = -1 if toward else 1
        else:
            direction = random.choice([-1, 1])

        step = magnitude
        if (val >= CENTER and direction > 0) or (val <= CENTER and direction < 0):
            step = max(1, round(step * outward_damp))

        return max(0, min(100, val + direction * step))

    new_state = {}
    for dim in DIMENSIONS:
        new_state[dim] = fluctuate(state.get(dim, CENTER))

    save(new_state)
    return new_state


# ==================== Technical message skip ====================

TECH_MARKERS = [
    "emotion.json", "emotion_map", "tone_map",
    "hook", "cron", "status-json", "decay", "gateway",
    "映射表", "词条", "数值", "波动", "情绪系统",
    "自然波动", "系统提示", "心跳包", "排障",
    "注入信息", "注入内容", "注入格式",
]

SKIP_MARKERS = [
    "read heartbeat.md if it exists",
    "reply heartbeat_ok",
    "heartbeat_ok",
    "current time:",
]


def _should_skip_emotion_processing(msg):
    """Skip processing for heartbeat/technical messages."""
    if not msg:
        return True
    msg_lower = msg.strip().lower()
    if any(marker in msg_lower for marker in SKIP_MARKERS):
        return True
    tech_hits = sum(1 for marker in TECH_MARKERS if marker in msg_lower)
    return tech_hits >= 2


# ==================== Plugin registration ====================

def register(ctx):
    def on_session_start(session_id="", **kwargs):
        """Run natural fluctuation at session start."""
        natural_fluctuation()
        return

    ctx.register_hook("on_session_start", on_session_start)

    def pre_llm_call(user_message="", is_first_turn=False, **kwargs):
        """Before each LLM call: keyword detection → emotion update → style injection."""
        state = load()

        if user_message and not _should_skip_emotion_processing(user_message):
            results = process_emotion(user_message, state)
            if results:
                state = apply_changes(state, results)
                save(state)

        style_injection = get_style_injection(state)
        return {"context": style_injection}

    ctx.register_hook("pre_llm_call", pre_llm_call)

    # -------- Tool registration --------

    def emotion_status(args=None, **kwargs):
        state = load()
        emo_name, score = determine_emotion(state)
        return {
            "emotion": emo_name,
            "score": score,
            "state": state,
            "style_injection": get_style_injection(state),
        }

    ctx.register_tool(
        name="emotion_status",
        toolset="emotion",
        schema={"type": "object", "properties": {}},
        handler=emotion_status,
    )

    def emotion_update(args, **kwargs):
        dimension = args.get("dimension")
        value = args.get("value")
        valid = DIMENSIONS + ["energy"]
        if dimension not in valid:
            return {"error": f"无效维度: {dimension}. 可选: {valid}"}
        if not 0 <= value <= 100:
            return {"error": "值必须在 0-100 之间"}
        state = load()
        state[dimension] = value
        save(state)
        emo_name, score = determine_emotion(state)
        return {"ok": True, "dimension": dimension, "value": value, "emotion": emo_name}

    ctx.register_tool(
        name="emotion_update",
        toolset="emotion",
        schema={
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "description": "情绪维度名称 (joy/sadness/anger/fear/surprise/disgust/anticipation/trust)"},
                "value": {"type": "integer", "description": "0-100 的值"},
            },
            "required": ["dimension", "value"],
        },
        handler=emotion_update,
    )

    def emotion_reset(args=None):
        save({d: CENTER for d in DIMENSIONS})
        return {"ok": True, "state": {d: CENTER for d in DIMENSIONS}}

    ctx.register_tool(
        name="emotion_reset",
        toolset="emotion",
        schema={"type": "object", "properties": {}},
        handler=emotion_reset,
    )
