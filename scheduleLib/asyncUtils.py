# Sage Santomenna, 2023
import asyncio
import logging

import httpx
from bs4 import BeautifulSoup


class AsyncHelper:
    """
    A helper class to facilitate easier asynchronous requesting.
    """

    def __init__(self, followRedirects: bool,timeout=120):
        self.timeout = timeout
        self.client = httpx.AsyncClient(follow_redirects=followRedirects, timeout=self.timeout)
        self.logger = logging.getLogger(__name__)

    def __del__(self):
        # Close connection when this object is destroyed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.client.aclose())
            else:
                loop.run_until_complete(self.client.aclose())
        except Exception:
            pass

    async def multiGet(self, URLlist, designations=None, soup=False, postContent=None):
        """
        Asynchronously make multiple url requests. Optionally, turn the result into soup with beautifulSoup. Requires internet connection
        :param URLlist: A list of URLs to query
        :param designations: An optional list of designations to be paired with request results in the return dictionary. If none, urls will be used as designations
        :param soup: bool. If true, soup result before returning
        :param postContent: list. if not none, will post postContent instead of using get
        :return: dictionary of {desig/url: completed request} or {desig/url:html soup retrieved}
        """

        if designations is not None and len(designations) != len(URLlist):
            raise ValueError("asyncMultiRequest: provided designation length does not match url list length")
        if postContent is not None and len(postContent) != len(URLlist):
            raise ValueError("asyncMultiRequest: provided postContent length does not match url list length")

        if designations is None:
            designations = URLlist
        if postContent is None:
            postContent = [None] * len(URLlist)
        tasks = []
        for i, url in enumerate(URLlist):
            tasks.append(
                asyncio.create_task(self.makeRequest(designations[i], url, soup=soup, postContent=postContent[i])))
        result = await asyncio.gather(*tasks)

        # gather tuples returned into dictionary, return
        returner = dict()
        for desig, item in result:
            returner.setdefault(desig, []).append(item)
        return returner

    async def makeRequest(self, desig, url, soup=False, postContent=None):
        """
        Asynchronously GET or POST to the indicated URL. Optionally, turn the result into soup with beautifulSoup. Calling this in a for loop probably won't work like you want it to, use multiGet for concurrent requests
        :param desig: An identifying designation for the html retrieved
        :param url: The URL to query
        :param soup: bool. If true, soup result before returning
        :param postContent: list. if not none, will POST postContent instead of using get
        :return: A tuple, (desig, completedRequest) or (desig,soup(completedRequest))
        """
        try:
            if postContent is not None:
                offsetReq = await self.client.post(url, data=postContent)
            else:
                offsetReq = await self.client.get(url)
        except (httpx.ConnectError, httpx.HTTPError):
            self.logger.exception("HTTP error. Unable to make async request to " + url)
            return desig, None
        except httpx.TimeoutException:
            self.logger.exception("Async request timed out. Timeout is set to "+str(self.timeout)+" seconds.")
        if offsetReq.status_code != 200:
            self.logger.error("Error: HTTP status code " + str(offsetReq.status_code) + ". Unable to make async request to " +
                        url + ". Reason given: " + offsetReq.reason_phrase)
            return desig, None
        if soup:
            offsetReq = BeautifulSoup(offsetReq.content, 'html.parser')
        return tuple([desig, offsetReq])
