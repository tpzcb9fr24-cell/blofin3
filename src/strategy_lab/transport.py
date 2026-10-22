"""Public market data only. Windows uses Schannel/WinHTTP and OS proxy settings.

No browser identity spoofing, browser cookies, challenge solving, credential
access, certificate bypass, alternate hosts or exchange write methods.
"""
import ctypes as ct
import html
import json
import re
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

AGENT='BloFinObserver/0.2.2 (public market data)'
HEADERS={'User-Agent':AGENT,'Accept':'application/json','Cache-Control':'no-cache'}
HOST='openapi.blofin.com'
PATHS={'/api/v1/market/candles','/api/v1/market/tickers'}
MAX_BYTES=4*1024*1024


def validate_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname!=HOST or p.port not in (None,443) or p.username or p.password or p.fragment or p.path not in PATHS:
        raise ValueError('Only official public BloFin candle/ticker HTTPS endpoints are permitted')
    return p.path+('?' + p.query if p.query else '')


class MarketHTTPError(RuntimeError):
    def __init__(self,status,body=b''):
        self.status=int(status)
        text=body.decode('utf-8','replace') if isinstance(body,bytes) else str(body)
        text=re.sub(r'<(head|style|script)\b[^>]*>.*?</\1>',' ',text,flags=re.S|re.I)
        text=html.unescape(re.sub(r'<[^>]+>',' ',text))
        text=' '.join(text.split())[:240]
        self.detail=text
        super().__init__(f'BloFin public data HTTP {self.status}'+(': '+text if text else '')+(' — request denied; no substitute market data used' if self.status==403 else ''))


def _api():
    if sys.platform!='win32':raise RuntimeError('Windows native networking requires Windows')
    from ctypes import wintypes as w
    dll=ct.WinDLL('winhttp',use_last_error=True)
    H=ct.c_void_p;D=w.DWORD;P=ct.c_void_p;S=w.LPCWSTR;PD=ct.POINTER(D)
    signatures={
        'WinHttpOpen':([S,D,S,S,D],H),
        'WinHttpSetTimeouts':([H,ct.c_int,ct.c_int,ct.c_int,ct.c_int],w.BOOL),
        'WinHttpConnect':([H,S,w.WORD,D],H),
        'WinHttpOpenRequest':([H,S,S,S,S,ct.POINTER(S),D],H),
        'WinHttpSetOption':([H,D,P,D],w.BOOL),
        'WinHttpSendRequest':([H,S,D,P,D,D,ct.c_size_t],w.BOOL),
        'WinHttpReceiveResponse':([H,P],w.BOOL),
        'WinHttpQueryHeaders':([H,D,S,P,PD,PD],w.BOOL),
        'WinHttpQueryDataAvailable':([H,PD],w.BOOL),
        'WinHttpReadData':([H,P,D,PD],w.BOOL),
        'WinHttpCloseHandle':([H],w.BOOL),
        'WinHttpWebSocketCompleteUpgrade':([H,ct.c_size_t],H),
        'WinHttpWebSocketSend':([H,ct.c_int,P,D],D),
        'WinHttpWebSocketReceive':([H,P,D,PD,ct.POINTER(ct.c_int)],D),
    }
    for name,(args,result) in signatures.items():
        fn=getattr(dll,name);fn.argtypes=args;fn.restype=result
    return dll


def _checked(value,stage):
    if not value:
        code=ct.get_last_error()
        if code==12002:raise TimeoutError('Windows network timeout: '+stage)
        raise OSError(code,'Windows network '+stage+' failed: '+ct.FormatError(code))
    return value


class _WindowsRequest:
    def __init__(self,path,timeout=15,websocket=False):
        self.api=_api();self.handles=[];self.socket=None
        try:
            # AUTOMATIC_PROXY=4 uses system and per-user proxy configuration.
            session=self._hold(self.api.WinHttpOpen(AGENT,4,None,None,0),'open')
            _checked(self.api.WinHttpSetTimeouts(session,5000,timeout*1000,timeout*1000,timeout*1000),'timeouts')
            connection=self._hold(self.api.WinHttpConnect(session,HOST,443,0),'connect')
            request=self._hold(self.api.WinHttpOpenRequest(connection,'GET',path,None,None,None,0x00800000),'request')
            # Never redirect to an unvalidated host.
            never=ct.c_ulong(0)
            _checked(self.api.WinHttpSetOption(request,88,ct.byref(never),ct.sizeof(never)),'redirect policy')
            if websocket:
                _checked(self.api.WinHttpSetOption(request,114,None,0),'websocket upgrade')
            headers='Accept: application/json\r\nCache-Control: no-cache\r\n'
            _checked(self.api.WinHttpSendRequest(request,headers,len(headers),None,0,0,0),'send')
            _checked(self.api.WinHttpReceiveResponse(request,None),'response')
            from ctypes import wintypes as w
            status=w.DWORD();length=w.DWORD(ct.sizeof(status))
            _checked(self.api.WinHttpQueryHeaders(request,19|0x20000000,None,ct.byref(status),ct.byref(length),None),'status')
            self.status=status.value;self.request=request
            if websocket and self.status==101:
                self.socket=self._hold(self.api.WinHttpWebSocketCompleteUpgrade(request,0),'complete upgrade')
            elif self.status!=200 or websocket:
                raise MarketHTTPError(self.status,self.read())
        except Exception:
            self.close();raise

    def _hold(self,handle,stage):
        _checked(handle,stage);self.handles.append(handle);return handle

    def read(self):
        from ctypes import wintypes as w
        parts=[];total=0
        while True:
            available=w.DWORD()
            _checked(self.api.WinHttpQueryDataAvailable(self.request,ct.byref(available)),'body size')
            if not available.value:break
            if total+available.value>MAX_BYTES:raise ValueError('BloFin response exceeds size limit')
            buffer=ct.create_string_buffer(available.value);received=w.DWORD()
            _checked(self.api.WinHttpReadData(self.request,buffer,available.value,ct.byref(received)),'body')
            if not received.value:break
            parts.append(buffer.raw[:received.value]);total+=received.value
        return b''.join(parts)

    def close(self):
        handles,self.handles=self.handles,[]
        for handle in reversed(handles):self.api.WinHttpCloseHandle(handle)
        self.socket=None


def get_json(url,timeout=15):
    path=validate_url(url)
    if sys.platform=='win32':
        request=_WindowsRequest(path,timeout)
        try:raw=request.read()
        finally:request.close()
        return json.loads(raw.decode('utf-8-sig'))
    try:
        with urlopen(Request(url,headers=HEADERS),timeout=timeout) as response:
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('BloFin response exceeds size limit')
        return json.loads(raw.decode('utf-8-sig'))
    except HTTPError as exc:
        raise MarketHTTPError(exc.code,exc.read(65536)) from None


class WindowsPublicSocket:
    def __init__(self,timeout=12):
        self.request=_WindowsRequest('/ws/public',timeout,websocket=True)

    def send(self,message):
        # This channel is only a public candle subscription and heartbeat.
        if message!='ping':
            payload=json.loads(message)
            if payload.get('op')!='subscribe' or set(payload)!={'op','args'}:
                raise ValueError('Only public subscriptions are allowed')
            from .market import SYMBOLS
            if not payload['args'] or any(set(a)!={'channel','instId'} or a['channel']!='candle5m' or a['instId'] not in SYMBOLS for a in payload['args']):
                raise ValueError('Only supported public five-minute candles are allowed')
        raw=message.encode('utf-8');buffer=ct.create_string_buffer(raw)
        result=self.request.api.WinHttpWebSocketSend(self.request.socket,2,buffer,len(raw))
        if result:raise OSError(result,'Windows public WebSocket send failed')

    def recv(self):
        from ctypes import wintypes as w
        chunks=[];total=0
        while True:
            buffer=ct.create_string_buffer(16384);received=w.DWORD();kind=ct.c_int()
            result=self.request.api.WinHttpWebSocketReceive(self.request.socket,buffer,len(buffer),ct.byref(received),ct.byref(kind))
            if result==12002:raise TimeoutError('Windows public WebSocket receive timeout')
            if result:raise OSError(result,'Windows public WebSocket receive failed')
            if kind.value==4:return ''
            if kind.value not in (2,3):raise ValueError('Unexpected non-text public WebSocket message')
            total+=received.value
            if total>MAX_BYTES:raise ValueError('Public WebSocket message too large')
            chunks.append(buffer.raw[:received.value])
            if kind.value==2:return b''.join(chunks).decode('utf-8')

    def close(self):self.request.close()


def public_socket(timeout=12):
    if sys.platform=='win32':return WindowsPublicSocket(timeout)
    import websocket
    return websocket.create_connection('wss://openapi.blofin.com/ws/public',timeout=timeout,suppress_origin=True,header={'User-Agent':AGENT})


def transport_name():
    return 'Windows native HTTPS/WebSocket (system proxy)' if sys.platform=='win32' else 'Standard public HTTPS/WebSocket'
