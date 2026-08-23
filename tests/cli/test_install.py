import plistlib

from claudechat.cli import install


def test_linux_writes_a_systemd_unit(tmp_path, monkeypatch):
    unit = tmp_path / "claudechat.service"
    monkeypatch.setattr(install, "is_macos", lambda: False)
    monkeypatch.setattr(install, "UNIT_PATH", unit)
    monkeypatch.setattr(install.shutil, "which", lambda name: "/usr/bin/uv")

    written = install.install_service(tmp_path)
    assert written == unit
    body = unit.read_text()
    assert "ExecStart=/usr/bin/uv run --project" in body
    assert "claudechat serve" in body
    assert "WantedBy=default.target" in body


def test_macos_writes_a_launchd_plist(tmp_path, monkeypatch):
    plist = tmp_path / "com.claudechat.daemon.plist"
    monkeypatch.setattr(install, "is_macos", lambda: True)
    monkeypatch.setattr(install, "PLIST_PATH", plist)
    monkeypatch.setattr(install.shutil, "which", lambda name: "/opt/homebrew/bin/uv")

    written = install.install_service(tmp_path)
    assert written == plist

    data = plistlib.loads(plist.read_bytes())
    assert data["Label"] == "com.claudechat.daemon"
    assert data["ProgramArguments"][0] == "/opt/homebrew/bin/uv"
    assert data["ProgramArguments"][-1] == "serve"
    assert data["RunAtLoad"] is True
    # KeepAlive only on failure — a deliberate stop must not be undone by launchd
    assert data["KeepAlive"] == {"SuccessfulExit": False}


def test_service_path_follows_the_platform(monkeypatch):
    monkeypatch.setattr(install, "is_macos", lambda: True)
    assert install.service_path().name.endswith(".plist")
    monkeypatch.setattr(install, "is_macos", lambda: False)
    assert install.service_path().name.endswith(".service")


def test_enable_commands_use_the_right_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "is_macos", lambda: True)
    assert all(c[0] == "launchctl" for c in install._enable_commands(tmp_path / "x.plist"))
    monkeypatch.setattr(install, "is_macos", lambda: False)
    assert all(c[0] == "systemctl" for c in install._enable_commands(tmp_path / "x.service"))
