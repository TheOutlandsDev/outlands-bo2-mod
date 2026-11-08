# BO2 multiplayer DLC readiness

The map catalog includes all 31 multiplayer maps: 14 base maps, Nuketown 2025
and 16 maps across Revolution, Uprising, Vengeance and Apocalypse.
Catalog membership does not mean the map is installed or tested.

## Current backend investigation

The inspected live host contains the 15 base/bonus main fastfiles. The 16 DLC
main fastfiles are absent from its installed game and running image.

An inspected extracted DLC archive has source recipes for all 16 maps but no
compiled `.ff`, `.ipak`, `.sabs` or `.sabl` packages. For example, Studio's recipe
references world geometry, collision, entities and sound-bank assets. Exported
props, textures and entity text alone cannot reconstruct a complete playable map
through the currently documented OAT asset import support.

Do not install these dumps as replacement map packages, or mark their maps ready
because extraction logs have no errors. Do not add missing maps to the live deck.

A separate, privately held full-game archive has been inventoried: it contains
the 16 compiled DLC main and English locale fastfiles, all four DLC texture
packages, per-map sound banks, and additional DLC faction packages. The 91
packages missing from the live game were CRC-checked while staging into a
private candidate image. This establishes a usable backend test input, not
native map/mode acceptance or client compatibility. The running image and live
DLC eligibility remain unchanged until the checks below pass.

## Required inputs

Use original compiled content from an owned PC installation, including the map
fastfiles and their required texture, sound and locale packages. Preserve package
relationships; copying only a main map fastfile is not a complete install check.
Keep commercial game content outside the public repository and source releases.

## Acceptance sequence

1. Inventory candidate content in a staging directory. The existing
   `tools/content_inventory.py --game-dir PATH` checks main-file coverage only;
   it does not prove dependency completeness, ownership or native loading.
2. Build a separate candidate game image. Keep the working image and original
   owned files intact, and use disposable state with no public network ports.
3. Load each installed DLC map in the native server. Require actual map/mode
   receipts, no missing-asset or native/script failures, the expected 16-player
   bot population, movement and increasing combat/objective counters.
4. Exercise supported modes and a normal map transition. Confirm weighted deck
   eligibility, recent-map protection and preserved native time/score limits.
   The new fail-closed gate requires passing `hosting/backend_verify.py` reports
   for **every enabled mode on each proposed map**. Prepare a private candidate
   JSON mapping each map ID to its complete reviewed list of required compiled
   package paths, including the main `.ff` and relevant texture/sound packages.
   Use `python3 -B -m hosting.dlc_gate --game-dir GAME --candidate CANDIDATE.json
   --report REPORT.json --catalog storage/t6/outlands_rotation.json
   --output dlc_acceptance.json`, repeating `--report` for all isolated runs.
   Copy the resulting private file into `/data/private/` only after reviewing
   the native results and confirming the running image contains those same files.
   This is an operator acceptance record, not proof of asset ownership or client
   rendering. A changed package hash or newly enabled, untested mode revokes
   rotation eligibility until fresh acceptance is generated.
5. Promote only accepted content, preserving private configuration and saves.
   Keep the previous image for rollback and respect connected players.
6. Have real clients with matching content join. Inspect geometry, collision,
   textures, sounds, objective locations, bot traversal and progression. Backend
   success does not establish client rendering or a complete client install.

## Tooling reference

OAT supports a useful subset of T6 assets. Its current published support table
does not provide a full raw map world/collision reconstruction path:
https://github.com/Laupetin/OpenAssetTools/blob/main/docs/SupportedAssetTypes.md
