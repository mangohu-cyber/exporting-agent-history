#!/usr/bin/env python3
"""摘要标签质量测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = SKILL_ROOT / "scripts" / "export_agent_history.py"
RULES_PATH = SKILL_ROOT / "references" / "tag-rules.json"


def load_export_module():
    spec = importlib.util.spec_from_file_location("export_agent_history", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 export_agent_history.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tags_for(text: str) -> set[str]:
    module = load_export_module()
    patterns = module.load_tag_patterns(RULES_PATH)
    return {name for name, pattern in patterns.items() if pattern.search(text)}


def test_generic_document_words_do_not_trigger_pdf():
    tags = tags_for("请整理接口文档，说明需求边界和验收规则。")
    assert "requirements" in tags
    assert "document-pdf" not in tags


def test_pdf_render_terms_trigger_only_document_pdf():
    tags = tags_for("检查 PDF 渲染、版式、字体和截图是否越界。")
    assert "document-pdf" in tags
    assert "requirements" not in tags


def test_explicit_document_formats_trigger_document_pdf():
    for text in (
        "Update the Markdown guide.",
        "Review README.md before release.",
        "Create a Word DOCX document.",
        "Prepare the PPT and PPTX slides.",
        "Prepare a Microsoft Word document.",
        "Review the Google Slides deck.",
    ):
        assert "document-pdf" in tags_for(text), text


def test_document_format_terms_require_explicit_context():
    for text in (
        "Document the API behavior.",
        "The parser reads AGENTS.md before coding.",
        "Use this word in a sentence.",
        "The panel slides into view.",
    ):
        assert "document-pdf" not in tags_for(text), text


def test_explicit_requirements_terms_trigger_requirements():
    tags = tags_for("明确多端数据模型、接口契约、版本冲突和验收标准。")
    assert "requirements" in tags
    assert "document-pdf" not in tags


def test_distinct_topics_can_keep_multiple_tags():
    tags = tags_for("修复地图 UI 刷新异常，并运行 CMake 测试验证。")
    assert {"debug", "map-ui", "state-cache", "build-verify"} <= tags


if __name__ == "__main__":
    for test in (
        test_generic_document_words_do_not_trigger_pdf,
        test_pdf_render_terms_trigger_only_document_pdf,
        test_explicit_document_formats_trigger_document_pdf,
        test_document_format_terms_require_explicit_context,
        test_explicit_requirements_terms_trigger_requirements,
        test_distinct_topics_can_keep_multiple_tags,
    ):
        test()
    print("tag quality tests passed")
