from micboost.ui.localization import tr


def test_translation_preserves_turkish_and_translates_english_and_french():
    assert tr("tr", "Ayarlar") == "Ayarlar"
    assert tr("en", "Ayarlar") == "Settings"
    assert tr("fr", "Ayarlar") == "Paramètres"
    assert tr("en", "Ses profili {slot}").format(slot=1) == "Audio profile 1"
    assert tr("fr", "Profili sil") == "Supprimer le profil"
    assert tr("en", "Adı kaydet") == "Save name"
