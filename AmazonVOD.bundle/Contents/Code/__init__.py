import re, pickle
from BeautifulSoup import BeautifulSoup

# PMS plugin framework
from PMS import *
from PMS.Objects import *
from PMS.Shortcuts import *


####################################################################################################

PLUGIN_PREFIX     = "/video/AmazonVOD"
PREFS_PREFIX      = "%s/prefs||Amazon Preferences/" % PLUGIN_PREFIX


AMAZON_PROXY_URL            = "http://atv-sr.amazon.com/proxy/proxy"
AMAZON_SEARCH_URL           = "http://www.amazon.com/s/"
AMAZON_PRODUCT_URL          = "http://www.amazon.com/gp/product/%s"

CACHE_INTERVAL              = 3600
DEBUG                       = True

global __customerId, __token, __tokensChecked
__customerId = None
__token      = None
__tokensChecked = False

####################################################################################################

def Start():
  Plugin.AddPrefixHandler(PLUGIN_PREFIX, Menu, L("amazon"), "icon-default.png", "art-default.png")
  Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")
  Plugin.AddViewGroup("List", viewMode="List", mediaType="items")

def CreatePrefs():
  Prefs.Add(id='login', type='text', default='', label='Login Email')
  Prefs.Add(id='password', type='text', default='', label='Password', option='hidden')
  
def Menu():
  dir = MediaContainer()
  if Prefs.Get('login'):
    dir.Append(Function(DirectoryItem(MenuYourPurchases,"Your Purchases")))
  dir.Append(Function(SearchDirectoryItem(MenuSearch,"Search", "Search", R("search.png"))))
  dir.Append(PrefsItem(title="Preferences"))
  return dir

def MenuYourPurchases(sender):
  dir = MediaContainer(title2=sender.itemTitle)
  purchasedAsinList = purchasedAsin()
  for i in makeDirItemsFromAsin(purchasedAsinList):
    dir.AppendItem(i)
  return dir

def MenuSearch(sender, query=None):
  PMS.Log("MenuSearch query: %s" % repr(query))
  dir = MediaContainer(title2=sender.itemTitle)
  res = asin_search(query)
  items = makeDirItemsFromAsin(res)
  if len(items) == 0:
    dir.SetMessage("Search","No results found for %s" % query)
  for i in items:
    dir.Append(i)
  return dir;

def MenuSeasonList(sender, asin=None):
  dir = MediaContainer(title2=sender.itemTitle)

  PMS.Log('seasonlist for %s' % asin)

  url = AMAZON_PRODUCT_URL % asin

  azPage = HTTP.Request(url, errors='replace')
  asinStart   = azPage.find("&asinList=") + 10
  asinListStr = azPage[asinStart:asinStart+azPage[asinStart:].find("&")]

  asinInfo = asin_info(asinListStr.split(','))
  for i in makeDirItemsFromAsin(asinInfo):
    dir.Append(i)

  return dir


  pass

####################################################################################################

def makeDirItemsFromAsin(items):

  ret = []

  for asin in items:
    #PMS.Log(repr(asin))
    thumb = asin.get('IMAGE_URL_LARGE',asin.get('IMAGE_URL_SMALL',''))
    desc = asin.get('SYNOPSIS','')
    rating = float(asin.get('AMAZONRATINGS',0.0))

    if 'EPISODENUMBER' in asin and 'SEASONNUMBER' in asin:
      title = 'S%02dE%02d : %s' % (int(asin['SEASONNUMBER']),int(asin['EPISODENUMBER']),asin['TITLE'])
    else:
      title = asin.get('TITLE','')

    url = AMAZON_PRODUCT_URL % asin['ASIN']
    PMS.Log("%s" % url)
    duration = int(asin.get('RUNTIME',0))*60*1000

    stream_url = asin.get('STREAM_URL_1','')

    if stream_url != '':
      other_args = dict()
      if 'SEASONNUMBER' in asin:
        other_args['season'] = asin['SEASONNUMBER']
      if 'EPISODENUMBER' in asin:
        other_args['episode'] = asin['EPISODENUMBER']
      item = WebVideoItem(url,title,summary=desc,duration=str(duration),thumb=thumb,rating=str(rating),**other_args)
    else:
      item = Function(DirectoryItem(MenuSeasonList,"%s" % title),asin=asin['ASIN'])

    ret.append(item)

  ret.sort(cmp=lambda a,b: cmp(a.__dict__.get('title'),b.__dict__.get('title')))
  return ret


def signIn():

  PMS.Log("signIn() called")

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
  x = HTTP.Request('https://www.amazon.com/gp/flex/sign-in/select.html',values=params,encoding='utf-8')

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
  html = HTTP.Request(AMAZON_PROXY_URL,values=params,encoding='utf-8')
  jsonString = html.split("\n")[2]
  for i in JSON.ObjectFromString(jsonString):
    asinInfo = i.get('FeedAttributeMap',None)
    if asinInfo and asinInfo.get('ISSTREAMABLE','N') == 'Y':
      ret.append(asinInfo)

  return ret

def HandleRequest(pathNouns, count):
  customerId, token = streamingTokens()

  if pathNouns[0].startswith("prefs"):
    dir = MediaContainer()
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

  html = HTTP.Request(AMAZON_SEARCH_URL,values=params,errors='replace')

  soup = BeautifulSoup(html)

  asinList = []

  for e in soup.findAll('div', 'productTitle'):
    asin = re.sub(r'srProductTitle_(.*?)_\d+',r'\1',e['id'])
    asinList.append(asin)

  return asin_info(asinList)

def asin_info(asinList):
  if(len(asinList) == 0):
    return []

  # http://atv-sr.amazon.com/proxy/proxy?c=&token=&f=getASINList&asinList=B000V22QJ0&t=Streaming
  params = {
    'c': '',
    'token': '',
    'f': 'getASINList',
    'asinList': ','.join(asinList),
    't': 'Streaming'
  }
  html = HTTP.Request(AMAZON_PROXY_URL,values=params, errors='replace')

  jsonString = html.split("\n")[2]

  ret = []
  for i in JSON.ObjectFromString(jsonString):
    if i.get('ISSTREAMABLE','N') == 'Y':
      ret.append(i)
  return ret
