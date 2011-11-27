#!/usr/bin/env python2.7

# This program is free software. It comes without any warranty, to the extent
# permitted by applicable law. You can redistribute it and/or modify it under
# the terms of the Do What The Fuck You Want To Public License, Version 2, as
# published by Sam Hocevar. See http://sam.zoy.org/wtfpl/COPYING for more
# details.

import configuration

import sys
import random
import re
import traceback

from omegle import OmegleConnection, OmegleException

from twisted.words.protocols.irc import IRCClient
from twisted.internet.protocol import ClientFactory
from twisted.internet.threads import deferToThread
from twisted.internet import reactor

from twisted.python import log

log.startLogging(sys.stdout)

CONTROL_CODES = re.compile(r"(?:\x02|\x03(?:\d{1,2}(?:,\d{1,2})?)?|\x0f|\x1f|\x1d)")

class coerce_types(object):
    def __init__(self, *args, **kwargs):
        self.argtypes = args
        self.kwargtypes = kwargs

    def __call__(self, fn):
        def _closure(*args, **kwargs):
            coerced_args = list(args)
            coerced_kwargs = kwargs.copy()

            for i, arg in enumerate(args):
                if i >= len(self.argtypes): break

                if not isinstance(arg, self.argtypes[i]):
                    coerced_args[i] = self.argtypes[i](arg)

            for key, kwarg in kwargs.iteritems():
                if key not in self.kwargtypes: continue

                if not isinstance(kwarg, self.kwargtypes[key]):
                    coerced_kwargs[key] = self.kwargtypes[key](kwarg)

            fn(*coerced_args, **coerced_kwargs)

        return _closure

class OmegleContext(object):
    def __init__(self, parent, channel_name):
        self.parent = parent

        self.channel_name = channel_name
        self.clients = {}

        # flags
        self.mute = False
        self.aware = False
        self.equi = False

    def msg(self, msg):
        self.parent.msg(self.channel_name, msg)

def omegle_dispatch(ircclient, client, context):
    frames = client.getFrames()

    if frames is not None:
        for frame in frames:
            print "Got Omegle frame for %s: %r" % (client.convid, frame)
            if frame.event == "gotMessage":
                for line in frame.data.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                    reactor.callFromThread(ircclient.msg, context.channel_name,
                                           "%s: %s" % (client.convid.encode("utf-8"), line.encode("utf-8")))

                    for other_client in context.clients.values():
                        if other_client is client:
                            continue

                        if context.aware:
                            other_client.send("[%s@Omegle] %s" % (client.convid.encode("utf-8"), line.encode("utf-8")))
                        else:
                            other_client.send(line.encode("utf-8"))
            elif frame.event == "connected":
                reactor.callFromThread(on_omegle_connect, ircclient, context, client)
            elif frame.event == "typing":
                for other_client in context.clients.values():
                    if other_client is client:
                        continue
                    other_client.typing()
            elif frame.event in ("strangerDisconnected", "recaptchaRequired"):
                del context.clients[client.convid]
                reactor.callFromThread(on_omegle_disconnect, ircclient, context, client)
                return

    deferToThread(omegle_dispatch, ircclient, client, context)

#
# EVENTS
#
def on_omegle_disconnect(self, context, client):
    self.msg(context.channel_name, "Disconnected: %s" % client.convid.encode("utf-8"))
    print "Disconnected: %s" % client.convid.encode("utf-8")
    if context.equi:
        self.cmd_connect()
    if context.aware:
        for other_client in context.clients.values():
            other_client.send("Disconnected: %s" % client.convid)

def on_omegle_connect(self, context, client):
    print "Connected: %s" % client.convid
    self.msg(context.channel_name, "Connected: %s" % client.convid.encode("utf-8"))
    if context.aware:
        for other_client in context.clients.values():
            if other_client is client:
                continue
            other_client.send("Connected: %s" % client.convid)

class OmegleIRCBot(IRCClient):
    @property
    def context(self):
        return self.contexts.get(self.current_context)

    @context.setter
    def context(self, value):
        self.contexts[self.current_context] = value

    def __init__(self):
        self.contexts = {}
        self.current_context = None

        self.username = configuration.IDENT
        self.realname = configuration.REALNAME

    #
    # COMMANDS
    #
    @coerce_types(object, int)
    def cmd_connect(self, num_clients=1):
        for i in xrange(num_clients):
            if len(self.context.clients) > configuration.MAX_CLIENTS:
                break

            connection = OmegleConnection(random.choice(configuration.OMEGLE_SERVERS))
            self.context.clients[connection.convid] = connection

            print "Initiated: %s" % connection.convid
            self.context.msg("Initiated: %s" % connection.convid.encode("utf-8"))

            deferToThread(omegle_dispatch, self, connection, self.context)

    def cmd_disconnect(self, convid=None):
        if convid is not None:
            clientpairs = [ (convid, self.context.clients[convid]) ]
        else:
            clientpairs = self.context.clients.items()

        for key, client in clientpairs:
            print "Disconnected: %s" % client.convid
            self.context.msg("Disconnected: %s" % client.convid.encode("utf-8"))
            del self.context.clients[key]
            client.disconnect()
            self.on_omegle_disconnect(client)

    def cmd_list(self):
        self.context.msg("Clients: %s" % (", ".join(client.convid.encode("utf-8") for client in self.context.clients.values()) or "none"))

    def cmd_mute(self):
        self.context.mute = not self.context.mute
        if self.context.mute:
            self.context.msg("Mute: active")
        else:
            self.context.msg("Mute: disabled")

    def cmd_aware(self):
        self.context.aware = not self.context.aware
        if self.context.aware:
            self.context.msg("Aware: active")
        else:
            self.context.msg("Aware: disabled")

    def cmd_equi(self):
        self.context.equi = not self.context.equi
        if self.context.equi:
            self.context.msg("Equilibirum: active")
        else:
            self.context.msg("Equilibirum: disabled")

    def cmd_sayas(self, convid, *msgparts):
        msg = " ".join(msgparts)
        client = self.context.clients[convid]
        for other_client in self.context.clients.values():
            if other_client is client: continue
            other_client.send(msg)
        self.context.msg("%s (sayas): %s" % (convid, msg))

    def cmd_sayto(self, convid, *msgparts):
        msg = " ".join(msgparts)
        client = self.context.clients[convid]
        client.send(msg)

    def cmd_flags(self):
        self.context.msg("Flags (capitalized means active): %sute, %sware, %squilibrium" % (
            self.context.mute and "M" or "m",
            self.context.aware and "A" or "a",
            self.context.equi and "E" or "e"
        ))

    def cmd_recaptcha(self, convid, *responseparts):
        response = " ".join(responseparts)
        client = self.context.clients[convid]
        client.recaptcha(response)

    cmd_c = cmd_connect
    cmd_d = cmd_disconnect
    cmd_l = cmd_list
    cmd_m = cmd_mute
    cmd_a = cmd_aware
    cmd_e = cmd_equi
    cmd_f = cmd_flags
    cmd_r = cmd_recaptcha

    #
    # EVENTS
    #
    def connectionMade(self):
        self.nickname = configuration.NICKNAME
        IRCClient.connectionMade(self)

    def irc_RPL_WELCOME(self, prefix, params):
        if configuration.NICKSERV_PASS is not None:
            self.msg("NickServ", "IDENTIFY %s" % configuration.NICKSERV_PASS)

        for channel in configuration.CHANNELS:
            self.join(channel)

    def connectionLost(self, reason):
        for context in self.contexts.values():
            for client in context.clients.values():
                try:
                    client.disconnect()
                except Exception:
                    pass

    def joined(self, channel_name):
        print "Joined: %s" % channel_name

        self.current_context = channel_name.lower()

        if self.context is None:
            self.contexts[self.current_context] = OmegleContext(self, channel_name)

    def privmsg(self, user, channel, msg):
        nick = user.split("!")[0]
        self.current_context = channel.lower()

        if msg.startswith(configuration.PREFIX_INVIS):
            return

        if channel.lower() not in self.contexts.keys():
            return

        msg = CONTROL_CODES.sub("", msg)

        if msg.lower().startswith(configuration.PREFIX_CMD):
            argv = msg[len(configuration.PREFIX_CMD):].split(" ")

            if hasattr(self, "cmd_%s" % argv[0].lower()):
                try:
                    getattr(self, "cmd_%s" %  argv[0].lower())(*argv[1:])
                except Exception, e:
                    self.context.msg("EXCEPTION - %s: %s" % (e.__class__.__name__, e))
                    traceback.print_exc()

        elif not self.context.mute:
            if self.context.clients:
                if msg[:8].lower() == "\x01action " and msg[-1] == "\x01":
                    msg = "*%s*" % msg[8:-1]

                if self.context.aware:
                    msg = "[%s@IRC] %s" % (nick, msg)

                print "Sending: %s" % msg

                for client in self.context.clients.values():
                    try:
                        client.send(msg)
                    except OmegleException, e:
                        self.context.msg("Omegle Library Exception: %s" % e)
                        traceback.print_exc()

    def action(self, user, channel, data):
        self.privmsg(user, channel, "\x01ACTION %s\x01" % data)

class OmegleBotFactory(ClientFactory):
    protocol = OmegleIRCBot

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason,)

if __name__ == "__main__":
    reactor.connectTCP(configuration.SERVER, configuration.PORT, OmegleBotFactory())
    reactor.run()
