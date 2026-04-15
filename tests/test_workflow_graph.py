from translip.orchestration.graph import resolve_template_plan


def test_resolve_template_plan_for_asr_dub_ocr_subs() -> None:
    plan = resolve_template_plan("asr-dub+ocr-subs")

    assert plan.template_id == "asr-dub+ocr-subs"
    assert plan.node_order == [
        "stage1",
        "ocr-detect",
        "task-a",
        "task-b",
        "task-c",
        "ocr-translate",
        "task-d",
        "task-e",
        "task-g",
    ]
    assert plan.nodes["ocr-detect"].required is True
    assert plan.nodes["ocr-translate"].required is True


def test_resolve_template_plan_marks_optional_nodes() -> None:
    plan = resolve_template_plan("asr-dub+ocr-subs+erase")

    assert plan.nodes["ocr-detect"].required is True
    assert plan.nodes["ocr-translate"].required is False
    assert plan.nodes["subtitle-erase"].required is False
