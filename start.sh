#!/bin/bash

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
screen -d -m python main.py
