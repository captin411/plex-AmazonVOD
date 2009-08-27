import time

# PMS plugin framework
from PMS import *
from PMS.Objects import *
from PMS.Shortcuts import *
#from lxml import etree
from boto.connection import AWSQueryConnection


####################################################################################################

PLUGIN_PREFIX     = "/video/AmazonVOD"
PREFS_PREFIX      = "%s/prefs||Amazon Preferences/" % PLUGIN_PREFIX

AMAZON_PROXY_URL            = "http://atv-sr.amazon.com/proxy/proxy"
AMAZON_PRODUCT_URL          = "http://www.amazon.com/gp/product/%s"
AMAZON_PLAYER_URL           = "http://www.amazon.com/gp/video/streaming/mini-mode.html?asin=%s&version=r-180"
AMAZON_AWS_HOST             = "ecs.amazonaws.com"
AMAZON_AWS_PATH             = "/onca/xml"
AMAZON_AWS_URL              = "http://%s%s" % (AMAZON_AWS_HOST, AMAZON_AWS_PATH)
AMAZON_AWS_KEY              = "0BARCCRGVHBC4DBYAN82"
AMAZON_AWS_SECRET           = "iwJYwj3RPe/pwLKKhU1cmJRuEu3RSUpNp+UiVRsm" # yeah don't even try it, I have no paid services with Amazon so this isn't really 'secret' =)

CACHE_INTERVAL              = 3600
DEBUG                       = True

__customerId = None
__token      = None
__tokensChecked = False

__purchasedAsins = dict()

####################################################################################################

def Start():
  Plugin.AddPrefixHandler(PLUGIN_PREFIX, Menu, L("amazon"), "icon-default.png", "art-default.jpg")
  Plugin.AddPrefixHandler("%s/:/prefs/set" % PLUGIN_PREFIX ,PrefsHandler, "phandler")
  Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")
  Plugin.AddViewGroup("List", viewMode="List", mediaType="items")

def CreatePrefs():
  Prefs.Add(id='login', type='text', default='', label='Login Email')
  Prefs.Add(id='password', type='text', default='', label='Password', option='hidden')

def PrefsHandler(login=None,password=None):
  message_add = ""
  global __customerId, __token, __tokensChecked
  if login != None and password != None:
      __customerId = None
      __token = None
      __tokensChecked = False
      Prefs.Set('login',login)
      Prefs.Set('password',password)
      cid,tok  = streamingTokens()
      if cid and tok:
        message_add = "Login to Amazon OK"
        Plugin.Restart() # this will cause the message to NOT be shown
      else:
        message_add = "Could not log into Amazon"

  title = "Preferences Updated"
  message = "Amazon preferences updated."
  dir = MessageContainer(title,"%s\n%s" % (message,message_add))
  return dir

def Menu(message_title=None,message_text=None):

  customerId, token = streamingTokens()
  dir = MediaContainer()
  if message_title != None and message_text != None:
    dir = MessageContainer(message_title,message_text)
    return dir
  if customerId != None:
    dir.Append(Function(DirectoryItem(MenuYourPurchases,"Your Purchases")))
  dir.Append(Function(SearchDirectoryItem(MenuSearch,"Search", "Search", R("search.png"))))
  dir.Append(PrefsItem(title="Preferences"))
  dir.nocache = 1
  return dir

def MenuYourPurchases(sender):
  dir = MediaContainer(title2=sender.itemTitle)
  purchasedAsinList = purchasedAsin()
  for i in makeDirItemsFromAsin(purchasedAsinList):
    dir.Append(i)
  return dir

def MenuSearch(sender, query=None):
  dir = MediaContainer(title2=sender.itemTitle)
  res = asin_search(query)
  items = makeDirItemsFromAsin(res)
  if len(items) == 0:
    dir = MessageContainer("Search","No results found for %s" % query)
    return dir
  for i in items:
    dir.Append(i)
  return dir;

def MenuSeasonList(sender, asin=None):
  dir = MediaContainer(title2=sender.itemTitle)

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


def signIn():

  PMS.Log("signIn() called")

  USER = Prefs.Get("login")
  PASS = Prefs.Get("password")

  PMS.Log('user: %s' % USER)
  PMS.Log('pass: %s' % '******')

  if not (USER and PASS):
    PMS.Log('user or pass is empty')
    return False

  x = HTTP.Request('https://www.amazon.com/gp/sign-in.html', errors='replace')

  PMS.Log('signing in')

  sessId = None
  for idx,cookie in enumerate(HTTP.__cookieJar):
    PMS.Log("cookie: %s" % repr(cookie))
    Prefs.Set(cookie.name,cookie.value)
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
  x = HTTP.Request('https://www.amazon.com/gp/flex/sign-in/select.html',values=params,errors='replace')

  return True

####################################################################################################

def streamingTokens():
  PMS.Log('streamingTokens()')
  global __customerId, __token, __tokensChecked

  if (__customerId and __token) or __tokensChecked:
      PMS.Log('found customerid+token or tokensChecked')
      return (__customerId,__token)

  html = HTTP.Request('http://www.amazon.com/gp/video/streaming/',errors='replace')
  paramStart = html.find("&customer=")
  if paramStart == -1:
      ret = signIn()
      if not ret:
        PMS.Log('ttry1 fail')
        return (None,None)
      html = HTTP.Request('http://www.amazon.com/gp/video/streaming/',errors='replace')
      paramStart = html.find("&customer=")
      if paramStart == -1:
          PMS.Log('ttry2 fail')
          return (None,None)

  custParamStart = paramStart+10
  custParamEnd   = custParamStart + html[custParamStart:].find("&")
  __customerId = html[custParamStart:custParamEnd]

  tokenParamStart = html.find("&token=") + 7
  tokenParamEnd   = tokenParamStart + html[tokenParamStart:].find("&")
  __token         = html[tokenParamStart:tokenParamEnd]

  __tokensChecked = True

  PMS.Log("__customerId: %s" % __customerId)
  PMS.Log("__token: %s" % __token)
  return (__customerId,__token)

def purchasedAsin():
  ret = []

  global __purchasedAsins

  __purchasedAsins = dict()


  customerId, token = streamingTokens()

  if not (customerId and token):
    return ret

  # http://atv-sr.amazon.com/proxy/proxy?c=<customer id>&f=getQueue&token=<token>&t=Streaming
  params = {
    'c': customerId,
    'token': token,
    'f': 'getQueue',
    't': 'Streaming'
  }
  html = HTTP.Request(AMAZON_PROXY_URL,values=params,errors='replace')
  jsonString = html.split("\n")[2]
  for i in JSON.ObjectFromString(jsonString):
    asinInfo = i.get('FeedAttributeMap',None)
    if asinInfo and asinInfo.get('ISSTREAMABLE','N') == 'Y' and asinInfo.get('ISRENTAL','N') == 'N':
      __purchasedAsins[asinInfo['ASIN']] = asinInfo
      ret.append(asinInfo)

  return ret

def asin_search(query):

  # "http://ecs.amazonaws.com/onca/xml?Service=AWSECommerceService&AWSAccessKeyId=0BARCCRGVHBC4DBYAN82&Operation=ItemSearch&SearchIndex=UnboxVideo&Keywords=Battlestar%20Galactica&ResponseGroup=ItemIds"
  # thanks to http://jjinux.blogspot.com/2009/06/python-amazon-product-advertising-api.html for the hack

  params = {
    'Service': 'AWSECommerceService',
    'AWSAccessKeyId': AMAZON_AWS_KEY,
    'Operation': 'ItemSearch',
    'SearchIndex': 'UnboxVideo',
    'Keywords': query,
    'ResponseGroup': 'ItemIds',
    'Timestamp': time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

  }
  aws_conn = AWSQueryConnection(
      aws_access_key_id=AMAZON_AWS_KEY,
      aws_secret_access_key=AMAZON_AWS_SECRET, is_secure=False,
      host=AMAZON_AWS_HOST)
  aws_conn.SignatureVersion = '2'
  qs, signature = aws_conn.get_signature(params, 'POST', AMAZON_AWS_PATH)
  params['Signature'] = signature
  
  xml = XML.ElementFromURL(AMAZON_AWS_URL,values=params,errors='replace')
  #PMS.Log(etree.tostring(xml))
  asinList = xml.xpath('//ns:ASIN/text()', namespaces={'ns': 'http://webservices.amazon.com/AWSECommerceService/2005-10-05'} )
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
    if i.get('ISSTREAMABLE','N') == 'Y' and i.get('ISRENTAL','N') == 'N':
      ret.append(i)
  return ret

def makeDirItemsFromAsin(items):

  global __purchasedAsins

  ret = []

  for asin in items:
    other_args = dict()
    thumb = asin.get('IMAGE_URL_LARGE',asin.get('IMAGE_URL_SMALL',''))
    desc = asin.get('SYNOPSIS','')
    rating = float(asin.get('AMAZONRATINGS',0.0)) * 2

    if 'EPISODENUMBER' in asin and 'SEASONNUMBER' in asin:
      title = 'S%02dE%02d : %s' % (int(asin['SEASONNUMBER']),int(asin['EPISODENUMBER']),asin['TITLE'])
    else:
      title = asin.get('TITLE','')

    if 'RELEASEDATE' in asin:
      # 2001-11-16T00:00:00
      subtitle = str((time.strptime(asin['RELEASEDATE'],'%Y-%m-%dT%H:%M:%S'))[0])
      other_args['subtitle'] = subtitle
    else:
      subtitle = ''

    PMS.Log("rating: %s, title: %s subtitle: %s" % (str(rating), title, subtitle))
    url = AMAZON_PRODUCT_URL % asin['ASIN']
    if asin.get('ASIN') in __purchasedAsins:
      duration = int(asin.get('RUNTIME',0))*60*1000
    else:
      duration = int(asin.get('FREERUNTIME',0))*1000
      

    stream_url = asin.get('STREAM_URL_1','')

    if stream_url != '':
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

