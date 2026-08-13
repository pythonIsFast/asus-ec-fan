from backend.config import AppConfig, is_supported_model


def test_verified_br1402fga_dmi_names_are_supported():
    assert is_supported_model("ASUS BR1402FGA")
    assert is_supported_model("BR1402FGA")
    assert is_supported_model("ASUS BR1402FGA_BR1402FGA")


def test_unknown_or_similar_models_are_not_supported():
    assert not is_supported_model("Unknown")
    assert not is_supported_model("ASUS BR1402FGA-UNVERIFIED")
    assert not is_supported_model("ASUS BR1402")


def test_real_mode_never_defaults_to_user_writable_build_helper(tmp_path):
    config = AppConfig.defaults(tmp_path)
    assert config.helper_path.as_posix() == "/usr/local/libexec/asus-ec-fan-helper"
