#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2021 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by pytthe License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""


__author__ = "Josh Ingeniero <jingenie@cisco.com>"
__copyright__ = "Copyright (c) 2020 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"


from tinydb import TinyDB, Query

import requests
import datetime
import json
import urllib3
import logging


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(filename='app.log', filemode='a', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)


def check_upgrades(vmanage):
    TinyDB.DEFAULT_TABLE_KWARGS = {'cache_size': 0}
    db = TinyDB('db.json')

    datenow = datetime.datetime.now().strftime('%Y-%m-%d')
    timenow = datetime.datetime.now().strftime('%H:%M')

    Job = Query()
    jobs = db.search((Job.date == datenow) & (Job.time == timenow))

    logging.info(f"Number of jobs: {len(jobs)}")

    if len(jobs) < 1:
        return 0

    count = 1
    for job in jobs:
        logging.info("--------------------\n")
        logging.info(f"Job #{count} - {len(job['devices'])} Devices")
        for device in job['devices']:
            payload = {
                "action": "install",
                "input": {
                    "vEdgeVPN": 0,
                    "vSmartVPN": 0,
                    "version": job['version'],
                    "versionType": "vmanage",
                    "reboot": True,
                    "sync": True
                },
                "devices": [
                    {
                        "deviceIP": device['deviceIP'],
                        "deviceId": device['chasisNumber']
                    }
                ],
                "deviceType": "vedge"
            }
            upgradeResponse = vmanage.call('/dataservice/device/action/install', json.dumps(payload), 'POST').json()
            logging.debug(upgradeResponse)
            logging.info(f"Device {[device['chasisNumber']]} upgrade in progress")
            logging.info(f"Process ID is {upgradeResponse['id']}")
        logging.info("Job Complete!!!")
        count += 1
