from PMS import Plugin, Log, XML, HTTP, Utils, JSON, Prefs
from PMS.MediaXML import *
from PMS.Shorthand import _L, _R, _E, _D
import re
import pickle
from BeautifulSoup import BeautifulSoup

####################################################################################################

PLUGIN_PREFIX     = "/video/AmazonVOD"
PREFS_PREFIX      = "%s/prefs||Amazon Preferences/" % PLUGIN_PREFIX


AMAZON_PROXY_URL            = "http://atv-sr.amazon.com/proxy/proxy"
AMAZON_SEARCH_URL           = "http://www.amazon.com/s/"
AMAZON_PRODUCT_URL          = "http://www.amazon.com/gp/product/%s"

CACHE_INTERVAL              = 3600
DEBUG                       = True

__customerId = None
__token      = None
__tokensChecked = False

####################################################################################################

def Start():
  Plugin.AddRequestHandler(PLUGIN_PREFIX, HandleRequest, _L("amazon"), "icon-default.png", "art-default.png")
  Plugin.AddViewGroup("InfoList", viewMode="InfoList", contentType="items")
  Plugin.AddViewGroup("List", viewMode="List", contentType="items")
  HTTP.__headers["User-agent"] = "Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_5_6; en-gb) AppleWebKit/528.16 (KHTML, like Gecko) Version/4.0 Safari/528.16"
  Prefs.Expose("loginemail", "Login Email")
  Prefs.Expose("password", "Password")
  
####################################################################################################

def makeDirItemsFromAsin(items):

  ret = []

  for asin in items:
    Log.Add(repr(asin))
    thumb = asin.get('IMAGE_URL_LARGE',asin.get('IMAGE_URL_SMALL',''))
    desc = asin.get('SYNOPSIS','')
    rating = float(asin.get('AMAZONRATINGS',0.0))

    if 'EPISODENUMBER' in asin and 'SEASONNUMBER' in asin:
      title = 'S%02dE%02d : %s' % (int(asin['SEASONNUMBER']),int(asin['EPISODENUMBER']),asin['TITLE'])
    else:
      title = asin.get('TITLE','')

    url = AMAZON_PRODUCT_URL % asin['ASIN']
    Log.Add("%s" % url)
    duration = int(asin.get('RUNTIME',0))*60*1000

    stream_url = asin.get('STREAM_URL_1','')

    if stream_url != '':
      item = WebVideoItem(url,title,desc,str(duration),thumb)
      item.SetAttr('rating',str(rating))
      if 'SEASONNUMBER' in asin:
        item.SetAttr('season',asin['SEASONNUMBER'])
      if 'EPISODENUMBER' in asin:
        item.SetAttr('episode',asin['EPISODENUMBER'])
    else:
      item = DirectoryItem("%s/seasonlist/%s" % (PLUGIN_PREFIX, asin['ASIN']),title,title)

    ret.append(item)

  ret.sort(cmp=lambda a,b: cmp(a.GetAttr('title'),b.GetAttr('title')))
  return ret


def signIn():

  Log.Add("signIn() called")

  USER = Prefs.Get("loginemail")
  PASS = Prefs.Get("password")

  if not (USER and PASS):
    return False

  x = HTTP.Get('https://www.amazon.com/gp/sign-in.html')

  sessId = None
  for idx,cookie in enumerate(HTTP.__cookieJar):
    if cookie.name == 'session-id':
      sessId = cookie.value

  if not sessId:
      return False

  params = {
      'path': '/gp/homepage.html',
      'useRedirectOnSuccess': '0',
      'protocol': 'https',
      'sessionId': sessId,
      'action': 'sign-in',
      'password': PASS,
      'email': USER
  }
  x = HTTP.Post('https://www.amazon.com/gp/flex/sign-in/select.html',params)

  return True

def streamingTokens():
  global __customerId, __token, __tokensChecked


  if (__customerId and __token) or __tokensChecked:
      return (__customerId,__token)

  __tokensChecked = True

  html = HTTP.Get('http://www.amazon.com/gp/video/streaming/')
  paramStart = html.find("&customer=")
  if paramStart == -1:
      ret = signIn()
      if not ret:
        return (None,None)
      html = HTTP.Get('http://www.amazon.com/gp/video/streaming/')
      paramStart = html.find("&customer=")
      if paramStart == -1:
          return (None,None)

  custParamStart = paramStart+10
  custParamEnd   = custParamStart + html[custParamStart:].find("&")
  __customerId = html[custParamStart:custParamEnd]

  tokenParamStart = html.find("&token=") + 7
  tokenParamEnd   = tokenParamStart + html[tokenParamStart:].find("&")
  __token         = html[tokenParamStart:tokenParamEnd]

  return (__customerId,__token)

def purchasedAsin():
  ret = []

  customerId, token = streamingTokens()

  if not (customerId and token):
    return ret

  # http://atv-sr.amazon.com/proxy/proxy?c=A2UADYTSXK548T&f=getQueue&token=af2c81f6854618a5a1b72fe206d674a2&t=Streaming
  params = {
    'c': customerId,
    'token': token,
    'f': 'getQueue',
    't': 'Streaming'
  }
  html = HTTP.Post(AMAZON_PROXY_URL,params, {})
  jsonString = html.split("\n")[2]
  for i in JSON.DictFromString(jsonString):
    asinInfo = i.get('FeedAttributeMap',None)
    if asinInfo and asinInfo.get('ISSTREAMABLE','N') == 'Y':
      ret.append(asinInfo)

  return ret

def HandleRequest(pathNouns, count):
  Log.Add("HandleRequest(%s,%d)" % (repr(pathNouns), count))

  customerId, token = streamingTokens()

  Log.Add("c: %s t: %s" % (str(customerId),str(token)))

  if count == 0:

    dir = MenuContainer()
    dir.SetAttr("title2","Main Menu")

    if customerId and token:
      dir.AppendItem(DirectoryItem("purchased","Your Purchases"))
    dir.AppendItem(SearchDirectoryItem("search","Search","Search", _R("search.png")))
    dir.AppendItem(DirectoryItem(PREFS_PREFIX, "Amazon Preferences", ""))

    return dir.ToXML()

  elif pathNouns[0].startswith("purchased"):
    dir = MenuContainer()
    dir.SetAttr("title2","Your Purchases")
    Log.Add('purchased')
    purchasedAsinList = purchasedAsin()
    for i in makeDirItemsFromAsin(purchasedAsinList):
      dir.AppendItem(i)
    return dir.ToXML()

    

  elif pathNouns[0].startswith("seasonlist"):
    dir = MenuContainer()

    Log.Add('seasonlist')

    if count == 2:
      asin = pathNouns[1]
      url = AMAZON_PRODUCT_URL % asin

      azPage = HTTP.Get(url)
      asinStart = azPage.find("&asinList=") + 10
      asinListStr  = azPage[asinStart:asinStart+azPage[asinStart:].find("&")]

      asinInfo = asin_info(asinListStr.split(','))
      for i in makeDirItemsFromAsin(asinInfo):
        dir.AppendItem(i)

    return dir.ToXML()


  # Framework Additions: - borrowed from iPlayer plugin
  elif pathNouns[0].startswith("search"):

    dir = MenuContainer()

    if count > 1:
      query = pathNouns[1]
      if count > 2:
        for i in range(2, len(pathNouns)): query += "/%s" % pathNouns[i]

      dir.SetAttr("title2","Search: %s" % query)
      res = asin_search(query)
      items = makeDirItemsFromAsin(res)
      if len(items) == 0:
        dir.SetMessage("Search","No results found for %s" % query)
      for i in items:
        dir.AppendItem(i)

    return dir.ToXML();

  elif pathNouns[0].startswith("prefs"):
    dir = MenuContainer()
    dir.SetAttr("title2","Amazon Preferences")

    loginemail = Prefs.Get("loginemail")
    password = Prefs.Get("password")

    if count >= 3:
        dir.SetAttr('replaceParent', '1')
        field = pathNouns[-2].split("^")[1]
        Prefs.Set(field, pathNouns[-1])
        __tokensChecked = False
        loginemail = Prefs.Get("loginemail")
        password = Prefs.Get("password")

        message_add = ""
        if loginemail != None and password != None:
            global __customerId, __token, __tokensChecked
            __customerId = None
            __token = None
            cid,tok  = streamingTokens()
            if cid and tok:
              message_add = "Login to Amazon OK"
            else:
              message_add = "Could not log into Amazon"


        title = "Preferences Updated"
        if field == 'loginemail':
            message = "Amazon login email updated."
        else:
            message = "Amazon password updated."

        dir.SetMessage(title,"%s\n%s" % (message,message_add))

    if loginemail != None:
        dir.AppendItem(SearchDirectoryItem(PREFS_PREFIX + "prefs^loginemail", "Change your email login", "Change your email login", ""))
    else:
        dir.AppendItem(SearchDirectoryItem(PREFS_PREFIX + "prefs^loginemail", "Set your email login", "Set your email login", ""))


    if password != None:
        dir.AppendItem(SearchDirectoryItem(PREFS_PREFIX + "prefs^password", "Change your password", "Change your password", ""))
    else:
        dir.AppendItem(SearchDirectoryItem(PREFS_PREFIX + "prefs^password", "Set your password", "Set your password", ""))


    return dir.ToXML();



def asin_search(query):

  params = {
    'search-alias': 'amazontv',
    'field-keywords': query
  }

  html = HTTP.Post(AMAZON_SEARCH_URL,params, {})

  soup = BeautifulSoup(html)

  asinList = []

  for e in soup.findAll('div', 'productTitle'):
    asin = re.sub(r'srProductTitle_(.*?)_\d+',r'\1',e['id'])
    asinList.append(asin)

  return asin_info(asinList)

def asin_info(asinList):
  if(len(asinList) == 0):
    return []

  # http://atv-sr.amazon.com/proxy/proxy?c=A2UADYTSXK548T&token=af2c81f6854618a5a1b72fe206d674a2&f=getASINList&asinList=B000V22QJ0&t=Streaming
  params = {
    'c': '',
    'token': '',
    'f': 'getASINList',
    'asinList': ','.join(asinList),
    't': 'Streaming'
  }
  html = HTTP.Post(AMAZON_PROXY_URL,params, {})

  jsonString = html.split("\n")[2]

  ret = []
  for i in JSON.DictFromString(jsonString):
    if i.get('ISSTREAMABLE','N') == 'Y':
      ret.append(i)
  return ret

class MenuContainer(MediaContainer):
  def __init__(self, art="art-default.png", viewGroup="List", title1=None, title2=None, noHistory=False, replaceParent=False):
    if title1 is None:
      title1 = _L("amazonlong")
    MediaContainer.__init__(self, art, viewGroup, title1, title2, noHistory, replaceParent)
