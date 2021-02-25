# err-forward
ErrBot plugin for forwarding messages

At this moment, it publish the command in a Slack channel where other bots can read and execute it. There is no prevention for several bots trying to execute the same command (no blocking).

Credentials for Slack are stored in the file ~/.rssSlack and there is only a field with the `api-key`:

    [Slack]
    api-key:your-api-key

The channel used for communication is a bot config, for example:

    {'channel': 'general'}

All the bots must write and read on the same channel.

**TODO:** Double forward does not work: `,fw !fw *status `
