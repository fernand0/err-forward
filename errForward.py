from errbot import BotPlugin, botcmd, webhook
from slackclient import SlackClient
import configparser
import os, pwd
import datetime


class ErrForward(BotPlugin):
    """
    An Err plugin for forwarding instructions
    """

    def getMyIP(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('google.com', 0))
        return(s.getsockname()[0])
         
    def activate(self):
        """
        Triggers on plugin activation

        You should delete it if you're not using it to override any default behaviour
        """
        #super(Skeleton, self).activate()
        
        super().activate()
        self.publishSlack('Msg', 'Hello! from %s' % self.getMyIP())
        self.start_poller(60, self.readSlack)

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
        return(sc.api_call(
              "chat.postMessage",
               channel=chan,
               text= text
               ))
    
    def readSlack(self):
        config = configparser.ConfigParser()
        config.read([os.path.expanduser('~/'+'.rssSlack')])
    
        slack_token = config["Slack"].get('api-key')
        sc = SlackClient(slack_token) 
        self.publishSlack('In', 'reading')

        chanList = sc.api_call("channels.list")['channels']
        chan = "#" + str(self._check_config('channel'))
        for channel in chanList:
            if channel['name_normalized'] == chan:
                theChannel = channel['id']
                history = sc.api_call( "channels.history", channel=theChannel)
                for msg in history['messages']: 
                    pos = msg['text'].find('Cmd')
                    if pos >= 0: 
                        self.publishSlack('Msg', msg['text'][pos+5+1:-1])      
                        yield(msg['ts'])
                        self.deleteSlack(chan, msg['ts'])

    def deleteSlack(self, theChannel, ts):
        config = configparser.ConfigParser()
        config.read([os.path.expanduser('~/'+'.rssSlack')])
    
        slack_token = config["Slack"].get('api-key')
        sc = SlackClient(slack_token) 
        sc.api_call("chat.delete", channel=theChannel, ts=ts) 

    @botcmd
    def forward(self, mess, args):
        yield(self.publishSlack('Cmd', args))
        yield(type(self._bot.all_commands.items()))
        yield(type(self._bot.all_commands.keys()))
        listCommands = self._bot.all_commands
        if 'sf' in listCommands:
            yield(listCommands['sf'])
        #for (name, command) in self._bot.all_commands.items():
        #    yield(name)

    @botcmd
    def myIP(self, mess, args):
        yield(self.getMyIP())
