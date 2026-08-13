import app


def test_linux_root_detection(monkeypatch):
    monkeypatch.setattr(app.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app.os, "geteuid", lambda: 0)
    assert app.process_is_elevated() is True


def test_linux_normal_user_detection(monkeypatch):
    monkeypatch.setattr(app.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app.os, "geteuid", lambda: 1000)
    assert app.process_is_elevated() is False
