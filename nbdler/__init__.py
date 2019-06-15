#---------------------------------------------------------------------------
# Name:        nbdler/__init__.py
# Author:      ZSAIm
#
# Created:     20-Jan-2019
# License:     Apache-2.0
#---------------------------------------------------------------------------


from .DLManager import Manager
from .DLProgress import GlobalProgress
from .DLHandler import AUTO, MANUAL, Handler
from .DLError import DLUrlError
import zlib
import io
from wsgiref.headers import Headers






__all__ = ['open', 'DLHandler', 'DLManager', 'DLProgress']

def open(fp=None, **kwargs):
    dlh = DLHandler.Handler()
    if fp:
        if 'read' in dir(fp):
            fp.seek(0)
            packet = fp.read()
        else:
            with io.open(fp + '.nbdler', 'rb') as f:
                packet = f.read()
        packet = eval(bytes.decode(zlib.decompress(packet)))
        dlh.unpack(packet)
    else:
        dlh.config(**kwargs)
        if kwargs.get('wait_for_run', False):
            dlh._batchnode_bak = kwargs
        else:
            dlh.batchAdd(**kwargs)

    return dlh


