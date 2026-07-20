# Bundled Noto fonts

MCLab bundles these variable fonts from the Google Fonts repository:

- `NotoSansKR[wght].ttf` — matplotlib plot text
- `NotoSansMono[wdth,wght].ttf` — source for the static mono instances

Both are distributed under the SIL Open Font License in `OFL.txt`.

The desktop app registers the static single-weight instances in `static/`
instead of the variable originals: several Qt/DirectWrite releases resolve
non-default variable weights (`wght=600`/`700`) to mismatched glyph indexes on
Windows, which rendered bold Korean labels as the wrong syllables. Regenerate
the static set from the variable originals with:

```text
.venv/bin/python scripts/build_static_fonts.py
```

Source URLs:

- https://github.com/google/fonts/tree/main/ofl/notosanskr
- https://github.com/google/fonts/tree/main/ofl/notosansmono

Pinned file SHA-256 values:

```text
194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252  NotoSansKR[wght].ttf
2cb2adb378a8f574213e23df697050b83c54c27df465a2015552740b2769a081  NotoSansMono[wdth,wght].ttf
1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9  OFL.txt
4609a7b62a6da24cae3a8b73ecde7003581b8f60662d60cc8f55a3793de07763  static/NotoSansKR-Regular.ttf
4546aaa0be877f52e67a6f8b14e708a654d34f6ff921d7a469ec7ed8d3bf7080  static/NotoSansKR-Medium.ttf
ce82b8c9368de1a2c82c1fc78822e0277268ff95859b4e26e9996c598bc9745a  static/NotoSansKR-SemiBold.ttf
cf93c6acfa4c4adcb580d156aa46fc3614ed0310f1e2ef23b5954476e85c872e  static/NotoSansKR-Bold.ttf
c886cba7994069f6ba1c1a97c49d3aff58a3c131e6b4710237a452bd67a845a4  static/NotoSansMono-Regular.ttf
49c8761ad973eac5f2904c0a07ee9532858b610a51f4c06a7c9c5354ea069ea6  static/NotoSansMono-Bold.ttf
```
