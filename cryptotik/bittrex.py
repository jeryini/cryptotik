# -*- coding: utf-8 -*-

import requests
from cryptotik.common import APIError, OutdatedBaseCurrenciesError, headers, ExchangeWrapper
from common import is_sale
from cryptotik.exceptions import InvalidBaseCurrencyError, InvalidDelimiterError
import time
import hmac
import hashlib
from datetime import datetime
from decimal import Decimal


class Bittrex(ExchangeWrapper):

    name = 'bittrex'
    url = 'https://bittrex.com/api/v1.1/'
    delimiter = "-"
    headers = headers
    taker_fee, maker_fee = 0.0025, 0.0025
    private_commands = ('getopenorders', 'cancel', 'sellmarket', 'selllimit',
                        'buymarket', 'buylimit')
    public_commands = ('getbalances', 'getbalance', 'getdepositaddress',
                       'withdraw')
    base_currencies = ['btc', 'eth', 'usdt']
    quote_order = 1

    def __init__(self, apikey=None, secret=None, timeout=None, proxy=None):
        '''initialize bittrex class'''

        if apikey and secret:
            self.apikey = apikey.encode("utf-8")
            self.secret = secret.encode("utf-8")

        if proxy:
            assert proxy.startswith('https'), {'Error': 'Only https proxies supported.'}
        self.proxy = {'https': proxy}

        if not timeout:
            self.timeout = (8, 15)
        else:
            self.timeout = timeout

        self.api_session = requests.Session()

    def get_base_currencies(self):
        '''return base markets supported by this exchange.'''

        bases = list(set([i.split('-')[0] for i in self.get_markets()]))
        try:
            assert sorted(bases) == sorted(self.base_currencies)
        except AssertionError:
            raise OutdatedBaseCurrenciesError('Update the hardcoded base currency clist!',
                                              {'actual': bases,
                                               'hardcoded': self.base_currencies})

    def get_nonce(self):
        '''return nonce integer'''

        nonce = getattr(self, '_nonce', 0)
        if nonce:
            nonce += 1
        # If the unix time is greater though, use that instead (helps low
        # concurrency multi-threaded apps always call with the largest nonce).
        self._nonce = max(int(time.time()), nonce)
        return self._nonce

    @classmethod
    def format_pair(self, pair):
        """format the pair argument to format understood by remote API."""

        pair = pair.replace("_", self.delimiter)

        if not pair.islower():
            return pair.lower()
        else:
            return pair

    def _verify_response(self, response):
        '''verify if API responded properly and raise apropriate error.'''

        if not response.json()['success'] is True:
            raise APIError(response.json()['message'])

    def _generate_signature(self, url):

        return hmac.new(self.secret, url.encode(), hashlib.sha512).hexdigest()

    def api(self, url, params):
        """call api"""

        try:
            response = self.api_session.get(url, params=params, headers=self.headers,
                                            timeout=self.timeout, proxies=self.proxy)

            response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            print(e)

        self._verify_response(response)
        return response.json()

    def private_api(self, url, params):
        '''handles private api methods'''

        params.update({"apikey": self.apikey, "nonce": self.get_nonce()})
        url += "?" + requests.compat.urlencode(params)
        self.headers.update({"apisign": self._generate_signature(url)
                             })
        try:
            response = self.api_session.get(url, headers=self.headers,
                                            timeout=self.timeout,
                                            proxies=self.proxy)

            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(e)

        self._verify_response(response)
        return response.json()

    def get_markets(self):
        '''find out supported markets on this exhange.'''

        r = self.api(self.url + "public" + "/getmarkets", params={})["result"]
        pairs = [i["MarketName"].lower() for i in r]

        return pairs

    def get_summaries(self):
        '''get summary of all active markets'''

        return self.api(self.url + "public" + "/getmarketsummaries",
                        params={})["result"]

    def get_market_ticker(self, pair):
        '''returns simple current market status report'''

        return self.api(self.url + "public" + "/getticker",
                        params={"market": self.format_pair(pair)})["result"]

    def get_market_trade_history(self, pair, depth=200):
        '''returns last <n> trades for the pair'''

        if depth > 200:
            raise ValueError("Bittrex API allows maximum history of last 200 trades.")

        return self.api(self.url + "public" + "/getmarkethistory",
                        params={"market": self.format_pair(pair)}
                        )["result"][-depth:]

    def get_market_orders(self, pair, depth=50):
        '''return market order book, default <depth> is 50'''

        if depth > 50:
            raise ValueError("Bittrex API allows maximum depth of last 50 offers.")

        order_book = self.api(self.url + "public" + "/getorderbook",
                              params={'market': self.format_pair(pair),
                                      'type': 'both',
                                      'depth': depth})["result"]

        return order_book

    def get_market_depth(self, pair):
        '''returns market depth'''

        order_book = self.get_market_orders(self.format_pair(pair))
        return {"bids": sum([Decimal(i["Quantity"]) * Decimal(i["Rate"]) for i in order_book["buy"]]),
                "asks": sum([Decimal(i["Quantity"]) for i in order_book["sell"]])
                }

    def get_market_summary(self, pair):
        '''return basic market information'''

        return self.api(self.url + "public" + "/getmarketsummary",
                        params={"market": self.format_pair(pair)})["result"][0]

    def get_market_volume(self, pair):
        '''return market volume [of last 24h]'''

        smry = self.get_market_summary(pair)

        return {'BTC': smry['BaseVolume'], pair.split(self.delimiter)[1].upper(): smry['Volume']}

    def get_market_spread(self, pair):
        '''return first buy order and first sell order'''

        d = self.get_market_summary(self.format_pair(pair))
        return Decimal(d["Ask"]) - Decimal(d["Bid"])

    def buy_limit(self, pair, rate, amount):  # buy_limit as default
        """creates buy order for <pair> at <rate> for <amount>"""

        return self.private_api(self.url + "market" + "/buylimit",
                                params={"market": self.format_pair(pair),
                                        "quantity": amount,
                                        "rate": rate})

    def sell_limit(self, pair, rate, amount):  # sell_limit as default
        """creates sell order for <pair> at <rate> for <amount>"""

        return self.private_api(self.url + "market" + "/selllimit",
                                params={"market": self.format_pair(pair),
                                        "quantity": amount,
                                        "rate": rate})

    def cancel_order(self, order_id):
        """cancel order <id>"""

        return self.private_api(self.url + "market" + "/cancel",
                                params={"uuid": order_id})["result"]

    def get_open_orders(self, market=None):
        """get open orders for <market>
           or all open orders if called without an argument."""

        if market:
            params = {"market": self.format_pair(market)}
        else:
            params = {}

        return self.private_api(self.url + "market" + "/getopenorders",
                                params=params)["result"]

    def cancel_all_orders(self):

        for order in self.get_open_orders():
            self.cancel_order(order['OrderUuid'])

    def get_order_history(self):
        """get order history"""

        return self.private_api(self.url + "account" + "/getorderhistory",
                                params={})["result"]

    def get_balances(self):
        """get all balances from your account"""

        balances = self.private_api(self.url + "account" + "/getbalances",
                                    params={})["result"]

        return [i for i in balances if i["Balance"] > 0]

    def get_deposit_address(self, coin):
        """retrieve or generate an address for <coin>.
        If there is none, call will return empty, call again to get it."""

        addr = self.private_api(self.url + "account" + "/getdepositaddress",
                                params={"currency": coin.upper()})["result"]

        return addr["Address"]

    def withdraw(self, coin, amount, address):
        """withdraw <coin> <amount> to <address>"""

        return self.private_api(self.url + "account" + "/withdraw",
                                params={"currency": coin.upper(),
                                        "quantity": amount,
                                        "address": address})

    def get_order(self, order_id):
        """retrieve a single order by uuid."""

        return self.private_api(self.url + "account" + "/getorder",
                                params={"uuid": order_id})["result"]

    def get_withdraw_history(self, coin=None):
        """retrieve withdrawal history."""

        if coin:
            params = {"currency": self.format_pair(coin)}
        else:
            params = {}

        return self.private_api(self.url + "account" + "/getwithdrawalhistory",
                                params=params)["result"]

    def get_deposit_history(self, coin=None):
        """retreive deposit history."""

        if coin:
            params = {"currency": self.format_pair(coin)}
        else:
            params = {}

        return self.private_api(self.url + "account" + "/getdeposithistory",
                                params=params)["result"]


class BittrexNormalized(Bittrex):

    def __init__(self, apikey=None, secret=None, timeout=None, proxy=None):
        super(BittrexNormalized, self).__init__(apikey, secret, timeout, proxy)

    @staticmethod
    def _iso_string_to_datetime(ts):
        '''convert ISO timestamp to unix timestamp'''

        try:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f")
        except:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")

    @classmethod
    def format_pair(self, market_pair):
        """
        Expected input is quote - base.
        Normalize the pair inputs and
        format the pair argument to a format understood by the remote API."""

        market_pair = market_pair.lower()  # bittrex takes lowercase

        if "-" not in market_pair:
            raise InvalidDelimiterError('Agreed upon delimiter is "-".')

        quote, base = market_pair.split('-')

        if base not in self.base_currencies:
            raise InvalidBaseCurrencyError('''Expected input is quote-base, you have provided with {pair}'''.format(pair=market_pair))

        return base + '-' + quote  # for bittrex quote comes second

    def get_markets(self):
        '''normalized Bittrex.get_markets'''

        m = []
        for i in super().get_markets():
            base, quote = i.split('-')
            m.append(quote + '-' + base)

        return m

    def get_market_ticker(self, market):

        ticker = super().get_market_ticker(market)

        return {k.lower(): v for k, v in ticker.items()}

    def get_market_trade_history(self, market):

        upstream = super().get_market_trade_history(market)
        downstream = []

        for data in upstream:

            downstream.append({
                'timestamp': self._iso_string_to_datetime(data['TimeStamp']),
                'is_sale': is_sale(data['OrderType']),
                'rate': data['Price'],
                'amount': data['Quantity'],
                'trade_id': data['Id']
            })

        return downstream

    def get_market_orders(self, market, depth=50):
        '''
        :return:
            dict['bids': list[price, quantity],
                 'asks': list[price, quantity]
                ]
        bids[0] should be first next to the spread
        asks[0] should be first next to the spread
        '''

        orders = super().get_market_orders(market, depth)

        return {
            'bids': [[i['Rate'], i['Quantity']] for i in orders['buy']],
            'asks': [[i['Rate'], i['Quantity']] for i in orders['sell']]
        }
