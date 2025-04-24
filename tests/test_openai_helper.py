from scansynclib.openai_helper import validate_smb_filename
import pytest


@pytest.mark.parametrize("input_str", [
    "",  # leer
    "   ",  # nur Leerzeichen
    ".",  # nur Punkt
    "..",  # doppelte Punkte
    "valid_filename",  # bereits gültig
    "   valid_filename   ",  # Trim-Test
    "file.with.dot.",  # Punkt am Ende
    "file/with/slash",  # Slash entfernen
    "file\\with\\backslash",  # Backslash entfernen
    "file:with:colon",  # Doppelpunkt entfernen
    "file*with*asterisk",  # Stern entfernen
    "file?with?question",  # Fragezeichen entfernen
    "file\"with\"quotes",  # Anführungszeichen entfernen
    "file<with<less",  # Kleiner-als-Zeichen entfernen
    "file>with>greater",  # Größer-als-Zeichen entfernen
    "file|with|pipe",  # Pipe entfernen
    "file\x00with\x1Fcontrol",  # Steuerzeichen entfernen
    "    ..file..   ",  # Kombi: Leerzeichen und Punkte
    "🦄📁🐍",  # Emojis
    "übermäßig-länger-als-fünfzig-zeichen-und-noch-ein-bisschen-mehr",
    "1234567890" * 6,  # Viel zu lang
    "valid—filename—with—emdash",  # Unicode Bindestrich
    "dateiname mit leerzeichen",  # Leerzeichen
    "   ⛔️ Ungültig: Datei | Name * 💾  ",  # Kombi mit Symbolen
    ".....hiddenfile",  # viele Punkte vorne
    "filename.",  # Punkt am Ende
    "filename..",  # doppelte Punkte am Ende
    "filename . ",  # Punkt mit Leerzeichen
    "CON",  # Reservierter Name unter Windows
    "file.txt",  # mit Extension (wird nicht entfernt, aber evtl. relevant)
    "support300_BE_no_votelnote</imagine>",  # HTML-Tag
])
def test_validate_smb_filename(input_str):
    result = validate_smb_filename(input_str)

    # 1. Nicht leer
    assert result != "", f"Result was unexpectedly empty for input: {input_str}"

    # 2. Keine ungültigen Zeichen
    assert not any(c in result for c in '<>:"/\\|?*'), f"Invalid chars still in result: {result}"

    # 3. Keine Steuerzeichen
    assert all('\x00' > c or c > '\x1F' for c in result), f"Control chars found in result: {result}"

    # 4. Keine Punkte oder Leerzeichen am Anfang oder Ende
    assert not result.startswith(('.', ' ')), f"Starts with invalid char: {result}"
    assert not result.endswith(('.', ' ')), f"Ends with invalid char: {result}"

    # 5. Maximal 50 Zeichen
    assert len(result) <= 50, f"Filename too long: {len(result)} chars"

    # Optional: Ausgabe zur Sichtkontrolle (nur bei Bedarf aktivieren)
    # print(f"'{input_str}' → '{result}'")
