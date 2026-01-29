# Flight Control Analysis 3 - 设计说明（代码阅读版）

本文档基于对本仓库 `e:/flight-control-analysis3` 的代码阅读整理，目标是说明：程序由哪些模块组成、从哪些外部服务/数据库读数据、往哪些地方写数据，以及大致的调用链路。

## 1. 总览

本项目本质上是一个 **Flask Web 服务 + 若干数据分析/自动化任务**：

- Flask 提供 HTTP API（大量 `POST` 接口）和一个简单前端页面（`GET /index` 渲染 `templates/index.html`）。
- API 触发后端算法：通过 **TTNoNC Frontend BFF（openapi-transform）** 拉取任务/航天器信息，再从 **InfluxDB** 拉取遥测/动作记录，使用 pandas/numpy 计算统计结果。
- 部分“自动化接口”会把结果写入 **MongoDB**（作为中间结果/缓存/可追溯存储）。
- 轨道精度相关功能会把计算结果写入 **MariaDB**。
- 日报/截图发布会把图片上传到 **阿里云 OSS**，并通过 **通知服务**（DingTalk 机器人/事件处理）推送链接。
- 另有 ODPA3 的空间环境接口，以及一个 Dify/DeepSeek 风格的 LLM 总结接口。

## 2. 目录与模块职责

- `start.py`
  - 主入口：读取 `PYTHON_ENV`，加载 `config/config.yaml`，初始化各类客户端（Influx/Mongo/MariaDB/OSS），注册 Flask 路由。
- `config/`
  - `config.yaml`：多环境配置（`COMMON` + `DEV/BETA/TEST/...`），包含所有外部依赖的地址与凭据。
  - `logging.yaml`：日志配置；`gun.conf`：Gunicorn 配置（默认 bind `0.0.0.0:7878`）。
- `utils/`
  - `factory.py`：按 `PYTHON_ENV` 从 `config/config.yaml` 读配置并配置 logging。
  - `db.py`：InfluxDB/Mongo/MariaDB/OSS 的轻量封装。
  - `flightcontrol_utils.py`：与 BFF(openapi-transform) 交互、拼 InfluxQL 查询、组装 DataFrame 的“数据获取层”。
  - `core_algorithm.py` 等：若干通用分析算法（锁定区间/间隔计算等）。
  - `dailyreport_utils.py`：日报相关的辅助查询与数据整形。
- `task/`
  - `flightcontrol_algorithms.py`：飞控统计类算法（上下行、锁定/掉锁、文件检查、异常等）。
  - `flightcontrol_automation_tasks.py`：把多项统计结果批量写入 Mongo 的自动化任务。
  - `satellitestatus_algorithm.py` + `satellitestatus_automation_tasks.py`：OBC 切换/复位检测、累计复位计数，并推送通知。
  - `ASsatellite_tasks.py` / `LZ04satellite_tasks.py`：AS02/AS03/LZ04 相关任务分析与接口封装（主要读 Influx + 调 BFF）。
  - `od_algorithm.py`：轨道精度/星历传播与误差统计（读 Influx + 调 BFF/传播服务，写 MariaDB）。
  - `space_enviroment_info.py`：调用 ODPA3 的空间环境摘要接口。
- `aggregation/dailyreport.py`
  - 生成“蜘蛛星”飞控日报（合并多算法结果 + 告警 + 轨道信息），以及截图上传 OSS、推送通知、LLM 总结等。
- `templates/` + `static/`
  - 前端页面与静态资源；页面会调用后端 API 生成日报内容，并可截图上传。
- `satop/`
  - Docker/Jenkins 相关文件（部署流水线）。

## 3. 配置与环境选择

运行时必须设置环境变量：

- `PYTHON_ENV=DEV|BETA|TEST|...`：决定从 `config/config.yaml` 读取哪一段配置（见 `utils/factory.py`）。
- 常见还会设置：`PYTHONUNBUFFERED=1`（立即刷新 stdout，便于看日志）。

`config/config.yaml` 中关键配置项（不要在文档里硬编码真实密码/密钥；此处只列“键”）：

- InfluxDB：`INFLUXDB_HOST/PORT/USER/PASSWD` + `INFLUXDB_DB_INPUT/DB_ACTION/DB_CHRONOGRAF/DB_ORBITDATA`
- MongoDB：`MONGO_HOSTS`、`MONGO_AUTH_SOURCE`、`MONGO_INITDB_ROOT_USERNAME/PASSWORD`
- MariaDB：`MARIADB_HOST/PORT`、`MARIADB_ODDBNAME`、`MARIADB_USER/PASSWORD`
- OSS：`OSS2_ENDPOINT/ACCESS/SECRET/BUCKET`
- Token：`POST_TOKEN_URL/USERNAME/PASSWORD`（用于获取 `x-web-token`）
- BFF/服务入口：`METE_DATA`、`ORBIT_SERVICE`、`ORBIT_PROPAGATION`、`ORBIT_MANEUVER`、`APPLICATION_TASK`
- 报表/文件：`POST_SATELLITE_REPORT_SEARCH`、`GET_SATELLITE_FILE_DOWNLOAD`
- 通知：`NOTIFICATION_URL`
- ODPA：`ODPA3_URL`
- LLM：`DSR1_URL/DSR1_TOKEN`

## 4. 外部依赖：读/写关系一览

### 4.1 InfluxDB（读为主）

代码位置：`utils/db.py`（`Influxdb` 封装）、`utils/flightcontrol_utils.py`、`utils/od_utils.py`、`utils/satellitestatus_utils.py` 等。

主要用途：

- 遥测（输入库 `measure`）：各类 `tm_all_*`（按 `tctmVersion` 拼接），用于计算上下行统计、锁定区间、文件检查、OBC 复位/切换等。
- 动作/指令（动作库 `action`）：例如 `tcSendRecord`（见 `Influxdb.get_command()`），用于统计发令/上星。
- 轨道数据（`orbit_data`）：`alt`、`phase`、`phase_diff` 等（见 `utils/od_utils.py` 的 `get_altitude/get_phase/get_phase_new`）。

注意：项目里配置有 `INFLUXDB_HOST_OUTPUT`，但当前代码中几乎未使用“输出 Influx”写入逻辑。

### 4.2 MongoDB（读写：中间结果/告警数据）

代码位置：`utils/db.py`（`Mongo` 封装）、`task/flightcontrol_automation_tasks.py`、`task/satellitestatus_algorithm.py`、`task/AS_satellitestatus_automation_task.py`、`utils/dailyreport_utils.py` 等。

1) 写入：`flight-control-middle-data` 数据库（项目自己的“中间数据”库）

- 过站/飞控统计自动写入（`task/flightcontrol_automation_tasks.py`）：
  - `downlink_statics_experiment`
  - `uplink_statics_experiment`
  - `experimental_telemetry`
  - `experimental_uplock`
  - `hist_interval`
  - `gnss_interval`
  - `spiderling_file_inspect_experiment`
  - `mission_accomplish_status`
- 卫星状态/OBC（`task/satellitestatus_algorithm.py`）：
  - `OBC_reset_records`
  - `OBC_switch_records`
  - `cumulative_reset_count`（写入后会向 `NOTIFICATION_URL` 推送）
- AS02/AS03 自动任务去重结果（`task/AS_satellitestatus_automation_task.py`）：
  - `AS02-upload-sensing-task`、`AS02-payload-data-transmission`、`AS02-platform-data-transmission`、`AS02-histdatasave`、`AS02-silicon-battery`、`AS02-delete-*-task`...
  - `AS03-upload-sensing-task`、`AS03-insight-sensing-task`、`AS03-outsight-sensing-task`、`AS03-*-task`...
  - 写法：基于业务字段拼接 composite key，再 `md5` 得到 `_id`，通过 `replace_one(..., upsert=True)` 去重写入。

2) 读取：告警/事件数据（用于日报统计）

- `ttnonc-notice.notice_record`：通过 aggregation pipeline 拉取告警（`Mongo.read_alert_data`）。
- `ttnonc-event.event_status`：查询告警是否结束（`Mongo.read_alert_data_end_status`）。

### 4.3 MariaDB（写：轨道精度结果）

代码位置：`utils/db.py`（`Mariadb` 连接）、`task/od_algorithm.py`。

主要写入：

- `orbit_precision_summary_96hr`
- `orbit_precision_data_96hr`

写入方式：`mariadb.connect(...)` 获取连接 + `cursor.execute(INSERT ...)` + `commit()`。

### 4.4 OSS（写：日报/图片）

代码位置：`utils/db.py`（`OSS2`）、`aggregation/dailyreport.py`（`publish_report_task` / `upload_to_oss2_only_report_task`）。

流程：

- 前端把截图（base64）POST 到后端。
- 后端把图片 bytes 通过 `put_object` 上传到 `OSS2_BUCKET` 的固定路径（例如 `flight-control-analysis/dailyreport/<file>`）。
- 生成带有效期的签名 URL（默认 30 天）。

### 4.5 通知服务（写：推送）

代码位置：`task/satellitestatus_algorithm.py`、`utils/notification_content.py`、`aggregation/dailyreport.py`。

用途：

- OBC 累计复位计数：写入 Mongo 后，组装 `Satellite_Reset_Count` 的 payload，POST 到 `NOTIFICATION_URL`。
- 日报发布：上传 OSS 后生成链接，组装 `spiderling_flight_control_report` payload，POST 到 `NOTIFICATION_URL`。

### 4.6 TTNoNC Frontend BFF / openapi-transform（读：任务/航天器/轨道活动等）

代码位置：`utils/flightcontrol_utils.py`、`utils/od_utils.py`、`utils/dailyreport_utils.py` 等。

通用模式：

1) 先 `POST_TOKEN_URL` 用用户名/密码换取 token（`utils/authentication.py`）。
2) 调用 BFF 的 `.../v2/api/openapi-transform/...`，在 header 中带 `x-web-token`。

典型接口：

- 任务列表：`/get-all-task`（见 `get_task_list`）
- 航天器列表：`/get-all-spacecraft`（见 `tm_table`）
- 轨道外推/传播：`/orbit-forecast`（见 `task/od_algorithm.py`）
- 轨控活动（点火等）：`/orbit-fire-period`（见 `utils/dailyreport_utils.py#get_fire_records`）
- 网关任务：`/get-all-application-task`（见 `utils/dailyreport_utils.py` / `utils/dailyreport_utils.py` 调用链）

### 4.7 其它外部服务

- ODPA3：`task/space_enviroment_info.py` 调 `ODPA3_URL/space-environment-info-with-summary`。
- 航天器信息上报/文件下载：
  - `POST_SATELLITE_REPORT_SEARCH`：搜索上报记录
  - `GET_SATELLITE_FILE_DOWNLOAD`：下载文件（见 `task/od_algorithm.py`）
- LLM（Dify/DeepSeek 风格）：`aggregation/dailyreport.py#ask_dify` 调 `DSR1_URL`（Bearer `DSR1_TOKEN`）。

## 5. 主要“业务链路”说明（从请求到数据流）

### 5.1 单次查询：飞控统计类接口

以 `POST /downlink-stats` 为例（见 `start.py` -> `task/flightcontrol_algorithms.py`）：

1) 从 BFF 拉取任务过站列表（`get_task_list`）。
2) 从 InfluxDB 读取遥测帧（`vcIdnew` 等），按任务窗口统计“理论/实际下行帧数、时间差”等。
3) 结果以 JSON 返回给前端/调用方（通常不落库）。

其它类似接口：`/uplink-stats*`、`/downgap-experiment`、`/upgap-experiment`、`/hist-interval-experiment`、`/gnss-interval-experiment`、`/targetdetect-stats`、`/com-stats`、`/spiderlingfileinspection-stats*` 等。

### 5.2 自动化写库：飞控中间数据沉淀

入口：`POST /flight-operation-middle-data`（见 `start.py` -> `task/flightcontrol_automation_tasks.py`）。

- 对每个 satID，批量调用多种统计函数（下行、上行、掉锁、锁定、hist/gnss 间隔、文件检查等）。
- 把每个 mission 的结果按 `mission_id` upsert 到 `flight-control-middle-data` 的对应 collection（见上文 4.2）。

### 5.3 卫星状态自动化：OBC 切换/复位 + 通知

入口：`POST /satellite-status-auto-mission`（见 `start.py` -> `task/satellitestatus_automation_tasks.py`）。

- 从 Influx 拉取 OBC 相关测点，检测“复位区间/切换区间”，写入 `OBC_*_records`。
- 计算累计复位次数写入 `cumulative_reset_count`，并把摘要 POST 到通知服务。

### 5.4 日报生成与发布

前端页面：`GET /index`（模板 `templates/index.html` + 静态资源 `static/`）。

核心接口：

- `POST /spiderlingdailyreport`：后端调用 `aggregation/dailyreport.py#daily_report_spiderling`：
  - 汇总飞控统计（downlink/uplink/payload/file_inspect/异常/轨控等）
  - 读取 Mongo 告警并聚合
  - 读取/计算轨道高度、相位差等
  - 返回大 JSON 给前端渲染
- `POST /publish-spiderlingdailyreport`：
  - 前端把截图 base64 发给后端
  - 后端上传 OSS，生成签名 URL
  - 通过通知服务推送日报链接
- `POST /upload-to-oss2-only`：只上传 OSS，不推送
- `POST /dailyreport-ai-summary`：调用 `ask_dify` 获取总结（会清理 `<think>...</think>`）

## 6. 运行与部署方式（代码/仓库现状）

开发（本地）：

- 必须设置 `PYTHON_ENV=DEV`（你现在的 VS Code `fca3-dev` 已配置）。
- 直接运行：`python start.py`，默认端口 `7877`（可用 `PORT` 覆盖）。

生产/部署相关文件：

- `satop/Dockerfile-online`：容器入口直接跑 `python start.py`，对外暴露 `7878`。
- `config/gun.conf`：Gunicorn bind `0.0.0.0:7878`。
- `run.sh`：尝试以 gunicorn + celery 启动，但当前仓库 **没有** `wsgi_gunicorn.py`，`schedule/celery_scheduling.py` 也引用了不存在的 `app.task.*`；这部分看起来是历史遗留，若要用 gunicorn/celery 需要补齐/修正入口模块。
- `restart.sh`：提到 redis 和 `data/gen_data.py`，但当前仓库未包含 `gen_data.py`；同样像历史遗留。

## 7. 代码层面的几个“重要事实/风险点”（便于你后续改造）

- `start.py` 先用 `create_app()` 创建了一个带配置+logging 的 Flask app，用它的 `app.config` 初始化各种客户端；随后又执行 `app = Flask(__name__)` 覆盖了变量名。
  - 结果：路由挂载在“新 app”上，但 logging/CORS/配置并未通过 `create_app()` 统一注入；目前因为外部连接对象在覆盖前就已创建，很多接口仍可工作，但这是一处架构不一致点，后续如果要做更标准的 Flask 工厂模式建议合并为单一 app。
- 配置文件里包含明文凭据；建议后续迁移到环境变量/secret manager（至少把密码/token 拆出去）。

