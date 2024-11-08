import configparser
import os, pwd
import datetime
import inspect
import re
import json
import urllib.parse
import sys


from errbot import BotPlugin, botcmd, webhook
from errbot.backends.base import Message, Identifier
from errbot.templating import tenv

from socialModules.configMod import *
# You need to:
# pip install social-modules@git+https://git@github.com/fernand0/socialModules@dist


def end(msg=""):
    return("END"+msg)

class ErrForward(BotPlugin):
    """
    An Err plugin for forwarding instructions
    """
        
    def activate(self):
        """
        Triggers on plugin activation

        You should delete it if you're not using it to override any default
        behaviour """
        
        self.log.info("Super activation")
        super().activate()
        self.log.info("Let's go")

        #myModule = 'moduleGitter' 
        #self.idPost = 'id'
        myModule = 'moduleSlack'
        mySocModule = f"socialModules.{myModule}"
        self.idPost = 'ts'
		
        import importlib
        mod = importlib.import_module(mySocModule) 
        cls = getattr(mod, myModule)
        site = cls()
        site.setUrl(myModule)

        site.setClient(myModule)

        self.sc = site
        #self['sc'] = site
        # It fails with can't pickle _thread.RLock objects..
        self.log.debug(f"Chan config: {format(self._check_config('channel'))}")
        if not self.config:
            self.log.info("ErrForward is not configured. Forbid activation")
            return
        self['chan'] = str(self._check_config('channel'))
        site.setChannel(self['chan'])
        self['userName'] = pwd.getpwuid(os.getuid())[0]
        self['userHost'] = os.uname()[1]

        msgJ = self.prepareMessage(
                typ = 'Msg', 
                args = 'Hello! IP: {}. Commands [{}]. Name: {}. Backend: {}'\
                        .format(self.getMyIP(), 
                            self._bot.bot_config.BOT_PREFIX, 
                            self['userHost'], self._bot.bot_config.BACKEND, ))

        chan = self['chan']
        self.log.debug(" Chan: {}".format(chan))
        #self['sc'].publishPost(chan, msgJ)
        self.sc.publishPost(msgJ, '', chan)
        
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
        if ((mess.body.find(userName) == -1) 
                or (mess.body.find(hostName) == -1)):
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

    def prepareMessage(self, usr="", host="", frm="", 
            mess = "", typ ="", cmd = "", args =""):
        self.log.info("Start prepareMessage")

        if not frm and mess: 
            frm = mess.frm 

        if args and typ != 'Msg':
            self.log.debug(f"prepareMessage args: {args}")
            args = urllib.parse.quote(args)

        msg = {'userName': usr, 'userHost': host, 
                'frm': str(frm), 'typ': typ, 'cmd': cmd, 'args': args }
        msgJ = json.dumps(msg)

        self.log.info("End prepareMessage")
        return(msgJ)

    def extractArgs(self, msg):
        self.log.debug("   Converting args")
        self.log.debug("Msg: %s" % msg)

        if 'text' in msg: 
            try: 
                msgE = json.loads(msg['text']) 
            except: 
                self.log.debug("    Error Converting json: %s" % str(msg)) 
                msgE = msg['text']
        else: 
            self.log.info("No text!")
            msgE = None
            
        if msgE and ('args' in msgE) \
              and ('type' in msgE) and (msgE['typ'] != 'Msg'):
            self.log.info("   Converting args")
            # Unquoting the args
            self.log.debug("Reply args before: %s " % msgE['args'])
            tmpJ = urllib.parse.unquote(msgE['args'])
            msgE['args'] = tmpJ
            self.log.debug("Reply args after: %s " % msgE['args'])
            self.log.debug("Reply args after: %s " % msgE['frm'])
            self.log.info("   End Converting")

        return(msgE)

    def broadcastCommand(self, msg, cmd): 
        self.log.info("Starting Broadcast")
        #for bot in self['sc'].getBots(self['chan']):
        listBots = self.sc.getBots(self['chan'])
        self.log.debug(f"Bots: {listBots}")
        for bot in listBots:
            self.log.info("Bot %s" % str(bot))
            start = bot[bot.find('[')+1]
            newCmd = start + cmd
            self.log.info(f" broadcastCommand. Inserting {newCmd} command")
            msgJ = self.prepareMessage(mess=msg['mess'], usr=self['userName'], 
                host= self['userHost'], typ = 'Cmd' , cmd = newCmd, 
                args = msg['args']) 
            self.log.debug("The new command %s" % msgJ)

            #self['sc'].publishPost(self['chan'], msgJ)
            self.sc.publishPost(msgJ, '', self['chan'])
        self.log.info("End Broadcast")

    def manageCommand(self, chan, msgE, msg):
        self.log.info(f"Start manage command ({msgE['cmd']})")
        cmd = msgE['cmd']
        lenPrefix = len(self._bot.bot_config.BOT_PREFIX)
        prefix = cmd[:lenPrefix]
        cmd = cmd[lenPrefix:]
        self.log.debug(f" Bot prefix {self._bot.bot_config.BOT_PREFIX}")
        if prefix == self._bot.bot_config.BOT_PREFIX:
            self.log.info(f" {cmd} it's for me")
            self.log.debug(f" It's for me: {str(msg)}")
            oldChan = self.sc.getChannel()
            self.sc.setChannel(chan)
            result = self.sc.deletePostId(msg[self.idPost])
            self.sc.channel = oldChan
            # Consider avoiding it (?)
            # Maybe we could also have separated the command from args

            listCommands = self._bot.all_commands
            if cmd in listCommands:
                method = listCommands[cmd]                   
                txtR = ''
                self.log.debug(f"Args Forwarded Message {msgE['args']}")
                if msgE['args']:
                    newArgs = urllib.parse.unquote(msgE['args'])
                    newMsg = ""
                else:
                    # There is no from, we need to set some. We will use
                    # one of the bot admins
                    newMsg = Message(frm = self._bot.build_identifier(
                        self.bot_config.BOT_ADMINS[0]))
                    self.log.debug(f" No from, newFrm {newMsg.frm}")
                    newArgs = ""

                replies = method(newMsg, newArgs) 
                if (not inspect.isgeneratorfunction(method) 
                    and not isinstance(replies, tuple) 
                    and not isinstance(replies, list)): 
                    #FIXME ?
                    replies = [ replies ]

                for reply in replies: 
                    if isinstance(reply, str):
                        txtR = txtR + '\n' + reply 
                    else:
                        # What happens if there is no template?
                        # https://github.com/errbotio/errbot/blob/master/errbot/core.py
                        if not method._err_command_template: 
                            txtR = f"{txtR} {reply}"
                        else:
                            self.log.debug("tenv -> %s%s" 
                                    % (method._err_command_template,
                                        '.md'))
                            txtR = txtR + tenv().get_template(
                                    method._err_command_template 
                                    + '.md').render(reply)

                replyMsg = self.prepareMessage(typ = 'Rep', 
                                               usr= msgE['userName'], 
                                               host=msgE['userHost'], 
                                               frm = msgE['frm'], 
                                               args = txtR)
                # Split long Rep.
                # Adding a new type of Rep?
        
                chanP = self['chan']
                #self['sc'].publishPost(chanP, replyMsg)
                self.sc.setChannel(chan)
                self.log.info(" Begin forward (reply)")
                self.sc.publishPost(replyMsg, '', chanP)
                self.log.info(" End forward (reply)")
            else:
                self.log.info("Command not available %s in %s"%(cmd, msgE))
        else: 
            self.log.info(f" {cmd} is not for me")
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
            #self['sc'].deletePost(msg[self.idPost], chan)
            oldChan = self.sc.getChannel()
            self.sc.setChannel(chan)
            self.sc.deletePostId(msg[self.idPost])
            self.sc.channel = oldChan
            
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
        self.log.info(f"Start managing posts in channel {self['chan']}")

        chan = self['chan']
        #site = self['sc']
        site = self.sc
        site.setPosts()
        #self.log.debug("Messages %s" % str(site.getPosts()))

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
        self.log.info(f"Begin forward {mess} from {mess.frm}")
        self.log.debug(f" Args forwardCommand: {args}")
        if args.find(' ') >= 0:
            argsS = args.split()
            cmd = argsS[0]
            newArgs = ' '.join(argsS[1:])
        else:
            cmd = args
            newArgs = ""
            
        self.log.debug(f" forwardCommand Command: {cmd}")
        self.log.debug(f" forwardCommand Args before: {newArgs}")
        if cmd.startswith('*'):
            newCmd = cmd[1:]
            self.log.debug(" forwardCommand new command %s" % newCmd)
            msg = {'mess':mess, 'usr':self['userName'], 
                    'host':self['userHost'], 'typ' : 'Cmd' , 
                    'cmd' : newCmd, 'args': newArgs} 
            self.broadcastCommand(msg, newCmd) 
        else: 
            msgE = self.prepareMessage(mess=mess, 
                                       usr=self['userName'],
                                       host= self['userHost'],
                                       typ = 'Cmd',
                                       cmd = cmd,
                                       args = newArgs) 
            chan = self['chan'] 
            #self['sc'].publishPost(chan, msgE) 
            self.sc.publishPost(msgE, '', chan) 
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
        #bots = self['sc'].getBots(self['chan'])
        bots = self.sc.getBots(self['chan'])
        yield({'text': bots})
        yield(end())

