from translip.orchestration.graph import resolve_template_plan


def test_resolve_template_plan_for_asr_dub_ocr_subs() -> None:
    plan = resolve_template_plan("asr-dub+ocr-subs")

    assert plan.template_id == "asr-dub+ocr-subs"
    assert plan.node_order == [
        "stage1",
        "ocr-detect",
        "task-a",
        "asr-ocr-correct",
        "task-b",
        "task-c",
        "ocr-translate",
        "task-d",
        "task-e",
        "task-g",
    ]
    assert plan.nodes["ocr-detect"].required is True
    assert plan.nodes["asr-ocr-correct"].required is True
    assert plan.nodes["ocr-translate"].required is True
    assert plan.dependencies_for("task-b") == ("asr-ocr-correct",)


def test_basic_template_does_not_include_asr_ocr_correction() -> None:
    plan = resolve_template_plan("asr-dub-basic")

    assert "asr-ocr-correct" not in plan.nodes
    assert plan.dependencies_for("task-b") == ("stage1", "task-a")


def test_resolve_template_plan_marks_optional_nodes() -> None:
    plan = resolve_template_plan("asr-dub+ocr-subs+erase")

    assert plan.nodes["ocr-detect"].required is True
    assert plan.nodes["ocr-translate"].required is False
    assert plan.nodes["subtitle-erase"].required is False
