#!/bin/bash

py -m venv venv
source venv/bin/activate
pip install -r requirements.txt
screen -d -m py  main.py
