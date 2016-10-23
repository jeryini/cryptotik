import requests
from .common import APIError, headers
import time

class Bittrex:

    url = 'https://bittrex.com/api/v1.1/'
    delimiter = "-"
    headers = headers
    fee = "0.0025"

    def __init__(self, key, secret):
        self.key = key
        self.secret = secret
        self.nonce = int(time.time())

    @classmethod
    def format_pair(cls, pair):
        """format the pair argument to format understood by remote API."""

        pair = pair.replace("_", cls.delimiter)

        if not pair.islower():
            return pair.lower()
        else:
            return pair

    @classmethod
    def api(cls, url, params):
        """call api"""

        result = requests.get(url, params, headers=cls.headers, timeout=3).json()

        assert result["success"] is True

        return result

    def private_api(self, data): # private methods api
        '''        if method in MARKET_SET:
            method_set = 'market'
        elif method in ACCOUNT_SET:
            method_set = 'account'

request_url = (BASE_URL % method_set) + method + '?'''
        #if method_set != 'public':
            #request_url += 'apikey=' + self.api_key + "&nonce=" + nonce + '&'
        # headers={"apisign": hmac.new(self.api_secret.encode(), request_url.encode(), hashlib.sha512).hexdigest()}

    @classmethod
    def get_markets(cls):
        '''find out supported markets on this exhange.'''

        r = cls.api(cls.url + "public" + "/getmarkets", params={})["result"]
        pairs = [i["MarketName"].lower() for i in r]

        return {
            "base_pairs": set([i.split("-")[0] for i in pairs]),
            "market_pairs": set([i.split("-")[1] for i in pairs]),
            "markets": pairs
        }

    @classmethod
    def get_market_ticker(cls, pair):
        '''returns simple current market status report'''

        return cls.api(cls.url + "public" + "/getticker", params={"market": cls.format_pair(pair)})["result"]

    @classmethod
    def get_market_trade_history(cls, pair, depth=200):
        '''returns last 200 trades for the pair'''

        return cls.api(cls.url + "public" + "/getmarkethistory", params={"market": cls.format_pair(pair),
                                                            "count": depth})["result"]

    @classmethod
    def get_market_order_book(cls, pair, depth=200):
        '''return market order book, default <depth> is 200'''

        order_book = cls.api(cls.url + "public" + "/getorderbook",
                             params={'market': cls.format_pair(pair), 'type': 'both',
                                     'depth': depth})["result"]

        return order_book

    @classmethod
    def get_market_depth(cls, pair):
        '''returns market depth'''

        from decimal import Decimal

        order_book = cls.get_market_order_book(cls.format_pair(pair))
        return {"bids": sum([Decimal(i["Quantity"]) * Decimal(i["Rate"]) for i in order_book["buy"]]),
                "asks": sum([Decimal(i["Quantity"]) for i in order_book["sell"]])
               }

    @classmethod
    def get_markets_summaries(cls):
        '''return basic market information for all supported pairs'''
    
        return cls.api(cls.url + "public" + "/getmarketsummaries", params={})["result"]
    
    @classmethod
    def get_market_summary(cls, pair):
        '''return basic market information'''
    
        return cls.api(cls.url + "public" + "/getmarketsummary", params={"market": cls.format_pair(pair)})["result"][0]
    
    @classmethod
    def get_market_spread(cls, pair):
        '''return first buy order and first sell order'''
        
        from decimal import Decimal
        
        d = cls.get_market_summary(cls.format_pair(pair))
        return Decimal(d["Ask"]) - Decimal(d["Bid"])

    @classmethod
    def sort_markets_by_volume(cls, n=10):
        """returns list of >n< markets sorted by daily volume expressed in base pair"""
        
        r = cls.get_markets_summaries()
        markets = sorted(r, key=lambda k: k['BaseVolume'])
        markets.reverse()
        volume = [i["BaseVolume"] for i in markets[:n]]
        name = [i["MarketName"].lower() for i in markets[:n]]

        return zip(name, volume)

