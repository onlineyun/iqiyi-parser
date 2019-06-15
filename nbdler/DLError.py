
import threading






class DLUrlError(Exception):
    def __init__(self, handler, res):
        # self.thread = thread
        self.handler = handler
        self.respond = res

    def __repr__(self):
        return '<%s> - %s' % (self.handler.file.name, self.respond.__repr__())


class HTTPErrorCounter:
    ERR_4XX_THRESHOLD = 4
    ERR_TIMEOUT_THRESHOLD = 100
    ERR_UNKNOWN_THRESHOLD = 20

    def __init__(self):
        self._counter = {}

    def http_timeout(self, handler, res):

        self._counter['timeout'] = self._counter.get('timeout', 0) + 1
        if self._counter['timeout'] % HTTPErrorCounter.ERR_TIMEOUT_THRESHOLD == 0:
            raise DLUrlError(handler, res)

    def http_4xx(self, handler, res):
        self._counter[res.status] = self._counter.get(res.status, 0) + 1
        if self._counter[res.status] % HTTPErrorCounter.ERR_4XX_THRESHOLD == 0:
            raise DLUrlError(handler, res)

    def http_unknown(self, handler, res):
        self._counter['unknown'] = self._counter.get('unknown', 0) + 1
        if self._counter['unkown'] % HTTPErrorCounter.ERR_UNKNOWN_THRESHOLD == 0:
            raise DLUrlError(handler, res)

    def getCounter(self, status):
        return self._counter[status]

    def clear(self):
        self._counter = {}
