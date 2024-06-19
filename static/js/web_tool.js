document.addEventListener('DOMContentLoaded', () => {
    const satIDMapping = {
        1: 'GS-1a',
        2: 'GS-2',
        3: 'GS-2AP01',
        4: 'GS-2AP02',
        5: 'GS-2AP03',
        6: 'GS-2BP01',
        7: 'GS-2BP02',
        14: 'GS-NY01'
    };

    const satIDCheckboxes = document.getElementById('satIDCheckboxes');

    // Add a "select all" checkbox
    const selectAllCheckbox = document.createElement('input');
    selectAllCheckbox.type = 'checkbox';
    selectAllCheckbox.id = 'selectAll';
    selectAllCheckbox.name = 'selectAll';
    selectAllCheckbox.checked = true; // Default to checked

    const selectAllLabel = document.createElement('label');
    selectAllLabel.htmlFor = 'selectAll';
    selectAllLabel.textContent = 'Select All';

    satIDCheckboxes.appendChild(selectAllCheckbox);
    satIDCheckboxes.appendChild(selectAllLabel);

    for (let i = 1; i <= 14; i++) {
        // Skip checkboxes 8 through 13
        if (i >= 8 && i <= 13) {
            continue;
        }

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `satID_${i}`;
        checkbox.value = i;
        checkbox.name = 'satID';
        checkbox.checked = true; // Default to checked

        const label = document.createElement('label');
        label.htmlFor = `satID_${i}`;
        label.textContent = satIDMapping[i];

        satIDCheckboxes.appendChild(checkbox);
        satIDCheckboxes.appendChild(label);
    }

    // Set default start and end times
    const startInput = document.getElementById('start');
    const endInput = document.getElementById('end');

    const now = moment().tz('Asia/Shanghai');
    const startOfDay = now.clone().startOf('day');
    const formattedStart = startOfDay.format('YYYY-MM-DDTHH:mm');
    const formattedEnd = now.format('YYYY-MM-DDTHH:mm');

    startInput.value = formattedStart;
    endInput.value = formattedEnd;

    const submitButton = document.getElementById('submitButton');

    submitButton.addEventListener('click', (event) => {
        event.preventDefault(); // Prevent form submission

        const start = document.getElementById('start').value;
        const end = document.getElementById('end').value;
        const selectedSatIDs = Array.from(document.querySelectorAll('input[name="satID"]:checked')).map(cb => cb.value);
        const satID = selectedSatIDs.join(',');

        const requestData = {
            start: new Date(start).toISOString(),
            end: new Date(end).toISOString(),
            date: new Date().toISOString().split('T')[0],
            satID: satID
        };

        fetch(`${local_report_url}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(async (data) => {
            // Process data from the first API
            populateFlightControlTable(data.satellites);
            populateSubsystemTable(data.satellites);
            populateLevelDoughnutChart(data.satellites);
            plotCompanyChart(data.satellites);

            // Fetch data from the second API
            const trackQualityResponse = await fetch(`${local_trackquality_url}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            if (!trackQualityResponse.ok) {
                throw new Error(`Error: ${trackQualityResponse.status} ${trackQualityResponse.statusText}`);
            }
            const trackQualityData = await trackQualityResponse.json();
            plotHorizontalLines(trackQualityData.mission_quality);

            // Fetch data from the third API
            const cumulativeResetResponse = await fetch(`${local_reset_url}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            if (!cumulativeResetResponse.ok) {
                throw new Error(`Error: ${cumulativeResetResponse.status} ${cumulativeResetResponse.statusText}`);
            }
            const cumulativeResetData = await cumulativeResetResponse.json();
            plotCumulativeResetChart(cumulativeResetData);

             // Fetch data from the fire records API
            const fireRecordsResponse = await fetch(`${local_fire_records}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            if (!fireRecordsResponse.ok) {
                throw new Error(`Error: ${fireRecordsResponse.status} ${fireRecordsResponse.statusText}`);
            }

            const fireRecordsData = await fireRecordsResponse.json();

            // Now call plotSatellites with fireRecordsData
            plotSatellites(data, fireRecordsData.data.list);

            // Update the summary with both sets of data
            updateSummaryTextarea1(data, trackQualityData.mission_quality, fireRecordsData);

            // Fetch and display fire records
            populateFireRecordsTable(fireRecordsData.data.list); // Populate the fire records table

            // Fetch data from the gateway tasks API
            const gatewayTasksResponse = await fetch(`${local_gateway_task}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            if (!gatewayTasksResponse.ok) {
                throw new Error(`Error: ${gatewayTasksResponse.status} ${gatewayTasksResponse.statusText}`);
            }

            const gatewayTasksData = await gatewayTasksResponse.json();

            // Populate the gateway tasks table
            populateGatewayTasksTable(gatewayTasksData.data); // New function to populate the gateway tasks table
        })

        .catch(error => console.error('Error:', error));
    });

    function updateSummaryTextarea1(data, missionQuality, fireRecordsData) {
        const date = new Date().toISOString().split('T')[0];

        let telemetryZeroCount = 0;
            for (const missionId in missionQuality) {
                const mission = missionQuality[missionId];
                const telemetry = mission.telemetry;
                for (const key in telemetry) {
                    if (telemetry[key].start === 0 && telemetry[key].end === 0) {
                        telemetryZeroCount++;
                        break; // Assuming only one such telemetry per mission is needed
                    }
                }
            }

        let unstableMissionsCount = 0;
            for (const missionId in missionQuality) {
                const mission = missionQuality[missionId];
                if (Object.keys(mission.telemetry).length > 10 || Object.keys(mission.uplink).length > 10) {
                    unstableMissionsCount++;
                }
            }

        const vTransmissionsCount = data.satellites.reduce((count, satellite) => {
            return count + satellite.flightcontrol.filter(fc => fc.com_status === "通信+v数传").length;
        }, 0);

        let fileInspectStatus = data.satellites.every(satellite =>
            satellite.flightcontrol.every(fc => fc.fileinspect === "")
        ) ? "未执行文件巡检任务" : data.satellites.map(satellite => {
            const inspectTasks = satellite.flightcontrol.filter(fc => fc.fileinspect !== "").map(fc => fc.fileinspect);
            return inspectTasks.length > 0 ? `${satellite.satID}执行文件巡检任务，${inspectTasks.join(", ")}` : "";
        }).filter(Boolean).join("，");

        let summaryText = `今日(${date}) 小蜘蛛8星,总计跟踪 ${data.total_mission} 个轨次。`;
        summaryText += unstableMissionsCount === 0 ? "全部飞控任务执行正常。" : `其中${telemetryZeroCount}个轨次由于地面站原因跟踪失败。`;
        summaryText += `共上注${data.total_comtask_sent}个通信任务。`;
        summaryText += `执行v数传任务${vTransmissionsCount}次。${fileInspectStatus}。`;

        if (data.auto_anomal_mission === 0) {
            summaryText += "无复位切机异常。";
        } else {
            summaryText += "在轨复位切机情况如下：";
            data.satellites.forEach(satellite => {
                if (satellite.total_anomal_sum > 0) {
                    summaryText += ` ${satellite.satID} 出现复位切机 ${satellite.total_anomal_sum} 次。`;
                }
            });
        }

        summaryText += '\n';

        summaryText += ` 共计发令 ${data.total_command_sent} 条。`;

        let allUpdiffZero = data.satellites.every(satellite => satellite.updiff === 0);
        if (allUpdiffZero) {
            summaryText += "指令全部上星。";
        } else {
            summaryText += "指令相差情况如下：";
            data.satellites.forEach(satellite => {
                if (satellite.updiff !== 0) {
                    const updiffMissions = satellite.flightcontrol.filter(fc => fc.up !== 0 && fc.increase !== fc.up).length;
                    summaryText += ` ${satellite.satID} 共出现 ${updiffMissions} 轨，总计发令相差 ${satellite.updiff} 条。`;
                }
            });
        }

        summaryText += `\n`;


        summaryText += ` 跟踪质量：`;

        let hasUnstableMissions = false;

        data.satellites.forEach(satellite => {
            let telemetryUnstableCount = 0;
            let uplinkUnstableCount = 0;

            satellite.flightcontrol.forEach(fc => {
                const mission = missionQuality[fc.mission_id];
                if (mission) {
                    const telemetryCount = Object.keys(mission.telemetry).length;
                    const uplinkCount = Object.keys(mission.uplink).length;

                    if (telemetryCount > 5) {
                        telemetryUnstableCount++;
                    }
                    if (uplinkCount > 5) {
                        uplinkUnstableCount++;
                    }
                }
            });

            if (telemetryUnstableCount > 0) {
                summaryText += `${satellite.satID}今日共出现${telemetryUnstableCount}轨遥测不稳定轨次，`;
                hasUnstableMissions = true;
            }

            if (uplinkUnstableCount > 0) {
                summaryText += `${satellite.satID}今日共出现${uplinkUnstableCount}轨上行不稳定轨次，`;
                hasUnstableMissions = true;
            }
        });

        if (hasUnstableMissions) {
            summaryText += "其余轨次跟踪正常。\n";
        }

        const stateMapping = {
            1: '未开始',
            2: '正常结束',
            3: '异常结束',
            4: '取消',
            5: '控中',
            6: '未定',
            7: '已删除'
        };

        const periodDirectionMapping = {
            1: '升轨',
            2: '降轨',
            3: '请人工填写',
            4: '请人工填写',
            5: '请人工填写',
            6: '请人工填写',
            7: '请人工填写'
        };

        fireRecordsData.data.list.forEach(record => {
            const state = stateMapping[record.state] || '未知';
            const periodDirection = periodDirectionMapping[record.periodDirection] || '未知';
            const startTime = new Date(record.periodStartMs).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
            const duration = (record.periodEndMs - record.periodStartMs) / 1000;

            if (record.state === 1) {
                summaryText += `${record.spacecraftCode}出现新序列，${periodDirection}，起控时间 ${startTime}，时长 ${duration} 秒。`;
            } else if (record.state === 2) {
                summaryText += `${record.spacecraftCode}轨控正常结束，实际控制时长 ${record.thrusterTime} 秒。`;
            } else if (record.state === 3) {
                summaryText += `${record.spacecraftCode}轨控异常结束，实际控制时长 ${record.thrusterTime} 秒。`;
            }
        });

        const summaryTextarea1 = document.getElementById('summaryTextarea1');
        summaryTextarea1.innerText = summaryText;
    }


    function plotCumulativeResetChart(data) {
        const satCodes = data.map(d => d.sat_code);
        const previousCumulativeReset = data.map(d => d.previous_cumulative_reset);
        const todayCumulativeReset = data.map(d => d.today_cumulative_reset);
        const maxReset = data.map(d => d.max_reset);

        const rawData = [
            previousCumulativeReset,
            todayCumulativeReset,
            maxReset
        ];

        const totalData = [];
        for (let i = 0; i < rawData[0].length; ++i) {
            let sum = 0;
            for (let j = 0; j < rawData.length; ++j) {
                sum += rawData[j][i];
            }
            totalData.push(sum);
        }

        const series = ['累计复位次数', '今日新增复位次数', 'MAX'].map((name, sid) => {
            return {
                name: sid === 2 ? '' : name, // 将 MAX 系列的名称设置为空字符串，使其不出现在图例中
                type: 'bar',
                stack: 'total',
                barWidth: '60%',
                itemStyle: {
                    color: name === '累计复位次数' ? '#00DCDC' : (name === '今日新增复位次数' ? '#D64161FF' : 'lightgray')
                },
                label: {
                    show: sid !== 2,
                    formatter: (params) => {
                        // Check if the value is 0 and the series is '今日新增复位次数'
                        if (sid === 1 && params.value === 0) {
                            return '';
                        }
                        return Math.round(params.value);
                    }
                },
                data: rawData[sid]
            };
        });

        const option = {
            legend: {
                selectedMode: false
            },
            yAxis: {
                type: 'value',
                max: 8
            },
            xAxis: {
                type: 'category',
                data: satCodes,
                interval: 0,
                textStyle: {
                    fontSize: 2 // 您可以根据需要调整这个值
                },
                axisLabel: {
                    rotate: 60
                }
            },
            series
        };

        const chartDom = document.getElementById('cumulativeResetChart');
        const myChart = echarts.init(chartDom);
        myChart.setOption(option);
    }


    function plotSatellites(data, fireRecords) {
        const satelliteData = data.satellites;
        const phaseDiffData = data.phase_diff;

        const svgPaths = {
            default: "/static/svg/satellite-icon1.svg",
            state1Up: "/static/svg/satellite-icon1uparrowgreen.svg",
            state1Down: "/static/svg/satellite-icon1downarrowgreen.svg",
            state2Up: "/static/svg/satellite-icon1upallgreen.svg",
            state2Down: "/static/svg/satellite-icon1downallgreen.svg",
            state3Up: "/static/svg/satellite-icon1upallred.svg",
            state3Down: "/static/svg/satellite-icon1downallred.svg"
        };

        const container = document.getElementById('satelliteContainer');
        container.innerHTML = '';
        const names = ["GS-1a", "GS-2", "GS-2AP01", "GS-2AP02", "GS-2BP01", "GS-2AP03", "GS-2BP02", "GS-NY01"];

        const itemContainer = document.createElement('div');
        itemContainer.className = 'item-container';
        container.appendChild(itemContainer);

        const positions = [];

        names.forEach((name) => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'item-div';

            const nameDiv = document.createElement('div');
            nameDiv.textContent = name;
            nameDiv.className = 'name-div';

            const svgDiv = document.createElement('div');
            svgDiv.className = 'svg-div';

            // Find the latest fire record for the current satellite
            const latestFireRecord = fireRecords.reduce((latest, record) => {
                if (record.spacecraftCode === name && (!latest || record.periodStartMs > latest.periodStartMs)) {
                    return record;
                }
                return latest;
            }, null);

            // Determine the SVG path based on the latest fire record
            let svgPath = svgPaths.default;
            if (latestFireRecord) {
                const { state, periodDirection } = latestFireRecord;
                if (state === 1) {
                    svgPath = periodDirection === 1 ? svgPaths.state1Up : svgPaths.state1Down;
                } else if (state === 2) {
                    svgPath = periodDirection === 1 ? svgPaths.state2Up : svgPaths.state2Down;
                } else if (state === 3) {
                    svgPath = periodDirection === 1 ? svgPaths.state3Up : svgPaths.state3Down;
                }
            }

            svgDiv.innerHTML = `<img src="${svgPath}" alt="Satellite">`;
            itemDiv.appendChild(nameDiv);
            itemDiv.appendChild(svgDiv);

            const satellite = satelliteData.find(sat => sat.satID === name);
            if (satellite && satellite.orbit && satellite.orbit.h) {
                const altDiv = document.createElement('div');
                altDiv.textContent = `${satellite.orbit.h.alt.toFixed(3)} km`;
                altDiv.className = 'alt-div';
                itemDiv.appendChild(altDiv);
            }

            itemContainer.appendChild(itemDiv);
            positions.push(itemDiv);
        });

        const phaseTable = document.createElement('table');
        phaseTable.className = 'phase-table';
        const tableHeader = `
            <thead>
                <tr>
                    <th>卫星代号</th>
                    <th>星间相位(°)</th>
                </tr>
            </thead>
        `;
        phaseTable.innerHTML = tableHeader;
        const tableBody = document.createElement('tbody');

        phaseDiffData.forEach(diff => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${diff._satelliteCode}</td>
                <td>${diff.phase_diff.toFixed(2)}</td>
            `;
            tableBody.appendChild(row);
        });

        phaseTable.appendChild(tableBody);
        container.appendChild(phaseTable);
    }




    function populateFlightControlTable(satellites) {
        const flightControlTableBody = document.getElementById('flightControlTable').getElementsByTagName('tbody')[0];
        flightControlTableBody.innerHTML = '';

        satellites.forEach(satellite => {
            const tasks = satellite.flightcontrol;
            const totalRows = tasks.length * 2; // Each mission has a corresponding line row

            tasks.forEach((task, index) => {
                const row = flightControlTableBody.insertRow();
                row.setAttribute('data-mission-id', task['mission_id']); // Add data-mission-id attribute

                // Process the task for starting time and up/increase combination
                let processedTask = { ...task };
                if (processedTask.starting) {
                    processedTask.starting = processedTask.starting.replace(' CST+0800', '');
                }
                if (processedTask.up !== undefined && processedTask.increase !== undefined) {
                    processedTask['up/increase'] = `${processedTask.up}/${processedTask.increase}`;
                    delete processedTask.up;
                    delete processedTask.increase;
                }

                // Define the order of keys to ensure the correct column order
                const keysInOrder = [
                    'satellite_code',
                    'remark',
                    'starting',
                    'station_name',
                    'up/increase',
                    'com_status',
                    'fileinspect',
                    'anomal'
                ];

                keysInOrder.forEach(key => {
                    const cell = row.insertCell();
                    cell.textContent = processedTask[key] !== undefined ? processedTask[key] : '';
                });

                // Add a new row for the plot container
                const plotRow = flightControlTableBody.insertRow();
                const plotCell = plotRow.insertCell();
                plotCell.colSpan = keysInOrder.length; // Span all columns
                plotCell.innerHTML = `<div id="id_${task['mission_id']}-chart1" class="chart-container"></div>`;
            });
        });
    }



    function populateSubsystemTable(satellites) {
        // console.log('Populating subsystem table...');
        const subsystemTableBody = document.getElementById('subsystemTable').querySelector('tbody');
        subsystemTableBody.innerHTML = ''; // Clear previous data

        const rows = [];

        satellites.forEach(satellite => {
            const subsystems = satellite.subsystem;

            if (Object.keys(subsystems).length === 0) {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${satellite.satID}</td>
                    <td>-</td>
                    <td>0</td>
                    <td><div id="chart_${satellite.satID}_empty" class="chart-container"></div></td>
                `;
                rows.push(row);
            } else {
                for (let subsystem in subsystems) {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${satellite.satID}</td>
                        <td>${subsystem}</td>
                        <td>${subsystems[subsystem].count}</td>
                        <td><div id="chart_${satellite.satID}_${subsystem}" class="chart-container"></div></td>
                    `;
                    rows.push(row);
                }
            }
        });

        let prevSatID = '';
        let rowspanCount = 0;
        let firstCell = null;

        rows.forEach((row, index) => {
            const currentSatID = row.children[0].textContent;

            if (prevSatID !== currentSatID) {
                if (firstCell) {
                    firstCell.rowSpan = rowspanCount;
                }
                prevSatID = currentSatID;
                rowspanCount = 1;
                firstCell = row.children[0];
            } else {
                rowspanCount++;
                row.children[0].style.display = 'none';
            }

            subsystemTableBody.appendChild(row);

            if (index === rows.length - 1 && firstCell) {
                firstCell.rowSpan = rowspanCount;
            }
        });
    }

    function populateLevelDoughnutChart(satellites) {
        // console.log('Populating doughnut chart...');

        satellites.forEach(satellite => {
            const levels = satellite.level;

            if (Object.keys(levels).length === 0) {
                return; // Skip rendering if no level data exists
            }

            for (let subsystem in levels) {
                const levelData = levels[subsystem];
                const chartId = `chart_${satellite.satID}_${subsystem}`;
                // console.log("Chart ID:", chartId);

                const chartContainer = document.getElementById(chartId);
                if (!chartContainer) {
                    console.error(`Chart container with ID ${chartId} not found`);
                    continue;
                }

                const chart = echarts.init(chartContainer);

                const data = Array.isArray(levelData) ? levelData : [
                    { value: levelData.FATAL, name: 'FATAL', itemStyle: { color: '#cd0020' } },
                    { value: levelData.CRITICAL, name: 'CRITICAL', itemStyle: { color: '#f83800' } },
                    { value: levelData.WARNING, name: 'WARNING', itemStyle: { color: '#f8b800' } },
                    { value: levelData.INFO, name: 'INFO', itemStyle: { color: '#00a800' } }
                ];

                const options = {
                    tooltip: {
                        trigger: 'item'
                    },
                    series: [{
                        name: '',
                        type: 'pie',
                        radius: ['60%', '100%'],
                        avoidLabelOverlap: false,
                        itemStyle: {
                            borderRadius: 1,
                            borderColor: 'black',
                            borderWidth: 0
                        },
                        label: {
                            show: false,
                            position: 'center'
                        },
                        emphasis: {
                            label: {
                                show: false,
                                fontSize: '10',
                                fontWeight: 'bold'
                            }
                        },
                        labelLine: {
                            show: false
                        },
                        data: data
                    }]
                };

                chart.setOption(options);
            }
        });
    }




    function plotHorizontalLines(missionQuality) {
        const rows = Object.values(missionQuality);

        rows.forEach(mission => {
            const missionId = `id_${mission.mission_id}`;
            const missionDiv = d3.select(`#${missionId }-chart1`)
                .style("position", "relative")
                .append("div")
                .attr("class", "plot-container");

            const width = 550;
            const height = 20;
            const margin = { left: 10, right: 10 };

            const svg = missionDiv.append("svg")
                .attr("width", width)
                .attr("height", height);

            const xScale = d3.scaleTime()
                .domain([new Date(mission.starting), new Date(mission.ending)])
                .range([margin.left, width - margin.right]);

            svg.append("line")
                .attr("x1", xScale(new Date(mission.starting)))
                .attr("x2", xScale(new Date(mission.ending)))
                .attr("y1", height / 2)
                .attr("y2", height / 2)
                .attr("stroke", "grey")
                .attr("stroke-width", 4);

            Object.values(mission.telemetry).forEach(d => {
                svg.append("line")
                    .attr("x1", xScale(new Date(d.start)))
                    .attr("x2", xScale(new Date(d.end)))
                    .attr("y1", height / 2)
                    .attr("y2", height / 2)
                    .attr("stroke", "red")
                    .attr("stroke-width", 4)
                    .on("mouseover", function(event) {
                        d3.select(".tooltip").transition().duration(200).style("opacity", .9);
                        d3.select(".tooltip").html(`Telemetry Start: ${new Date(d.start).toLocaleString()}<br/>Telemetry End: ${new Date(d.end).toLocaleString()}`)
                            .style("left", (event.pageX) + "px")
                            .style("top", (event.pageY - 28) + "px");
                    })
                    .on("mouseout", function() {
                        d3.select(".tooltip").transition().duration(500).style("opacity", 0);
                    });
            });

            Object.values(mission.uplink).forEach(d => {
                svg.append("line")
                    .attr("x1", xScale(new Date(d.start)))
                    .attr("x2", xScale(new Date(d.end)))
                    .attr("y1", height / 2)
                    .attr("y2", height / 2)
                    .attr("stroke", "#00b800")
                    .attr("stroke-width", 4)
                    .on("mouseover", function(event) {
                        d3.select(".tooltip").transition().duration(200).style("opacity", .9);
                        d3.select(".tooltip").html(`Uplink Start: ${new Date(d.start).toLocaleString()}<br/>Uplink End: ${new Date(d.end).toLocaleString()}`)
                            .style("left", (event.pageX) + "px")
                            .style("top", (event.pageY - 28) + "px");
                    })
                    .on("mouseout", function() {
                        d3.select(".tooltip").transition().duration(500).style("opacity", 0);
                    });
            });
        });
    }

    function plotCompanyChart(data) {
        const companyCount = {};

        data.forEach(satellite => {
            satellite.flightcontrol.forEach(control => {
                const companyName = control.company_name;
                if (companyCount[companyName]) {
                    companyCount[companyName]++;
                } else {
                    companyCount[companyName] = 1;
                }
            });
        });

        const chartData = Object.keys(companyCount).map(companyName => ({
            value: companyCount[companyName],
            name: companyName
        }));

        const chart = echarts.init(document.getElementById('companyChart'));
        const option = {
            title: {
                text: '测站公司统计',
                left: 'left'
            },
            tooltip: {
                trigger: 'item',
                formatter: '{a} <br/>{b}: {c} ({d}%)'
            },
            legend: {
                orient: 'vertical',
                left: 'right'
            },
            series: [{
                name: '供应商',
                type: 'pie',
                radius: ['40%', '65%'], // 环状图的内外半径
                data: chartData,
                label: {
                    show: true, // 显示标签
                    position: 'inside', // 标签显示在环内
                    formatter: '{b}: {c}' // 格式化标签显示内容
                },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: '10',
                        fontWeight: 'bold'
                    }
                }
            }]
        };

        chart.setOption(option);
    }


    // Function to populate the fire records table
    function populateFireRecordsTable(fireRecords) {
        const fireRecordsTableContainer = document.getElementById('fireRecordsTableContainer');
        fireRecordsTableContainer.innerHTML = ''; // Clear any existing content

        const table = document.createElement('table');
        table.classList.add('fire-records-table');

        // Create table header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');

        const headers = ['卫星代号', '轨控区间', '实际控制时长', '完成状态', '方向'];
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });

        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create table body
        const tbody = document.createElement('tbody');

        fireRecords.forEach(record => {
            const row = document.createElement('tr');

            const spacecraftCodeCell = document.createElement('td');
            spacecraftCodeCell.textContent = record.spacecraftCode;
            row.appendChild(spacecraftCodeCell);

            const periodCell = document.createElement('td');
            const periodStart = moment(record.periodStartMs).tz('Asia/Shanghai').format('YYYY-MM-DD HH:mm:ss');
            const periodEnd = moment(record.periodEndMs).tz('Asia/Shanghai').format('YYYY-MM-DD HH:mm:ss');
            periodCell.textContent = `${periodStart} - ${periodEnd}`;
            row.appendChild(periodCell);

            const thrusterTimeCell = document.createElement('td');
            thrusterTimeCell.textContent = record.thrusterTime;
            row.appendChild(thrusterTimeCell);

            const stateCell = document.createElement('td');
            const stateMapping = {
                1: '未开始',
                2: '正常结束',
                3: '异常结束',
                4: '取消',
                5: '控中',
                6: '未定',
                7: '已删除'
            };
            stateCell.textContent = stateMapping[record.state] || record.state;
            row.appendChild(stateCell);

            // Add control direction column
            const controlDirectionCell = document.createElement('td');
            const directionMapping = {
                1: '+X',
                2: '-X'
            };
            controlDirectionCell.textContent = directionMapping[record.periodDirection] || '转移';
            row.appendChild(controlDirectionCell);

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        fireRecordsTableContainer.appendChild(table);
    }


    function populateGatewayTasksTable(tasks) {
        const tableContainer = document.getElementById('gatewayTasksTableContainer');
        tableContainer.innerHTML = ''; // Clear any existing content

        const table = document.createElement('table');
        table.classList.add('gateway-tasks-table');

        // Create table header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');

        const headers = ['卫星代号', '信关站址', '任务时间', '模式', '波束', '申请方'];
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });

        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create table body
        const tbody = document.createElement('tbody');

        const modeMapping = {
            1: '平飞',
            2: '凝视'
        };

        const systemMapping = {
            'ttnonc': '银河测运控',
            'yhcom': '银河中心站控'
        };

        tasks.forEach(task => {
            const row = document.createElement('tr');

            const spacecraftCodeCell = document.createElement('td');
            spacecraftCodeCell.textContent = task.spacecraft.code;
            row.appendChild(spacecraftCodeCell);

            const stationNameCell = document.createElement('td');
            stationNameCell.textContent = task.antenna.name;
            row.appendChild(stationNameCell);

            const taskTimeCell = document.createElement('td');
            const startAt = moment(task.startAt).tz('Asia/Shanghai').format('YYYY-MM-DD HH:mm:ss');
            const endAt = moment(task.endAt).tz('Asia/Shanghai').format('YYYY-MM-DD HH:mm:ss');
            taskTimeCell.textContent = `${startAt} - ${endAt}`;
            row.appendChild(taskTimeCell);

            const modeCell = document.createElement('td');
            modeCell.textContent = modeMapping[task.communicationParam.flightAttitude] || task.communicationParam.flightAttitude;
            row.appendChild(modeCell);

            const beamCell = document.createElement('td');
            beamCell.textContent = parseInt(task.communicationParam.beamNumber) + 1;
            row.appendChild(beamCell);

            const systemCell = document.createElement('td');
            systemCell.textContent = systemMapping[task.belongedSystem] || task.belongedSystem;
            row.appendChild(systemCell);

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        tableContainer.appendChild(table);
    }

    document.getElementById('snapshotButton').addEventListener('click', function() {
        // Get all buttons and the form
        const elementsToHide = document.querySelectorAll('form#dataForm, button');

        // Hide all targeted elements
        elementsToHide.forEach(element => element.style.display = 'none');

        // Take the screenshot
        html2canvas(document.body).then(canvas => {
            // Restore the visibility of the targeted elements
            elementsToHide.forEach(element => element.style.display = '');

            // Create a link to download the screenshot
            const link = document.createElement('a');
            link.href = canvas.toDataURL();
            link.download = 'screenshot.png';
            link.click();
        });
    });

});
