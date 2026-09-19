"""Public data adapters. No executable JavaScript is evaluated."""
import ast
from datetime import datetime,timezone,timedelta
from difflib import SequenceMatcher
import gzip,html,json,math,re,time,unicodedata
from urllib.request import Request,urlopen,build_opener,ProxyHandler

TZ=timezone(timedelta(hours=8))
CORE={1:'澳彩',31:'利记',3:'皇冠',8:'Bet365'}
BOOK_NAMES={**CORE,50:'1xBet',17:'Mansion88',24:'12bet',42:'18Bet',12:'Easybet',4:'Ladbrokes',14:'Vcbet',19:'Interwetten'}

def book_name(cid):return BOOK_NAMES.get(int(cid),'公司ID '+str(cid))

def now():return datetime.now(TZ)
def fetch(url,referer,timeout=18):
    error=None
    for attempt in range(2):
        try:
            request=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':referer})
            # A failed system proxy must not make the independent job lose every
            # checkpoint. Retry public data directly; never disable TLS checking.
            open_request=urlopen if attempt==0 else build_opener(ProxyHandler({})).open
            with open_request(request,timeout=timeout) as response:raw=response.read()
            if raw[:2]==b'\x1f\x8b':raw=gzip.decompress(raw)
            if not raw:raise ValueError('empty source response')
            return raw
        except Exception as exc:
            error=exc
            if attempt==0:time.sleep(.5)
    raise error

def listing(raw):
    text=raw.decode('gb18030',errors='replace')
    period=re.search(r'name="expect"\s+value="(\d+)"',text)
    if not period:raise ValueError('Cannot read current Beidan issue')
    out=[]
    for tag,body in re.findall(r'(<tr\b[^>]*class="vs_lines[^>]*>)(.*?)</tr>',text,re.S):
        value=re.search(r'value="([^"]+)"',tag)
        if not value:continue
        r=dict(re.findall(r"(\w+):'([^']*)'",html.unescape(value[1])))
        if not r.get('homeTeam') or not r.get('guestTeam'):continue
        r['no']=int(r['index']);r['period']=period[1];out.append(r)
    if not out:raise ValueError('No fixtures parsed from Beidan source')
    if len({(r['period'],r['no']) for r in out})!=len(out):raise ValueError('Duplicate Beidan fixture numbers')
    return out

def scalar_array(raw):
    parts=[];start=0;quote=None;escape=False
    for i,ch in enumerate(raw):
        if escape:escape=False
        elif quote and ch=='\\':escape=True
        elif quote and ch==quote:quote=None
        elif not quote and ch in ('"',"'"):quote=ch
        elif not quote and ch==',':parts.append(raw[start:i]);start=i+1
    parts.append(raw[start:]);out=[]
    for x in parts:
        x=x.strip()
        out.append(None if x in ('','null','undefined') else True if x=='true' else False if x=='false' else ast.literal_eval(x))
    return out

def fixtures(raw):
    doc=json.loads(raw)
    if doc.get('ErrCode')!=0:raise ValueError('Fixture API error')
    tables={'A':{},'B':{}}
    for table,n,values in re.findall(r'([AB])\[(\d+)\]=\[(.*?)\];',doc['Data']):tables[table][int(n)]=scalar_array(values)
    expected=int(re.search(r'var matchcount=(\d+)',doc['Data'])[1])
    if len(tables['A'])!=expected:raise ValueError('Fixture schema/count changed')
    out=[]
    for a in tables['A'].values():
        d=[int(v) for v in a[6].split(',')];d[1]+=1
        out.append(dict(id=a[0],home=a[4],away=a[5],home_id=a[2],away_id=a[3],league=tables['B'][a[1]][2],kickoff=datetime(*d,tzinfo=timezone.utc).astimezone(TZ).isoformat(),state=a[7],home_score=a[8],away_score=a[9]))
    return out

def clean(s):
    s=html.unescape(re.sub(r'<[^>]*>','',s or ''))
    s=s.replace('(中)','').replace('（中）','')
    return re.sub(r'[^\w\u4e00-\u9fff]','',unicodedata.normalize('NFKC',s)).lower()

def bridge(raw):
    text=raw.decode('utf-8-sig');out=[]
    for value in re.findall(r'A\[\d+\]="(.*?)"\.split\(\x27\^\x27\)',text):
        a=value.split('^')
        if len(a)<60:continue
        if not a[59].isdigit():continue
        out.append(dict(id=int(a[0]),no=int(a[59]),home=clean(a[5]),away=clean(a[8]),date=a[36],year=a[43]))
    if not out:raise ValueError('No Beidan cross-reference from Titan source')
    return out

def compatible(cn,other):
    a,b=clean(cn),clean(other)
    if a==b:return True
    # Preserve youth, reserve and women's qualifiers; never merge their teams.
    def markers(s):return ('女' in s,tuple(re.findall(r'u\d+',s)),'b队' in s or '预备' in s or '青年' in s)
    if markers(a)!=markers(b):return False
    return len(a)>=3 and len(b)>=3 and SequenceMatcher(None,a,b).ratio()>=.7

def match_fixture(row,all_fixtures,bridges,aliases):
    target=datetime.fromisoformat(row['endTime']).replace(tzinfo=TZ)+timedelta(minutes=10)
    candidates=[f for f in all_fixtures if abs((datetime.fromisoformat(f['kickoff'])-target).total_seconds())<=1200]
    bridged=[]
    for f in candidates:
        for b in bridges:
            if b['id']==f['id'] and b['no']==row['no']:
                # Fixture ID+number+time, plus both actual team labels.
                home_ok=compatible(row['homeTeam'],b['home']) or f['home'] in aliases.get(row['homeTeam'],[])
                away_ok=compatible(row['guestTeam'],b['away']) or f['away'] in aliases.get(row['guestTeam'],[])
                if home_ok and away_ok:bridged.append(f)
    bridged={f['id']:f for f in bridged}
    if len(bridged)==1:return next(iter(bridged.values())),'北单编号+双队名+时间'
    named=[f for f in candidates if f['home'] in aliases.get(row['homeTeam'],[]) and f['away'] in aliases.get(row['guestTeam'],[])]
    if len(named)==1:return named[0],'双队名词典+时间'
    return None,'无法唯一核对两队及时间'

def parse_odds(raw):
    doc=json.loads(raw)
    if doc.get('ErrCode')!=0 or doc.get('MatchState')!=0:raise ValueError('Odds not prematch')
    books={}
    for c in doc['Data'].get('mixodds',[]):
        ou=c.get('ou',{});f,l=ou.get('f'),ou.get('l')
        if not f or not l:continue
        try:
            qs=[dict(line=float(q['g']),over=float(q['u']),under=float(q['d'])) for q in (f,l)]
            if not all(math.isfinite(v) and v>0 for q in qs for v in q.values()):continue
            if any(abs(q['line']*4-round(q['line']*4))>1e-8 for q in qs):continue
            books[int(c['cid'])]=dict(initial=qs[0],live=qs[1])
        except (KeyError,TypeError,ValueError):continue
    if not books:raise ValueError('No valid prematch quotes')
    return books

def settlement(total,line,water,side):
    if side not in ('over','under') or not isinstance(total,int) or total<0 or not all(math.isfinite(v) and v>0 for v in (line,water)) or abs(line*4-round(line*4))>1e-8:raise ValueError('Invalid settlement')
    parts=[line-.25,line+.25] if round(line*4)%2 else [line]
    signs=[(total-p)*(1 if side=='over' else -1) for p in parts]
    label='全赢' if all(x>0 for x in signs) else '全输' if all(x<0 for x in signs) else '半赢' if any(x>0 for x in signs) else '半输' if any(x<0 for x in signs) else '走盘'
    return label,round(sum(water if x>0 else -1 if x<0 else 0 for x in signs)/len(signs),6)
