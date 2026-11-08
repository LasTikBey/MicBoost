from micboost.config import AppConfig
from micboost.dsp import Settings


def test_new_config_defaults_to_english():
    assert AppConfig().language == "en"
    assert AppConfig().latency_mode == "low"


def test_app_config_loads_french_language(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    AppConfig(language="fr").save()
    assert AppConfig.load().language == "fr"


def test_app_config_round_trips_all_saved_selections(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    settings = Settings(
        input_volume=73.0,
        mic_gain_db=18.4,
        output_gain_db=-4.5,
        bypass=True,
        ns_on=False,
        ns_strength=0.73,
        eq_on=True,
        eq_100_db=2.0,
        eq_300_db=-3.0,
        eq_1k_db=1.5,
        eq_3k_db=4.0,
        eq_10k_db=-2.5,
        gate_on=False,
        gate_threshold_db=-44.0,
        gate_range_db=36.0,
        agc_on=True,
        agc_target_db=-18.0,
        agc_max_gain_db=22.0,
        comp_on=False,
        comp_threshold_db=-20.0,
        comp_ratio=4.5,
        comp_attack_ms=12.0,
        comp_release_ms=180.0,
        comp_makeup_db=3.0,
        limiter_on=False,
        limiter_ceiling_db=-2.0,
        limiter_release_ms=95.0,
    )
    config = AppConfig(
        dsp=settings,
        mic_key="Microphone|WASAPI",
        out_key="Virtual Cable|WASAPI",
        monitor_key="Headphones|WASAPI",
        latency_mode="safe",
        autostart_engine=True,
        language="en",
        theme="light",
        close_behavior="quit",
        profiles={"1": Settings(mic_gain_db=24, ns_on=False).to_dict()},
        profile_names={"1": "Podcast"},
    )

    config.save()
    restored = AppConfig.load()

    assert restored.dsp.to_dict() == settings.to_dict()
    assert restored.mic_key == config.mic_key
    assert restored.out_key == config.out_key
    assert restored.monitor_key == config.monitor_key
    assert restored.latency_mode == config.latency_mode
    assert restored.autostart_engine is config.autostart_engine
    assert restored.language == config.language
    assert restored.theme == config.theme
    assert restored.close_behavior == config.close_behavior
    assert restored.profiles == config.profiles
    assert restored.profile_names == config.profile_names


def test_app_config_ignores_invalid_profile_slots_and_clamps_saved_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    config = AppConfig(profiles={
        "1": {"mic_gain_db": 500},
        "unknown": {"mic_gain_db": 20},
        "2": "not a profile",
    }, profile_names={"1": "  Podcast  ", "2": " ", "6": "Invalid"})
    config.save()

    restored = AppConfig.load()

    assert restored.profiles == {"1": Settings(mic_gain_db=30).to_dict()}
    assert restored.profile_names == {"1": "Podcast"}
