from errbot import BotPlugin, botcmd, webhook
from slackclient import SlackClient
import configparser
import os, pwd
import datetime
import inspect
import re
import json

def end(msg=""):
    return("END"+msg)

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
        self['chan'] = str(self._check_config('channel'))
        self['userName'] = pwd.getpwuid(os.getuid())[0]
        self['userHost'] = os.uname()[1]

        self.publishSlack(cmd = 'Msg', args = 'Hello! from %s' % self.getMyIP())
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
        userName = self['userName']
        userHost = self['userHost']
        if (mess.body.find(userName) == -1) or (mess.body.find(hostName) == -1):
            yield("Trying!")

    def publishSlack(self, usr="", host="", frm="", mess = "", cmd ="", args =""):

        if mess:
            frm = mess.frm
        else:
            frm = "-"

        msg = {'userName': usr, 'userHost': host, 
                'frm': str(frm), 'cmd': cmd, 'args': args }
        msgJ = json.dumps(msg)

        chan = self['chan']
        self['sc'].api_call( "chat.postMessage", channel = chan, text = msgJ)

    def normalizedChan(self, chan): 
        chanList = self['sc'].api_call("channels.list")['channels'] 
        for channel in chanList: 
            if channel['name_normalized'] == chan:
                return(channel['id'])
        return('')

    def readSlack(self):
        # Don't put yield in this function!
        self.log.info('Start reading Slack')

        chan = self.normalizedChan(self._check_config('channel'))
        history = self['sc'].api_call("channels.history", channel=chan)

        for msg in history['messages']: 
            try:
                self.log.info("Converting args")
                msgJ = json.loads(msg['text'])
                argsJ = msgJ['args']
                userNameJ = msgJ['userName'] 
                userHostJ = msgJ['userHost']
                frmJ = msgJ['frm']
                cmdJ = msgJ['cmd']
                argsJ = msgJ['args']
                self.log.info("End Converting")
    
                if cmdJ == 'Cmd':                    
                    # It's a command
                    listCommands = self._bot.all_commands
                    if argsJ.startswith(self._bot.bot_config.BOT_PREFIX): 
                        # Consider avoiding it (?)
                        # Maybe we could also have separated the command from
                        # args
                        posE = argsJ.find(' ')
                        if posE > 0:
                            cmd = argsJ[1:posE]
                        else:
                            cmd = argsJ[1:]
                        args = argsJ[len(cmd)+1+1:]
    
                        self.log.debug("Cmd: %s"% cmd)
                        if cmd in listCommands:
                            self.log.debug("I'd execute -%s- with argument -%s-"
                                    % (cmd, args))
                            method = listCommands[cmd]                   
                            txtR = ''
                            if inspect.isgeneratorfunction(method): 
                                replies = method("", args) 
                                for reply in replies: 
                                    if isinstance(reply, str):
                                        txtR = txtR + '\n' + reply 
                            else: 
                                reply = method("", args) 
                                if isinstance(reply,str):
                                    txtR = txtR + reply
                                else:
                                    txtR = txtR + str(reply)

                            self.publishSlack(cmd = 'Rep', usr= userNameJ,
                                    host=userHostJ, frm = frmJ, args = txtR)
    
                            self.deleteSlack(chan, msg['ts'])
                elif cmdJ == 'Rep':                    
                    # It's a reply
                    if ((userNameJ == self['userName']) 
                            and (userHostJ == self['userHost'])):
                        # It's for me
                        replies = argsJ 
                        for reply in replies.split('\n'):
                            self.log.debug("FRm",frmJ)
                            if not (frmJ == '-'):
                                msgTo = self._bot.build_identifier(frmJ)
                            else:
                                msgTo = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])

                            self.send(msgTo, '{0}'.format(reply))

                        self.deleteSlack(chan, msg['ts'])
                    #else
                    # Maybe we could clean old messages here?
                    # Hello
                    # Messages not executed
                    # ...
            except:
                self.log.info("Error in msg: %s" % msg)
        self.log.info('End reading Slack')

    def deleteSlack(self, theChannel, ts):
        self['sc'].api_call("chat.delete", channel=theChannel, ts=ts) 

    @botcmd
    def forward(self, mess, args):
        self.log.debug("Begin forward %s"%mess)
        self.publishSlack(mess=mess, usr=self['userName'], host= self['userHost'], cmd = 'Cmd' , args = args)
        self.log.debug("End forward %s"%mess)

    @botcmd
    def myIP(self, mess, args):
        yield(self.getMyIP())
        yield(end())
