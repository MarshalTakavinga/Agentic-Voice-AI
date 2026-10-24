"""Headless UI tests using Streamlit's AppTest."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


def _run(page: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.switch_page(f"views/{page}.py").run()
    assert not at.exception, at.exception
    return at


def test_home_renders():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Agentic Voice AI" in t.value for t in at.title)


def test_ivr_full_balance_call():
    at = _run("ivr")
    assert "Northwind Fiber" in at.chat_message[0].markdown[0].value
    for text in ["what's my balance", "10000001", "1234"]:
        at.chat_input[0].set_value(text).run()
        assert not at.exception, at.exception
    last = at.chat_message[-1].markdown[0].value
    assert "$89.99" in last
    assert any(m.label == "Verified" and m.value == "Yes" for m in at.metric)


def test_ivr_quick_button_and_escalation():
    at = _run("ivr")
    next(b for b in at.button if "Human" in b.label).click().run()
    assert not at.exception
    assert any("transferred" in w.value for w in at.warning)


def test_sip_doctor_sample_nat():
    at = _run("sip_doctor")
    at.selectbox[0].select("nat_one_way_audio").run()
    assert not at.exception, at.exception
    assert any(m.label == "Root cause" and m.value == "media_to_private_address" for m in at.metric)
    assert any("Matches" in c.value for c in at.caption)


def test_sip_doctor_every_sample_matches_label():
    at = _run("sip_doctor")
    for option in at.selectbox[0].options:
        at.selectbox[0].select(option).run()
        assert not at.exception, (option, at.exception)
        assert any("Matches" in c.value for c in at.caption), option
