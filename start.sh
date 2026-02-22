#!/bin/bash
cd /home/sids/stacks/rainbot

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
cd /home/sids/stacks/rainbot
/home/sids/stacks/rainbot/pyenv/bin/python rainbot.py
