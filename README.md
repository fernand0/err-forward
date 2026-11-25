# err-forward
ErrBot plugin for forwarding messages

At this moment, it publish the command in a Slack channel where other bots can read and execute it. There is no prevention for several bots trying to execute the same command (no blocking).

Installation:

Go to the plugins dir of your errbot installation and clone this repo:

```
git clone https://github.com/fernand0/err-forward
```

You'll need the Slack credentials.
Credentials for Slack are stored in the file ~/.rssSlack and there is only a field with the `api-key`:

```
[Slack]
api-key:your-api-key
```

The channel used for communication is a bot config, for example:

```json
{'channel': 'general'}
```

## Configuration

The plugin reads its configuration from Errbot’s plugin config (YAML/INI). The required keys are:

| Key | Description | Example |
|-----|-------------|---------|
| `channel` | Slack (or other social) channel name used for publishing and listening. | `general` |
| `module` | Backend module that talks to the social platform. | `moduleSlack` |
| `id_post_override` | (Optional) Name of the field that stores the post identifier for deletions. Leave empty to use defaults (`ts` for Slack, `id` for Gitter, etc.). | `ts` |
| `user_name` | (Optional) Bot’s user name embedded in outgoing JSON. If empty, the OS user name is used. | `errbot-bot` |
| `user_host` | (Optional) Bot’s host label embedded in outgoing JSON. If empty, the machine hostname is used. | `my-host` |
| `bot_id` | (Optional) Stable identifier used in signed messages and key filenames. | `bot1` |
| `priv_key_path` | (Optional) PEM file containing the bot’s Ed25519 private key. | `/home/errbot/.errbot/bot1_key.pem` |

All the bots must write and read on the same channel.

## Authentication keys

Forwarded commands are signed with an Ed25519 private key. If `priv_key_path`
does not exist, ErrForward generates the key automatically when the plugin is
activated and stores it with permissions restricted to the owner. The default
filename is `<bot_id>_key.pem` (or `bot_key.pem` when no `bot_id` is configured).
The default location is Errbot’s `BOT_DATA_DIR`, then `~/.errbot`, and finally
the plugin directory.

To generate a key explicitly, run:

```bash
python - <<'PY'
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

key = ed25519.Ed25519PrivateKey.generate()
with open("/home/errbot/.errbot/bot1_key.pem", "wb") as file:
    file.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
PY
chmod 600 /home/errbot/.errbot/bot1_key.pem
```

Keep the private key secret. The corresponding public key is announced by the
bot so that peers can verify signed commands.

If you want a more detailed description of the main ideas you can read [A (non intelligent) chatbot multi-interface and distributed as a personal information manager.](https://dev.to/fernand0/a-non-intelligent-chatbot-multi-interface-and-distributed-as-a-personal-information-manager-5b2h) and of, course, do not hesitate to ask.

Chained/double forwarding is supported (e.g., `,fw !fw *status`).