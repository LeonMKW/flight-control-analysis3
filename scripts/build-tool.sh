#! /usr/bin/env bash

function restart {
    #pm2 start start.py --name=healthy-management  --interpreter  /usr/local/miniconda/envs/healthy-management/bin/python
    pm2 stop flight-control-analysis
    pm2 delete flight-control-analysis
    pm2 start start.py --name=flight-control-analysis  --interpreter  /usr/local/miniconda/envs/flight-control-analysis/bin/python
    pm2 save
}

action=${1}
$action
