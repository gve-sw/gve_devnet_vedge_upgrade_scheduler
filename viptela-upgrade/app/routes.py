#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2021 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

__author__ = "Josh Ingeniero <jingenie@cisco.com>"
__contributors__ = [
    "Robert Landires <rlandire@cisco.com>"
]
__copyright__ = "Copyright (c) 2021 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"

import requests
import datetime
import json
import urllib3
import pprint
import time
import os
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from flask import render_template, redirect, url_for, request, session, flash, g
from functools import wraps

from DETAILS import *
from app import app
from scheduler import *
from tinydb import TinyDB, Query

global db
global HOST
global USERNAME
global PASSWORD

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
pp = pprint.PrettyPrinter(indent=2)
logging.basicConfig(filename='app.log', filemode='a', format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)
TinyDB.DEFAULT_TABLE_KWARGS = {'cache_size': 0}
db = TinyDB('db.json')


sched = BackgroundScheduler()


# vManage Class
class Vmanage:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        try:
            if not (host and username and password):
                raise ValueError("Check empty arguments")
        except Exception as e:
            logging.exception("Exception occurred")

        self.jsessionid = self.get_jsessionid()
        self.token = self.get_token()
        if self.token is not None:
            self.header = {'Content-Type': "application/json", 'Cookie': self.jsessionid, 'X-XSRF-TOKEN': self.token}
        else:
            self.header = {'Content-Type': "application/json", 'Cookie': self.jsessionid}

    def get_jsessionid(self):
        api = "/j_security_check"
        base_url = "https://%s" % (self.host)
        url = base_url + api
        payload = {'j_username': self.username, 'j_password': self.password}

        response = requests.post(url=url, data=payload, verify=False)
        try:
            cookies = response.headers["Set-Cookie"]
            jsessionid = cookies.split(";")
            return (jsessionid[0])
        except Exception as e:
            logging.exception("No valid JSESSION ID returned\n")
            # raise ValueError("Invalid Credentials")

    def get_token(self):
        headers = {'Cookie': self.jsessionid}
        base_url = "https://%s" % (self.host)
        api = "/dataservice/client/token"
        url = base_url + api
        response = requests.get(url=url, headers=headers, verify=False)
        if response.status_code == 200:
            return (response.text)
        else:
            return None

    def call(self, api, payload, method):
        # Url
        base_url = "https://%s" % (self.host)
        url = base_url + api
        response = requests.request(method, url=url, verify=False, headers=self.header, data=payload)
        return response


# Check if logged in
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('You need to login first')
            return redirect(url_for('login'))

    return wrap


# Logout
@app.route('/logout', methods=['GET'])
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))


# Login screen
@app.route('/login', methods=['GET', 'POST'])
def login():
    global HOST
    global USERNAME
    global PASSWORD
    if request.method == 'GET':
        try:
            session['HOST'] = HOST
            session['USERNAME'] = USERNAME
            session['PASSWORD'] = PASSWORD
            session['logged_in'] = True
            vmanage = Vmanage(HOST, USERNAME, PASSWORD)
            logging.info(f"Logged in with {HOST}, {USERNAME}:{PASSWORD}")
            sched.add_job(check_upgrades, trigger='cron', minute='*', id='1', replace_existing=True,
                          args=[vmanage])
            logging.info("Scheduler Started")
            session['logged_in'] = True
            try:
                sched.start()
            except Exception as e :
                logging.exception('Scheduler failed to start Upgrade Job or it is already running')
            return redirect(url_for('index'))
        except Exception as e:
            logging.info('credentials not found, redirecting to log in')
            return render_template('login.html', title='Log In')
    elif request.method == 'POST':
        try:
            details = request.form
            logging.debug(details)
            session['HOST'] = details['url']
            session['USERNAME'] = details['username']
            session['PASSWORD'] = details['password']
            session['logged_in'] = True
            logging.info('Logged in')

            vmanage = Vmanage(session['HOST'], session['USERNAME'], session['PASSWORD'])
            sched.add_job(check_upgrades, trigger='cron', minute='*', id='1', replace_existing=True,
                          args=[vmanage])
            try:
                sched.start()
            except Exception as e:
                logging.exception('Scheduler failed to start Upgrade Job or it is already running')
            return redirect(url_for('index'))
        except Exception as e:
            logging.exception('Invalid credentials')
            return redirect(url_for('login'))


# Mode Selection
@app.route('/', methods=['GET'])
@login_required
def index():
    return render_template('index.html', title='Welcome')


# vEdge selection screen
@app.route('/devices', methods=['GET', 'POST'])
@login_required
def devices():
    vmanage = Vmanage(session['HOST'], session['USERNAME'], session['PASSWORD'])
    logging.info(f"Logged in with {session['HOST']}, {session['USERNAME']}:{session['PASSWORD']}")
    vedges = []
    payload = {}
    vedgeResponse = vmanage.call('/dataservice/system/device/vedges', payload, 'GET').json()['data']

    for item in vedgeResponse:
        vedges.append(item)
    now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')
    if request.method == 'GET':
        session['selectedDevices'] = []
        return render_template('devices.html', title='vEdge Upgrade Scheduler', timenow=now, vedges=vedges)
    elif request.method == 'POST':
        devlist = request.form.getlist('devs')
        devices = []
        for device in devlist:
            value = {
                "deviceIP": device.split(',')[0],
                "chasisNumber": device.split(',')[1],
                "platformFamily": device.split(',')[2]
            }
            devices.append(value)
        session['selectedDevices'] = devices
        return redirect('schedule', code=302)


# Device scheduling screen
@app.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    global db
    vmanage = Vmanage(session['HOST'], session['USERNAME'], session['PASSWORD'])
    logging.info(f"Logged in with {session['HOST']}, {session['USERNAME']}:{session['PASSWORD']}")
    vedges = session['selectedDevices']
    versions = []
    payload = {}
    now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')
    if request.method == 'GET':
        softwareResponse = vmanage.call('/dataservice/device/action/software', payload, 'GET').json()['data']
        for item in softwareResponse:
            family = item['platformFamily'][0]
            if family == vedges[0]["platformFamily"]:
                versions.append(item)
        return render_template('scheduling.html', title='vEdge Upgrade Scheduler', timenow=now, vedges=vedges,
                               versions=versions)
    elif request.method == 'POST':
        details = request.form
        upgrade = {
            "devices": session['selectedDevices'],
            "date": details['date'],  # %Y-%m-%d
            "time": details['time'],  # %H:%M
            "version": details['version']
        }
        db.insert(upgrade)
        session['selectedDevices'] = {}
        return redirect('devices', code=302)


# View existing schedules
@app.route('/view', methods=['GET', 'POST'])
@login_required
def view():
    global db
    if request.method == 'GET':
        now = datetime.datetime.now().strftime('%d-%m-%Y %H:%M')
        schedules = []
        for item in db.all():
            item['id'] = item.doc_id
            schedules.append(item)
        print(schedules)
        return render_template('view.html', title='vEdge Upgrade Scheduler', timenow=now, schedules=schedules)
    elif request.method == 'POST':
        templist = request.form.getlist('dels')
        deletelist = []
        for item in templist:
            deletelist.append(int(item))
        db.remove(doc_ids=deletelist)
        return redirect('view', code=302)
