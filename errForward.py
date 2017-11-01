from errbot import BotPlugin, botcmd, webhook
from slackclient import SlackClient
import configparser
import os


class ErrForward(BotPlugin):
    """
    An Err plugin for forwarding instructions
    """

    #def activate(self):
    #    """
    #    Triggers on plugin activation

    #    You should delete it if you're not using it to override any default behaviour
    #    """
    #    super(Skeleton, self).activate()

    #def deactivate(self):
    #    """
    #    Triggers on plugin deactivation

    #    You should delete it if you're not using it to override any default behaviour
    #    """
    #    super(Skeleton, self).deactivate()

    def get_configuration_template(self):
        """
        """
        return {'channel': "general"
               }

    def _check_config(self, option):

        # if no config, return nothing
        if self.config is None:
            return None
        else:
            # now, let's validate the key
            if option in self.config:
                return self.config[option]
            else:
                return None

    @botcmd
    def forward(self, mess, args):
        config = configparser.ConfigParser()
        config.read([os.path.expanduser('~/'+'.rssSlack')

        slack_token = config["Slack"].get('api-key')
        sc = SlackClient(slack_token)

        chan = "#" + str(self._check_config('channel'))
        yield(chan)
        yield(sc.api_call(
          "chat.postMessage",
           channel=chan,
           text= args
           ))

