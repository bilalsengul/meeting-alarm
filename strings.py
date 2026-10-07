"""User-visible strings for meeting-alarm. Add a language by adding a dict here."""

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "header": "MEETING",
        "starts_in": "starts in {minutes} min · {time}",
        "starts_now": "starting NOW · {time}",
        "in_progress": "started {minutes} min ago · {time}",
        "untitled": "(untitled)",
        "join": "Join  (Enter)",
        "ok": "OK  (Enter)",
        "snooze": "Snooze {minutes} min  (Space)",
        "dismiss": "Dismiss  (Esc)",
        "hint": "This screen stays until you press a key.",
        "test_title": "Test meeting",
        "test_subtitle": "This is a test · closes by itself in 6 seconds",
        "auth_page_ok": "Calendar access granted, you can close this tab.",
        "auth_page_nocode": "no code",
    },
    "tr": {
        "header": "TOPLANTI",
        "starts_in": "{minutes} dakika sonra başlıyor · {time}",
        "starts_now": "ŞİMDİ başlıyor · {time}",
        "in_progress": "{minutes} dakikadır devam ediyor · {time} başladı",
        "untitled": "(başlıksız)",
        "join": "Katıl  (Enter)",
        "ok": "Tamam  (Enter)",
        "snooze": "{minutes} dk ertele  (Space)",
        "dismiss": "Kapat  (Esc)",
        "hint": "Bu ekran sen bir tuşa basana kadar kapanmaz.",
        "test_title": "Deneme toplantısı",
        "test_subtitle": "Bu bir test · 6 saniye sonra kendiliğinden kapanır",
        "auth_page_ok": "Takvim yetkisi alındı, bu sekmeyi kapatabilirsin.",
        "auth_page_nocode": "code yok",
    },
}


def t(lang: str, key: str, **kw: object) -> str:
    """Look up a string; unknown language or key falls back to English."""
    table = STRINGS.get(lang) or STRINGS["en"]
    text = table.get(key) or STRINGS["en"].get(key, key)
    return text.format(**kw) if kw else text
