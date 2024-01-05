#!/usr/bin/env bash

# 服务器重启后的流程
# 1.启动redis
/usr/local/redis/bin/redis-server /usr/local/redis/bin/redis.conf
# 2.更新report_values
cd data
python gen_data.py


