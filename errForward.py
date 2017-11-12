from errbot import BotPlugin, botcmd, webhook
from slackclient import SlackClient
import configparser
import os, pwd
import datetime


class ErrForward(BotPlugin):
    """
    An Err plugin for forwarding instructions
    """

    def activate(self):
        """
        Triggers on plugin activation

        You should delete it if you're not using it to override any default behaviour
        """
        #super(Skeleton, self).activate()
        
        self.publishSlack('Msg', 'Hello!')
        super().activate()

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

    def callback_message(self, mess):
        userName = pwd.getpwuid(os.getuid())[0]
        userHost = os.uname()[1]
        if (mess.body.find(userName) == -1) or (mess.body.find(hostName) == -1):
            yield("Trying!")

    def publishSlack(self, cmd, args):
        config = configparser.ConfigParser()
        config.read([os.path.expanduser('~/'+'.rssSlack')])
    
        slack_token = config["Slack"].get('api-key')
        sc = SlackClient(slack_token)
    
        chan = "#" + str(self._check_config('channel'))
        #dateNow = datetime.datetime.now().isoformat()
        userName = pwd.getpwuid(os.getuid())[0]
        userHost = os.uname()[1]
        text = "User:%s at Host:%s. %s: '%s'" % (userName, userHost, cmd, args)
        sc.api_call(
              "chat.postMessage",
               channel=chan,
               text= text
               )

    def readSlack(self):
        config = configparser.ConfigParser()
        config.read([os.path.expanduser('~/'+'.rssSlack')])
    
        slack_token = config["Slack"].get('api-key')
        sc = SlackClient(slack_token) 

        chanList = sc.api_call("channels.list")['channels']
        for channel in chanList:
            if channel['name_normalized'] == 'general':
                theChannel = channel['id']
                history = sc.api_call( "channels.history", channel=theChannel)
                for msg in history['messages']: 
                    if msg['text'].find('')>=0: 
        
    @botcmd
    def forward(self, mess, args):
        yield(self.publishSlack('Cmd', args))

