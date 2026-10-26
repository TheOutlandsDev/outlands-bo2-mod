# Outlands local bot chat and careers

This optional worker gives the native multiplayer bots occasional short banter,
public-chat replies, and bounded two-bot exchanges. After an accepted banter line,
a different native bot can respond once to that bot's name and preceding line.
The second turn cannot start another turn. The adapter ignores bot-originated
chat notifications; conversations are scheduled from accepted deliveries rather
than an automatic reply loop. `round_end` is reserved protocol support and is not
emitted yet. Optional bot careers retain a fictional roster's cosmetic progression
and structured bot-to-bot familiarity across worker/server restarts. The model
does not control combat, read player saves, award player XP, or change unlocks.
The lobby should disclose that the
AI players are bots even when their clan tags are blank.

The worker uses Python's standard library. It calls your local Ollama instance,
with one generation at a time, four CPU threads, a 2,048-token context, and at most
48 output tokens, with an eight-second request timeout. It keeps four recent bot
lines and at most sixteen opener records for sixty seconds in memory. Neither
human nor generated chat strings are written to the career ledger. Public human
chat supplied by the GSC adapter can enter the short
model context; team/hidden chat must be excluded by that adapter.

`config.example.json` defaults to disabled. The optional hosting AI profile enables
it explicitly with `T6_CHAT_ENABLED=1` and the matching server GSC dvar. If Ollama
is absent, times out, or returns unusable text, safe canned lines keep the chat
adapter usable. Set `T6_CHAT_MODE=fallback` for canned chat without a model.
This also supports safe canned second-turn responses. Set the game dvar
`outlands_chat_dialogue 0` to disable bot-to-bot exchanges while keeping human
replies. The worker has a matching `dialogue_enabled` setting, or
`T6_CHAT_DIALOGUE_ENABLED=0` environment override. The overall
`outlands_chat_enabled 0` game switch silences all speech and clears queued work.

The first model load can exceed the timeout and use a canned fallback. Keep the
model loaded during play; the worker requests a five-minute keep-alive. Ollama's
daemon health check alone does not prove that the Outlands model has been created.

The model recipe is an Outlands prompt and runtime configuration built on
`qwen3:1.7b`. It does not contain new model weights or claim to be a model trained
from scratch. Its base weights are obtained separately by the host, outside the
GitHub source package. An existing local Ollama host can create the character
model with:

```bash
ollama create outlands-bo2-chat -f ai/Modelfile
```

Do this from the `outlands-t6` project directory after installing Ollama through
its official installation method. The hosting guide covers the contained setup;
do not publish Ollama's port or expose the game's RCON credential to clients.

Personalities live in `personalities.json`. All 48 profiles have a style, role,
temperament, motivation and speech traits. Profile keys must match the canonical
bot names in `storage/t6/bots.txt`. Unlisted names use the default chat personality
and are excluded from persistent careers. These traits guide short model replies;
the model cannot choose native combat settings or career awards.
Keep fallback lines short and friendly. Output is capped at 120 characters and
six requests per minute; cooldowns cannot be shorter than ten seconds globally
or thirty seconds per bot. Defaults allow four requests per minute,
ten seconds globally, and sixty seconds per bot. Both turns consume the same
budgets, and failures consume the cooldown too. The game adapter defaults to a
twelve-second request gap, sixty-second periodic banter, and a fourteen-second
pause after accepted banter before a possible second turn. It has matching
`outlands_chat_max_per_minute` and `outlands_chat_bot_cooldown` controls. These are
shared limits, not extra budgets for dialogue.

New worker events use a two-item queue and expire after fifteen seconds. Human
replies take priority over ambient chatter. The game keeps at most one latest
public human message for twenty seconds; a new human message cancels a queued
bot followup. A request already in flight can finish first. Dialogue also stops
if its originating bot disconnects or changes identity before dispatch. No chat
is generated without at least one human connected.

Validate and test without launching the game or contacting Ollama:

```bash
python3 ai/bridge.py --check
python3 -m unittest discover -s ai/tests -v
```

The container runs as UID/GID 10001 with a read-only mount of server state.
Careers additionally need a private writable volume mounted at `/rivals`, owned
by UID 10001 with mode 700. It reads `/data/plutonium/console.log` and a mode-600 generated credential
at `/data/private/outlands_rcon_password`. It shares the private game network
namespace so the RCON destination stays `127.0.0.1:4977`. Only loopback IPs are
accepted, and the server must whitelist that source. Neither the log nor the
secret is included in GitHub. The worker logs operational results without raw
player text, generated chat, or credentials.

Environment overrides:

| Variable | Purpose |
| --- | --- |
| `T6_CHAT_ENABLED` | Explicit `0` or `1` switch |
| `T6_CHAT_MODE` | `ollama` or `fallback` |
| `T6_CHAT_DIALOGUE_ENABLED` | Explicit `0` or `1` switch for second turns |
| `T6_CAREERS_ENABLED` | Independent explicit `0` or `1` switch for private bot careers |
| `T6_CAREERS_STATE_FILE` | Private ledger path, default `/rivals/careers.json` |
| `OLLAMA_URL` | Local/private Ollama origin, e.g. `http://ollama:11434` |
| `OLLAMA_MODEL` | Locally available model name, default `outlands-bo2-chat` |
| `T6_CHAT_LOG` | Console log path |
| `T6_CHAT_RCON_HOST` | Loopback IP only, default `127.0.0.1` |
| `T6_CHAT_RCON_PORT` | Game UDP port, default `4977` |
| `T6_CHAT_RCON_SECRET_FILE` | Private generated RCON credential path |

Transport contract, version 1:

```text
OUTLANDS_CHAT_V1|request_id|bot_slot|bot_name|kind|map|gametype|speaker|text
```

The GSC adapter prints that exact marker at the beginning of a line. Fields cannot
contain pipes or control characters. Request IDs are 1–64 ASCII letters, digits,
underscores or hyphens; bot names are 1–24 safe ASCII characters. Supported kinds
are `banter`, `reply`, `bot_reply`, and reserved `round_end`. Human context is
bounded to 240 characters. A `bot_reply` request appends `_r` to its opener's ID,
uses a different recipient bot, and includes the preceding bot's exact safe line
and name. The worker requires a matching recently submitted banter opener from
the same map/mode, admits one followup only, and rejects nested reply IDs. The
game schedules it only after validating and delivering the opener itself.
The worker tails from EOF on startup, handles log rotation, rejects malformed
records, drops large backlogs, and deduplicates the last 128 request IDs.

Chat uses this fixed command:

```text
set outlands_chat_response "request_id|bot_slot|bot_name|chat_text"
```

Chat text is reduced to ASCII letters, digits, spaces, and `. , ! ? ' -`. Quotes,
semicolons, backslashes, color codes, control characters, markup, and subsequent
lines cannot escape into the RCON command. The model never selects a command or
gets tools, RCON access, passwords, or filesystem access. The GSC adapter remains
responsible for checking the current map's pending request ID, exact slot/name,
test-client status, and expiry before calling the game's native bot chat method.

## Private bot careers

`careers_enabled` defaults to `false`. Set `T6_CAREERS_ENABLED=1` and enable the
matching game dvar `outlands_bot_careers` to retain bot careers. This runs without
Ollama and independently of `T6_CHAT_ENABLED`: disabling chat does not stop career
snapshots. Both disabled means the worker exits without opening state or secrets.
`--check` never opens or creates a ledger, even with either feature enabled.

`careers.py` accepts only the 48 configured fictional aliases and structured
native bot scoreboard samples. Each alias begins with stable, weighted fictional
experience: level 1–55 and prestige 0–10, biased toward prestige zero. Its curated
role is `rusher`, `assault`, `objective`, `support` or `marksman`. This seed is
character background; `earned_xp` starts at zero. Future validated native deltas
earn **100 × kills gained + positive score gained** career XP. Score already
includes native kill scoring; the extra kill weight is intentional for these
fictional careers. Each 5,000 XP advances one cosmetic level; level 55 wraps to
level 1 at the next prestige, capped at prestige 10 / level 55. Deaths and observed
round endings are tracked without a reward. No win/loss result is inferred.

A first `hello` or a missed-hello first snapshot establishes current counters
without awarding existing totals. A decreasing counter rebases the whole sample
without an award. An increase above 128 kills, 128 deaths or 100,000 score in one
sample also rebases without an award. These conservative limits can omit progress
after a missed interval or a native score penalty; they prevent a bad sample from
granting a large career jump. New per-connection tokens prevent a reused slot
from inheriting another connection's baseline. Out-of-order or duplicate samples
do not earn XP. Repeated original `hello` requests return the current profile
without resetting counters; this supports bounded periodic cosmetic refresh.

The worker commits the sequence, baseline and aggregate before sending a restore
response. State is atomic, mode 600, and directory-fsynced; a failed response can
be retried after a worker restart without awarding the same sample again. It
retains at most 128 connection records and 512 retired connection hashes. Replay
protection covers this bounded retention window; the log follower also starts
at EOF rather than replaying historical files. Aggregates and social counts have
numeric caps. One worker must own a ledger; sharing it between simultaneous
workers is unsupported.

The JSON file contains only allowlisted bot aliases, their derived career XP and
native bot aggregates, bounded connection metadata, and counts of acknowledged
bot-to-bot exchanges. Chat strings, human names/IDs, human saves, addresses and
credentials are excluded. Counts provide a little familiar tone without storing
what anyone said. In-memory recent lines still disappear at worker restart.
After submitting a second turn, the worker keeps at most sixteen identity-only
pending records for five seconds. It increments familiarity only when GSC emits
an exact matching request/slot/alias/kind acknowledgment after native delivery;
stale, altered or duplicate acknowledgments do nothing.
Prompt context can include the recipient bot's latest own scoreboard sample for
the current map/mode, its cosmetic career and a known bot peer's exchange count.
Scoreboard context requires a new snapshot observed by this worker process in
the last 180 seconds; persisted counters and original-hello retries cannot make
old match evidence appear current after restart. Human reply
contexts never acquire persistent human memory.

Back up the private `/rivals` volume separately while its worker is stopped; keep
it out of source packages and public diagnostics. Missing state starts a new
fictional career ledger. Corrupt data, unknown aliases, future schema versions,
symlinks, public file modes or unsafe parent directories stop the optional worker
without replacing the file. Restore a private valid backup to recover it.
Schema 1 accepts aggregate-only files with absent optional session/social caches;
the next write adds those caches without changing earned career totals.

The independent career transport is:

```text
OUTLANDS_BOT_V1|session|event_id|kind|bot_slot|alias|kills|deaths|score|map|mode
set outlands_bot_profile_response "event_id|bot_slot|alias|level|prestige|role"
OUTLANDS_CHAT_ACK_V1|request_id|bot_slot|alias|kind
```

`session` is a per-bot connection token of at most 48 safe ASCII identifier
characters. `event_id` is `session_numericsequence`, at most 64 characters, with
sequence 1–2,147,483,647. Kinds are `hello`, `snapshot`, `depart`, and `match_end`.
Only `hello` requests a profile response, and the game serializes that mailbox.
Native bot identity, exact request/slot/alias, expiry and cosmetic bounds must
pass in GSC before application. The worker's complete command surface consists
of the two fixed response dvars above; the model cannot select either command,
alter career values or write human progression.

Synthetic tests cover restart/duplicate handling, connection reuse, counter
resets/outliers, private atomic storage, corrupt state, optional-cache migration,
bounded replay caches, fixed transport and independent feature switches. Native
career restore/display and richer production chat still require host validation;
these tests do not establish client gameplay or a model's conversational quality.

Ollama API and model recipe syntax follow the [official chat API](https://docs.ollama.com/api/chat)
and [Modelfile reference](https://docs.ollama.com/modelfile). Native chat support is
documented in the [Plutonium changelog](https://plutonium.pw/docs/changelog/).
Use the [validation guide](../docs/VALIDATION.md) to check the complete event,
model/fallback, fixed mailbox, identity-validation and native delivery path.
Synthetic worker tests cannot establish GSC compilation, rendered chat or client
gameplay. Model startup latency depends on hardware and model state; test both
cold-model fallback and warm-model replies.
