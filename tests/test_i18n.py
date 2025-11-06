"""Basic tests for the i18n helper."""

from utils.i18n import I18n


def test_i18n_lookup_and_switch() -> None:
    zh = I18n("zh_CN")
    assert zh.t("navigation.home") == "首页 · 项目简介"

    zh.switch_locale("en_US")
    assert zh.t("navigation.home") == "Home · Project Overview"


def test_i18n_missing_key_returns_key() -> None:
    i18n = I18n("en_US")
    assert i18n.t("nonexistent.key") == "nonexistent.key"
