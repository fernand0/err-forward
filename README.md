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

All the bots must write and read on the same channel.

If you want a more detailed description of the main ideas you can read [A (non intelligent) chatbot multi-interface and distributed as a personal information manager.](https://dev.to/fernand0/a-non-intelligent-chatbot-multi-interface-and-distributed-as-a-personal-information-manager-5b2h) and of, course, do not hesitate to ask.

Chained/double forwarding is supported (e.g., `,fw !fw *status`).