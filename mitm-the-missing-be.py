import logging
import os
import json
from collections import defaultdict
from dataclasses import dataclass
import random
import time
from mitmproxy import http
from mitmproxy import types
from mitmproxy import command
from mitmproxy.http import HTTPFlow
from pathlib import Path
from typing import TypedDict, cast, NotRequired, Optional


JSON = (
    None
    | bool
    | int
    | float
    | str
    | list["JSON"]
    | dict[str, "JSON"]
)

@dataclass
class Header:
    key: str
    values: list[str]

@dataclass
class ResponseItem:
    statusCode: int
    body: Optional[JSON] = None
    headers:  Optional[list[Header]] = None

class ResponseFileData(TypedDict):
    statusCode: NotRequired[int]
    path: str
    body: NotRequired[str]

class MissingBe:
    def comparePaths(self, abstractPath: str, path: str):
        abstractPathParts = [p for p in abstractPath.split("/") if p]
        pathParts = [p for p in path.split("/") if p]

        if len(abstractPathParts) != len(pathParts):
            return False

        for a, b in zip(abstractPathParts, pathParts):
            if a != b and not a.startswith(":"):
                return False

        return True
    
    def parseStringAsNumber(self, s: str | None):
        if s is None:
            return None
        try:
            return int(s)
        except ValueError:
            return None
        
    def getAbsolutePath(self, path_str: str):
        return str((Path.cwd() / Path(path_str)).resolve())
    
    @command.command("missingbe.load")
    def loadResponseFiles(self, path: types.Path):
        absolutePath = self.getAbsolutePath(path)

        logging.info(f"Loading response files from {absolutePath}")

        self.responses.clear()
        obj = os.scandir(absolutePath)
        for entry in obj:
            if entry.is_file() and entry.name.startswith("response") and entry.name.endswith(".json"):
                logging.info(f"Response file loaded: {entry.name}")
                with open(entry.path, 'r') as file:
                    data_raw = json.load(file)

                    if not isinstance(data_raw, dict):
                        raise ValueError("Expected response file to contain an JSON-object")

                    data = cast(ResponseFileData, data_raw)
                    
                    if "path" not in data:
                        raise ValueError("Expected response object to contain path")
                    
                    body = data.get("body")
                    statusCode = data.get("statusCode");

                    responseItem = ResponseItem(statusCode=statusCode if statusCode is not None else 200, body=body if body is not None else None)
                    self.responses[data["path"]].append(responseItem) 

    def __init__(self):
        self.responses : defaultdict[str, list[ResponseItem]] = defaultdict(list)
        self.loadResponseFiles(types.Path(os.getcwd()));

    def request(self, flow: HTTPFlow):
        logging.info("Request")
        sleep = self.parseStringAsNumber(flow.request.query.get("sleep"))
        logging.info(f"sleep {sleep}")
        
        data = {}
        #set_by_path(data, "users[].name", "Alice")
        logging.info(f"This is it: {data}")

        if sleep:
            logging.info("I'm sleeping")
            time.sleep(sleep / 1000)

        currentPathWithoutQuery = flow.request.path.split('?', 1)[0]
        logging.info(currentPathWithoutQuery)
        logging.info(flow.request.method)
 
        responseCandidates = [item for k, items in self.responses.items() if self.comparePaths(k, currentPathWithoutQuery) for item in items]
        response = random.choice(responseCandidates) if responseCandidates else None

        if flow.request.method == "GET" and response and response.statusCode:
            flow.response = http.Response.make(response.statusCode, json.dumps(response.body), {"Content-Type": "application/json; charset=utf-8"})
            
    def response(self, flow: HTTPFlow):
        logging.info("response")

addons = [MissingBe()]