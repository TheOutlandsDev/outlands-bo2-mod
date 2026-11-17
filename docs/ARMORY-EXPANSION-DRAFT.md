# Outlands native armory expansion — design draft

Status: research and proposed acceptance gates; no imported content implemented.
The portable challenge rule now has a separately installed native event-adapter
preview and original Lua menu source. Neither is enabled in the live setup;
human event provenance, client loading/rendering, camo assets and equipment
grants remain separate acceptance gates. See [challenge preview](CHALLENGES.md)
and the [native menu source](../client-preview/README.md).
Priority: preserve the restored vanilla match limits and validate installed DLC
maps before expanding the live content rotation. Preserve the stable combat
controller.

## Intended experience

Extend BO2 through its own Lua/LUI menus, visual language, controls and class
flow. Add weapons gradually without replacing existing weapons, camos or earned
progression. A matching client content package will be necessary; server-side
scripts alone cannot supply new rendered weapon assets.

## Player-facing menu decision

The shipping experience should use BO2's normal menu navigation and visual
language, with Outlands entries where players already expect them:

- Create-a-Class: owned weapons, attachments and camos beside stock choices,
  each with a preview, lock reason and equip action.
- Barracks/Challenges: Outlands career, weapon mastery and earned rewards.
- After-action report: verified challenge progress and unlock notifications.
- In-match class selection: edit a future spawn only if a client-side menu hook
  can preserve stock input, class validation and the current life's inventory.

This is a client-menu integration target, not a claim that the existing GSC HUD
editor implements those screens. The HUD and Tailscale portal can remain optional
development and account views; they cannot substitute for Create-a-Class
acceptance. Menu presentation should read versioned Outlands catalog and progress
data. The trusted server remains authoritative for kills, unlocks and equipment
grants, and native BO2 saves remain untouched until a separately verified format
and migration path exists.

Prove one stock-weapon Outlands Dusk camo entry first: a locked preview in the
normal class flow, progress from native server-observed gameplay, an equip choice,
restart persistence and matching appearance on a second client. Backend tests
can validate the catalog, ownership and event rules, but cannot establish that
T6 loads the client menu hook, that stock controllers work, or that an original
asset replicates. If the hook or representation fails, keep this feature gated
and continue using the stable stock menus; do not simulate it with save edits.

### Client menu feasibility gate

Plutonium's public T6 raw-assets repository contains Lua/LUI menu rawfiles and
a `plutonium_mp.zone` manifest that packages them. Its `build.bat` invokes
OpenAssetTools Linker against the installed `ui_mp.ff`. The published
`ui_mp/t6/hud/class.lua` shows a stock in-match Choose Class action, but this
is the pause/class menu, not proof that a third-party package can extend the
normal Create-a-Class camo list. The local owned game has `zone/all/ui_mp.ff`;
no Linker executable or Lua compiler was found on the development host during
this review. No Outlands client menu package has been built or installed.

The first disposable client test should therefore check loading before adding
rewards: back up the current Plutonium client content, install an original
Outlands-only Lua rawfile in a test package, show a clearly labeled locked
Outlands Dusk entry beside the stock AN-94 camos, navigate it with the normal
menu controls, then remove the package and confirm stock menus return. Do not
replace Plutonium's own fastfile or publish extracted BO2 menu sources. A
successful static build is only a package check; a real client must verify the
entry, focus, back behavior and lack of impact on existing camos. Server kill
event wiring, unlock persistence and second-client appearance are later gates.

Plutonium documents simple texture overrides as local-only, so an `.iwi`
replacement alone cannot establish a shared new camo. Its general FastDL
documentation also requires a publicly reachable HTTP download server; verify
the distribution model separately before relying on it for this tailnet-only
service. Use an opt-in client installer package for the first test.

## Subsequent imported-weapon milestone

After the stock-weapon camo proof, add one imported weapon using the same
menu, asset and award boundaries. The
COD4 M40A3 is a candidate because a public T6 port provides a concrete reference;
its compatibility, reuse terms and save behavior have not been accepted here.

1. Reach the weapon and camo through Create-a-Class.
2. Display the preview, locked requirement and challenge progress.
3. Earn the camo using native server-observed eligible gameplay. The current
   AN-94 rule is only a backend preview; imported-weapon eligibility is undecided.
4. Equip it, restart the client and server, and retain the selection.
5. Confirm a second client sees the correct world model and camo, while stock
   weapons, camos, attachments, class selections and progression remain intact.

New IDs must preserve existing meanings. Do not copy a reference mod's complete
renumbered stats table over the current catalog. Additional item/camo capacity,
native validation, stat schemas and network representation are research gates.

## Proposed implementation boundaries

- Lua/LUI: native menu navigation, lock descriptions, previews and class editing.
- GSC: native event observations, eligibility checks and validated spawn grants.
- Python: versioned custom catalog, account-bound progression, idempotent awards
  and persistent selections. Existing native BO2 saves remain separate.
- OpenAssetTools: pinned asset conversion/build pipeline and dependency checks.
- Rust: optional installer tooling; not a prerequisite for the prototype.

## First challenge-rule preview

`ai/camo_challenge.py` provides a small, portable proof of the award boundary.
It uses the stock AN-94 (`an94_mp`) and an original reserved Outlands Dusk camo
ID, not the proposed imported weapon. The preview requires 25 confirmed enemy
headshot kills by a human with that weapon. It accepts only events supplied by a
trusted server adapter with a private salted player key, a session and monotonic
event sequence. Browser requests, chat, scoreboard totals and client assertions
must never become award evidence. The isolated native adapter uses the existing
additional death-callback list and a private worker credential; its all-bot
test verifies exclusions, not real-human awards.

The rule records progress and event receipts in an owned private file using an
atomic replacement. Duplicate native events count once; changed replays and
ineligible kills do not advance. The file stores only hashed player keys and
event receipts, not game identities. A single writer is required until a real
service or transactional store owns the ledger. Tests use synthetic trusted
events to check eligibility, idempotence, restart persistence, player separation,
tampered state and interrupted writes. They do not prove a visible or equippable
camo, native event provenance, multi-server synchronization or multiplayer
appearance. The source release includes the rule and tests; it does not add
anything to BO2 saves or a deployed server.

The existing Armory supports a bounded base-class subset. Its HUD editor and
backend rules do not establish native Create-a-Class support for imported guns,
attachments or camos. Mid-match editing should save a revision and apply it on
the next normal respawn, without replenishing current-life weapons or streaks.

## Later progression concepts

- Repeatable Outlands prestige in a separate career ledger, keeping native BO2
  values within verified bounds. Historical prestige badges are a candidate;
  the exact historical content scope remains to be clarified.
- Original Dark Matter-inspired mastery after Gold on every weapon in an
  explicitly versioned collection. Later additions should not revoke an earned
  reward. Prove a static camo before investigating animated materials.
- Add weapons individually after model, animation, sound, balance, attachment,
  menu, persistence and multiplayer acceptance. An unlimited arsenal is not a
  demonstrated engine capability.

## Backend and client acceptance

Extend the existing isolated native runner and portable Armory tests:

- Audit asset dependencies, hashes, ID uniqueness and package compatibility.
- Reject wrong-weapon, ineligible, replayed and duplicate gameplay events.
- Check locked-item refusal, account separation and exactly-once reward grants.
- Check persistence, interrupted writes, revision conflicts and rollback.
- Read back native weapons, ammo and supported attachments across respawns.
- Run stock progression and class regressions alongside the new feature.

Backend/native receipts cannot accept menu layout, first-person animations,
materials, sound quality or another real client seeing the content. Those need
Windows/Linux client tests and a two-client multiplayer check.

## DLC content prerequisite

Extracted meshes and textures are not an installable multiplayer map. Validate
compiled owned map fastfiles and required texture/sound packages separately.
Add only maps that pass isolated native loading, bot movement/combat and mode
checks to the live weighted rotation. Real clients must also have compatible
map content. Missing or failed candidates must remain excluded.

## Research references

- https://github.com/Laupetin/OpenAssetTools
- https://github.com/Laupetin/OpenAssetTools/blob/main/docs/SupportedAssetTypes.md
- https://github.com/OpenAssetTools/Examples/tree/main/zone_raw/t6_xmodel_import
- https://github.com/SadSlothXL/t6-ports
- https://github.com/plutoniummod/client-raw-assets
- https://github.com/plutoniummod/client-raw-assets/blob/master/t6/zone_source/plutonium_mp.zone
- https://github.com/plutoniummod/client-raw-assets/blob/master/t6/build.bat
- https://github.com/plutoniummod/client-raw-assets/blob/master/t6/raw/ui_mp/t6/hud/class.lua
- https://plutonium.pw/docs/modding/loading-textures/
- https://plutonium.pw/docs/server/t6/fastdl/

Keep commercial asset dumps, private inventories, credentials, accounts and raw
runtime diagnostics outside the public source and release packages.
