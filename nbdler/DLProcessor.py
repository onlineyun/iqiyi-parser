
# from urllib import request
import socket, ssl
import threading
import time
from .DLInfos import Target
# import logging
import traceback
from .DLError import HTTPErrorCounter, DLUrlError
# import gc
# import io
from . import DLCommon as cv
import http.client

import sys

if sys.version_info <= (2, 7):
    from urllib import splitvalue, splitquery, urlencode

elif sys.version_info >= (3, 0):
    from urllib.parse import splitvalue, splitquery, urlencode


TMP_BUFFER_SIZE = 1024 * 1024 * 1

socket.setdefaulttimeout(3)
ssl._create_default_https_context = ssl._create_unverified_context

class OpaReq:
    def __init__(self):
        self.cut = []
        self.pause = False
        self.switch = False
        self.wait = 0

    def clear(self):
        self.cut = []
        self.pause = False
        self.switch = False
        self.wait = 0




class Processor(object):
    def __init__(self, Progress, Urlid):
        self.progress = Progress

        self.url = None
        self.urlid = Urlid

        self.buff = []
        self.buff_inc = 0
        self.opareq = OpaReq()

        self.target = Target()

        self.connection = None
        self.respond = None

        self.__thread__ = None

        self.__opa_lock__ = threading.Lock()
        self.__run_lock__ = threading.Lock()
        self.__buff_lock__ = threading.Lock()

        self.err = HTTPErrorCounter()

        self.critical = False

        # self.shutdwon_flag = False
        # self.err_counter =

    def Thread(self, *args, **kwargs):
        return self.getHandler().threads.Thread(*args, **kwargs)

    def loadUrl(self, Urlid):

        urls = self.getHandler().url.getAllUrl()

        if Urlid in urls:
            self.url = urls[Urlid]
            self.target.load(self.url.url)
        else:
            self.url = None

        self.urlid = Urlid

    def isReady(self):
        return not self.progress.status.isGoEnd() and not self.progress.status.pausing() and \
               not self.progress.status.isPaused() and not self.critical


    def isRunning(self):
        return self.__thread__ and self.__thread__.isRunning()


    def getHandler(self):
        return self.progress.globalprog.handler


    def selfCheck(self):

        if self.opareq.pause:
            self.getPause()
            return False

        if not self.url:
            self.loadUrl(self.urlid)

        if not self.url or not self.getHandler().url.hasUrl(self.urlid):
            self.getSwitch()

        if self.isReady():
            if not self.isRunning():
                if self.opareq.cut:
                    self.getCut()

                if self.opareq.pause:
                    self.getPause()
                    return False

                return True
        else:
            self.close()

        return False

    def run(self):
        with self.__run_lock__:
            if self.selfCheck():

                thr = self.Thread(target=self.__getdata__, name=cv.PROCESSOR)
                self.__thread__ = thr
                thr.start()

    def __getdata__(self):
        if self.opareq.cut:
            self.getCut()

        if self.opareq.pause:
            self.getPause()
            return

        conn, res = self.makeConnection()

        self.connection = conn
        self.respond = res

        if res:
            if res.status == 206 or res.status == 200:
                self.target.update(headers=res.headers._headers, code=res.status)
                self.err.clear()
                self.__recv_loop__(conn, res)
            elif res.status >= 400 and res.status < 500:
                print(res.status)
                self._4xx(res)
            elif res.status == 302:
                self.target.update(url=res.headers.get('location'))
            else:
                print(res.status)
            res.close()

        conn.close()



    def makeConnection(self):
        conn = None
        res = None

        try:

            if self.target.protocol == 'https':
                conn = http.client.HTTPSConnection(host=self.target.host, port=self.target.port)
            elif self.target.protocol == 'http':
                conn = http.client.HTTPConnection(host=self.target.host, port=self.target.port)

            req_path, req_headers = self.makeReqHeaders()

            conn.request('GET', req_path, '', req_headers)
            res = conn.getresponse()
        except socket.timeout as e:
            self._timeout(e)
        except Exception as e:
            traceback.print_exc()
            self._unknown(e)

        return conn, res


    def makeReqHeaders(self):

        range_format = self.url.range_format
        Range = (self.progress.begin + self.progress.go_inc, self.progress.end)

        req_path = self.target.path

        req_headers = dict(self.url.headers.items())

        if range_format[0] == '&':
            path, query = splitquery(self.target.path)
            query_dict = extract_query(query)
            range_format = range_format % Range
            for i in range_format[1:].split('&'):
                param_key, param_value = splitvalue(i)
                query_dict[param_key] = param_value

            new_query = urlencode(query_dict)
            req_path = '%s?%s' % (path, new_query)

        else:

            range_field = range_format % Range
            key_value = [i.strip() for i in range_field.split(':')]

            key = key_value[0]
            value = key_value[1]

            add_headers = {
                key: value,
                'Accept-Ranges': 'bytes'
            }

            req_headers.update(add_headers)

        return req_path, req_headers



    def _unknown(self, res):
        handler = self.getHandler()
        try:
            self.err.http_unknown(handler, res)
        except DLUrlError as e:
            if self.err.getCounter('unknown') >= len(handler.url.getAllUrl()) * HTTPErrorCounter.ERR_UNKNOWN_THRESHOLD:
                self.getCritical(e)
            else:
                self.getSwitch()

    def _4xx(self, res):
        handler = self.getHandler()
        try:
            self.err.http_4xx(handler, res)
        except DLUrlError as e:
            if self.err.getCounter(res.status) >= len(handler.url.getAllUrl()) * HTTPErrorCounter.ERR_4XX_THRESHOLD:
                self.getCritical(e)
            else:
                self.getSwitch()

    def _timeout(self, res):
        handler = self.getHandler()
        try:
            self.err.http_timeout(handler, res)
        except DLUrlError as e:
            if self.err.getCounter('timeout') >= len(handler.url.getAllUrl())*HTTPErrorCounter.ERR_TIMEOUT_THRESHOLD:
                self.getCritical(e)

            else:
                self.getSwitch()

    def isCritical(self):
        return self.critical


    def getCritical(self, err):
        self.critical = True
        self.shutdown()
        self.progress.globalprog.raiseUrlError(err)

    def __recv_loop__(self, conn, res):
        buff = b''
        while True:
            if self.opareq.cut:
                self.getCut()

            if self.opareq.pause:
                self.buffer(buff)
                self.getPause()
                break

            # if self.opareq.wait:
            #     self.getWait()

            last_len = len(buff)
            rest = self.progress.length - self.progress.go_inc
            try:
                if rest == 0:
                    if len(buff) != 0:
                        self.buffer(buff)
                        buff = ''
                        self.close()
                    break
                elif rest < 4096:
                    buff += res.read(rest)
                else:
                    buff += res.read(4096)
            except:

                self.buffer(buff[:last_len])
                return

            if len(buff) == last_len:
                if len(buff) != 0:
                    self.buffer(buff)
                return

            if len(buff) - last_len > rest:
                self.buffer(buff[:self.progress.length - self.progress.done_inc - self.buff_inc])
                return

            self.progress.go(len(buff) - last_len)

            if self.progress.go_inc >= self.progress.length:
                self.buffer(buff[:self.progress.length - self.progress.done_inc - self.buff_inc])
                self.close()
                break
            elif len(buff) >= TMP_BUFFER_SIZE:
                self.buffer(buff)
                buff = b''


    def close(self):
        self.progress.globalprog.ckeckAllGoEnd()
        self.opareq.clear()


    def pause(self):
        self.opareq.pause = True
        self.progress.status.startPause()

    shutdown = pause

    def getPause(self):
        self.opareq.pause = False
        self.progress.status.endPause()

    def getWait(self):
        time.sleep(self.opareq.wait)

    def getSwitch(self):

        next_urlid = self.getHandler().url.getNextId(self.urlid)
        self.loadUrl(next_urlid)


    def buffer(self, buff):
        with self.__buff_lock__:
            self.buff.append(buff)
            self.buff_inc += len(buff)

        self.progress.globalprog.checkBuffer(len(buff))

    def clearBuffer(self):
        self.buff = []
        self.buff_inc = 0

    def releaseBuffer(self, f):
        with self.__buff_lock__:
            f.seek(self.progress.begin + self.progress.done_inc)
            buff = b''.join(self.buff)
            f.write(buff)
            self.progress.done(len(buff))

            self.clearBuffer()

    def cutRequest(self, Range):

        last_range = [self.progress.begin, self.progress.end]

        self.opareq.cut = [Range[0], Range[1]]

        while True:
            if not self.opareq.cut or (self.isReady() and not self.isRunning() and not self.getHandler().threads.getAll(cv.INSPECTOR)):
                break

            time.sleep(0.01)

        return [self.progress.end, last_range[1]] if last_range[1] != self.progress.end else []


    def getCut(self):
        while self.progress.begin + self.progress.go_inc >= self.opareq.cut[0]:
            self.opareq.cut[0] += self.progress.globalprog.handler.file.BLOCK_SIZE

        if self.opareq.cut[0] >= self.opareq.cut[1]:
            retrange = []
        else:
            retrange = self.opareq.cut

        if retrange:
            self.progress.globalprog.cut(self.progress, retrange)

        self.opareq.cut = []



def extract_query(query_str):
    querys = {}
    if query_str:
        for i in query_str.split('&'):
            key_value = splitvalue(i)
            querys[key_value[0]] = key_value[1]

    return querys