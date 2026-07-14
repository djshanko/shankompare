from shankompare.sessions import AUTH_KEY, ConnectionProfile, ProfileStore
from shankompare.sessions import profiles as profiles_module


def test_load_missing_file_returns_empty(tmp_path):
    assert ProfileStore(tmp_path).load() == []


def test_save_load_roundtrip(tmp_path):
    store = ProfileStore(tmp_path)
    original = [
        ConnectionProfile(name="prod", host="example.com", port=2222, username="deploy"),
        ConnectionProfile(
            name="nas",
            host="192.168.1.10",
            username="shanko",
            auth_method=AUTH_KEY,
            key_file="C:/keys/id_ed25519",
            initial_path="/srv/share",
        ),
    ]
    store.save(original)
    assert store.load() == original


def test_unknown_json_keys_are_ignored(tmp_path):
    store = ProfileStore(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        '[{"name": "x", "host": "h", "added_in_future_version": true}]', encoding="utf-8"
    )
    assert store.load() == [ConnectionProfile(name="x", host="h")]


def test_to_sftp_kwargs_password_auth():
    profile = ConnectionProfile(name="p", host="h", username="u", initial_path="/data")
    kwargs = profile.to_sftp_kwargs("secret")
    assert kwargs == {"port": 22, "username": "u", "root": "/data", "password": "secret"}


def test_to_sftp_kwargs_key_auth():
    profile = ConnectionProfile(
        name="p", host="h", username="u", auth_method=AUTH_KEY, key_file="/k/id_rsa"
    )
    kwargs = profile.to_sftp_kwargs("passphrase")
    assert kwargs["key_file"] == "/k/id_rsa"
    assert kwargs["key_passphrase"] == "passphrase"
    assert "password" not in kwargs


def test_secrets_use_keyring_service(monkeypatch):
    calls = {}

    def fake_set(service, user, secret):
        calls["set"] = (service, user, secret)

    def fake_get(service, user):
        calls["get"] = (service, user)
        return "stored"

    monkeypatch.setattr(profiles_module.keyring, "set_password", fake_set)
    monkeypatch.setattr(profiles_module.keyring, "get_password", fake_get)

    ProfileStore.set_secret("myprofile", "hunter2")
    assert calls["set"] == ("shankompare", "myprofile", "hunter2")
    assert ProfileStore.get_secret("myprofile") == "stored"
    assert calls["get"] == ("shankompare", "myprofile")
