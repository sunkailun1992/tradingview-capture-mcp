from tradingview_capture_mcp.errors import OUTPUT_EXISTS, CaptureError


def test_capture_error_carries_code_message_and_detail():
    exc = CaptureError(OUTPUT_EXISTS, "refusing to overwrite", {"path": "batch"})
    assert exc.code == "OUTPUT_EXISTS"
    assert str(exc) == "OUTPUT_EXISTS: refusing to overwrite"
    assert exc.to_dict() == {
        "code": "OUTPUT_EXISTS",
        "message": "refusing to overwrite",
        "detail": {"path": "batch"},
    }


def test_detail_defaults_to_an_empty_dict():
    assert CaptureError(OUTPUT_EXISTS, "x").detail == {}
