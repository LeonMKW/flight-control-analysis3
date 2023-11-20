#! /usr/bin/env bash

function restart {
    #pm2 start start.py --name=healthy-management  --interpreter  /usr/local/miniconda/envs/healthy-management/bin/python
    pm2 stop flight-control-analysis
    pm2 delete flight-control-analysis
    pm2 start api.py --name=flight-control-analysis  --interpreter  /usr/local/miniconda/envs/flight-control-analysis/bin/python
    pm2 save
}

function start {
  pip install -r requirements.txt -i pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  python api.py
}

action=${1}
$action
