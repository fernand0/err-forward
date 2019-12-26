from errbot import BotPlugin, botcmd, webhook
from errbot.backends.base import Message, Identifier
from errbot.templating import tenv
import moduleSlack
import configparser
import os, pwd
import datetime
import inspect
import re
import json
import urllib.parse

from configMod import *

def end(msg=""):
    return("END"+msg)

#class MyMessage():
#    def __init__(self):
#        self.frm =''

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
        
        super().activate()
        self.log.info("Let's go")

        config = configparser.ConfigParser()
        config.read(CONFIGDIR + '/.rssBlogs')

        site = moduleSlack.moduleSlack()
        section = "Blog7"
        url = config.get(section, "url")
        site.setUrl(url)

        SLACKCREDENTIALS = os.path.expanduser(CONFIGDIR + '/.rssSlack')
        site.setSlackClient(SLACKCREDENTIALS)

        self['sc'] = site
        self['chan'] = str(self._check_config('channel'))
        self['userName'] = pwd.getpwuid(os.getuid())[0]
        self['userHost'] = os.uname()[1]

        msgJ = self.prepareMessage(typ = 'Msg', 
                args = 'Hello! IP: %s. Commands with [%s]. Name: %s' % 
                (self.getMyIP(), 
                    self._bot.bot_config.BOT_PREFIX, self['userHost']))

        chan = self['chan']
        self['sc'].publishPost(chan, msgJ)
        
        self.start_poller(60, self.managePosts)
        self.log.info('ErrForward has been activated')

    def get_configuration_template(self):
        """
        """
        return {'channel': "general"}

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

    def getMyIP(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('google.com', 0))
        return(s.getsockname()[0])
 
    @botcmd
    def myIP(self, mess, args):
        """ IP of the bot
        """
        yield(self.getMyIP())
        yield(end())
    def prepareMessage(self, usr="", host="", frm="", mess = "", 
            typ ="", cmd = "", args =""):

        if not frm: 
            if mess: 
                frm = mess.frm 

        if args and typ != 'Msg':
            self.log.info("Args _%s_"%args)
            args = urllib.parse.quote(args)

        msg = {'userName': usr, 'userHost': host, 
                'frm': str(frm), 'typ': typ, 'cmd': cmd, 'args': args }
        msgJ = json.dumps(msg)

        return(msgJ)

    def extractArgs(self, msg):
        self.log.info("   Converting args")
        self.log.debug("Msg: %s" % msg)

        if 'text' in msg: 
            try: 
                msgE = json.loads(msg['text']) 
            except: 
                self.log.info("    Error Converting json: %s" % str(msg)) 
                msgE = msg['text']
        else: 
            self.log.info("No text!")
            msgE = None
            
        if msgE and ('args' in msgE) \
              and ('type' in msgE) and (msgE['typ'] != 'Msg'):
            # Unquoting the args
            self.log.debug("Reply args before: %s " % msgE['args'])
            tmpJ = urllib.parse.unquote(msgE['args'])
            msgE['args'] = tmpJ
            self.log.debug("Reply args after: %s " % msgE['args'])
            self.log.debug("Reply args after: %s " % msgE['frm'])
            self.log.info("End Converting")

        return(msgE)

    def broadcastCommand(self, msg, cmd): 
        self.log.info("Starting Broadcast")
        for bot in self['sc'].getBots():#.split('\n'):
            self.log.info("Bot %s" % str(bot))
            start = bot[bot.find('[')+1]
            #  2019-12-16 [,] 159.69.89.133 elmundoesimperfecto 
            newCmd = start + cmd
            self.log.info("Inserting %s command" % newCmd)
            msgJ = self.prepareMessage(mess=msg['mess'], usr=self['userName'], 
                host= self['userHost'], typ = 'Cmd' , cmd = newCmd, 
                args = msg['args']) 
            self.log.debug("The new command %s" % msgJ)

            self['sc'].publishPost(self['chan'], msgJ)
        self.log.info("End Broadcast")

    def manageCommand(self, chan, msgE, msg):
        self.log.info("Starting manage command")
        self.log.info("Command %s" % msgE['cmd'])
        cmd = msgE['cmd']
        lenPrefix = len(self._bot.bot_config.BOT_PREFIX)
        prefix = cmd[:lenPrefix]
        cmd = cmd[lenPrefix:]
        self.log.debug("Bot prefix %s" % self._bot.bot_config.BOT_PREFIX)
        if prefix == self._bot.bot_config.BOT_PREFIX:
            self.log.info("It's for me")
            self['sc'].deletePost(msg['ts'], chan)
            # Consider avoiding it (?)
            # Maybe we could also have separated the command from args

            listCommands = self._bot.all_commands
            if cmd in listCommands:
                method = listCommands[cmd]                   
                txtR = ''
                self.log.info("Args Forwarded Message %s" %msgE['args'])
                if msgE['args']:
                    newArgs = urllib.parse.unquote(msgE['args'])
                    newMsg = ""
                else:
                    # There is no from, we need to set some. We will use
                    # one of the bot admins
                    newMsg = Message(frm = self._bot.build_identifier(self.bot_config.BOT_ADMINS[0]))
                    self.log.info("newFrm %s" % newMsg.frm)
                    newArgs = ""

                replies = method(newMsg, newArgs) 
                if not inspect.isgeneratorfunction(method) and not isinstance(replies, tuple) and not isinstance(replies, list): 
                    replies = [ replies ]

                for reply in replies: 
                    if isinstance(reply, str):
                        txtR = txtR + '\n' + reply 
                    else:
                        self.log.info("Reply not string %s" % str(reply))
                        # What happens if there is no template?
                        # https://github.com/errbotio/errbot/blob/master/errbot/core.py
                        self.log.debug("tenv -> %s%s" 
                                % (method._err_command_template,
                                    '.md'))
                        txtR = txtR + tenv().get_template(method._err_command_template+'.md').render(reply)

                replyMsg = self.prepareMessage(typ = 'Rep', 
                        usr= msgE['userName'], host=msgE['userHost'], 
                        frm = msgE['frm'], args = txtR)
                # Split long Rep.
                # Adding a new type of Rep?
        
                chanP = self['chan']
                self['sc'].publishPost(chanP, replyMsg)
                self.log.info("End forward")
            else:
                self.log.info("Command not available %s in %s"%(cmd, msgE))
        else: 
            self.log.info("Not for me")
            self.log.debug("Not for me %s in %s"%(cmd, msgE))
        self.log.info("End manage command")

    def manageReply(self, chan, msgE, msg):
        self.log.info("Starting manage reply command")
        self.log.info("Command %s" % msgE['cmd'])
        self.log.debug("User: %s - %s | %s - %s" %
                (msgE['userName'], self['userName'], 
                    msgE['userHost'], self['userHost']))
        if ((msgE['userName'] == self['userName']) 
                and (msgE['userHost'] == self['userHost'])):
            # It's for me
            self.log.info("It's for me")
            self['sc'].deletePost(msg['ts'], chan)
            
            replies = urllib.parse.unquote(msgE['args'])
            if not (msgE['frm'] == '-'):
                msgTo = self._bot.build_identifier(msgE['frm'])
            else:
                msgTo = self._bot.build_identifier(self._bot.bot_config.BOT_ADMINS[0])
            # Escaping some markdown. Maybe we will need more
            replies = replies.replace('_','\_')
            
            self.send(msgTo, replies)
        self.log.info("End manage reply")

    def managePosts(self):
        # Don't put yield in this function!
        self.log.info('Start managing posts')
        self.log.info('Slack channel %s' % self['chan'])

        chan = self['sc'].getChanId(self['chan'])
        site = self['sc']
        site.setPosts(self['chan'])
        self.log.debug("Messages %s" % str(site.getPosts()))
                        
        for msg in site.getPosts(): 
            self.log.debug("msg %s" % str(msg))
            msgE = self.extractArgs(msg) 
            self.log.debug("msgE %s" % str(msgE))
            if msgE and ('typ' in msgE): 
                if msgE['typ'] == 'Cmd': 
                    # It's a command 
                    self.manageCommand(chan, msgE, msg) 
                elif msgE['typ'] == 'Rep':                    
                    # It's a reply 
                    self.manageReply(chan, msgE, msg)
        self.log.info('End managing posts')

    def forwardCommand(self, mess, args):
        self.log.info("Begin forward %s from %s" % (mess, mess.frm))
        self.log.info("Args: *%s*"% args)
        if args.find(' ') >= 0:
            argsS = args.split()
            cmd = argsS[0]
            newArgs = ' '.join(argsS[1:])
        else:
            cmd = args
            newArgs = ""
            
        self.log.info("Command: *%s*"% cmd)
        self.log.info("Args before: *%s*"% newArgs)
        if cmd.startswith('*'):
            newCmd = cmd[1:]
            self.log.info("New command %s" % newCmd)
            msg = {'mess':mess, 'usr':self['userName'], 'host':self['userHost'],
                    'typ' : 'Cmd' , 'cmd' : newCmd, 'args': newArgs} 
            self.broadcastCommand(msg, newCmd) 
        else: 
            msgE = self.prepareMessage(mess=mess, usr=self['userName'], 
                host= self['userHost'], typ = 'Cmd' , cmd = cmd, args = newArgs) 
            chan = self['chan'] 
            self['sc'].publishPost(chan, msgE) 
        self.log.info("End forward %s"%mess)

    @botcmd
    def forward(self, mess, args):
        """ Command forwarding to another bot
        """
        yield self.forwardCommand(mess, args)

    @botcmd
    def fw(self, mess, args):
        """ Command forwarding to another bot (abrv)
        """
        yield self.forwardCommand(mess, args)

    @botcmd(template='monospace')
    def listB(self, mess, args):
        """ List bots connected to the Slack channel
        """
        bots = self['sc'].getBots()
        yield({'text': bots})
        yield(end())


