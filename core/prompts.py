"""
轻量级 Prompt 模板加载器

从 config/prompts/ 目录加载 .txt 模板并渲染变量。
零依赖 agent/config 层，lru_cache 只读一次磁盘，fallback 保证向后兼容。
"""

from pathlib import Path
from functools import lru_cache
from typing import Optional

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _strip_front_matter(text: str) -> str:
    """Strip YAML front matter (--- ... ---) from template text."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    body_start = end + 4
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    return text[body_start:]


@lru_cache(maxsize=64)
def _load_raw(name: str) -> Optional[str]:
    path = _PROMPTS_DIR / name
    if not path.exists():
        return None
    return _strip_front_matter(path.read_text("utf-8"))


def render(template_name: str, fallback: str, **kwargs) -> str:
    """加载模板并渲染，文件不存在时 fallback 到硬编码字符串。

    使用逐个占位符替换而非 str.format()，避免 kwargs 值中的花括号
    （如 ``{t1, t2}``、JSON 片段等）被误解析为格式化占位符。
    """
    raw = _load_raw(template_name) or fallback
    if not kwargs:
        return raw
    result = raw
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def load_metadata(template_name: str) -> dict:
    """Load YAML front matter metadata from a prompt template."""
    path = _PROMPTS_DIR / template_name
    if not path.exists():
        return {}
    text = path.read_text("utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    import yaml
    try:
        return yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
