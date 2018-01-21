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
        self.log.info("Let's go")

        config = configparser.ConfigParser()
        config.read([os.path.expanduser('~/'+'.rssSlack')])
    
        slack_token = config["Slack"].get('api-key')
        
        self['sc'] = SlackClient(slack_token)
        self['chan'] = str(self._check_config('channel'))
        self['userName'] = pwd.getpwuid(os.getuid())[0]
        self['userHost'] = os.uname()[1]

        self.publishSlack(typ = 'Msg', args = 'Hello! from %s' % self.getMyIP())
        self.start_poller(60, self.readSlack)
        self.log.info('ErrForward has been activated')

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

        if not frm: 
            if mess: 
                frm = mess.frm 
            elif frm: 
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

    def extractArgs(self, msg):
        self.log.info("Converting args")
        self.log.info("Msg: %s" % msg)

        if True:
            msgJ = json.loads(msg['text'])
            
            if msgJ['args'] and (msgJ['typ'] != 'Msg'):
                # Unquoting the args
                self.log.debug("Reply args before: %s " % msgJ['args'])
                tmpJ = urllib.parse.unquote(msgJ['args'])
                msgJ['args'] = tmpJ
                self.log.debug("Reply args after: %s " % msg['args'])
                self.log.debug("Reply args after: %s " % msg['frm'])
                self.log.info("End Converting")
        else:
            self.log.info("Error Converting: %s" % msg)
            msgJ = ""
        return(msgJ)

    def manageCommand(self, chan, msgJ, msg):
        self.log.info("Starting manage command")
        listCommands = self._bot.all_commands
        if msgJ['cmd'].startswith(self._bot.bot_config.BOT_PREFIX): 
            # Consider avoiding it (?)
            # Maybe we could also have separated the command from
            # args
            cmd = msgJ['cmd'][len(self._bot.bot_config.BOT_PREFIX):]

            self.log.debug("Cmd: %s"% cmd)
            if cmd in listCommands:
                self.log.debug("I'd execute -%s- args -%s-" 
                        % (cmd, msgJ['args']))
                method = listCommands[cmd]                   
                self.log.debug("template -%s-" 
                        % method._err_command_template)
                txtR = ''
                if inspect.isgeneratorfunction(method): 
                    replies = method("", msgJ['args']) 
                    for reply in replies: 
                        if isinstance(reply, str):
                            txtR = txtR + '\n' + reply 
                else: 
                    reply = method("", msgJ['args']) 
                    if isinstance(reply,str):
                        txtR = txtR + reply
                    else:
                        # What happens if ther is no template?
                        # https://github.com/errbotio/errbot/blob/master/errbot/core.py
                        self.log.debug("tenv -> %s%s" 
                                % (method._err_command_template,
                                    '.md'))
                        txtR = txtR + tenv().get_template(method._err_command_template+'.md').render(reply)

                self.publishSlack(typ = 'Rep', usr= msgJ['userName'],
                        host=msgJ['userHost'], frm = msgJ['frm'], args = txtR)
        
                self.deleteSlack(chan, msg['ts'])
        self.log.info("End manage command")

    def manageReply(self, chan, msgJ, msg):
        self.log.info("Starting manage command")
        self.log.info("Is it for me?")
        self.log.debug("User: %s - %s | %s - %s" %
                (msgJ['userName'], self['userName'], 
                    msgJ['userHost'], self['userHost']))
        if ((msgJ['userName'] == self['userName']) 
                and (msgJ['userHost'] == self['userHost'])):
            # It's for me
            self.log.info("Yes. It's for me")
            replies = msgJ['args'] 
            if not (msgJ['frm'] == '-'):
                msgTo = self._bot.build_identifier(msgJ['frm'])
            else:
                msgTo = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
            # Escaping some markdown. Maybe we will need more
            replies = replies.replace('_','\_')
            
            self.send(msgTo, replies)
            self.deleteSlack(chan, msg['ts'])
        self.log.info("End manage reply")

    def readSlack(self):
        # Don't put yield in this function!
        self.log.info('Start reading Slack')

        chan = self.normalizedChan(self._check_config('channel'))
        history = self['sc'].api_call("channels.history", channel=chan)

        for msg in history['messages']: 
            msgJ = self.extractArgs(msg) 
            if ('typ' in msgJ):
                if msgJ['typ'] == 'Cmd':                    
                    # It's a command 
                    self.manageCommand(chan, msgJ, msg) 
                elif msgJ['typ'] == 'Rep':                    
                    # It's a reply 
                    self.manageReply(chan, msgJ, msg)
            #else
                # Maybe we could clean old messages here?
                # Hello
                # Messages not executed
                # ...
            #except:
            #    self.log.info("Error in msg: %s" % msg)
        self.log.info('End reading Slack')

    def deleteSlack(self, theChannel, ts):
        self['sc'].api_call("chat.delete", channel=theChannel, ts=ts) 

    def forwardCmd(self, mess, args):
        self.log.info("Begin forward %s"%mess)
        if args.find(' ') >= 0:
            cmd, argsS = args.split()
        else:
            cmd = args
            argsS = ""
        self.publishSlack(mess=mess, 
                usr=self['userName'], host= self['userHost'], 
                typ = 'Cmd' , cmd = cmd, args = argsS)
        self.log.info("End forward %s"%mess)

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
