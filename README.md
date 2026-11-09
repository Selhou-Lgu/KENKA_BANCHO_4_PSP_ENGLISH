# KENKA_BANCHO_4_PSP_ENGLISH
yeah basically kenka bancho for psp used claude code for translation so it might be kinda buggy but yeah enjoy the game i guess :D

---

Fan-made English patch for **Kenka Banchou 4: Ichinen Sensou** (喧嘩番長4 一年戦争, PSP, ULJS00268).

This repo has **no game files**: no ISO, no game data. You need your own copy of the Japanese ISO. The patch only stores the differences.

## What's translated

- **Dialogue and story text:** all of it (machine-translated, then cleaned up)
- **Menus and interface:** pause menu, My Room, status, items, phone, outfits, moves, shops, options
- **Names:** all students, crews, schools, the 47 prefecture bosses
- **Items, weapons, clothing, hairstyles, food, furniture, locations, fight moves**
- **System messages:** saving, install, network, mahjong and poker rules
- **Menu graphics:** about 90 textures redrawn in English (menu headers, buttons, stamps, popups, report cards, title-screen options and more)
- **Half-width font:** English text displays normally instead of spaced out

**Not translated (on purpose):** shop signs, posters and banners in the 3D town, and the title logo. They're scenery.

## How to patch

1. Get your Japanese ISO. It should match:
   - **CRC32:** `932A69E3`
   - **MD5:** `abdf6c3f1e129dfc471f8940c724afeb`
   - **SHA-1:** `6c9740416f5d693602b89be86b0572fc45de2704`
2. Download `KenkaBanchou4_English.xdelta` from the **[Releases](../../releases)** page.
3. Apply it with one of these:
   - **Windows (easy):** [Delta Patcher](https://github.com/marco-calautti/DeltaPatcher). Pick the original ISO, pick the `.xdelta` file, press Apply.
   - **Command line:**
     ```
     xdelta3 -d -s "Kenka Banchou 4 - Ichinen Sensou (Japan, Asia).iso" KenkaBanchou4_English.xdelta "Kenka Banchou 4 (English).iso"
     ```
   The patched ISO's SHA-1 should be `d4d3006090dd639c625ca9c17a4d35af94bf4b78`.
4. Play the new ISO in **PPSSPP** (tested there) or on a PSP with custom firmware.

## Important

- **Don't use the in-game "media install" option.** The install data is the original Japanese copy, so the game would load Japanese text from it. If you already installed, turn install data **OFF** in Options, or delete it.
- The patched ISO is bigger (~1.25 GB) than the original. That's normal.

## Known issues / please report

- Machine translation, so some lines may read oddly, especially slang.
- About 10 very long dialogue lines may run past their text box.
- **Smack-talk (tanka) battles** draw their big text with a separate font, so English there may look wrong.
- **Mahjong** rule text uses the minigame's own font and hasn't been fully tested.
- Character name romanizations are best guesses.

Found a bug? Open an issue with a screenshot and where it happened.

## Building from source (advanced)

`tools/` has the Python toolchain that made this patch: archive unpacker/repacker, LZSS codec, text codec, half-width font builder, EBOOT string patcher, texture editor and ISO patcher. `translation/eboot_*.json` and `tex/spec.json` hold the menu/name/texture translations.

To rebuild you also need things this repo can't include: your own ISO, a decrypted EBOOT (dumped with PPSSPP), and the dialogue translation spreadsheet (left out because it contains the game's full script). See the scripts' docstrings for the steps.

## Credits

- Project and dialogue translation: **Selhou-Lgu**
- Tools, menu/name translation and graphics: made with [Claude Code](https://claude.com/claude-code)
- Kenka Banchou 4 © Spike. This is an unofficial fan project, not affiliated with Spike. Please support the official release.
