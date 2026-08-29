from app.components import empty_state_html, kpi_card_html, process_rail_html, topbar_html


def test_kpi_card_escapes_artifact_text():
    """Artifact text must not be able to inject markup into the app shell."""
    rendered = kpi_card_html("<script>alert(1)</script>", "500", "真实数据", "文")

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "500" in rendered


def test_kpi_cards_can_be_concatenated_without_markdown_code_indentation():
    """Joined cards must stay raw HTML instead of becoming a Markdown code block."""
    rendered = "".join(
        [
            kpi_card_html("已索引资料", "500", "manifest", "文"),
            kpi_card_html("知识库规模", "200,515", "chunks", "层"),
        ]
    )

    assert "\n    <section" not in rendered
    assert rendered.count('<section class="br-kpi">') == 2


def test_topbar_describes_demo_role_without_fake_user_identity():
    """The shell must present a role context, not an invented named account."""
    rendered = topbar_html("可信RAG问答", True)

    assert "竞赛演示环境 / 监管分析角色" in rendered
    assert "索引就绪" in rendered
    assert "张三" not in rendered


def test_process_rail_uses_exact_five_audit_stages():
    """Dropping a provenance stage must break the explanation flow."""
    rendered = process_rail_html("制度问答", has_citations=True, answered=True)

    for label in ("问题", "Query理解", "知识库检索", "证据采用", "答案生成"):
        assert label in rendered


def test_empty_state_keeps_boundary_copy_visible():
    """An unavailable feature must explain the boundary instead of showing fake data."""
    rendered = empty_state_html("尚无可验证时序数据", "当前演示版不伪造结果", "▱")

    assert "尚无可验证时序数据" in rendered
    assert "当前演示版不伪造结果" in rendered
