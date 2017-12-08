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
        self.log.info('Vamos allá')

        config = configparser.ConfigParser()
        config.read([os.path.expanduser('~/'+'.rssSlack')])
    
        slack_token = config["Slack"].get('api-key')
        
        self['sc'] = SlackClient(slack_token)

        self.publishSlack('Msg', 'Hello! from %s' % self.getMyIP())
        self.start_poller(60, self.readSlack)
        self.log.info('Debería estar activo')

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

        chan = str(self._check_config('channel'))
        #dateNow = datetime.datetime.now().isoformat()
        userName = pwd.getpwuid(os.getuid())[0]
        userHost = os.uname()[1]
        text = "User:%s at Host:%s. %s: '%s'" % (userName, userHost, cmd, args)
        return(self['sc'].api_call(
              "chat.postMessage",
               channel = chan,
               text = text
               ))

    def normalizedChan(self, chan): 
        chanList = self['sc'].api_call("channels.list")['channels'] 
        for channel in chanList: 
            if channel['name_normalized'] == chan:
                return(channel['id'])
        return('')

    def readSlack(self):
        self.log.info('Start reading Slack')
        chan = self.normalizedChan(self._check_config('channel'))
        history = self['sc'].api_call( "channels.history", channel=chan)
        for msg in history['messages']: 
            self.log.info(msg['text'])
            pos = msg['text'].find('Cmd')
            if pos >= 0: 
                self.log.debug('Msg -%s-' % msg['text'][pos+5+1:-1])
                listCommands = self._bot.all_commands
                cmdM = msg['text'][pos+5+1:-1]
                if not cmdM.startswith(','): return ""
                posE = cmdM.find(' ')
                if posE > 0:
                    cmd = cmdM[1:posE]
                else:
                    cmd = cmdM[1:]
                self.log.debug('Msg-cmd -%s-' % cmd)
                if cmd in listCommands:
                    self.log.debug("I'd execute -%s- with argument -%s-" % (cmd, cmdM[len(cmd)+1:]))
                    myMsg = self._bot.build_message(cmdM)
                    botAdmin = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
                    myMsg.frm =  botAdmin
                    myMsg.to = botAdmin
                    self._bot.process_message(myMsg)
                    self.deleteSlack(chan, msg['ts'])
        self.log.info('End reading Slack')

    def deleteSlack(self, theChannel, ts):
        self['sc'].api_call("chat.delete", channel=theChannel, ts=ts) 

    @botcmd
    def forward(self, mess, args):
        self.publishSlack('Cmd', args)
        listCommands = self._bot.all_commands
        if 'sf' in listCommands:
            yield(listCommands['sf'])
        #for (name, command) in self._bot.all_commands.items():
        #    yield(name)

    @botcmd
    def myIP(self, mess, args):
        yield(self.getMyIP())
