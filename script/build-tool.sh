#! /usr/bin/env bash

function restart {
    #pm2 start start.py --name=healthy-management  --interpreter  /usr/local/miniconda/envs/healthy-management/bin/python
    pm2 stop healthy-management
    pm2 delete healthy-management
    pm2 start start.py --name=healthy-management  --interpreter  /usr/local/miniconda/envs/healthy-management/bin/python
    pm2 save
}

action=${1}
$action
