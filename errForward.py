from errbot import BotPlugin, botcmd, webhook
from errbot.templating import tenv
from slackclient import SlackClient
import configparser
import os, pwd
import datetime
import inspect
import re
import json
import urllib.parse

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

        self.publishSlack(typ = 'Msg', args = 'Hello! from %s' % self.getMyIP())
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

    def publishSlack(self, usr="", host="", frm="", mess = "", typ ="", cmd = "", args =""):

        if mess:
            frm = mess.frm
        else:
            frm = "-"

        if args and typ != 'Msg':
            args = urllib.parse.quote(args)

        msg = {'userName': usr, 'userHost': host, 
                'frm': str(frm), 'typ': typ, 'cmd': cmd, 'args': args }
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
                self.log.info("Msg: %s" % msg)
                msgJ = json.loads(msg['text'])
                argsJ = msgJ['args']
                userNameJ = msgJ['userName'] 
                userHostJ = msgJ['userHost']
                frmJ = msgJ['frm']
                typJ = msgJ['typ']
                cmdJ = msgJ['cmd']
                argsJ = msgJ['args']
                self.log.info("End Converting")
                if argsJ and (typJ != 'Msg'):
                    self.log.debug("Reply args before: %s " % argsJ)
                    argsJ = urllib.parse.unquote(argsJ)
                    self.log.debug("Reply args after: %s " % argsJ)
                    self.log.debug("Msg args after: %s " % msgJ)
    
                if typJ == 'Cmd':                    
                    # It's a command
                    listCommands = self._bot.all_commands
                    if cmdJ.startswith(self._bot.bot_config.BOT_PREFIX): 
                        # Consider avoiding it (?)
                        # Maybe we could also have separated the command from
                        # args
                        cmdJ = cmdJ[1:]
    
                        self.log.debug("Cmd: %s"% cmdJ)
                        #self.log.debug("Cmd: %s"% listCommands)
                        if cmdJ in listCommands:
                            self.log.debug("I'd execute -%s- with argument -%s-"
                                    % (cmdJ, argsJ))
                            method = listCommands[cmdJ]                   
                            self.log.debug("template -%s-" % method._err_command_template)
                            txtR = ''
                            if inspect.isgeneratorfunction(method): 
                                replies = method("", argsJ) 
                                for reply in replies: 
                                    if isinstance(reply, str):
                                        txtR = txtR + '\n' + reply 
                            else: 
                                reply = method("", argsJ) 
                                if isinstance(reply,str):
                                    txtR = txtR + reply
                                else:
                                    # What happens if ther is no template?
                                    # https://github.com/errbotio/errbot/blob/master/errbot/core.py
                                    self.log.debug("tenv -> %s%s" % (method._err_command_template,'.md'))
                                    txtR = txtR + tenv().get_template(method._err_command_template+'.md').render(reply)

                            self.publishSlack(typ = 'Rep', usr= userNameJ,
                                    host=userHostJ, frm = frmJ, args = txtR)
    
                            self.deleteSlack(chan, msg['ts'])
                elif typJ == 'Rep':                    
                    # It's a reply
                    self.log.info("Is it for me?")
                    self.log.debug("User: %s - %s | %s - %s" %
                            (userNameJ, self['userName'], 
                                userHostJ, self['userHost']))
                    if ((userNameJ == self['userName']) 
                            and (userHostJ == self['userHost'])):
                        # It's for me
                        self.log.info("It's for me")
                        replies = argsJ 
                        for reply in replies.split('\n'):
                            self.log.debug("FRm",frmJ)
                            self.log.debug("Reply: %s " % reply)
                            if not (frmJ == '-'):
                                msgTo = self._bot.build_identifier(frmJ)
                            else:
                                msgTo = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
                            if reply.startswith('{'):
                                # Is it a dictionary?
                                reply = reply.replace('_','\_')

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

    def forwardCmd(self, mess, args):
        self.log.debug("Begin forward %s"%mess)
        if args.find(' ') >= 0:
            cmd, argsS = args.split()
        else:
            cmd = args
            argsS = ""
        self.publishSlack(mess=mess, usr=self['userName'], host= self['userHost'], typ = 'Cmd' , cmd = cmd, args = argsS)
        self.log.debug("End forward %s"%mess)

    @botcmd
    def forward(self, mess, args):
        yield self.forwardCmd(mess, args)

    @botcmd
    def fw(self, mess, args):
        yield self.forwardCmd(mess, args)

    @botcmd
    def myIP(self, mess, args):
        yield(self.getMyIP())
        yield(end())
