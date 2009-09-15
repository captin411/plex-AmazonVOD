import time

# PMS plugin framework
from PMS import *
from PMS.Objects import *
from PMS.Shortcuts import *
from boto.connection import AWSQueryConnection


####################################################################################################

PLUGIN_PREFIX     = "/video/AmazonVOD"

AMAZON_PLAYER_URL = "http://www.amazon.com/gp/video/streaming/mini-mode.html?asin=%s"
AMAZON_AWS_KEY    = "0BARCCRGVHBC4DBYAN82"
AMAZON_AWS_SECRET = "iwJYwj3RPe/pwLKKhU1cmJRuEu3RSUpNp+UiVRsm"

AMAZON_ART = 'art-default.jpg'

CACHE_INTERVAL              = 3600
DEBUG                       = False

if DEBUG:
    from lxml import etree

__customerId = None
__token      = None
__tokensChecked = False


####################################################################################################

def Start():
  Plugin.AddPrefixHandler(PLUGIN_PREFIX, Menu, L("amazon"), "icon-default.png", AMAZON_ART)
  Plugin.AddPrefixHandler("%s/:/prefs/set" % PLUGIN_PREFIX ,PrefsHandler, "phandler")
  Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")
  Plugin.AddViewGroup("List", viewMode="List", mediaType="items")
  MediaContainer.art = R(AMAZON_ART)

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
    dir.Append(Function(DirectoryItem(MenuYourPurchases,"Your Purchases", thumb=R("purchased.png"))))
  dir.Append(Function(InputDirectoryItem(MenuSearch,"Search", "Search", thumb=R("search.png") )))
  dir.Append(PrefsItem(title="Preferences", thumb=R("gear.png")) )
  dir.nocache = 1
  return dir

def MenuYourPurchases(sender):
  dir = MediaContainer(title2=sender.itemTitle,view='InfoList')

  customerId, token = streamingTokens()
  purchasedItems = UnboxClient.purchasedItems(customerId, token)
  items = makeDirFromItems(purchasedItems)
  if len(items) == 0:
    dir = MessageContainer("Purchases","You do not have any purchases")
    return dir
  for i in items:
    dir.Append(i)
  return dir;

def MenuSearch(sender, query=None):
  dir = MediaContainer(title2=sender.itemTitle,view='InfoList')
  res = UnboxClient.itemSearch(query)
  items = makeDirFromItems(res)
  if len(items) == 0:
    dir = MessageContainer("Search","No results found for %s" % query)
    return dir
  for i in items:
    dir.Append(i)
  return dir;

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

def makeDirFromItems(items):
  ret = []
  for item in items:
    wvi = WebVideoItem(
        item['url'],
        item['title'],
        summary=item['description'],
        subtitle=item['subtitle'],
        duration=item['duration'],
        thumb=item['thumb'],
        rating=item['rating'])
    ret.append(wvi)
  ret.sort(cmp=lambda a,b: cmp(a.__dict__.get('title'),b.__dict__.get('title')))
  return ret

class AmazonUnbox:
    def __init__(self, key, secret):
        self.XML_NS = 'http://webservices.amazon.com/AWSECommerceService/2009-03-31'
        self.AMAZON_PROXY_URL = "http://atv-sr.amazon.com/proxy/proxy"
        self.NS = {'ns': self.XML_NS}
        self.KEY = key
        self.SECRET = secret
        self._conn = AWSQueryConnection(
            aws_access_key_id=self.KEY,
            aws_secret_access_key=self.SECRET,
            is_secure=False,
            host='ecs.amazonaws.com')
        self._conn.SignatureVersion = '2'
  
    def _request_xml(self,params):
        params['Timestamp'] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        params['AWSAccessKeyId'] = self.KEY
        params['Version']='2009-03-31'
        qs, signature = self._conn.get_signature(params, 'POST', '/onca/xml')
        params['Signature'] = signature
        return XML.ElementFromURL("http://ecs.amazonaws.com/onca/xml",values=params,errors='replace')

    def item(self,asin):
        return self.items([ asin ], max=1)[0]

    def items(self,asinList, max=0):
        items = []
        count = 0
        for maxTenList in self._lists_of_n(asinList,10):
            params = {
                'Service': 'AWSECommerceService',
                'Operation': 'ItemLookup',
                'ItemId': ','.join(maxTenList),
                'ResponseGroup': 'RelatedItems,Large,OfferFull,PromotionDetails',
                'RelationshipType': 'Episode,Season'
            }
            xml = self._request_xml(params)
            for e in xml.xpath('//ns:Items/ns:Item', namespaces=self.NS):
                count = count + 1
                i = self._parse_item_el(e)
                items.append( i )
                if max > 0 and count >= max:
                    return items
        return items

    def itemSearch(self,query, page=0):
        params = {
            'Service': 'AWSECommerceService',
            'Operation': 'ItemSearch',
            'SearchIndex': 'UnboxVideo',
            'Keywords': query,
            'ResponseGroup': 'RelatedItems,Large,OfferFull,PromotionDetails',
            'RelationshipType': 'Episode,Season',
        }
        xml = self._request_xml(params)
        items = []
        ids = []
        for e in xml.xpath('//ns:Items/ns:Item', namespaces=self.NS):
            item = self._parse_item_el(e)
            ids.append(item['asin'])
            if item['parent'] != '':
                if item['parent'] in ids:
                    continue
                item = self.item(item['parent'])
                ids.append(item['asin'])
            items.append( item )
        if len(items) == 0:
            PMS.Log( XML.StringFromElement(xml) )

        return items

    def purchasedItems(self, customerId=None, token=None):
        if customerId == None or token == None:
            return []

        ret = []

        params = {
            'c':     customerId,
            'token': token,
            'f':     'getQueue',
            't':     'Streaming'
        }
        html = HTTP.Request(self.AMAZON_PROXY_URL,values=params,errors='replace')
        jsonString = html.split("\n")[2]
        asinList = []
        for i in JSON.ObjectFromString(jsonString):
            asinInfo = i.get('FeedAttributeMap',None)
            if asinInfo and asinInfo.get('ISSTREAMABLE','N') == 'Y' and asinInfo.get('ISRENTAL','N') == 'N':
                asinList.append(asinInfo['ASIN'])
                ret.append(asinInfo)

        return self.items(asinList)

    def _parse_item_el(self, el):
        asin = el.xpath('ns:ASIN/text()', namespaces=self.NS)[0]
        title = el.xpath('ns:ItemAttributes/ns:Title/text()', namespaces=self.NS)[0]
        thumb = el.xpath('ns:LargeImage/ns:URL/text()', namespaces=self.NS)[0]

        duration = ''
        try:
            duration = int(el.xpath('ns:ItemAttributes/ns:RunningTime/text()', namespaces=self.NS)[0])*60*1000
        except:
            pass

        release_date = ''
        try:
            release_date = el.xpath('ns:ItemAttributes/ns:TheatricalReleaseDate/text()', namespaces=self.NS)[0]
        except:
            try:
                release_date = el.xpath('ns:ItemAttributes/ns:ReleaseDate/text()', namespaces=self.NS)[0]
            except:
                pass

        description = ''
        try:
            description = el.xpath('ns:ItemAttributes/ns:LongSynopsis/text()', namespaces=self.NS)[0]
        except:
            try:
                description = el.xpath('ns:ItemAttributes/ns:ShortSynopsis/text()', namespaces=self.NS)[0]
            except:
                pass

        rating = ''
        try:
            rating = float(el.xpath('ns:CustomerReviews/ns:AverageRating/text()',namespaces=self.NS)[0])*2
        except:
            pass

        season = 0
        try:
            season = el.xpath('ns:ItemAttributes/ns:SeasonSequence/text()',namespaces=self.NS)[0]
        except:
            pass

        episode = 0
        try:
            episode = el.xpath('ns:ItemAttributes/ns:EpisodeSequence/text()',namespaces=self.NS)[0]
        except:
            pass

        if season == 0 and episode > 0:
            season, episode = [ episode, season ]

        parent = ''
        children = []

        try:
            for ris in el.xpath('ns:RelatedItems',namespaces=self.NS):
                rel = ris.xpath('ns:Relationship/text()',namespaces=self.NS)[0]
                if rel == 'Parents':
                    parent = ris.xpath('ns:RelatedItem/ns:Item/ns:ASIN/text()',namespaces=self.NS)[0]
                elif rel == 'Children':
                    for ri in ris.xpath('ns:RelatedItem',namespaces=self.NS):
                        children.append( ri.xpath('ns:Item/ns:ASIN/text()',namespaces=self.NS)[0] )
        except:
            raise      
            pass

        subtitle = release_date.split('-')[0]

        ret = {
            'asin': asin,
            'title': title,
            'url': AMAZON_PLAYER_URL % asin,
            'rating': rating,
            'duration': duration,
            'thumb': thumb,
            'description': description,
            'subtitle': subtitle,
            'season': season,
            'episode': episode,
            'parent': parent,
            'children': children
        }

        return ret
        pass

    def _lists_of_n(self, myList, n):
        """Some amazon queries restrict the number of things that can be
        passed in. For example, item lookups are restricted to 10 at a time.
        this helps split lists into lists of lists"""
        if len(myList) <= 0:
            return []
        
        if len(myList) <= n:
            return [ myList ]

        ret = []
        currentList = []
        count = 0
        for item in myList:
            count = count + 1
            currentList.append(item)
            if count % n == 0:
                ret.append(currentList)
                currentList = []
        if len(currentList) > 0:
            ret.append(currentList)
        return ret
UnboxClient = AmazonUnbox( key=AMAZON_AWS_KEY, secret=AMAZON_AWS_SECRET )
