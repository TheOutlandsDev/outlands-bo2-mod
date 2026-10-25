# Outlands local bot chat

This optional worker gives the native multiplayer bots occasional short banter
and public-chat replies. The current game adapter emits those two event types;
`round_end` is reserved protocol support and is not emitted yet. It does not control their combat,
read player saves, award XP, or change unlocks. The lobby should disclose that the
AI players are bots even when their clan tags are blank.

The worker uses Python's standard library. It calls your local Ollama instance,
with one generation at a time, four CPU threads, a 2,048-token context, and at most
48 output tokens, with an eight-second request timeout. It keeps four recent bot lines in memory and stores no chat
history itself. Public human chat supplied by the GSC adapter can enter the short
model context; team/hidden chat must be excluded by that adapter.

`config.example.json` defaults to disabled. The optional hosting AI profile enables
it explicitly with `T6_CHAT_ENABLED=1` and the matching server GSC dvar. If Ollama
is absent, times out, or returns unusable text, safe canned lines keep the chat
adapter usable. Set `T6_CHAT_MODE=fallback` for canned chat without a model.

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

Personalities live in `personalities.json`. Profile keys must match the canonical
bot names in `storage/t6/bots.txt`. Unlisted names use the default personality.
Keep fallback lines short and friendly. Configuration can reduce message volume;
it cannot exceed 120 characters, six messages per minute, a 10-second global
cooldown, or a 30-second per-bot cooldown. Defaults are more restrained: three
messages per minute, 25 seconds globally, and 90 seconds per bot. New events use a
two-item queue and expire after 15 seconds. Failures consume the cooldown too.

Validate and test without launching the game or contacting Ollama:

```bash
python3 ai/bridge.py --check
python3 -m unittest discover -s ai/tests -v
```

The container runs as UID/GID 10001 and needs only a read-only mount of server
state. It reads `/data/plutonium/console.log` and a mode-600 generated credential
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
are `banter`, `reply`, and `round_end`. Human context is bounded to 240 characters.
The worker tails from EOF on startup, handles log rotation, rejects malformed
records, drops large backlogs, and deduplicates the last 128 request IDs.

The only command the worker can submit is:

```text
set outlands_chat_response "request_id|bot_slot|bot_name|chat_text"
```

Chat text is reduced to ASCII letters, digits, spaces, and `. , ! ? ' -`. Quotes,
semicolons, backslashes, color codes, control characters, markup, and subsequent
lines cannot escape into the RCON command. The model never selects a command or
gets tools, RCON access, passwords, or filesystem access. The GSC adapter remains
responsible for checking the current map's pending request ID, exact slot/name,
test-client status, and expiry before calling the game's native bot chat method.

Ollama API and model recipe syntax follow the [official chat API](https://docs.ollama.com/api/chat)
and [Modelfile reference](https://docs.ollama.com/modelfile). Native chat support is
documented in the [Plutonium changelog](https://plutonium.pw/docs/changelog/).
The Linux container deployment has passed a live end-to-end check with one human
and eleven native bots. The local Outlands model returned a synthetic test line
in 4.51 seconds. During play, the worker submitted four responses: the first used
the cold-start fallback and the next three came from Ollama. Matching game-side
acknowledgments confirmed native bot delivery for both periodic banter and a
public human-chat reply. This checks the full event, generation, fixed mailbox,
identity validation, and native chat path. Windows client gameplay remains
untested; the worker itself runs in the Linux hosting container.
