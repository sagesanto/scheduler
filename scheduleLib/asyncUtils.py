# Sage Santomenna, 2023

import httpx
import asyncio
from bs4 import BeautifulSoup

class AsyncHelper:
    """
    A helper class to facilitate easier asynchronous requesting. Calling private methods externally can derail your control flow; don't do it.
    """
    def __init__(self,followRedirects:bool):
        # # --- set up loops make our own ---
        # self.loop = asyncio.new_event_loop()
        self.followRedirects = followRedirects
        print("Async helper initialized. Remember to await methods")
        # self.oldLoop = None

    # def __del__(self):
    #     self._releaseLoop()
    #     self.loop.close()
    #
    #
    # def _grabLoop(self,oldLoop):
    #     """
    #     DO NOT USE EXTERNALLY. Internal: save the current event loop for the thread, then run our code on our loop
    #     :return:
    #     """
    #     try:
    #         if oldLoop != self.loop:
    #             self.oldLoop = oldLoop
    #     except Exception as e:
    #         print("except:",repr(e))
    #         self.oldLoop = None
    #
    #     print("Grabbing loop")
    #     print(self.oldLoop)
    #     print(type(self.oldLoop))
    #
    #     asyncio.set_event_loop(self.loop)
    #     print("Grabbed")
    # def _releaseLoop(self):
    #     """
    #     DO NOT USE EXTERNALLY. Internal: yield back to the previous event loop, if one exists and is open
    #     """
    #     print("Releasing loop")
    #     self.loop.stop()
    #     if self.oldLoop and isinstance(self.oldLoop,asyncio.AbstractEventLoop):
    #         if not self.oldLoop.is_closed:
    #             asyncio.set_event_loop(self.oldLoop)
    #     print("Released")

    async def _runAsync(self, func, *args,**kwargs):
        """
        Internal: Manages loop grabbing and releasing. Must call all private methods through this method.
        """
        # try:
        #     loop = asyncio.get_event_loop()
        #     if loop.is_running(): # is this going to break everything
        #         print("Async event loop already running. Attempting to grab it.")
        #         self._grabLoop(loop)
        #         try:
        #             results = self.loop.run_until_complete(func(*args, **kwargs))
        #         except Exception as e: # error arose in function that was passed to us
        #             print("Encountered exception in",func,"during async event loop")
        #             self.loop.stop()
        #             self.loop.close()
        #             print(repr(e))
        #             exit()
        #         self._releaseLoop()
        #     else:
        #         results = loop.run_until_complete(func(*args, **kwargs))
        # except KeyboardInterrupt as k:  # user tried to stop
        #     print("Keyboard interrupt! Trying to exit gracefully")
        #     self.loop.stop()
        #     self.loop.close()
        #     raise k
        # except Exception as e:  # presumably, there is no current event loop active. oh boy this part is unsafe
        #     print("Except!",e)
        #     asyncio.set_event_loop(self.loop)
        #     results = self.loop.run_until_complete(func(*args, **kwargs))

        results = await func(*args,**kwargs)
        return results

    async def asyncMultiGet(self,URLlist,designations=None,soup=False, postContent = None):
        """
        Asynchronously make multiple url get requests or posts. Optionally, turn the result into soup with beautifulSoup. Requires internet connection
        :param URLlist: A list of URLs to query
        :param designations: An optional list of designations to be paired with request results in the return dictionary. If none, urls will be used as designations
        :param soup: bool. If true, soup result before returning
        :param postContent: If not none, will post postContent instead of using get
        :return: dictionary of {desig/url: completed request} or {desig/url:html soup retrieved}
        """
        return await self._runAsync(self._internalAsyncMultiGet,URLlist,designations,soup=soup,postContent=postContent)

    async def _internalMakeAsyncRequest(self,desig, client, url,soup=False,postContent=None):
        """
        DO NOT CALL EXTERNALLY. Internal: Asynchronously get the indicated URL. Optionally, turn the result into soup with beautifulSoup.
        :param func: The function to call - must be a method of httpx.AsyncClient and must return a response object
        :param desig: An identifying designation for the html retrieved
        :param url: The URL to query
        :param soup: bool. If true, soup result before returning
        :param postContent: list. if not none, will post postContent instead of using get
        :return: A tuple, (desig, completedRequest) or (desig,soup(completedRequest))
        """
        try:
            if postContent is not None:
                offsetReq = await client.post(url, data=postContent)
            else:
                offsetReq = await client.get(url)
        except (httpx.ConnectError, httpx.HTTPError) as err:
            print("Unable to make async request to",url)
            return desig, None
        if offsetReq.status_code != 200:
            print("Unable to make async request to", url)
            return desig, None
        if soup:
            offsetReq = BeautifulSoup(offsetReq.content, 'html.parser')
        return tuple([desig, offsetReq])

    async def _internalAsyncMultiGet(self,URLlist,designations=None,soup=False,postContent = None):
        """
        DO NOT CALL EXTERNALLY. Internal: Asynchronously make multiple url requests. Optionally, turn the result into soup with beautifulSoup. Must be called in an asyncio loop using run_until_complete. Requires internet connection
        :param URLlist: A list of URLs to query
        :param designations: An optional list of designations to be paired with request results in the return dictionary. If none, urls will be used as designations
        :param soup: bool. If true, soup result before returning
        :return: dictionary of {desig/url: completed request} or {desig/url:html soup retrieved}
        """

        if designations is not None and len(designations) != len(URLlist):
            raise ValueError("asyncMultiRequest: provided designation length does not match url list length")
        if designations is not None and len(designations) != len(URLlist):
            raise ValueError("asyncMultiRequest: provided designation length does not match url list length")

        if designations is None:
            designations = URLlist
        if postContent is None:
            postContent = [None]*len(URLlist)
        tasks = []
        with httpx.AsyncClient(follow_redirects=self.followRedirects, timeout=60.0) as client:
            for i, url in enumerate(URLlist):
                tasks.append(asyncio.create_task(self._internalMakeAsyncRequest(designations[i],client,url,soup=soup,postContent=postContent[i])))
            result = await asyncio.gather(*tasks)

        #gather tuples returned into dictionary, return
        returner = dict()
        for desig, item in result:
            returner.setdefault(desig, []).append(item)
        return returner
