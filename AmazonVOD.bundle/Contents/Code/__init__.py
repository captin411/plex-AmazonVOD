import time, re, htmlentitydefs

# PMS plugin framework
from PMS import *
from PMS.Objects import *
from PMS.Shortcuts import *
from boto.connection import AWSQueryConnection

####################################################################################################

PLUGIN_PREFIX     = "/video/AmazonVOD"

AMAZON_BASE_URL   = "https://www.amazon.com"
AMAZON_PLAYER_URL = "http://www.amazon.com/gp/video/streaming/mini-mode.html?asin=%s"
AMAZON_AWS_KEY    = "0BARCCRGVHBC4DBYAN82"
AMAZON_AWS_SECRET = "iwJYwj3RPe/pwLKKhU1cmJRuEu3RSUpNp+UiVRsm"
ASSOC_TAG = "plco09-20"

FORCE_COOKIE_STORAGE = True


AMAZON_ART = 'art-default.png'
AMAZON_ICON = 'icon-default.png'

CACHE_INTERVAL              = 3600
DEBUG                       = False

if DEBUG:
    from lxml import etree

__customerId = None
__token      = None
__tokensChecked = False

####################################################################################################

def Start():
  Plugin.AddPrefixHandler(PLUGIN_PREFIX, Menu, L("amazon"), AMAZON_ICON, AMAZON_ART)
  Plugin.AddPrefixHandler("%s/:/prefs/set" % PLUGIN_PREFIX ,PrefsHandler, "phandler")
  Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")
  Plugin.AddViewGroup("List", viewMode="List", mediaType="items")
  MediaContainer.art = R(AMAZON_ART)
  DirectoryItem.thumb = R(AMAZON_ICON)

  # when the plugin fires up (PMS is started) go ahead
  # and log in and snag the purchased items to make things
  # seem faster when you come into the plugin
  @spawn
  def preCache():
      try:
          customerId, token = streamingTokens()
          if customerId and token:
              UnboxClient.purchasedItems(customerId, token)
      except:
          pass

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

def ChildTitlesMenu(sender,asin=None,purchasedOnly=False):
    dir = MediaContainer(title2=sender.itemTitle,viewGroup='InfoList')
    children = UnboxClient.childrenOf(asin)
    dir = makeDirFromItems(children,dir,purchasedOnly=purchasedOnly)
    return dir

def MakePurchase(sender,asin=None):

    if asin is not None:
        customerId,token = streamingTokens()
        purchasedAsins = UnboxClient.purchasedAsins(customerId,token)

        if asin in purchasedAsins:
            return MessageContainer("Already Purchased","You have already purchased this item")

        orderNumber = UnboxClient.doPurchase(customerId, [ asin ])
        if orderNumber is not None:
            message = """Your order number is %s. The
video will now be in "Your Purchases" section.
Pre-orders may not be available immediately.""" % orderNumber
            return MessageContainer("Purchase Complete",message)
        else:
            message = """You need to have a valid payment method listed for your
 1-Click settings.  You may want to try your first purchase
 from amazon.com directly."""
            return MessageContainer("Purchase Failed",message)
    else:
        return MessageContainer("Purchase Failed","No Product was provided")

def addPurchaseOptions(dir,item,detail):

    price = '%s' % item['price']
    asin  = '%s' % item['asin']

    action = None
    noun   = None
    if detail.get('ISRENTAL','N') == 'Y':
        if detail.get('ISPREORDER','N') == 'Y':
            action = 'Pre-order'
        else:
            action = 'Rent'
        noun = '%s Rental' % _niceRentDuration(detail)
    elif detail.get('BUYABLE','N') == 'Y':
        if detail.get('ISPREORDER','N') == 'Y':
            action = 'Pre-order'
        else:
            action = 'Buy'

        if detail.get('ISSEASONPASS','N') == 'Y':
            noun = 'Season Pass'
        elif item['has_children']:
            noun = 'Season'
        else:
            noun = 'Video'

    if action != None and noun != None:
        title = "%s %s - %s" % (action,noun,price)
        dir.Append(Function(DirectoryItem(MakePurchase,title,title),asin=asin))

    return dir


def VideoPopupMenu(sender,asin=None):
    item = UnboxClient.item(asin)
    dir = MediaContainer(title1="Unpurchased",title2=sender.itemTitle)
    wvi = webvideoFromItem(item) 
    wvi.title = "Watch Preview"
    dir.Append(wvi)


    c,t = streamingTokens()
    if c and t:
        detail = UnboxClient.itemDetail(asin)
        @spawn
        def registerClick(asin=asin):
            UnboxClient.registerProductClick(asin)
        dir = addPurchaseOptions(dir,item,detail)
    return dir

def FolderPopupMenu(sender,asin=None,purchasedOnly=False):
    item = UnboxClient.item(asin)
    dir = MediaContainer(title1="Unpurchased",title2=sender.itemTitle)
    seeItems = folderdirFromItem(item,purchasedOnly=purchasedOnly)
    seeItems.title = "See Series or Episodes"
    dir.Append(seeItems)
    c,t = streamingTokens()
    if c and t:
        detail = UnboxClient.itemDetail(asin)
        @spawn
        def registerClick(asin=asin):
            UnboxClient.registerProductClick(asin)
        dir = addPurchaseOptions(dir,item,detail)

    return dir

def _niceRentDuration(item):

    try:
        dur = int(item['RENTALDURATION'])
        days = int(float(dur)/24)
        if days > 1:
            return '%d Day' % days
        else:
            return '1 Day'
    except Exception, e:
        return ''

def TopGenreMenu(sender):
    dir = MediaContainer(title1="Genres", title2=sender.itemTitle,viewGroup='InfoList')
    genres = UnboxClient.browseNodes()
    for g in genres:
        dir.Append(Function(DirectoryItem(GenreOptions,'%s' % g['name'], '%s' % g['name']),browseNode='%s' % g['id']))

    return dir

def BrowseNodeSearch(sender,browseNode=None,opts=None):
    dir = MediaContainer(title1='Search Results', title2=sender.itemTitle,viewGroup='InfoList')
    opts['BrowseNode'] = browseNode

    res = UnboxClient.itemSearch(opts=opts)
    dir = makeDirFromItems(res,dir,doSort=False)
    return dir

def GenreOptions(sender,browseNode=None,depth=1):
    dir = MediaContainer(title1='Genre Options', title2=sender.itemTitle,viewGroup='InfoList')

    if depth > 1:
        dir.Append(Function(
            DirectoryItem(
                BrowseNodeSearch,
                'Best Sellers',
                'Best Sellers'
            ),
            browseNode=browseNode,
            opts={
                'Sort': 'salesrank'
            }
        ))
        dir.Append(Function(
            DirectoryItem(
                BrowseNodeSearch,
                'New Arrivals',
                'New Arrivals'
            ),
            browseNode=browseNode,
            opts={
                'Sort': '-video-release-date'
            }
        ))
    else:
        genres = UnboxClient.browseNodes(root=browseNode)
        for g in genres:
            dir.Append(Function(DirectoryItem(GenreOptions,'%s' % g['name'], '%s' % g['name']),browseNode='%s' % g['id'],depth=depth+1))

    return dir
    



def Menu(message_title=None,message_text=None):

  customerId, token = streamingTokens()

  dir = MediaContainer(title1="Amazon VOD",viewGroup="List")
  if message_title != None and message_text != None:
    dir = MessageContainer(message_title,message_text)
    return dir
  if customerId != None:
    dir.Append(Function(DirectoryItem(MenuYourPurchases,"Your Purchases", thumb=R("purchased.png"))))
  dir.Append(Function(DirectoryItem(TopGenreMenu,"Genres", "Genres", thumb=R("search.png") )))
  dir.Append(Function(InputDirectoryItem(MenuSearch,"Search", "Search", thumb=R("search.png") )))
  dir.Append(PrefsItem(title="Preferences", thumb=R("gear.png")) )
  dir.nocache = 1
  return dir

def MenuYourPurchases(sender):
  dir = MediaContainer(title1="Your Purchases", title2=sender.itemTitle,viewGroup='InfoList')

  customerId, token = streamingTokens()
  purchasedItems = UnboxClient.parentize(UnboxClient.purchasedItems(customerId, token))
  dir = makeDirFromItems(purchasedItems,dir,purchasedOnly=True)
  return dir

def MenuSearch(sender, query=None):
  dir = MediaContainer(title1="Search Results", title2=sender.itemTitle,viewGroup='InfoList')
  res = UnboxClient.parentize(UnboxClient.itemSearch(query=query))
  dir = makeDirFromItems(res,dir)
  return dir

####################################################################################################

def folderdirFromItem(item,purchasedOnly=False):
    tn = item['thumb']
    if tn == '':
        tn = R(AMAZON_ICON)
    return Function(
            DirectoryItem(
                ChildTitlesMenu,
                unescape("%s" % item['long_title']),
                thumb=tn,
                subtitle='',
                art='',
                summary=unescape(item['description'])
            ),
            asin="%s" % item['asin'],
            purchasedOnly=purchasedOnly
        )


def webvideoFromItem(item):
    tn = item['thumb']
    if tn == '':
        tn = R(AMAZON_ICON)
    return WebVideoItem(
        item['url'],
        unescape("%s" % item['long_title']),
        summary=unescape(item['description']),
        subtitle=item['subtitle'],
        duration=item['duration'],
        thumb=tn,
        rating=item['rating'])

def makeDirFromItems(items, dir, purchasedOnly=False, doSort=True):
  if doSort:
    items.sort(cmp=lambda a,b: cmp(a.get('long_title','').lower(),b.get('long_title','').lower()))
  customerId,token = streamingTokens()
  purchased = UnboxClient.purchasedAsins(customerId,token)

  for item in items:
    tn = item['thumb']
    if tn == '':
        tn = R(AMAZON_ICON)
    if item['has_children']:
        isPurchased = False
        if item['asin'] in purchased or item.get('purchased_hint',False):
            isPurchased = True

        if purchasedOnly and not isPurchased:
            continue

        if isPurchased or item['price_int'] == 0:
            di = folderdirFromItem(item,purchasedOnly=purchasedOnly)
        else:
            di = Function(
                    PopupDirectoryItem(
                        FolderPopupMenu,
                        unescape("%s %s" % (item['long_title'], item['price'])),
                        thumb=tn,
                        summary=unescape(item['description']),
                        subtitle='',
                        art=''
                    ),
                    asin="%s" % item['asin'],
                    purchasedOnly=purchasedOnly
            )

        dir.Append(di)
    else:
        isPurchased = False
        if item['asin'] in purchased or item.get('purchased_hint',False):
            isPurchased = True

        if purchasedOnly and not isPurchased:
            continue

        if not isPurchased and item['price'] == '':
            continue
        if isPurchased or item['price_int'] == 0:
            di = webvideoFromItem(item)
        else:
            di = Function(
                    PopupDirectoryItem(
                        VideoPopupMenu,
                        unescape("%s %s" % (item['long_title'], item['price'])),
                        thumb=tn,
                        summary=unescape(item['description']),
                        subtitle=item['subtitle'],
                        art='',
                        duration=item['duration'],
                        rating=item['rating']
                    ),
                    asin="%s" % item['asin']
                 )
        dir.Append(di)

  return dir



def signIn():

  PMS.Log('signin()')

  USER = Prefs.Get("login")
  PASS = Prefs.Get("password")

  if not (USER and PASS):
    PMS.Log('user or pass is empty')
    return False

  x = HTTP.Request('https://www.amazon.com/?tag=%s' % ASSOC_TAG, errors='replace')
  x = HTTP.Request('https://www.amazon.com/gp/sign-in.html?tag=%s' % ASSOC_TAG, errors='replace')

  PMS.Log('signing in')
  sessId = None
  for idx,cookie in enumerate(HTTP.__cookieJar):
    if FORCE_COOKIE_STORAGE:
        cookie.discard = False
        cookie.expires = int(2147483647)
    if cookie.name == 'session-id':
      sessId = cookie.value
 
  if not sessId:
      return False

  params = {
      'path': '/gp/homepage.html',
      'useRedirectOnSuccess': '1',
      'protocol': 'https',
      'sessionId': sessId,
      'action': 'sign-in',
      'password': PASS,
      'email': USER,
      'x': '62',
      'y': '11'
  }
  x = HTTP.Request('https://www.amazon.com/gp/flex/sign-in/select.html?ie=UTF8&protocol=https&tag=%s' % ASSOC_TAG,values=params,errors='replace')

  if FORCE_COOKIE_STORAGE:
      for idx,cookie in enumerate(HTTP.__cookieJar):
        cookie.discard = False
        cookie.expires = int(2147483647)

  return True

####################################################################################################

def streamingTokens():
  global __customerId, __token, __tokensChecked

  if (__customerId and __token) or __tokensChecked:
      return (__customerId,__token)

  ## find any movie and follow the link so that we can find a page with a
  ## flash player on it

  mostPopularHTML = HTTP.Request('http://www.amazon.com/Genres/b/ref=sv_atv_0?ie=UTF8&node=16261641')

  # <a class="title" href="http://www.amazon.com/Home/dp/B00451SU6G/ref=sr_1_3?s=digital-video&ie=UTF8&qid=1286168594&sr=1-3">
  try:
      firstProductLinkURL = re.search('href="(http://www.amazon.com/[^/"]+/dp/[^"]+s=digital-video[^"]*)"',mostPopularHTML).group(1)
  except:
      PMS.Log("unable to find a page with a flash player for inspection")
      return (None, None)

  PMS.Log(firstProductLinkURL)
  
  html = HTTP.Request(firstProductLinkURL)
  paramStart = html.find("&customer=")
  if paramStart == -1:
      ret = signIn()
      if not ret:
        PMS.Log('ttry1 fail')
        return (None,None)
      html = HTTP.Request('http://www.amazon.com/gp/video/streaming/?tag=%s' % ASSOC_TAG,errors='replace')
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

  ## ok, now make sure that the region is allowed.  don't want
  ## to ever charge people and give them nothing
  geoCheck = UnboxClient.geoCheck(__customerId)
  if geoCheck != 'true':
      PMS.Log("geo check fail, marking as not logged in")
      __customerId = None
      __token      = None

  return (__customerId,__token)

##
# http://effbot.org/zone/re-sub.htm#unescape-html
# Removes HTML or XML character references and entities from a text string.
#
# @param text The HTML (or XML) source text.
# @return The plain text, as a Unicode string, if necessary.
def unescape(text):
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)

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
        self.__cache = {}
        self._conn.SignatureVersion = '2'

    def _internal_proxy_request(self,params):
        html = HTTP.Request(self.AMAZON_PROXY_URL,values=params,errors='replace')
        jsonString = html.split("\n")[2]
        return JSON.ObjectFromString(jsonString)
  
    def _request_xml(self,params):
        params['Timestamp'] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        params['AWSAccessKeyId'] = self.KEY
        params['Version']='2009-03-31'
        params['AssociateTag'] = ASSOC_TAG
        qs, signature = self._conn.get_signature(params, 'POST', '/onca/xml')
        params['Signature'] = signature
        return XML.ElementFromURL("http://ecs.amazonaws.com/onca/xml",values=params,errors='replace')

    def itemDetail(self,asin,cache=True):

        k = 'itemDetail_%s' % asin
        ret = self.__cache.get(k)
        if not ret:
            params = {
                'c':     '',
                'token': '',
                'f':     'getASINList',
                't':     'Streaming',
                'asinList': asin
            }
            try:
                ret = self._internal_proxy_request(params)[0]
                self.__cache[k] = ret
            except:
                ret = {}
        return ret

    def item(self,asin,cache=True):
        return self.items([ asin ], max=1, cache=cache)[0]

    def items(self,asinList, max=0, purchased=False, cache=True):
        items = []
        for maxTenList in self._lists_of_n(asinList,10):

            uncachedAsins = []
            # check cache first
            for asin in maxTenList:
                k = 'asin_%s' % asin
                i = self.__cache.get(k)
                if i and cache:
                    i['purchased_hint'] = purchased
                    items.append(i)
                else:
                    uncachedAsins.append(asin)

            if len(uncachedAsins) > 0:
                params = {
                    'Service': 'AWSECommerceService',
                    'Operation': 'ItemLookup',
                    'ItemId': ','.join(uncachedAsins),
                    'ResponseGroup': 'RelatedItems,Large,OfferFull,PromotionDetails,AlternateVersions',
                    'RelationshipType': 'Episode,Season'
                }
                xml = self._request_xml(params)
                for e in xml.xpath('//ns:Items/ns:Item', namespaces=self.NS):
                    i = self._parse_item_el(e)
                    k = 'asin_%s' % i['asin']
                    self.__cache[k] = i
                    i['purchased_hint'] = purchased
                    items.append( i )

        if max > 0 and len(items) >= max:
            return items[0:max]
        else:
            return items

    def browseNodes(self,root='16261641'):
        params = {
            'Service': 'AWSECommerceService',
            'Operation': 'BrowseNodeLookup',
            'ResponseGroup': 'BrowseNodeInfo',
            'BrowseNodeId': root
        }

        xml = self._request_xml(params)
        items = []
        for e in xml.xpath('//ns:Children/ns:BrowseNode', namespaces=self.NS):
            id = e.xpath('ns:BrowseNodeId/text()', namespaces=self.NS)[0]
            name = e.xpath('ns:Name/text()', namespaces=self.NS)[0]
            items.append( { 'id': id, 'name': name } )

        return items


    def itemSearch(self,query='', opts={}):
        if query != '':
            opts['Keywords'] = query

        params = {
            'Service': 'AWSECommerceService',
            'Operation': 'ItemSearch',
            'SearchIndex': 'UnboxVideo',
            'ResponseGroup': 'RelatedItems,Large,OfferFull,PromotionDetails,AlternateVersions',
            'RelationshipType': 'Episode,Season',
        }
        params.update(opts)

        xml = self._request_xml(params)
        items = []
        for e in xml.xpath('//ns:Items/ns:Item', namespaces=self.NS):
            item = self._parse_item_el(e)
            items.append( item )
        if len(items) == 0:
            PMS.Log( XML.StringFromElement(xml) )

        return items

    def parentize(self,items):
        newItems = []

        item_count = len(items)
        iter = 0
        foundAsins = []
        parent_purchased_hint = {}
        while item_count > 0:
            iter = iter + 1
            parents_found = []
            parentAsins = []
            for i in items:
                if i['parent'] == '' and i['asin'] not in foundAsins:
                    newItems.append(i)
                    foundAsins.append(i['asin'])
                elif i['parent'] not in parents_found:
                    if i.get('purchased_hint',False):
                        parent_purchased_hint[i['parent']] = True
                    parents_found.append(i['parent'])
                    parentAsins.append( i['parent'] )
            if len(parentAsins) > 0:
                items = []
                for i in self.items(parentAsins):
                    if i['asin'] in parent_purchased_hint:
                        i['purchased_hint'] = True
                    items.append(i)
            else:
                items = []
            item_count = len(items)
        return newItems

    def geoCheck(self,customerId=''):
        params = {
            't': 'Streaming',
            'c': customerId,
            'f': 'geoCheck'
        }

        return self._internal_proxy_request(params)

    def registerProductClick(self,asin):
        try:
            item = self.item(asin)
            x = HTTP.Request(item['detail_url'], errors='replace')
            return True
        except:
            pass
        return False


    def doPurchase(self,customerId,asinList):
        PMS.Log("purchasing")

        if len(asinList) == 0:
            PMS.Log("no ASINs found - fail")
            return None

        if not customerId or customerId == '':
            PMS.Log("no customerId found - fail")
            return None


        first_asin = asinList[0]
        PURCHASE_HANDLER = 'http://www.amazon.com/gp/video/order/handle-buy-box.html'
        params = {
            't': 'atv',
            'ref.atv.clientid': '00000000-0000-0000-000000000000',
            'o_cust': customerId,
            'o_cust_os': 'Macintosh',
            'itemCount': len(asinList),
            'retJSON': 'true',
            'o_asin': first_asin,
        }
        count = 0
        for asin in asinList:
            params['ASIN.%d' % count] = asin
            count = count + 1

        PMS.Log(params)

        try:
            jsonStr = HTTP.Request(PURCHASE_HANDLER,values=params,errors='replace')
            PMS.Log(jsonStr)
            jsonObj = JSON.ObjectFromString(jsonStr)
            PMS.Log(jsonObj)

            if jsonObj['success'] == 'true':
                self.clearCache()
                return jsonObj['orderID']
        except Exception, e:
            PMS.Log(e)

        return None
        pass

    def clearCache(self):
        self.__cache = {}
        return True

    def purchasedAsins(self, customerId=None, token=None):
        if customerId == None or token == None:
            return []

        asinList = []
        k = 'purchased_%s_%s' % (customerId,token)
        if self.__cache.get(k):
            asinList = self.__cache.get(k)
        else:
            params = {
                'c':     customerId,
                'token': token,
                'f':     'getQueue',
                't':     'Streaming'
            }
            now = int(time.time())
            for i in self._internal_proxy_request(params):
                rentalExpiry = 0
                try:
                    rentalExpiry = int(int(i['QueueItem']['RentalExpiry'])/1000)
                except:
                    pass
                asinInfo = i.get('FeedAttributeMap',None)
                if rentalExpiry > 0 and rentalExpiry < now:
                    PMS.Log("rental expired for %s " % asinInfo['TITLE'])
                    continue
                if asinInfo and asinInfo.get('ISSTREAMABLE','N') == 'Y':
                    asinList.append(asinInfo['ASIN'])
            self.__cache[k] = asinList

        return asinList

    def purchasedItems(self, customerId=None, token=None):

        return self.items(self.purchasedAsins(customerId,token),purchased=True)

    def _parse_item_el(self, el):
        asin = el.xpath('ns:ASIN/text()', namespaces=self.NS)[0]
        detail_url = el.xpath('ns:DetailPageURL/text()', namespaces=self.NS)[0]
        title = el.xpath('ns:ItemAttributes/ns:Title/text()', namespaces=self.NS)[0]

        thumb = ''
        try:
            thumb = el.xpath('ns:LargeImage/ns:URL/text()', namespaces=self.NS)[0]
        except:
            pass

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
            season = int(el.xpath('ns:ItemAttributes/ns:SeasonSequence/text()',namespaces=self.NS)[0])
        except:
            pass

        episode = 0
        try:
            episode = int(el.xpath('ns:ItemAttributes/ns:EpisodeSequence/text()',namespaces=self.NS)[0])
        except:
            pass

        price = ''
        price_int = 0
        try:
            price = el.xpath('ns:OfferSummary/ns:LowestNewPrice/ns:FormattedPrice/text()',namespaces=self.NS)[0]
            price_int = int(el.xpath('ns:OfferSummary/ns:LowestNewPrice/ns:Amount/text()',namespaces=self.NS)[0])
        except:
            pass

        if season == 0 and episode > 0:
            season, episode = [ episode, season ]

        parent = ''
        parent_name = ''
        children = []

        try:
            for ris in el.xpath('ns:RelatedItems',namespaces=self.NS):
                rel = ris.xpath('ns:Relationship/text()',namespaces=self.NS)[0]
                if rel == 'Parents':
                    parent = ris.xpath('ns:RelatedItem/ns:Item/ns:ASIN/text()',namespaces=self.NS)[0]
                    parent_name = ris.xpath('ns:RelatedItem/ns:Item/ns:ItemAttributes/ns:Title/text()',namespaces=self.NS)[0]
                elif rel == 'Children':
                    for ri in ris.xpath('ns:RelatedItem',namespaces=self.NS):
                        children.append( ri.xpath('ns:Item/ns:ASIN/text()',namespaces=self.NS)[0] )
        except:
            raise      
            pass

        subtitle = release_date.split('-')[0]

        has_children = len(children) > 0

        long_title = title

        if not has_children and season > 0:
            long_title = "Episode %02d: %s" % (episode,title)
            subtitle = "%s" % parent_name

        ret = {
            'asin': asin,
            'title': title,
            'price': price,
            'price_int': price_int,
            'long_title': long_title,
            'url': AMAZON_PLAYER_URL % asin,
            'detail_url': detail_url,
            'rating': rating,
            'duration': duration,
            'thumb': thumb,
            'description': description,
            'subtitle': subtitle,
            'season': season,
            'episode': episode,
            'parent': parent,
            'parent_name': parent_name,
            'has_children': has_children
        }

        return ret
        pass

    def childrenOf(self, asin):

        k = 'children_of_asin_%s' % asin
        childAsins = []
        if self.__cache.get(k):
            childAsins = self.__cache.get(k)
        else:
            max_pages = 1 
            current_page = 1
            while current_page <= max_pages:
                params = {
                    'Service': 'AWSECommerceService',
                    'Operation': 'ItemLookup',
                    'ItemId': asin,
                    'RelatedItemPage': current_page,
                    'ResponseGroup': 'RelatedItems',
                    'RelationshipType': 'Episode,Season'
                }
                xml = self._request_xml(params)
                for e in xml.xpath('//ns:Items/ns:Item', namespaces=self.NS):
                    try:
                        for ris in e.xpath('ns:RelatedItems',namespaces=self.NS):
                            rel = ris.xpath('ns:Relationship/text()',namespaces=self.NS)[0]
                            if rel == 'Children':
                                max_pages = int(ris.xpath('ns:RelatedItemPageCount/text()',namespaces=self.NS)[0])
                                for ri in ris.xpath('ns:RelatedItem',namespaces=self.NS):
                                    a = ri.xpath('ns:Item/ns:ASIN/text()',namespaces=self.NS)[0]
                                    if a not in childAsins:
                                        childAsins.append( a )
                    except:
                        pass
                current_page = current_page + 1
            self.__cache[k] = childAsins

        return self.items(childAsins)

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

