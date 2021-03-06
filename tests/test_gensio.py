#
#  gensio - A library for abstracting stream I/O
#  Copyright (C) 2018  Corey Minyard <minyard@acm.org>
#
#  SPDX-License-Identifier: LGPL-2.1-only
#

import utils
import gensio
import sys
import os
from serialsim import *

class Logger:
    def gensio_log(self, level, log):
        print("***%s log: %s" % (level, log))

gensio.gensio_set_log_mask(gensio.GENSIO_LOG_MASK_ALL)
o = gensio.alloc_gensio_selector(Logger());

def check_raddr(io, testname, expected):
    r = io.raddr()
    if r != expected:
        raise Exception("%s raddr was not '%s', it was '%s'" %
                        (testname, expected, r));

def check_laddr(acc, testname, expected):
    r = acc.control(0, True, gensio.GENSIO_ACC_CONTROL_LADDR, "0")
    if r != expected:
        raise Exception("%s laddr was not '%s', it was '%s'" %
                        (testname, expected, r));

def check_port(acc, testname, expected):
    r = acc.control(0, True, gensio.GENSIO_ACC_CONTROL_LPORT, "0")
    if r != expected:
        raise Exception("%s port was not '%s', it was '%s'" %
                        (testname, expected, r));

def test_echo_gensio():
    print("Test echo gensio")
    io = utils.alloc_io(o, "echo")
    check_raddr(io, "echo", "echo")
    utils.test_dataxfer(io, io, "This is a test string!")
    utils.io_close(io)
    print("  Success!")

def test_echo_device():
    print("Test echo device")
    io = utils.alloc_io(o, "serialdev,/dev/ttyEcho0,38400")
    check_raddr(io, "echo device", "/dev/ttyEcho0,38400N81 RTSHI DTRHI")
    utils.test_dataxfer(io, io, "This is a test string!")
    utils.io_close(io)
    print("  Success!")

def test_serial_pipe_device():
    print("Test serial pipe device")
    io1 = utils.alloc_io(o, "serialdev,/dev/ttyPipeA0,9600")
    io2 = utils.alloc_io(o, "serialdev,/dev/ttyPipeB0,9600")
    utils.test_dataxfer(io1, io2, "This is a test string!")
    utils.io_close(io1)
    utils.io_close(io2)
    print("  Success!")

class TestAccept:
    def __init__(self, o, io1, iostr, tester, name = None,
                 io1_dummy_write = None, do_close = True,
                 expected_raddr = None, expected_acc_laddr = None,
                 expected_acc_port = None):
        self.o = o
        if (name):
            self.name = name
        else:
            self.name = iostr
        self.io1 = io1
        self.io2 = None
        self.waiter = gensio.waiter(o)
        self.acc = gensio.gensio_accepter(o, iostr, self);
        self.acc.startup()
        if expected_acc_laddr:
            check_laddr(self.acc, self.name, expected_acc_laddr)
        if expected_acc_port:
            check_port(self.acc, self.name, expected_acc_port)
        io1.open_s()
        if expected_raddr:
            check_raddr(io1, self.name, expected_raddr)
        if (io1_dummy_write):
            # For UDP, kick start things.
            io1.write(io1_dummy_write, None)
        self.wait()
        if (io1_dummy_write):
            self.io2.handler.set_compare(io1_dummy_write)
            if (self.io2.handler.wait_timeout(1000) == 0):
                raise Exception(("%s: %s: " % ("test_accept",
                                               self.io2.handler.name)) +
                        ("Timed out waiting for dummy read at byte %d" %
                         self.io2.handler.compared))
        tester(self.io1, self.io2)
        if do_close:
            self.close()

    def close(self):
        self.io1.read_cb_enable(False)
        if self.io2:
            self.io2.read_cb_enable(False)
        utils.io_close(self.io1)
        if self.io2:
            utils.io_close(self.io2)

        # Break all the possible circular references.
        del self.io1
        del self.io2
        self.acc.shutdown_s()
        del self.acc

    def new_connection(self, acc, io):
        utils.HandleData(self.o, None, io = io, name = self.name)
        self.io2 = io
        self.waiter.wake()

    def accepter_log(self, acc, level, logstr):
        print("***%s LOG: %s: %s" % (level, self.name, logstr))

    def wait(self):
        self.waiter.wait(1)

def do_test(io1, io2):
    utils.test_dataxfer(io1, io2, "This is a test string!")
    print("  Success!")

def ta_tcp():
    print("Test accept tcp")
    io1 = utils.alloc_io(o, "tcp,localhost,3023", do_open = False)
    TestAccept(o, io1, "tcp,localhost,3023", do_test,
               expected_raddr = "ipv4,127.0.0.1,3023",
               expected_acc_laddr = "ipv4,127.0.0.1,3023",
               expected_acc_port = "3023")

def ta_udp():
    print("Test accept udp")
    io1 = utils.alloc_io(o, "udp,localhost,3023", do_open = False)
    TestAccept(o, io1, "udp,localhost,3023", do_test, io1_dummy_write = "A",
               expected_raddr = "ipv4,127.0.0.1,3023",
               expected_acc_laddr = "ipv4,127.0.0.1,3023",
               expected_acc_port = "3023")

def ta_sctp():
    print("Test accept sctp")
    io1 = utils.alloc_io(o, "sctp,localhost,3023", do_open = False)
    # FIXME - the raddr and laddr areq not tested here, it's hard to
    # know what it would be because of sctp multihoming.
    TestAccept(o, io1, "sctp,3023", do_test,
               expected_acc_port = "3023")
    c = io1.control(0, True, gensio.GENSIO_CONTROL_STREAMS, None)
    if c != "instreams=1,ostreams=1":
        raise Exception("Invalid stream settings: %s" % c)

def ta_ssl_tcp():
    print("Test accept ssl-tcp")
    io1 = utils.alloc_io(o, "ssl(CA=%s/CA.pem),tcp,localhost,3023" % utils.keydir, do_open = False)
    ta = TestAccept(o, io1, "ssl(key=%s/key.pem,cert=%s/cert.pem),3023" % (utils.keydir, utils.keydir), do_test, do_close = False,
                    expected_raddr = "ipv4,127.0.0.1,3023")
    cn = io1.control(0, True, gensio.GENSIO_CONTROL_GET_PEER_CERT_NAME,
                     "-1,CN");
    i = cn.index(',')
    cn2 = cn[i+1:]
    i = cn2.index(',')
    if cn2[0:i] != "CN":
        raise Exception(
            "Invalid object name, expected %s, got %s" % ("CN", cn2[0:i]))
    if cn2[i+1:] != "ser2net.org":
        raise Exception(
            "Invalid common name in certificate, expected %s, got %s" %
            ("ser2net.org", cn2[i+1:]))
    cert = io1.control(0, True, gensio.GENSIO_CONTROL_CERT, None)
    print("Cert = \n" + cert)
    finger = io1.control(0, True, gensio.GENSIO_CONTROL_CERT_FINGERPRINT, None)
    print("Fingerprint = " + finger)
    i = 0;
    while True:
        v = io1.control(0, True, gensio.GENSIO_CONTROL_GET_PEER_CERT_NAME,
                        str(i))
        if v is None:
            break;
        print(v)
        i = i + 1
    ta.close()

def ta_certauth_tcp():
    print("Test accept certauth-ssl-tcp")
    io1 = utils.alloc_io(o, "certauth(cert=%s/clientcert.pem,key=%s/clientkey.pem,username=testuser,service=myservice),ssl(CA=%s/CA.pem),tcp,localhost,3023" % (utils.keydir, utils.keydir, utils.keydir), do_open = False)
    ta = TestAccept(o, io1, "certauth(CA=%s/clientcert.pem),ssl(key=%s/key.pem,cert=%s/cert.pem),tcp,3023" % (utils.keydir, utils.keydir, utils.keydir), do_test, do_close = False)
    cn = ta.io2.control(0, True, gensio.GENSIO_CONTROL_GET_PEER_CERT_NAME,
                        "-1,CN");
    i = cn.index(',')
    cn2 = cn[i+1:]
    i = cn2.index(',')
    if cn2[0:i] != "CN":
        raise Exception(
            "Invalid object name, expected %s, got %s" % ("CN", cn2[0:i]))
    if cn2[i+1:] != "gensio.org":
        raise Exception(
            "Invalid common name in certificate, expected %s, got %s" %
            ("gensio.org", cn2[i+1:]))
    username = ta.io2.control(0, True, gensio.GENSIO_CONTROL_USERNAME, None)
    if username != "testuser":
        raise Exception(
            "Invalid username, expected %s, got %s" % ("testuser", username))
    service = ta.io2.control(0, True, gensio.GENSIO_CONTROL_SERVICE, None)
    if service != "myservice":
        raise Exception(
            "Invalid service, expected %s, got %s" % ("myservice", service))
    ta.close()

def ta_mux_sctp():
    print("Test accept mux-tcp")
    io1 = utils.alloc_io(o, "mux(service=myservice),sctp,localhost,3023",
                         do_open = False)
    ta = TestAccept(o, io1, "mux,sctp,3023", do_test, do_close = False)
    service = ta.io2.control(0, True, gensio.GENSIO_CONTROL_SERVICE, None)
    if service != "myservice":
        raise Exception(
            "Invalid service, expected %s, got %s" % ("myservice", service))
    ta.close()

class SigRspHandler:
    def __init__(self, o, sigval):
        self.sigval = sigval
        self.waiter = gensio.waiter(o)
        return

    def signature(self, sio, err, value):
        if (err):
            raise Exception("Error getting signature: %s" % err)
        value = value.decode(encoding='utf-8')
        if (value != self.sigval):
            raise Exception("Signature value was '%s', expected '%s'" %
                            (value, self.sigval))
        self.waiter.wake();
        return

    def wait_timeout(self, timeout):
        return self.waiter.wait_timeout(1, timeout)

def do_telnet_test(io1, io2):
    io1.handler.set_expected_modemstate(0)
    io1.read_cb_enable(True);
    sio2 = io2.cast_to_sergensio()
    sio2.sg_modemstate(0);
    if (io1.handler.wait_timeout(2000) == 0):
        raise Exception("%s: %s: Timed out waiting for telnet modemstate 1" %
                        ("test open", io1.handler.name))
    do_test(io1, io2)
    sio1 = io1.cast_to_sergensio()
    io1.read_cb_enable(True);
    io2.read_cb_enable(True);

    h = SigRspHandler(o, "testsig")
    io2.handler.set_expected_sig_server_cb("testsig")
    sio1.sg_signature(None, h)
    if (h.wait_timeout(1000) == 0):
        raise Exception("Timeout waiting for signature")

    io2.handler.set_expected_server_cb("baud", 1000, 2000)
    io1.handler.set_expected_client_cb("baud", 2000)
    sio1.sg_baud(1000, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server baud set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client baud response")

    io2.handler.set_expected_server_cb("datasize", 5, 6)
    io1.handler.set_expected_client_cb("datasize", 6)
    sio1.sg_datasize(5, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server datasize set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client datasize response")

    io2.handler.set_expected_server_cb("parity", 1, 5)
    io1.handler.set_expected_client_cb("parity", 5)
    sio1.sg_parity(1, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server parity set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client parity response")

    io2.handler.set_expected_server_cb("stopbits", 2, 1)
    io1.handler.set_expected_client_cb("stopbits", 1)
    sio1.sg_stopbits(2, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server stopbits set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client stopbits response")

    io2.handler.set_expected_server_cb("flowcontrol", 1, 2)
    io1.handler.set_expected_client_cb("flowcontrol", 2)
    sio1.sg_flowcontrol(1, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server flowcontrol set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client flowcontrol response")

    io2.handler.set_expected_server_cb("iflowcontrol", 3, 4)
    io1.handler.set_expected_client_cb("iflowcontrol", 4)
    sio1.sg_iflowcontrol(3, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server flowcontrol set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client flowcontrol response")

    io2.handler.set_expected_server_cb("sbreak", 2, 1)
    io1.handler.set_expected_client_cb("sbreak", 1)
    sio1.sg_sbreak(2, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server sbreak set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client sbreak response")

    io2.handler.set_expected_server_cb("dtr", 1, 2)
    io1.handler.set_expected_client_cb("dtr", 2)
    sio1.sg_dtr(1, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server dtr set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client dtr response")

    io2.handler.set_expected_server_cb("rts", 2, 1)
    io1.handler.set_expected_client_cb("rts", 1)
    sio1.sg_rts(2, io1.handler)
    if io2.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for server rts set")
    if io1.handler.wait_timeout(1000) == 0:
        raise Exception("Timeout waiting for client rts response")
    io1.read_cb_enable(False)
    io2.read_cb_enable(False)
    return

def ta_telnet():
    print("Test accept telnet")
    io1 = utils.alloc_io(o, "telnet(rfc2217),tcp,localhost,3027",
                         do_open = False)
    ta = TestAccept(o, io1, "telnet(rfc2217=true),3027", do_telnet_test)

def test_modemstate():
    io1str = "serialdev,/dev/ttyPipeA0,9600N81,LOCAL"
    io2str = "serialdev,/dev/ttyPipeB0,9600N81"

    print("serialdev modemstate:\n  io1=%s\n  io2=%s" % (io1str, io2str))

    io1 = utils.alloc_io(o, io1str, do_open = False)
    io2 = utils.alloc_io(o, io2str)
    sio2 = io2.cast_to_sergensio();

    sio2.sg_dtr_s(gensio.SERGENSIO_DTR_OFF);
    sio2.sg_rts_s(gensio.SERGENSIO_RTS_OFF);
    set_remote_null_modem(io2.remote_id(), False);
    set_remote_modem_ctl(io2.remote_id(), (SERIALSIM_TIOCM_CAR |
                                           SERIALSIM_TIOCM_CTS |
                                           SERIALSIM_TIOCM_DSR |
                                           SERIALSIM_TIOCM_RNG) << 16)

    io1.handler.set_expected_modemstate(0)
    io1.open_s()
    io1.read_cb_enable(True);
    if (io1.handler.wait_timeout(2000) == 0):
        raise Exception("%s: %s: Timed out waiting for modemstate 1" %
                        ("test dtr", io1.handler.name))

    io2.read_cb_enable(True);

    io1.handler.set_expected_modemstate(gensio.SERGENSIO_MODEMSTATE_CD_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_CD)
    set_remote_modem_ctl(io2.remote_id(), ((SERIALSIM_TIOCM_CAR << 16) |
                                           SERIALSIM_TIOCM_CAR))
    if (io1.handler.wait_timeout(2000) == 0):
        raise Exception("%s: %s: Timed out waiting for modemstate 2" %
                        ("test dtr", io1.handler.name))

    io1.handler.set_expected_modemstate(gensio.SERGENSIO_MODEMSTATE_DSR_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_CD |
                                        gensio.SERGENSIO_MODEMSTATE_DSR)
    set_remote_modem_ctl(io2.remote_id(), ((SERIALSIM_TIOCM_DSR << 16) |
                                           SERIALSIM_TIOCM_DSR))
    if (io1.handler.wait_timeout(2000) == 0):
        raise Exception("%s: %s: Timed out waiting for modemstate 3" %
                        ("test dtr", io1.handler.name))

    io1.handler.set_expected_modemstate(gensio.SERGENSIO_MODEMSTATE_CTS_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_CD |
                                        gensio.SERGENSIO_MODEMSTATE_DSR |
                                        gensio.SERGENSIO_MODEMSTATE_CTS)
    set_remote_modem_ctl(io2.remote_id(), ((SERIALSIM_TIOCM_CTS << 16) |
                                           SERIALSIM_TIOCM_CTS))
    if (io1.handler.wait_timeout(2000) == 0):
        raise Exception("%s: %s: Timed out waiting for modemstate 4" %
                        ("test dtr", io1.handler.name))

    io1.handler.set_expected_modemstate(gensio.SERGENSIO_MODEMSTATE_RI_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_CD |
                                        gensio.SERGENSIO_MODEMSTATE_DSR |
                                        gensio.SERGENSIO_MODEMSTATE_CTS |
                                        gensio.SERGENSIO_MODEMSTATE_RI)
    set_remote_modem_ctl(io2.remote_id(), ((SERIALSIM_TIOCM_RNG << 16) |
                                           SERIALSIM_TIOCM_RNG))
    if (io1.handler.wait_timeout(2000) == 0):
        raise Exception("%s: %s: Timed out waiting for modemstate 5" %
                        ("test dtr", io1.handler.name))

    io1.handler.set_expected_modemstate(gensio.SERGENSIO_MODEMSTATE_RI_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_CD_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_DSR_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_CTS_CHANGED)
    set_remote_modem_ctl(io2.remote_id(), (SERIALSIM_TIOCM_CAR |
                                           SERIALSIM_TIOCM_CTS |
                                           SERIALSIM_TIOCM_DSR |
                                           SERIALSIM_TIOCM_RNG) << 16)
    if (io1.handler.wait_timeout(2000) == 0):
        raise Exception("%s: %s: Timed out waiting for modemstate 6" %
                        ("test dtr", io1.handler.name))

    io1.handler.set_expected_modemstate(gensio.SERGENSIO_MODEMSTATE_CD_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_DSR_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_CTS_CHANGED |
                                        gensio.SERGENSIO_MODEMSTATE_CD |
                                        gensio.SERGENSIO_MODEMSTATE_DSR |
                                        gensio.SERGENSIO_MODEMSTATE_CTS)
    sio2.sg_dtr_s(gensio.SERGENSIO_DTR_ON);
    sio2.sg_rts_s(gensio.SERGENSIO_RTS_ON);
    set_remote_null_modem(io2.remote_id(), True);
    if (io1.handler.wait_timeout(2000) == 0):
        raise Exception("%s: %s: Timed out waiting for modemstate 7" %
                        ("test dtr", io1.handler.name))

    utils.io_close(io1)
    utils.io_close(io2)
    print("  Success!")
    return

def test_stdio_basic():
    print("Test stdio basic echo")
    io = utils.alloc_io(o, "stdio,cat", chunksize = 64)
    check_raddr(io, "stdio basic", 'stdio,"cat"')
    utils.test_dataxfer(io, io, "This is a test string!")
    utils.io_close(io)
    print("  Success!")

def test_stdio_basic_stderr():
    print("Test stdio basic stderr echo")
    io = utils.alloc_io(o, "stdio,sh -c 'cat 1>&2'", chunksize = 64)
    io.handler.ignore_input = True
    io.read_cb_enable(True)
    err = io.alloc_channel(None, None)
    err.open_s()
    check_raddr(err, "stderr basic", 'stderr,"sh" "-c" "cat 1>&2"')
    utils.HandleData(o, "stderr", chunksize = 64, io = err)
    utils.test_dataxfer(io, err, "This is a test string!")
    utils.io_close(io)
    utils.io_close(err)
    print("  Success!")

def test_pty_basic():
    print("Test pty basic echo")
    io = utils.alloc_io(o, "pty,cat", chunksize = 64)
    check_raddr(io, "pty basic", '"cat"')
    utils.test_dataxfer(io, io, "This is a test string!")
    utils.io_close(io)
    print("  Success!")

def test_stdio_small():
    print("Test stdio small echo")
    rb = os.urandom(512)
    io = utils.alloc_io(o, "stdio,cat", chunksize = 64)
    utils.test_dataxfer(io, io, rb)
    utils.io_close(io)
    print("  Success!")

def do_small_test(io1, io2):
    rb = os.urandom(512)
    print("  testing io1 to io2")
    utils.test_dataxfer(io1, io2, rb, timeout = 2000)
    print("  testing io2 to io1")
    utils.test_dataxfer(io2, io1, rb, timeout = 2000)
    print("  testing bidirection between io1 and io2")
    utils.test_dataxfer_simul(io1, io2, rb, timeout = 2000)
    print("  Success!")

def do_large_test(io1, io2):
    rb = os.urandom(1048570)
    print("  testing io1 to io2")
    utils.test_dataxfer(io1, io2, rb, timeout=30000)
    print("  testing io2 to io1")
    utils.test_dataxfer(io2, io1, rb, timeout=30000)
    print("  testing bidirection between io1 and io2")
    utils.test_dataxfer_simul(io1, io2, rb, timeout=30000)
    print("  Success!")

def test_tcp_small():
    print("Test tcp small")
    io1 = utils.alloc_io(o, "tcp,localhost,3023", do_open = False,
                         chunksize = 64)
    ta = TestAccept(o, io1, "tcp,3023", do_small_test)

def do_urgent_test(io1, io2):
    rb = "A" # We only get one byte of urgent data.
    print("  testing io1 to io2")
    utils.test_dataxfer_oob(io1, io2, rb)
    print("  testing io2 to io1")
    utils.test_dataxfer_oob(io2, io1, rb)
    print("  Success!")

def test_tcp_urgent():
    print("Test tcp urgent")
    io1 = utils.alloc_io(o, "tcp,localhost,3023", do_open = False,
                         chunksize = 64)
    ta = TestAccept(o, io1, "tcp,3023", do_urgent_test)

def test_sctp_small():
    print("Test sctp small")
    io1 = utils.alloc_io(o, "sctp,localhost,3023", do_open = False,
                         chunksize = 64)
    ta = TestAccept(o, io1, "sctp,3023", do_small_test)

def test_mux_sctp_small():
    print("Test mux sctp small")
    io1 = utils.alloc_io(o, "mux,sctp,localhost,3023", do_open = False,
                         chunksize = 64)
    ta = TestAccept(o, io1, "mux,sctp,3023", do_small_test)

def test_mux_tcp_large():
    print("Test mux tcp large")
    io1 = utils.alloc_io(o, "mux,tcp,localhost,3023", do_open = False,
                         chunksize = 64)
    ta = TestAccept(o, io1, "mux,tcp,3023", do_large_test)

def do_stream_test(io1, io2):
    rb = os.urandom(10)
    print("  testing io1 to io2")
    utils.test_dataxfer_stream(io1, io2, rb, 2)
    print("  testing io2 to io1")
    utils.test_dataxfer_stream(io2, io1, rb, 1)
    print("  Success!")

def test_sctp_streams():
    print("Test sctp streams")
    io1 = utils.alloc_io(o, "sctp(instreams=2,ostreams=3),localhost,3023",
                         do_open = False, chunksize = 64)
    ta = TestAccept(o, io1, "sctp(instreams=3,ostreams=2),3023", do_stream_test)

def do_oob_test(io1, io2):
    rb = os.urandom(512)
    print("  testing io1 to io2")
    utils.test_dataxfer_oob(io1, io2, rb)
    print("  testing io2 to io1")
    utils.test_dataxfer_oob(io2, io1, rb)
    print("  Success!")

def test_sctp_oob():
    print("Test sctp oob")
    io1 = utils.alloc_io(o, "sctp,localhost,3023",
                         do_open = False, chunksize = 64)
    ta = TestAccept(o, io1, "sctp,3023", do_oob_test)

def test_telnet_small():
    print("Test telnet small")
    io1 = utils.alloc_io(o, "telnet,tcp,localhost,3023", do_open = False,
                         chunksize = 64)
    ta = TestAccept(o, io1, "telnet(rfc2217=true),3023", do_small_test)

import ipmisimdaemon
def test_ipmisol_small():
    print("Test ipmisol small")
    isim = ipmisimdaemon.IPMISimDaemon(o)
    io1 = utils.alloc_io(o, "serialdev,/dev/ttyPipeA0,9600")
    io2 = utils.alloc_io(o, "ipmisol,lan -U ipmiusr -P test -p 9001 localhost,9600")
    utils.test_dataxfer(io1, io2, "This is a test string!")
    utils.io_close(io1)
    utils.io_close(io2)
    print("  Success!")

def test_ipmisol_large():
    print("Test ipmisol large")
    isim = ipmisimdaemon.IPMISimDaemon(o)
    io1 = utils.alloc_io(o, "serialdev,/dev/ttyPipeA0,115200")
    io2 = utils.alloc_io(o, "ipmisol,lan -U ipmiusr -P test -p 9001 localhost,115200")
    rb = os.urandom(104857)
    utils.test_dataxfer(io1, io2, rb, timeout=20000)
    utils.io_close(io1)
    utils.io_close(io2)
    print("  Success!")

def test_rs485():
    io1str = "serialdev,/dev/ttyPipeA0,9600N81,LOCAL,rs485=103:495"
    io2str = "serialdev,/dev/ttyPipeB0,9600N81"

    print("serialdev rs485:\n  io1=%s\n  io2=%s" % (io1str, io2str))

    io1 = utils.alloc_io(o, io1str)
    io2 = utils.alloc_io(o, io2str)

    rs485 = get_remote_rs485(io2.remote_id())
    check_rs485 = "103 495 enabled"
    if rs485 != check_rs485:
        raise Exception("%s: %s: RS485 was not '%s', it was '%s'" %
                        ("test rs485", io1.handler.name, check_rs485, rs485))

    utils.io_close(io1)
    utils.io_close(io2)
    print("  Success!")

class TestAcceptConnect:
    def __init__(self, o, iostr, io2str, io3str, tester, name = None,
                 io1_dummy_write = None, CA=None, do_close = True,
                 auth_begin_rv = gensio.GE_NOTSUP, expect_pw = None,
                 expect_pw_rv = gensio.GE_NOTSUP, password = None,
                 expect_remclose = True):
        self.o = o
        if (name):
            self.name = name
        else:
            self.name = iostr
        self.waiter = gensio.waiter(o)
        self.acc = gensio.gensio_accepter(o, iostr, self);
        self.acc.startup()
        self.acc2 = gensio.gensio_accepter(o, io2str, self);
        self.acc2.startup()
        self.io1 = self.acc2.str_to_gensio(io3str, None);
        self.io2 = None
        self.CA = CA
        h = utils.HandleData(o, io3str, io = self.io1, password = password,
                             expect_remclose = expect_remclose)
        self.auth_begin_rv = auth_begin_rv
        self.expect_pw = expect_pw
        self.expect_pw_rv = expect_pw_rv
        try:
            self.io1.open_s()
        except:
            self.io1 = None
            self.close()
            raise
        self.io1.read_cb_enable(True)
        if (io1_dummy_write):
            # For UDP, kick start things.
            self.io1.write(io1_dummy_write, None)
        try:
            self.wait()
        except:
            self.close()
            raise
        if (io1_dummy_write):
            self.io2.handler.set_compare(io1_dummy_write)
            if (self.io2.handler.wait_timeout(1000) == 0):
                raise Exception(("%s: %s: " % ("test_accept",
                                               self.io2.handler.name)) +
                        ("Timed out waiting for dummy read at byte %d" %
                         self.io2.handler.compared))
        tester(self.io1, self.io2)
        if do_close:
            self.close()

    def close(self):
        if (self.io1):
            self.io1.read_cb_enable(False)
        if self.io2:
            self.io2.read_cb_enable(False)
        if (self.io1):
            utils.io_close(self.io1)
        if self.io2:
            utils.io_close(self.io2)

        # Break all the possible circular references.
        del self.io1
        del self.io2
        self.acc.shutdown_s()
        del self.acc
        self.acc2.shutdown_s()
        del self.acc2

    def new_connection(self, acc, io):
        utils.HandleData(self.o, None, io = io, name = self.name)
        self.io2 = io
        self.waiter.wake()

    def auth_begin(self, acc, io):
        return self.auth_begin_rv;

    def precert_verify(self, acc, io):
        if self.CA:
            io.control(0, False, gensio.GENSIO_CONTROL_CERT_AUTH, self.CA)
            return gensio.GE_NOTSUP
        return gensio.GE_NOTSUP

    def password_verify(self, acc, io, password):
        if self.expect_pw is None:
            raise Exception("got password verify when none expected")
        if self.expect_pw != password:
            raise Exception("Invalid password in verify, expected %s, got %s"
                            % (self.expect_pw, password))
        return self.expect_pw_rv

    def accepter_log(self, acc, level, logstr):
        print("***%s LOG: %s: %s" % (level, self.name, logstr))

    def wait(self):
        self.waiter.wait(1)

def test_tcp_acc_connect():
    print("Test tcp accepter connect")
    TestAcceptConnect(o, "tcp,3023", "tcp,3024", "tcp,localhost,3023",
                      do_small_test)

def test_udp_acc_connect():
    print("Test udp accepter connect")
    TestAcceptConnect(o, "udp,3023", "udp,3024", "udp,localhost,3023",
                      do_small_test, io1_dummy_write = "A")

def test_sctp_acc_connect():
    print("Test sctp accepter connect")
    TestAcceptConnect(o, "sctp,3023", "sctp,3024", "sctp,localhost,3023",
                      do_small_test)

def test_telnet_sctp_acc_connect():
    print("Test telnet over sctp accepter connect")
    TestAcceptConnect(o, "telnet,sctp,3023", "telnet,sctp,3024",
                      "telnet,sctp,localhost,3023", do_small_test)

def test_ssl_sctp_acc_connect():
    print("Test ssl over sctp accepter connect")
    goterr = False
    try:
        TestAcceptConnect(o,
                "ssl(key=%s/key.pem,cert=%s/cert.pem,clientauth),sctp,3023"
                               % (utils.keydir, utils.keydir),
                "ssl(key=%s/key.pem,cert=%s/cert.pem),sctp,3024"
                           % (utils.keydir, utils.keydir),
                "ssl(CA=%s/CA.pem),sctp,localhost,3023" % utils.keydir,
                           do_small_test,
                          expect_remclose = False)
    except Exception as E:
        s = str(E)
        # We can race and get either one of these
        if (not (s.endswith("Communication error") or
                 s.endswith("Remote end closed connection"))):
            raise
        print("  Success checking no client cert")
        goterr = True
    if not goterr:
        raise Exception("Did not get error on no client certificate.")
    
    goterr = False
    try:
        TestAcceptConnect(o,
                "ssl(key=%s/key.pem,cert=%s/cert.pem,clientauth),sctp,3023"
                               % (utils.keydir, utils.keydir),
                "ssl(key=%s/key.pem,cert=%s/cert.pem),sctp,3024"
                               % (utils.keydir, utils.keydir),
                "ssl(CA=%s/CA.pem,key=%s/clientkey.pem,cert=%s/clientcert.pem)"
                ",sctp,localhost,3023"
                               % (utils.keydir, utils.keydir, utils.keydir),
                           do_small_test, expect_remclose = False)
    except Exception as E:
        s = str(E)
        # We can race and get either one of these
        if (not (s.endswith("Communication error") or
                 s.endswith("Remote end closed connection"))):
            raise
        print("  Success checking invalid client cert")
        goterr = True
    if not goterr:
        raise Exception("Did not get error on invalid client certificate.")
    
    TestAcceptConnect(o,
                "ssl(key=%s/key.pem,cert=%s/cert.pem,clientauth),sctp,3023"
                               % (utils.keydir, utils.keydir),
                "ssl(key=%s/key.pem,cert=%s/cert.pem),sctp,3024"
                               % (utils.keydir, utils.keydir),
                "ssl(CA=%s/CA.pem,key=%s/clientkey.pem,cert=%s/clientcert.pem)"
                ",sctp,localhost,3023"
                               % (utils.keydir, utils.keydir, utils.keydir),
                           do_small_test, CA="%s/clientcert.pem" % utils.keydir)

def test_certauth_sctp_acc_connect():
    print("Test certauth over ssl over sctp accepter connect")
    goterr = False
    try:
        TestAcceptConnect(o,
                "certauth(CA=%s/clientcert.pem),ssl(key=%s/key.pem,cert=%s/cert.pem),sctp,3023" % (utils.keydir, utils.keydir, utils.keydir),
                "certauth(CA=%s/clientcert.pem),ssl(key=%s/key.pem,cert=%s/cert.pem),sctp,3024" % (utils.keydir, utils.keydir, utils.keydir),
                "certauth(cert=%s/cert.pem,key=%s/key.pem,username=test1),ssl(CA=%s/CA.pem),sctp,localhost,3023" % (utils.keydir, utils.keydir, utils.keydir),
                           do_small_test)
    except Exception as E:
        s = str(E)
        # We can race and get either one of these
        if (not (s.endswith("Communication error") or
                 s.endswith("Remote end closed connection"))):
            raise
        print("  Success checking invalid client cert")
        goterr = True
    if not goterr:
        raise Exception("Did not get error on invalid client certificate.")

    TestAcceptConnect(o,
                "certauth(),ssl(key=%s/key.pem,cert=%s/cert.pem),sctp,3023" % (utils.keydir, utils.keydir),
                "certauth(),ssl(key=%s/key.pem,cert=%s/cert.pem),sctp,3024" % (utils.keydir, utils.keydir),
                "certauth(cert=%s/clientcert.pem,key=%s/clientkey.pem,username=test1),ssl(CA=%s/CA.pem),sctp,localhost,3023" % (utils.keydir, utils.keydir, utils.keydir),
                           do_small_test, CA="%s/clientcert.pem" % utils.keydir)

def test_certauth_ssl_tcp_acc_connect():
    print("Test certauth over ssl over tcp")

    # First test bypassing authentication from the auth_begin callback;
    TestAcceptConnect(o,
           ("certauth(),ssl(key=%s/key.pem,cert=%s/cert.pem),tcp,3023" %
            (utils.keydir, utils.keydir)),
           ("certauth(),ssl(key=%s/key.pem,cert=%s/cert.pem),tcp,3024" %
            (utils.keydir, utils.keydir)),
           "certauth(),ssl(CA=%s/CA.pem),tcp,localhost,3023" % utils.keydir,
                      do_small_test, auth_begin_rv=0)

    # Now try password authentication.
    TestAcceptConnect(o,
           ("certauth(enable-password),ssl(key=%s/key.pem,cert=%s/cert.pem),tcp,3023" %
            (utils.keydir, utils.keydir)),
           ("certauth(enable-password),ssl(key=%s/key.pem,cert=%s/cert.pem),tcp,3024" %
            (utils.keydir, utils.keydir)),
           ("certauth(enable-password,password=asdfasdf),ssl(CA=%s/CA.pem),tcp,localhost,3023" %
            utils.keydir),
                      do_small_test, expect_pw = "asdfasdf", expect_pw_rv = 0)

    # Test the password request
    TestAcceptConnect(o,
           ("certauth(enable-password),ssl(key=%s/key.pem,cert=%s/cert.pem),tcp,3023" %
            (utils.keydir, utils.keydir)),
           ("certauth(enable-password),ssl(key=%s/key.pem,cert=%s/cert.pem),tcp,3024" %
            (utils.keydir, utils.keydir)),
           ("certauth(enable-password),ssl(CA=%s/CA.pem),tcp,localhost,3023" %
            utils.keydir),
                      do_small_test, expect_pw = "jkl;", expect_pw_rv = 0,
                      password = "jkl;")

class MuxHandler:
    """ """
    def __init__(self, o, num_channels = 10):
        self.o = o
        self.channels = [None for x in range(num_channels)]
        self.waiter = gensio.waiter(o)
        self.expect_close = -1
        self.op_count = 0
        return

    def read_callback(self, io, err, buf, auxdata):
        i = int(io.control(0, True, gensio.GENSIO_CONTROL_SERVICE, None))
        if (err):
            if (self.expect_close != -1 and i != self.expect_close):
                raise utils.HandlerException(
                    "Invalid read close on channel %d: %s" % (i, err))
            if err != "Remote end closed connection":
                raise utils.HandlerException(
                    "Invalid error on read close: %s" % err)
            io.close(self)
            return 0
        raise utils.HandlerException("Unexpected read")
        return len(buf)

    def write_callback(self, io):
        return

    def dec_op_count(self):
        if (self.op_count == 0):
            raise utils.HandlerException("Too many ops")
        self.op_count -= 1
        if (self.op_count == 0):
            self.waiter.wake()
        return

    def new_channel(self, io1, io2, auxdata):
        i = int(io2.control(0, True, gensio.GENSIO_CONTROL_SERVICE, None))
        if (self.channels[i]):
            raise utils.HandlerException(
                "Got channel %d, but it already exists" % i)
        self.channels[i] = io2
        io2.set_cbs(self)
        self.dec_op_count()
        io2.read_cb_enable(True)
        return 0

    def new_connection(self, acc, io):
        self.new_channel(None, io, None)
        return

    def close_done(self, io):
        i = int(io.control(0, True, gensio.GENSIO_CONTROL_SERVICE, None))
        if (self.expect_close != -1 and self.expect_close != i):
            raise utils.HandlerException("Unexpected close for channel %d" % i)
        if (self.channels[i] is None):
            raise utils.HandlerException(
                "Got channel %d, but it didn't exist in array" % i)
        self.channels[i] = None;
        self.dec_op_count()
        return

    def set_expect_close(self, nr):
        self.expect_close = nr
        return

    def set_op_count(self, nr):
        self.op_count = nr
        return

    def open_done(self, io, err):
        i = int(io.control(0, True, gensio.GENSIO_CONTROL_SERVICE, None))
        if (err):
            raise utils.HandlerException(
                "Error opening channel %d: %s" % (i, err))
        io.read_cb_enable(True)
        self.dec_op_count()
        return

    def wait(self, count = 1, timeout = 0):
        if (timeout > 0):
            return self.waiter.wait_timeout(count, timeout)
        else:
            return self.waiter.wait(count)
        return

def test_mux_limits():
    print("Testing mux limits")
    handlemuxacc = MuxHandler(o, num_channels = 10)
    muxacc = gensio.gensio_accepter(o, "mux(max_channels=10),tcp,3023",
                                    handlemuxacc)
    muxacc.startup()

    handlemuxcl = MuxHandler(o, num_channels = 10)
    muxcl = gensio.gensio(o,
                          "mux(service=0,max_channels=10),tcp,localhost,3023",
                          handlemuxcl)
    handlemuxcl.channels[0] = muxcl
    handlemuxacc.set_op_count(1)
    handlemuxcl.set_op_count(1)
    muxcl.open(handlemuxcl)

    if (handlemuxcl.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for single client open finish")
    if (handlemuxacc.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for single client open finish")

    print("Opening all channels")
    handlemuxcl.set_op_count(9)
    handlemuxacc.set_op_count(9)
    for i in range(1, 10):
        handlemuxcl.channels[i] = muxcl.alloc_channel(["service=%d" % i],
                                                      handlemuxcl)
        handlemuxcl.channels[i].open(handlemuxcl)

    print("Waiting for channels");
    if (handlemuxcl.wait(timeout = 2000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for client open finish")
    if (handlemuxacc.wait(timeout = 2000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for server open finish")

    print("Trying an open that should fail")
    try:
        muxcl.alloc_channel(["service=%d" % 10], handlemuxcl)
    except Exception as err:
        if str(err) != "gensio:alloc_channel: Object was already in use":
            raise utils.HandlerException("Got wrong error: %s" % str(err))
    else:
        raise utils.HandlerException(
            "No exception when opening too many channels")

    print("Close one channel")
    handlemuxcl.set_expect_close(3)
    handlemuxacc.set_expect_close(3)
    handlemuxcl.set_op_count(1)
    handlemuxacc.set_op_count(1)
    handlemuxacc.channels[3].close(handlemuxacc)

    if (handlemuxcl.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for single client close finish")
    if (handlemuxacc.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for single server close finish")

    print("Open that channel again")
    handlemuxacc.set_op_count(1)
    handlemuxcl.set_op_count(1)
    handlemuxcl.channels[3] = muxcl.alloc_channel(["service=3"],
                                                  handlemuxcl)
    handlemuxcl.channels[3].open(handlemuxcl)

    if (handlemuxcl.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for client singe close finish")
    if (handlemuxacc.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for server single close finish")

    print("Close all channels")
    handlemuxcl.set_expect_close(-1)
    handlemuxacc.set_expect_close(-1)
    handlemuxcl.set_op_count(10)
    handlemuxacc.set_op_count(10)
    for i in range(0, 10):
        if (i % 2 == 0):
            handlemuxcl.channels[i].close(handlemuxcl)
        else:
            handlemuxacc.channels[i].close(handlemuxacc)

    if (handlemuxcl.wait(timeout = 2000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for client all close finish")
    if (handlemuxacc.wait(timeout = 2000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for server all close finish")

    print("Re-open the mux")
    handlemuxacc.set_op_count(1)
    handlemuxcl.set_op_count(1)
    muxcl.open(handlemuxcl)
    if (handlemuxcl.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for single client open finish")
    if (handlemuxacc.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for single client open finish")

    print("Re-close the mux")
    handlemuxacc.set_op_count(1)
    handlemuxcl.set_op_count(1)
    handlemuxcl.channels[0] = muxcl
    muxcl.close(handlemuxcl)
    if (handlemuxcl.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for single client open finish")
    if (handlemuxacc.wait(timeout = 1000) == 0):
        raise utils.HandlerException(
            "Timeout waiting for single client open finish")

    return

def test_mux_oob():
    print("Test mux sctp oob")
    io1 = utils.alloc_io(o, "mux,sctp,localhost,3023",
                         do_open = False, chunksize = 64)
    ta = TestAccept(o, io1, "mux,sctp,3023", do_oob_test)

class TestConCon:
    def __init__(self, o, io1, io2, tester, name,
                 do_close = True,
                 expected_raddr1 = None, expected_raddr2 = None):
        self.o = o
        self.name = name
        self.io1 = io1
        self.io2 = io2
        self.waiter = gensio.waiter(o)
        io1.open(self)
        io2.open(self)
        self.wait(2)
        if expected_raddr1:
            check_raddr(io1, self.name, expected_raddr1)
        if expected_raddr2:
            check_raddr(io2, self.name, expected_raddr2)
        tester(self.io1, self.io2)
        if do_close:
            self.close()

    def close(self):
        self.io1.read_cb_enable(False)
        self.io2.read_cb_enable(False)
        utils.io_close(self.io1)
        utils.io_close(self.io2)

        # Break all the possible circular references.
        del self.io1
        del self.io2

    def open_done(self, io, err):
        if err:
            raise Exception("TestConCon open error for %s: %s" %
                            (self.name, err))
        self.waiter.wake()

    def wait(self, nr):
        self.waiter.wait(nr)

def tc_relpkt():
    print("Test relpkt over msgdelim over serial")
    io1 = utils.alloc_io(o, "mux(mode=server),relpkt(mode=server),msgdelim,serialdev,/dev/ttyPipeA0", do_open = False)
    io2 = utils.alloc_io(o, "mux,relpkt,msgdelim,serialdev,/dev/ttyPipeB0", do_open = False)
    TestConCon(o, io1, io2, do_test, "relpkt1",
               expected_raddr1 = "/dev/ttyPipeA0,9600N81 RTSHI DTRHI",
               expected_raddr2 = "/dev/ttyPipeB0,9600N81 RTSHI DTRHI")

def tc_small_relpkt():
    print("Test small relpkt over msgdelim over serial")
    io1 = utils.alloc_io(o, "relpkt(mode=server),msgdelim,serialdev,/dev/ttyPipeA0", do_open = False)
    io2 = utils.alloc_io(o, "relpkt,msgdelim,serialdev,/dev/ttyPipeB0", do_open = False)
    TestConCon(o, io1, io2, do_small_test, "relpkt1",
               expected_raddr1 = "/dev/ttyPipeA0,9600N81 RTSHI DTRHI",
               expected_raddr2 = "/dev/ttyPipeB0,9600N81 RTSHI DTRHI")

def do_medium_test(io1, io2):
    rb = os.urandom(131071)
    print("  testing io1 to io2")
    utils.test_dataxfer(io1, io2, rb, timeout=10000)
    print("  testing io2 to io1")
    utils.test_dataxfer(io2, io1, rb, timeout=10000)
    print("  testing bidirection between io1 and io2")
    utils.test_dataxfer_simul(io1, io2, rb, timeout=10000)
    print("  Success!")

def tc_medium_relpkt():
    print("Test medium relpkt over msgdelim over serial")
    io1 = utils.alloc_io(o, "mux(mode=server),relpkt(mode=server),msgdelim,serialdev,/dev/ttyPipeA0,1000000", do_open = False)
    io2 = utils.alloc_io(o, "mux,relpkt,msgdelim,serialdev,/dev/ttyPipeB0,1000000", do_open = False)
    TestConCon(o, io1, io2, do_medium_test, "relpkt1",
               expected_raddr1 = "/dev/ttyPipeA0,1000000N81 RTSHI DTRHI",
               expected_raddr2 = "/dev/ttyPipeB0,1000000N81 RTSHI DTRHI")

def tc_large_relpkt():
    print("Test large relpkt over udp")
    io1 = utils.alloc_io(o, "mux,relpkt,udp,localhost,3023", do_open = False)
    TestAccept(o, io1, "mux,relpkt,udp,localhost,3023", do_large_test)

test_echo_gensio()
test_echo_device()
test_serial_pipe_device()
test_stdio_basic()
test_stdio_basic_stderr()
test_pty_basic()
test_stdio_small()
ta_tcp()
ta_udp()
ta_telnet()
ta_ssl_tcp()
ta_certauth_tcp()
ta_sctp()
test_tcp_small()
test_tcp_urgent()
test_telnet_small()
test_sctp_small()
test_sctp_streams()
test_sctp_oob()
test_ipmisol_small()

test_modemstate()

test_tcp_acc_connect()
test_udp_acc_connect()
test_sctp_acc_connect()
test_telnet_sctp_acc_connect()
test_ssl_sctp_acc_connect()
test_certauth_sctp_acc_connect()
test_certauth_ssl_tcp_acc_connect()

test_ipmisol_large()
test_rs485()

test_mux_limits()
ta_mux_sctp()
test_mux_sctp_small()
test_mux_tcp_large()
test_mux_oob()

tc_relpkt()
tc_small_relpkt()
tc_medium_relpkt()
tc_large_relpkt()
