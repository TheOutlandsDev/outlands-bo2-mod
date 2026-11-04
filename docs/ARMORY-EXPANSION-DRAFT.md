# Outlands native armory expansion — design draft

Status: research and proposed acceptance gates; no imported content implemented.
Priority: restore durable vanilla match limits and validate installed DLC maps
before beginning this expansion. Preserve the stable combat controller.

## Intended experience

Extend BO2 through its own Lua/LUI menus, visual language, controls and class
flow. Add weapons gradually without replacing existing weapons, camos or earned
progression. A matching client content package will be necessary; server-side
scripts alone cannot supply new rendered weapon assets.

## Proposed first milestone

One imported weapon, one original Outlands camo, one gameplay challenge. The
COD4 M40A3 is a candidate because a public T6 port provides a concrete reference;
its compatibility, reuse terms and save behavior have not been accepted here.

1. Reach the weapon and camo through Create-a-Class.
2. Display the preview, locked requirement and challenge progress.
3. Earn the camo using native server-observed eligible gameplay. A provisional
   challenge is 25 headshots with this weapon; final eligibility is undecided.
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
- https://plutonium.pw/docs/modding/loading-textures/

Keep commercial asset dumps, private inventories, credentials, accounts and raw
runtime diagnostics outside the public source and release packages.
