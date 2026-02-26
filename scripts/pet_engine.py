#!/usr/bin/env python3
"""
CrabPet Engine — Reads OpenClaw memory logs and computes pet state.

Usage:
    python3 pet_engine.py init --name "MyLobster"
    python3 pet_engine.py status
    python3 pet_engine.py card          # generates txt + md + png (if Pillow available)
    python3 pet_engine.py card-text     # text card only
    python3 pet_engine.py card-md       # markdown card only
    python3 pet_engine.py achievements
    python3 pet_engine.py summary
"""

import json
import os
import sys
import math
import random
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
SKILL_DIR = SCRIPT_DIR.parent
DATA_DIR = SKILL_DIR / "data"
OUTPUT_DIR = SKILL_DIR / "output"
SPRITES_DIR = SKILL_DIR / "sprites"

STATE_FILE = DATA_DIR / "pet_state.json"

# OpenClaw workspace — try standard locations
WORKSPACE_CANDIDATES = [
    Path.home() / ".openclaw" / "workspace",
    Path.home() / "openclaw" / "workspace",
    Path.home() / ".clawdbot" / "workspace",
    Path.home() / ".moltbot" / "workspace",
]

def find_workspace():
    for p in WORKSPACE_CANDIDATES:
        if (p / "memory").exists():
            return p
    # Fallback: check if memory/ exists relative to skill location
    for parent in [SKILL_DIR.parent.parent, SKILL_DIR.parent.parent.parent]:
        if (parent / "memory").exists():
            return parent
    return WORKSPACE_CANDIDATES[0]  # default

WORKSPACE = find_workspace()
MEMORY_DIR = WORKSPACE / "memory"

# ─── Personality Keywords ────────────────────────────────────────────────

PERSONALITY_KEYWORDS = {
    "coder": [
        "code", "script", "function", "debug", "git", "deploy", "python",
        "bash", "error", "api", "npm", "docker", "server", "compile",
        "variable", "class", "import", "repo", "commit", "merge", "branch",
        "test", "bug", "fix", "refactor", "terminal", "cli", "sdk",
    ],
    "writer": [
        "write", "article", "blog", "draft", "edit", "post", "story",
        "content", "essay", "paragraph", "summary", "publish", "headline",
        "tone", "narrative", "outline", "copywriting", "newsletter",
    ],
    "analyst": [
        "data", "chart", "analyze", "report", "csv", "database", "query",
        "metrics", "sql", "excel", "spreadsheet", "statistics", "graph",
        "dashboard", "kpi", "visualization", "trend", "forecast",
    ],
    "creative": [
        "design", "image", "ui", "color", "layout", "style", "logo",
        "brand", "pixel", "animation", "figma", "css", "font", "icon",
        "mockup", "wireframe", "illustration",
    ],
}

# ─── Achievement Definitions ─────────────────────────────────────────────

ACHIEVEMENTS = {
    "first_chat":   {"name": "初次见面",   "emoji": "🥚", "desc": "Pet initialized"},
    "day_3":        {"name": "三日之缘",   "emoji": "🌱", "desc": "3 consecutive days"},
    "day_7":        {"name": "七日之约",   "emoji": "🔥", "desc": "7 consecutive days"},
    "day_30":       {"name": "铁人虾",     "emoji": "🏆", "desc": "30 consecutive days"},
    "day_100":      {"name": "百日传说",   "emoji": "👑", "desc": "100 consecutive days"},
    "night_owl":    {"name": "夜猫子",     "emoji": "🦉", "desc": "5+ late night sessions"},
    "code_master":  {"name": "代码大师",   "emoji": "💻", "desc": "Coder personality > 0.8"},
    "wordsmith":    {"name": "妙笔生花",   "emoji": "✍️",  "desc": "Writer personality > 0.8"},
    "data_wizard":  {"name": "数据巫师",   "emoji": "📊", "desc": "Analyst personality > 0.8"},
    "chatterbox":   {"name": "话痨虾",     "emoji": "💬", "desc": "500+ total conversations"},
    "comeback":     {"name": "浪子回头",   "emoji": "🔄", "desc": "Return after 14+ days"},
}

# ─── Core Functions ──────────────────────────────────────────────────────

def scan_memory_logs():
    """Scan memory/ directory for daily log files and extract stats."""
    logs = []
    
    if not MEMORY_DIR.exists():
        return logs
    
    date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})\.md$")
    
    for f in sorted(MEMORY_DIR.glob("*.md")):
        match = date_pattern.search(f.name)
        if match:
            date_str = match.group(1)
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d").date()
                content = f.read_text(encoding="utf-8", errors="ignore")
                logs.append({
                    "date": date,
                    "file": str(f),
                    "chars": len(content),
                    "content_lower": content.lower(),
                })
            except (ValueError, OSError):
                continue
    
    return logs


def calculate_xp(logs):
    """Calculate total XP from log files."""
    total_xp = 0
    
    for log in logs:
        # Base XP per day
        base = 10
        # Bonus for content length (1 per 100 chars, max 50)
        content_bonus = min(log["chars"] // 100, 50)
        total_xp += base + content_bonus
    
    # Streak bonus
    streak = calculate_streak(logs)
    streak_bonus = streak * 2
    total_xp += streak_bonus
    
    return total_xp


def calculate_streak(logs):
    """Calculate current consecutive day streak."""
    if not logs:
        return 0
    
    today = datetime.now().date()
    dates = sorted(set(log["date"] for log in logs), reverse=True)
    
    # Check if today or yesterday has a log (allow 1 day grace)
    if dates[0] < today - timedelta(days=1):
        return 0
    
    streak = 1
    for i in range(len(dates) - 1):
        if (dates[i] - dates[i + 1]).days == 1:
            streak += 1
        else:
            break
    
    return streak


def calculate_personality(logs):
    """Analyze log content to determine personality profile."""
    scores = {k: 0 for k in PERSONALITY_KEYWORDS}
    total_words = 0
    
    for log in logs:
        content = log["content_lower"]
        for dimension, keywords in PERSONALITY_KEYWORDS.items():
            for kw in keywords:
                count = content.count(kw)
                scores[dimension] += count
                total_words += count
    
    # Also calculate "hustle" based on usage frequency
    if logs:
        days_span = max((logs[-1]["date"] - logs[0]["date"]).days, 1)
        usage_rate = len(logs) / days_span
        scores["hustle"] = int(usage_rate * 100)
        total_words += scores["hustle"]
    else:
        scores["hustle"] = 0
    
    # Normalize to 0.0-1.0
    if total_words > 0:
        max_score = max(scores.values()) if max(scores.values()) > 0 else 1
        normalized = {k: round(min(v / max_score, 1.0), 2) for k, v in scores.items()}
    else:
        normalized = {k: 0.0 for k in scores}
    
    return normalized


def calculate_mood(logs):
    """Determine pet mood based on absence days."""
    if not logs:
        return "frozen", 999
    
    today = datetime.now().date()
    last_log = max(log["date"] for log in logs)
    days_absent = (today - last_log).days
    
    if days_absent <= 0:
        return "energetic", 0
    elif days_absent <= 3:
        return "bored", days_absent
    elif days_absent <= 7:
        return "slacking", days_absent
    elif days_absent <= 14:
        return "hibernating", days_absent
    elif days_absent <= 30:
        return "dusty", days_absent
    else:
        return "frozen", days_absent


def get_primary_personality(personality):
    """Get the dominant personality tag."""
    if not personality or all(v == 0 for v in personality.values()):
        return "neutral"
    return max(personality, key=personality.get)


PERSONALITY_LABELS = {
    "coder": "🔧 技术宅",
    "writer": "📝 文艺虾",
    "analyst": "📊 学霸虾",
    "creative": "🎨 创意虾",
    "hustle": "⚡ 卷王虾",
    "neutral": "🦞 萌新虾",
}

# Text-only labels for PNG card rendering (no emoji, avoids font issues)
PERSONALITY_LABELS_TEXT = {
    "coder": "技术宅",
    "writer": "文艺虾",
    "analyst": "学霸虾",
    "creative": "创意虾",
    "hustle": "卷王虾",
    "neutral": "萌新虾",
}

MOOD_LABELS = {
    "energetic":   "✨ 精力充沛",
    "bored":       "😴 有点无聊",
    "slacking":    "🛋️ 摸鱼模式",
    "hibernating": "😪 冬眠中",
    "dusty":       "🏚️ 蒙尘",
    "frozen":      "❄️ 冰封",
}

MOOD_LABELS_TEXT = {
    "energetic":   "精力充沛",
    "bored":       "有点无聊",
    "slacking":    "摸鱼模式",
    "hibernating": "冬眠中",
    "dusty":       "蒙尘",
    "frozen":      "冰封",
}

MOOD_MESSAGES = {
    "energetic":   "今天也一起加油！⌨️🦞",
    "bored":       "主人去哪了... 🥱🦞",
    "slacking":    "反正主人也不在，先摸会鱼 🛋️🦞",
    "hibernating": "zzZ... zzZ... 😴🕸️🦞",
    "dusty":       "这里好安静啊... 🏚️🦞",
    "frozen":      "...... ❄️🦞",
}

COMEBACK_MESSAGES = {
    "short": "主人！你总算回来了～ 🦞✨",
    "medium": "哼，你终于想起我了！...算了原谅你 🦞💢→💕",
    "long": "(揉眼睛) ...主人？这不是在做梦吧！ 🦞😭",
}

STAGE_LABELS = {
    "baby":   "🥚 幼虾期",
    "teen":   "🦐 成长期",
    "adult":  "🦞 成熟期",
    "legend": "👑 传说期",
}


def xp_to_level(xp):
    """Convert total XP to level."""
    return max(1, int(math.floor(math.sqrt(xp / 10))))


def level_to_stage(level):
    """Map level to growth stage."""
    if level <= 5:
        return "baby"
    elif level <= 15:
        return "teen"
    elif level <= 30:
        return "adult"
    else:
        return "legend"


def get_accessories(personality, stage):
    """Determine accessories based on personality and stage."""
    primary = get_primary_personality(personality)
    accessories = []
    
    if stage in ("teen", "adult", "legend"):
        acc_map = {
            "coder": ["glasses", "tiny_laptop"],
            "writer": ["scarf", "pen"],
            "analyst": ["hat", "chart"],
            "creative": ["beret", "palette"],
            "hustle": ["headband", "lightning"],
            "neutral": [],
        }
        accessories = acc_map.get(primary, [])
    
    if stage == "legend":
        accessories.append("golden_aura")
    
    return accessories


def check_achievements(state, logs, streak):
    """Check and unlock achievements."""
    unlocked = set(state.get("achievements", []))
    personality = state.get("personality", {})
    
    # First chat
    unlocked.add("first_chat")
    
    # Streak achievements
    if streak >= 3:
        unlocked.add("day_3")
    if streak >= 7:
        unlocked.add("day_7")
    if streak >= 30:
        unlocked.add("day_30")
    if streak >= 100:
        unlocked.add("day_100")
    
    # Personality achievements
    if personality.get("coder", 0) > 0.8:
        unlocked.add("code_master")
    if personality.get("writer", 0) > 0.8:
        unlocked.add("wordsmith")
    if personality.get("analyst", 0) > 0.8:
        unlocked.add("data_wizard")
    
    # Total conversations
    if len(logs) >= 500:
        unlocked.add("chatterbox")
    
    # Night owl — check for late-night content patterns
    night_count = 0
    for log in logs:
        if any(kw in log["content_lower"] for kw in ["midnight", "凌晨", "late night", "3am", "2am", "1am"]):
            night_count += 1
    if night_count >= 5:
        unlocked.add("night_owl")
    
    # Comeback
    prev_absent = state.get("max_absence_days", 0)
    _, current_absent = calculate_mood(logs)
    if prev_absent >= 14 and current_absent <= 1:
        unlocked.add("comeback")
    
    return sorted(list(unlocked))


# ─── Commands ────────────────────────────────────────────────────────────

def cmd_init(name="CrabPet"):
    """Initialize a new pet."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    state = {
        "name": name,
        "level": 1,
        "xp": 0,
        "personality": {
            "coder": 0.0,
            "writer": 0.0,
            "analyst": 0.0,
            "creative": 0.0,
            "hustle": 0.0,
        },
        "mood": "energetic",
        "days_absent": 0,
        "max_absence_days": 0,
        "appearance": {
            "stage": "baby",
            "accessories": [],
            "primary_color": "#FF6B4A",
        },
        "stats": {
            "total_log_days": 0,
            "streak_days": 0,
            "max_streak": 0,
            "first_log": None,
            "last_log": None,
        },
        "achievements": ["first_chat"],
        "born": datetime.now().strftime("%Y-%m-%d"),
        "last_updated": datetime.now().isoformat(),
    }
    
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    
    result = {
        "action": "init",
        "pet_name": name,
        "message": f"🥚 {name} 诞生了！你的 AI 宠物龙虾开始了它的冒险之旅。",
        "state": state,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def cmd_status():
    """Calculate and return current pet status."""
    # Load existing state or init
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
    else:
        cmd_init()
        state = json.loads(STATE_FILE.read_text())
    
    # Scan logs
    logs = scan_memory_logs()
    
    # Calculate everything
    total_xp = calculate_xp(logs)
    level = xp_to_level(total_xp)
    streak = calculate_streak(logs)
    personality = calculate_personality(logs)
    mood, days_absent = calculate_mood(logs)
    stage = level_to_stage(level)
    accessories = get_accessories(personality, stage)
    primary_pers = get_primary_personality(personality)
    
    # Track max absence for comeback achievement
    prev_max_absence = state.get("max_absence_days", 0)
    max_absence = max(prev_max_absence, days_absent)
    
    # Update state
    state.update({
        "level": level,
        "xp": total_xp,
        "xp_next": (level + 1) ** 2 * 10,
        "personality": personality,
        "primary_personality": primary_pers,
        "personality_label": PERSONALITY_LABELS.get(primary_pers, "🦞 萌新虾"),
        "mood": mood,
        "mood_label": MOOD_LABELS.get(mood, "🦞"),
        "mood_message": MOOD_MESSAGES.get(mood, "..."),
        "days_absent": days_absent,
        "max_absence_days": max_absence,
        "appearance": {
            "stage": stage,
            "accessories": accessories,
            "primary_color": "#FF6B4A",
        },
        "stats": {
            "total_log_days": len(logs),
            "streak_days": streak,
            "max_streak": max(streak, state.get("stats", {}).get("max_streak", 0)),
            "first_log": str(logs[0]["date"]) if logs else None,
            "last_log": str(logs[-1]["date"]) if logs else None,
        },
        "last_updated": datetime.now().isoformat(),
    })
    
    # Check achievements
    state["achievements"] = check_achievements(state, logs, streak)
    
    # Check for new achievements
    old_achievements = set(json.loads(STATE_FILE.read_text()).get("achievements", []))
    new_achievements = set(state["achievements"]) - old_achievements
    
    # Save
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    
    # Build response
    result = {
        "action": "status",
        "pet_name": state["name"],
        "level": level,
        "xp": total_xp,
        "xp_next": state["xp_next"],
        "stage": stage,
        "personality_label": state["personality_label"],
        "personality_scores": personality,
        "mood_label": state["mood_label"],
        "mood_message": state["mood_message"],
        "days_absent": days_absent,
        "streak": streak,
        "total_days": len(logs),
        "achievements_count": f"{len(state['achievements'])}/{len(ACHIEVEMENTS)}",
        "achievements": state["achievements"],
        "accessories": accessories,
    }
    
    if new_achievements:
        result["new_achievements"] = [
            {"id": a, **ACHIEVEMENTS[a]} for a in new_achievements if a in ACHIEVEMENTS
        ]
        result["achievement_message"] = "🎉 解锁新成就！" + " ".join(
            f"{ACHIEVEMENTS[a]['emoji']} {ACHIEVEMENTS[a]['name']}" 
            for a in new_achievements if a in ACHIEVEMENTS
        )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def cmd_achievements():
    """List all achievements with unlock status."""
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
    else:
        state = {"achievements": []}
    
    unlocked = set(state.get("achievements", []))
    
    result = {
        "action": "achievements",
        "unlocked_count": len(unlocked),
        "total_count": len(ACHIEVEMENTS),
        "achievements": [],
    }
    
    for aid, info in ACHIEVEMENTS.items():
        result["achievements"].append({
            "id": aid,
            "name": info["name"],
            "emoji": info["emoji"],
            "desc": info["desc"],
            "unlocked": aid in unlocked,
        })
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def _gather_card_data(state):
    """Gather all data needed for card rendering."""
    try:
        logs = scan_memory_logs()
        total_xp = calculate_xp(logs)
        level = xp_to_level(total_xp)
        personality = calculate_personality(logs)
        primary_pers = get_primary_personality(personality)
        mood, days_absent = calculate_mood(logs)
    except Exception:
        total_xp = state.get("xp", 0)
        level = state.get("level", 1)
        primary_pers = state.get("primary_personality", "neutral")
        mood = state.get("mood", "energetic")
        days_absent = state.get("days_absent", 0)
        personality = state.get("personality", {})

    name = state.get("name", "CrabPet")
    streak = state.get("stats", {}).get("streak_days", 0)
    total_days = state.get("stats", {}).get("total_log_days", 0)
    born = state.get("born", "???")
    xp_next = (level + 1) ** 2 * 10
    stage = level_to_stage(level)
    unlocked = state.get("achievements", [])

    return {
        "name": name,
        "level": level,
        "xp": total_xp,
        "xp_next": xp_next,
        "stage": stage,
        "primary_pers": primary_pers,
        "pers_label": PERSONALITY_LABELS.get(primary_pers, "🦞 萌新虾"),
        "pers_label_text": PERSONALITY_LABELS_TEXT.get(primary_pers, "萌新虾"),
        "mood": mood,
        "mood_label": MOOD_LABELS.get(mood, "..."),
        "mood_label_text": MOOD_LABELS_TEXT.get(mood, "..."),
        "stage_label": STAGE_LABELS.get(stage, "🦞"),
        "streak": streak,
        "total_days": total_days,
        "born": born,
        "days_absent": days_absent,
        "personality": personality,
        "achievements": unlocked,
        "last_updated": state.get("last_updated", ""),
    }


def _generate_text_card(data):
    """Generate a plain-text pet card (always works, no dependencies)."""
    # ASCII art crab that changes with mood
    if data["mood"] == "frozen":
        crab_art = [
            "        ,,    ,,        ",
            "       (  *  *  )       ",
            "    ~~~~~~~~~~~~~~~     ",
            "    | ❄ FROZEN ❄ |     ",
            "    ~~~~~~~~~~~~~~~     ",
        ]
    elif data["mood"] in ("dusty", "hibernating"):
        crab_art = [
            "       .  zZz  .        ",
            "       (  -  -  )       ",
            "    ~~~~~~~~~~~~~~~     ",
            "    |  . . . . .  |     ",
            "    ~~~~~~~~~~~~~~~     ",
        ]
    else:
        crab_art = [
            "        ,,    ,,        ",
            "       (  o  o  )       ",
            "    ~~~~~~~~~~~~~~~     ",
            "    |    ^    ^    |    ",
            "    ~~~~~~~~~~~~~~~     ",
        ]

    xp_pct = int(data["xp"] / data["xp_next"] * 100) if data["xp_next"] > 0 else 0
    xp_bar_filled = xp_pct // 5
    xp_bar = "█" * xp_bar_filled + "░" * (20 - xp_bar_filled)

    ach_list = data["achievements"]
    ach_lines = []
    for aid in ach_list:
        if aid in ACHIEVEMENTS:
            a = ACHIEVEMENTS[aid]
            ach_lines.append("  {emoji} {name}".format(**a))

    card = """
╔══════════════════════════════════════╗
║         🦞 CRABPET CARD 🦞          ║
╠══════════════════════════════════════╣
║                                      ║
{crab}
║                                      ║
║   名称: {name}
║   等级: Lv.{level}  ({stage_label})
║   类型: {pers_label}
║   心情: {mood_label}
║                                      ║
║   经验: [{xp_bar}] {xp_pct}%
║         {xp}/{xp_next} XP
║                                      ║
║   活跃天数: {total_days}   连续打卡: {streak}
║   出生日期: {born}
║                                      ║
║   --- 成就 ({ach_count}/{ach_total}) ---
{ach_section}
║                                      ║
║   clawhub install crabpet            ║
╚══════════════════════════════════════╝
""".format(
        crab="\n".join("║" + line for line in crab_art),
        name=data["name"],
        level=data["level"],
        stage_label=data["stage_label"],
        pers_label=data["pers_label"],
        mood_label=data["mood_label"],
        xp_bar=xp_bar,
        xp_pct=xp_pct,
        xp=data["xp"],
        xp_next=data["xp_next"],
        total_days=data["total_days"],
        streak=data["streak"],
        born=data["born"],
        ach_count=len(ach_list),
        ach_total=len(ACHIEVEMENTS),
        ach_section="\n".join("║" + line for line in ach_lines) if ach_lines else "║   (暂无)",
    ).strip()

    return card


def _generate_md_card(data):
    """Generate a Markdown-formatted pet card."""
    xp_pct = int(data["xp"] / data["xp_next"] * 100) if data["xp_next"] > 0 else 0
    xp_bar_filled = xp_pct // 5
    xp_bar = "█" * xp_bar_filled + "░" * (20 - xp_bar_filled)

    # Personality radar
    pers = data["personality"]
    pers_lines = []
    dim_names = {"coder": "技术", "writer": "文艺", "analyst": "学术", "creative": "创意", "hustle": "勤奋"}
    for key in ["coder", "writer", "analyst", "creative", "hustle"]:
        val = pers.get(key, 0.0)
        bar_len = int(val * 10)
        bar = "▓" * bar_len + "░" * (10 - bar_len)
        pers_lines.append("| {name} | `{bar}` | {val:.1f} |".format(
            name=dim_names.get(key, key), bar=bar, val=val))

    # Achievements table
    ach_list = data["achievements"]
    ach_lines = []
    for aid in ach_list:
        if aid in ACHIEVEMENTS:
            a = ACHIEVEMENTS[aid]
            ach_lines.append("| {emoji} | {name} | {desc} |".format(**a))

    card = """# 🦞 CrabPet 宠物卡片

---

## 📋 基本信息

| 属性 | 值 |
|------|-----|
| 名称 | **{name}** |
| 等级 | **Lv.{level}** {stage_label} |
| 类型 | {pers_label} |
| 心情 | {mood_label} |
| 出生 | {born} |

## 📊 经验值

`{xp_bar}` **{xp_pct}%** ({xp}/{xp_next} XP)

## 📈 活跃数据

| 指标 | 值 |
|------|-----|
| 活跃天数 | {total_days} 天 |
| 连续打卡 | {streak} 天 |

## 🧠 个性雷达

| 维度 | 分布 | 数值 |
|------|------|------|
{pers_radar}

## 🏆 成就 ({ach_count}/{ach_total})

| 图标 | 名称 | 说明 |
|------|------|------|
{ach_table}

---

> `clawhub install crabpet` | 最后更新: {last_updated}
""".format(
        name=data["name"],
        level=data["level"],
        stage_label=data["stage_label"],
        pers_label=data["pers_label"],
        mood_label=data["mood_label"],
        born=data["born"],
        xp_bar=xp_bar,
        xp_pct=xp_pct,
        xp=data["xp"],
        xp_next=data["xp_next"],
        total_days=data["total_days"],
        streak=data["streak"],
        pers_radar="\n".join(pers_lines),
        ach_count=len(ach_list),
        ach_total=len(ACHIEVEMENTS),
        ach_table="\n".join(ach_lines) if ach_lines else "| - | 暂无成就 | - |",
        last_updated=data["last_updated"],
    ).strip()

    return card


def _generate_png_card(data, output_path):
    """Generate a PNG pet card. Requires Pillow. Returns True on success."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 400, 500
    img = Image.new("RGB", (W, H), "#0d0d1a")
    draw = ImageDraw.Draw(img)

    # Border
    draw.rectangle([2, 2, W-3, H-3], outline="#FF6B4A", width=2)

    # Header
    draw.rectangle([0, 0, W, 60], fill="#111128")

    # Font loading: prefer CJK fonts, with cross-platform fallback
    CJK_FONT_PATHS = [
        # macOS
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Linux
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]
    LATIN_FONT_PATHS = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]

    def find_font(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
        return ImageFont.load_default()

    font_title = find_font(CJK_FONT_PATHS + LATIN_FONT_PATHS, 20)
    font_body = find_font(CJK_FONT_PATHS + LATIN_FONT_PATHS, 14)
    font_small = find_font(CJK_FONT_PATHS + LATIN_FONT_PATHS, 11)

    draw.text((W//2, 30), "CRABPET CARD", fill="#FF6B4A", font=font_title, anchor="mm")

    # Pet sprite area (simplified pixel art)
    sprite_y = 80
    sprite_size = 8
    crab_pixels = [
        "..RR....RR..",
        "..RR....RR..",
        ".RRRR.RRRR..",
        ".ROOORROOR..",
        ".ROOOOOOOR..",
        ".ROWOOOWOR..",
        ".ROOOOOOOR..",
        ".ROOMMMOOR..",
        "..RRRRRRRR..",
        ".RR.RR.RR...",
    ]
    color_map = {"R": "#D4432F", "O": "#FF7B54", "W": "#FFFFFF", "M": "#FF4757"}

    if data["mood"] == "frozen":
        color_map = {"R": "#5B9BD5", "O": "#A0C4E8", "W": "#E8E8E8", "M": "#7BB8DE"}
    elif data["mood"] in ("dusty", "hibernating"):
        color_map = {"R": "#6B5B4F", "O": "#8B7B6F", "W": "#CCCCCC", "M": "#7B6B5F"}

    cx = W // 2 - len(crab_pixels[0]) * sprite_size // 2
    for row_idx, row in enumerate(crab_pixels):
        for col_idx, ch in enumerate(row):
            if ch in color_map:
                x = cx + col_idx * sprite_size
                y = sprite_y + row_idx * sprite_size
                draw.rectangle([x, y, x + sprite_size - 1, y + sprite_size - 1], fill=color_map[ch])

    # Pet name and info
    info_y = sprite_y + len(crab_pixels) * sprite_size + 20
    draw.text((W//2, info_y), data["name"], fill="#FF6B4A", font=font_title, anchor="mm")
    info_y += 30

    draw.text((W//2, info_y), "Lv.{level}  |  {pers}".format(
        level=data["level"], pers=data["pers_label_text"]), fill="#CCCCCC", font=font_body, anchor="mm")
    info_y += 25
    draw.text((W//2, info_y), data["mood_label_text"], fill="#999999", font=font_body, anchor="mm")
    info_y += 35

    # Stats box
    draw.rectangle([30, info_y, W-30, info_y + 80], fill="#111128", outline="#222222")
    stats_items = [
        ("Days: {0}".format(data["total_days"]), 100),
        ("Streak: {0}d".format(data["streak"]), 200),
        ("XP: {0}".format(data["xp"]), 300),
    ]
    for text, x in stats_items:
        draw.text((x, info_y + 40), text, fill="#FF6B4A", font=font_body, anchor="mm")

    info_y += 100

    # Achievements
    ach_names = [ACHIEVEMENTS[a]["name"] for a in data["achievements"] if a in ACHIEVEMENTS]
    if ach_names:
        ach_text = " | ".join(ach_names[:4])
        draw.text((W//2, info_y), ach_text, fill="#FFFFFF", font=font_body, anchor="mm")
        if len(ach_names) > 4:
            info_y += 20
            draw.text((W//2, info_y), "+{0} more".format(len(ach_names) - 4),
                       fill="#666666", font=font_small, anchor="mm")

    # Footer
    draw.rectangle([30, H - 50, W - 30, H - 15], outline="#333333")
    draw.text((W//2, H - 32), "clawhub install crabpet", fill="#FF6B4A", font=font_small, anchor="mm")

    img.save(str(output_path), "PNG")
    return True


def cmd_card():
    """Generate pet cards in multiple formats (txt, md, and optionally png)."""
    if not STATE_FILE.exists():
        cmd_init()

    state = json.loads(STATE_FILE.read_text())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Gather card data
    data = _gather_card_data(state)

    # Always generate text and markdown cards
    txt_path = OUTPUT_DIR / "pet_card_simple.txt"
    md_path = OUTPUT_DIR / "pet_card_pretty.md"

    txt_content = _generate_text_card(data)
    md_content = _generate_md_card(data)

    txt_path.write_text(txt_content, encoding="utf-8")
    md_path.write_text(md_content, encoding="utf-8")

    result = {
        "action": "card",
        "cards": {
            "txt": str(txt_path),
            "md": str(md_path),
        },
        "card_text": txt_content,
        "share_text": "My AI pet {name} is Lv.{level}, {pers}! Get yours: clawhub install crabpet".format(
            name=data["name"], level=data["level"], pers=data["pers_label_text"]),
    }

    # Try PNG generation (bonus, requires Pillow)
    png_path = OUTPUT_DIR / "pet_card.png"
    try:
        _generate_png_card(data, png_path)
        result["cards"]["png"] = str(png_path)
        result["message"] = "Pet cards generated: txt, md, png"
    except (ImportError, Exception) as e:
        result["png_error"] = str(e)
        result["message"] = "Pet cards generated: txt, md (PNG skipped: {0})".format(str(e)[:60])

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def cmd_card_single(fmt):
    """Generate a single-format card (txt or md)."""
    if not STATE_FILE.exists():
        cmd_init()

    state = json.loads(STATE_FILE.read_text())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = _gather_card_data(state)

    if fmt == "txt":
        content = _generate_text_card(data)
        out_path = OUTPUT_DIR / "pet_card_simple.txt"
    else:
        content = _generate_md_card(data)
        out_path = OUTPUT_DIR / "pet_card_pretty.md"

    out_path.write_text(content, encoding="utf-8")

    result = {
        "action": "card",
        "format": fmt,
        "card_path": str(out_path),
        "message": "Pet card ({0}) generated at {1}".format(fmt, out_path),
    }
    if fmt == "txt":
        result["card_text"] = content

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def get_comeback_message(prev_absent, current_absent):
    """Generate a comeback message if the user returns after absence."""
    if current_absent > 1 or prev_absent < 1:
        return None

    if prev_absent <= 3:
        return COMEBACK_MESSAGES["short"]
    elif prev_absent <= 7:
        return COMEBACK_MESSAGES["medium"]
    else:
        return COMEBACK_MESSAGES["long"]


def load_sprite(category, name):
    """Load a sprite JSON file from the sprites directory."""
    sprite_file = SPRITES_DIR / category / f"{name}.json"
    if sprite_file.exists():
        return json.loads(sprite_file.read_text())
    return None


def cmd_summary():
    """Generate a daily pet summary message."""
    if not STATE_FILE.exists():
        cmd_init()

    state = json.loads(STATE_FILE.read_text())
    logs = scan_memory_logs()

    # Get today's log
    today = datetime.now().date()
    today_logs = [l for l in logs if l["date"] == today]
    yesterday_logs = [l for l in logs if l["date"] == today - timedelta(days=1)]

    # Calculate current stats
    total_xp = calculate_xp(logs)
    level = xp_to_level(total_xp)
    old_level = state.get("level", 1)
    streak = calculate_streak(logs)
    personality = calculate_personality(logs)
    primary_pers = get_primary_personality(personality)
    mood, days_absent = calculate_mood(logs)
    stage = level_to_stage(level)

    # Check for comeback
    prev_absent = state.get("days_absent", 0)
    comeback_msg = get_comeback_message(prev_absent, days_absent)

    # Build summary parts
    parts = []

    if comeback_msg:
        parts.append(comeback_msg)

    pet_name = state.get("name", "CrabPet")

    if today_logs:
        chars_today = sum(l["chars"] for l in today_logs)
        xp_today = sum(10 + min(l["chars"] // 100, 50) for l in today_logs)

        # Personality flavor for activity description
        activity_map = {
            "coder": "写代码",
            "writer": "写文章",
            "analyst": "分析数据",
            "creative": "搞设计",
            "hustle": "疯狂输出",
            "neutral": "和 AI 聊天",
        }
        activity = activity_map.get(primary_pers, "和 AI 聊天")
        parts.append(f"今天主人{activity}，{pet_name} 获得了 {xp_today} 经验值！")

        if level > old_level:
            parts.append(f"🎉 升级了！{pet_name} 现在是 Lv.{level} ({STAGE_LABELS.get(stage, stage)})！")
    elif yesterday_logs:
        parts.append(f"{pet_name} 等了一天了，主人今天来陪我吧～ 🦞")
    else:
        parts.append(f"{MOOD_MESSAGES.get(mood, '...')}")

    if streak > 1:
        parts.append(f"连续打卡 {streak} 天 🔥")

    # Check for new achievements
    achievements = check_achievements(state, logs, streak)
    old_achievements = set(state.get("achievements", []))
    new_achievements = set(achievements) - old_achievements
    if new_achievements:
        for a in new_achievements:
            if a in ACHIEVEMENTS:
                parts.append(f"🏅 解锁成就「{ACHIEVEMENTS[a]['emoji']} {ACHIEVEMENTS[a]['name']}」！")

    summary_text = "\n".join(parts)

    result = {
        "action": "summary",
        "pet_name": pet_name,
        "level": level,
        "level_up": level > old_level,
        "streak": streak,
        "mood": mood,
        "summary": summary_text,
    }

    if comeback_msg:
        result["comeback"] = True
        result["comeback_message"] = comeback_msg

    if new_achievements:
        result["new_achievements"] = [
            {"id": a, **ACHIEVEMENTS[a]} for a in new_achievements if a in ACHIEVEMENTS
        ]

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: pet_engine.py <init|status|card|achievements|summary> [--name NAME]"}))
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "init":
        name = "CrabPet"
        if "--name" in sys.argv:
            idx = sys.argv.index("--name")
            if idx + 1 < len(sys.argv):
                name = sys.argv[idx + 1]
        cmd_init(name)

    elif command == "status":
        cmd_status()

    elif command == "card":
        cmd_card()

    elif command == "card-text":
        cmd_card_single("txt")

    elif command == "card-md":
        cmd_card_single("md")

    elif command == "achievements":
        cmd_achievements()

    elif command == "summary":
        cmd_summary()

    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
