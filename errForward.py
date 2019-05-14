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
        
        self.start_poller(60, self.readSlack)
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
 
    def prepareMessage(self, usr="", host="", frm="", mess = "", 
            typ ="", cmd = "", args =""):

        if not frm: 
            if mess: 
                frm = mess.frm 
            #elif frm: 
            #    frm = "-"

        if args and typ != 'Msg':
            args = urllib.parse.quote(args)

        msg = {'userName': usr, 'userHost': host, 
                'frm': str(frm), 'typ': typ, 'cmd': cmd, 'args': args }
        msgJ = json.dumps(msg)

        return(msgJ)


    #def publish(self, usr="", host="", frm="", mess = "", 
    #        typ ="", cmd = "", args =""):

    #    if not frm: 
    #        if mess: 
    #            frm = mess.frm 
    #        #elif frm: 
    #        #    frm = "-"

    #    if args and typ != 'Msg':
    #        args = urllib.parse.quote(args)

    #    msg = {'userName': usr, 'userHost': host, 
    #            'frm': str(frm), 'typ': typ, 'cmd': cmd, 'args': args }
    #    msgJ = json.dumps(msg)

    #    chan = self['chan']
    #    self['sc'].publishPost(chan, msgJ)

    #def normalizedChan(self, chan): 
    #    self.log.info('Searching for channel %s' % chan)
    #    chanList = self['sc'].api_call("channels.list")['channels'] 
    #    for channel in chanList: 
    #        if channel['name_normalized'] == chan:
    #            return(channel['id'])
    #    return('')

    def extractArgs(self, msg):
        self.log.info("Converting args")
        self.log.info("Msg: %s" % msg)

        try:
            msgJ = json.loads(msg['text'])
            
            if msgJ['args'] and (msgJ['typ'] != 'Msg'):
                # Unquoting the args
                self.log.debug("Reply args before: %s " % msgJ['args'])
                tmpJ = urllib.parse.unquote(msgJ['args'])
                msgJ['args'] = tmpJ
                self.log.debug("Reply args after: %s " % msgJ['args'])
                self.log.debug("Reply args after: %s " % msgJ['frm'])
                self.log.info("End Converting")
        except:
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
                    self.log.info("mmsg %s" %msgJ['args'])
                    if msgJ['args']:
                        reply = method("", msgJ['args']) 
                    else:
                        # There is no from, we need to set some. We will use
                        # one of the bot admins
                        newMsg = Message(frm= self._bot.build_identifier(self.bot_config.BOT_ADMINS[0]))
                        self.log.info("newFrm %s" % newMsg.frm)
                        # Do we need to delete the message before executing the
                        # command?
                        # At leas it can be true when restarting the bot
                        self['sc'].deletePost(msg['ts'], chan)
                        reply = method(newMsg, "") 

                    if isinstance(reply,str):
                        txtR = txtR + reply
                    else:
                        # What happens if ther is no template?
                        # https://github.com/errbotio/errbot/blob/master/errbot/core.py
                        self.log.debug("tenv -> %s%s" 
                                % (method._err_command_template,
                                    '.md'))
                        txtR = txtR + tenv().get_template(method._err_command_template+'.md').render(reply)

                msgJ = self.prepareMessage(typ = 'Rep', usr= msgJ['userName'],
                        host=msgJ['userHost'], frm = msgJ['frm'], args = txtR)
                # Split long Rep.
                # Adding a new type of Rep?
        
                chanP = self['chan']
                self['sc'].publishPost(chanP, msgJ)
                self.log.info("End forward %s"%mess)

                self['sc'].deletePost(msg['ts'], chan)
        self.log.info("End manage command")

    def manageReply(self, chan, msgJ, msg):
        self.log.info("Starting manage reply command")
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
            self['sc'].deletePost(msg['ts'], chan)
        self.log.info("End manage reply")

    def readSlack(self):
        # Don't put yield in this function!
        self.log.info('Start reading Slack')
        self.log.info('Slack channel %s' % self['chan'])

        chan = self['sc'].getChanId(self['chan'])
        site = self['sc']
        site.setPosts(self['chan'])
                        
        self.log.info('Slack channel posts %s' % self['sc'].getPosts())

        for msg in site.getPosts(): 
            msgJ = self.extractArgs(msg) 
            if ('typ' in msgJ):
                if msgJ['typ'] == 'Cmd':                    
                    # It's a command 
                    self.manageCommand(chan, msgJ, msg) 
                elif msgJ['typ'] == 'Rep':                    
                    # It's a reply 
                    self.manageReply(chan, msgJ, msg)
        self.log.info('End reading Slack')

    def forwardCmd(self, mess, args):
        self.log.info("Begin forward %s"%mess)
        if args.find(' ') >= 0:
            argsS = args.split()
            cmd = argsS[0]
            argsS = argsS[1:]
        else:
            cmd = args
            argsS = ""
            
        msgJ = self.prepareMessage(mess=mess, usr=self['userName'], 
                host= self['userHost'], typ = 'Cmd' , cmd = cmd, args = argsS)
        chan = self['chan']
        self['sc'].publishPost(chan, msgJ)
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
