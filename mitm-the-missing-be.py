import logging
import os
import json
from collections import defaultdict
from typing import Any
from dataclasses import dataclass
from mitmproxy import http
import random
import time

@dataclass
class ResponseItem:
    statusCode: int
    body: object

class MissingBe:
    def comparePaths(self, abstractPath, path):
        abstractPathParts = [p for p in abstractPath.split("/") if p]
        pathParts = [p for p in path.split("/") if p]

        if len(abstractPathParts) != len(pathParts):
            return False

        for a, b in zip(abstractPathParts, pathParts):
            if a != b and not a.startswith(":"):
                return False

        return True
    
    def parseStringAsNumber(self, s):
        if s is None:
            return None
        try:
            return int(s)
        except ValueError:
            return None
            
    def __init__(self):
        self.responses: dict[str, list[ResponseItem]] = defaultdict(list)
        obj = os.scandir()
        for entry in obj:
            if entry.is_file() and entry.name.startswith("response") and entry.name.endswith(".json"):
                logging.info(f"Response file loaded: {entry.name}")
                with open(entry.path, 'r') as file:
                    data = json.load(file)
                    if not isinstance(data, dict):
                        raise ValueError("Expected response file to contain an JSON-object")

                    if "statusCode" not in data:
                        raise ValueError("Expected response object to contain statusCode")
                    
                    if "path" not in data:
                        raise ValueError("Expected response object to contain path")

                    responseItem = ResponseItem(statusCode=data["statusCode"], body=data["body"])
                    self.responses[data["path"]].append(responseItem) 
        pass

    def request(self, flow):
        sleep = self.parseStringAsNumber(flow.request.query.get("sleep"))
        logging.info(f"sleep {sleep}")
        if sleep:
            logging.info("I'm sleeping")
            time.sleep(sleep / 1000)

        currentPathWithoutQuery = flow.request.path.split('?', 1)[0]
        logging.info(currentPathWithoutQuery)
        logging.info(flow.request.method)
 
        responseCandidates = [item for k, items in self.responses.items() if self.comparePaths(k, currentPathWithoutQuery) for item in items]
        response = random.choice(responseCandidates) if responseCandidates else None

        if flow.request.method == "GET" and response:
            flow.response = http.Response.make(response.statusCode, json.dumps(response.body), {"Content-Type": "application/json; charset=utf-8"})
            return


addons = [MissingBe()]