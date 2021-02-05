# err-forward
ErrBot plugin for forwarding messages

At this moment, it publish the command in a Slack channel where other bots can read and execute it. There is no prevention for several bots trying to execute the same command (no blocking).

Installation:

Go to the plugins dir of your errbot installation and clone this repo:

`git clone https://github.com/fernand0/err-forward`

You'll need the Slack credentials.
Credentials for Slack are stored in the file ~/.rssSlack and there is only a field with the `api-key`:

    [Slack]
    api-key:your-api-key

The channel used for communication is a bot config, for example:

    {'channel': 'general'}

All the bots must write and read on the same channel.

If you want a more detailed description of the main ideas you can read [A (non intelligent chatbot multi-interface and distributed as a personal information manager.](https://dev.to/fernand0/a-non-intelligent-chatbot-multi-interface-and-distributed-as-a-personal-information-manager-5b2h) and of, course, do not hesitate to ask.
