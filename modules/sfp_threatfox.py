# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:        sfp_threatfox
# Purpose:     Check if an IP address is malicious according to ThreatFox.
#
# Author:      <bcoles@gmail.com>
#
# Created:     2021-09-20
# Copyright:   (c) bcoles 2021
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import time

from spiderfoot import SpiderFootEvent, SpiderFootPlugin


class sfp_threatfox(SpiderFootPlugin):

    meta = {
        'name': "ThreatFox",
        'summary': "Check if an IP address is malicious according to ThreatFox.",
        'flags': [],
        'useCases': ["Investigate", "Passive"],
        'categories': ["Reputation Systems"],
        'dataSource': {
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': [
                "https://threatfox.abuse.ch/api/",
            ],
            'website': "https://threatfox.abuse.ch",
            'logo': "https://threatfox.abuse.ch/images/threatfox_logo.png",
            'description': "ThreatFox is a free platform from abuse.ch with the goal of sharing"
            "indicators of compromise (IOCs) associated with malware with the infosec community,"
            "AV vendors and threat intelligence providers.",
        }
    }

    opts = {
        'checkaffiliates': True
    }

    optdescs = {
        'checkaffiliates': "Apply checks to affiliates?"
    }

    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.results = self.tempStorage()

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["IP_ADDRESS", "AFFILIATE_IPADDR"]

    def producedEvents(self):
        return ["MALICIOUS_IPADDR", "MALICIOUS_AFFILIATE_IPADDR"]

    def query(self, qry):
        """Query IOCs

        Args:
            qry (str): IP address

        Returns:
            str: API response data as JSON
        """
        params = {
            'query': 'search_ioc',
            'search_term': qry
        }

        headers = {
            "Accept": "application/json",
        }

        res = self.sf.fetchUrl(
            "https://threatfox-api.abuse.ch/api/v1/",
            useragent=self.opts['_useragent'],
            timeout=self.opts['_fetchtimeout'],
            headers=headers,
            postData=json.dumps(params)
        )

        time.sleep(1)

        if res['content'] is None:
            return None

        if res['code'] == "429":
            self.sf.error("You are being rate-limited by ThreatFox.")
            self.errorState = True
            return None

        if res['code'] != '200':
            self.sf.error(f"Unexpected reply from ThreatFox: {res['code']}")
            self.errorState = True
            return None

        try:
            json_result = json.loads(res['content'])
        except Exception as e:
            self.sf.debug(f"Error processing JSON response from ThreatFox: {e}")
            return None

        query_status = json_result.get('query_status')

        if query_status == 'no_result':
            self.sf.debug(f"No results from ThreatFox for: {qry}")
            return None

        if query_status != 'ok':
            self.sf.debug(f"ThreatFox query failed: {query_status}")
            return None

        data = json_result.get('data')

        if not data:
            self.sf.debug(f"No results from ThreatFox for: {qry}")
            return None

        return data

    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        if self.errorState:
            return

        self.sf.debug(f"Received event, {eventName}, from {srcModuleName}")

        if eventData in self.results:
            self.sf.debug(f"Skipping {eventData}, already checked.")
            return

        if eventName not in self.watchedEvents():
            return

        self.results[eventData] = True

        if eventName == 'IP_ADDRESS':
            evtType = 'MALICIOUS_IPADDR'
        elif eventName == 'AFFILIATE_IPADDR':
            if not self.opts.get('checkaffiliates', False):
                return
            evtType = 'MALICIOUS_AFFILIATE_IPADDR'
        else:
            return

        data = self.query(eventData)

        if not data:
            return

        url = "https://threatfox-api.abuse.ch/api/v1/"
        text = f"ThreatFox [{eventData}]\n<SFURL>{url}</SFURL>"
        evt = SpiderFootEvent(evtType, text, self.__name__, event)
        self.notifyListeners(evt)

# End of sfp_threatfox class
