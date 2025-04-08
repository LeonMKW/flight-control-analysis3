document.addEventListener('DOMContentLoaded', () => {
        // Get the width of the screen
    const screenWidth = window.innerWidth;

    // Print the width to the console
    // console.log('Screen width:', screenWidth);

    // Set the current date
    const currentDateElement = document.getElementById('createDate');
    const createDate = moment().format('YYYY-MM-DD'); // Format the date as needed
    currentDateElement.textContent = createDate;

    const local_report_url = `${location.origin}/spiderlingdailyreport`;
    const local_flight_controller = `${location.origin}/get-flight-controller`;
    const local_trackquality_url = `${location.origin}/trackquality`;
    const local_reset_url = `${location.origin}/cumulative-reset`;
    const local_fire_records = `${location.origin}/fire-records`;
    const local_gateway_task = `${location.origin}/gateway-task`;
    const local_alerts =  `${location.origin}/get-all-alerts`; //new fetch
    const local_space_weather_enviroment =  `${location.origin}/space-environment-info-with-summary-from-odpa`; //new fetch
    const currentDate = new Date();
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    const formattedDate = currentDate.toLocaleDateString('zh-CN', options);
    document.getElementById('currentDate').textContent = `(${formattedDate})`;
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
    // selectAllCheckbox.id = 'selectAll';
    // selectAllCheckbox.name = 'selectAll';
    selectAllCheckbox.checked = true; // Default to checked

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

        // Define fetchWithAlert function
    async function fetchWithAlert(url, options) {
        try {
            const response = await fetch(url, options);

            if (!response.ok) {
                const errorData = await response.json();
                alert(`Error: ${errorData.Error}`);
                return null;
            }

            return await response.json();
        } catch (error) {
            console.error('Error:', error);
            alert('An unexpected error occurred.');
            return null;
        }
    }

    // adding submit buttion click event

    const submitButton = document.getElementById('submitButton');

    submitButton.addEventListener('click', async(event) => {
        event.preventDefault();

        const start = document.getElementById('start').value;
        const end = document.getElementById('end').value;

        // Parse the input values into moment objects with the correct timezone
        const startMoment = moment.tz(start, 'YYYY-MM-DDTHH:mm', 'Asia/Shanghai');
        const endMoment = moment.tz(end, 'YYYY-MM-DDTHH:mm', 'Asia/Shanghai');

        const selectedSatIDs = Array.from(document.querySelectorAll('input[name="satID"]:checked')).map(cb => cb.value);
        const satID = selectedSatIDs.join(',');

        const requestData = {
            start: new Date(start).toISOString(),
            end: new Date(end).toISOString(),
            date: new Date().toISOString().split('T')[0],
            satID: satID
        };

        // Format `startAt` and `endAt` in ISO 8601 format
        const controller_startAt = startMoment.toISOString();
        const controller_endAt = endMoment.toISOString();

        // Set `satelliteIDs` to an array containing only "1"
        const flight_controller_satelliteIDs = ["1"];
        // Prepare the requestData object
        const controller_requestData = {
            startAt: controller_startAt,
            endAt: controller_endAt,
            satelliteIDs: flight_controller_satelliteIDs
        };
        // console.log(controller_requestData)

        // Make the request to your server
        const flightControllerData = await fetchWithAlert(local_flight_controller, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(controller_requestData)
            });


        if (flightControllerData) {
            // Update the textarea with the flight controller's names
            displayFlightControllers(flightControllerData);

            // Update "制作人" and "修订人" with the first flight controller's name
            // or any logic you prefer (e.g., different names)
            updateProducerAndReviser(flightControllerData);
        } else {
            // Handle the case where no data is returned
            document.getElementById('producerName').textContent = '未知';
            document.getElementById('reviserName').textContent = '未知';
        }

        const loaderOverlay = document.getElementById('loaderOverlay');
        loaderOverlay.style.display = 'flex'; // Show loader

        try {
            // ✅ Pass `start` and `end` to fetchSpaceWeatherData()
            const spaceWeatherData = await fetchSpaceWeatherData(start, end);
            console.log("Space Weather Data:", spaceWeatherData); // Debugging

            // Fetch data from the first API
            const data = await fetchWithAlert(`${local_report_url}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            if (data) {
                // console.log('Success:', data);
                populateFlightControlTable(data.satellites);
                populateSubsystemTable(data.satellites);
                populateLevelDoughnutChart(data.satellites);
                plotCompanyChart(data.satellites);
            }

        // Process data from the first API
        populateFlightControlTable(data.satellites);
        populateSubsystemTable(data.satellites);
        populateLevelDoughnutChart(data.satellites);
        plotCompanyChart(data.satellites);

        // Fetch data from the second API
        const trackQualityData = await fetchWithAlert(`${local_trackquality_url}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });

        if (trackQualityData) {
            plotHorizontalLines(trackQualityData.mission_quality);
        }

        // Fetch data from the third API
        const cumulativeResetData = await fetchWithAlert(`${local_reset_url}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });

        if (cumulativeResetData) {
            plotCumulativeResetChart(cumulativeResetData);
        }
        plotCumulativeResetChart(cumulativeResetData);

        // Fetch data from the fire records API
        const fireRecordsData = await fetchWithAlert(`${local_fire_records}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });

        if (fireRecordsData) {
            plotSatellites(data, fireRecordsData.data.list);
            updateSummaryTextarea1(data, trackQualityData.mission_quality, fireRecordsData,spaceWeatherData);
            populateFireRecordsTable(fireRecordsData.data.list);
        }

        // Now call plotSatellites with fireRecordsData
        plotSatellites(data, fireRecordsData.data.list);

        // Update the summary with both sets of data
        updateSummaryTextarea1(data, trackQualityData.mission_quality, fireRecordsData,spaceWeatherData);

        // Fetch and display fire records
        populateFireRecordsTable(fireRecordsData.data.list); // Populate the fire records table

        // Fetch data from the gateway tasks API
        const gatewayTasksData = await fetchWithAlert(`${local_gateway_task}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });

        if (gatewayTasksData) {
            populateGatewayTasksTable(gatewayTasksData.data.fca);
        }

        // Populate the gateway tasks table
        populateGatewayTasksTable(gatewayTasksData.data.fca); // New function to populate the gateway tasks table


        //fetch data from alerts API
        const alertsresponse = await fetch(local_alerts, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

        if (!alertsresponse.ok) {
            throw new Error(`Error: ${alertsresponse.status} ${alertsresponse.statusText}`);
        }

         const alertData = await alertsresponse.json();
        populateAlertTable(alertData);

    } catch (error) {
        console.error('Error:', error);
    } finally {
        loaderOverlay.style.display = 'none'; // Hide loader
    }
});

    function displayFlightControllers(caretakers) {
        const textAreaNameElement = document.getElementById('textareaname');
        if (caretakers.length > 0) {
            // Join the caretaker names into a string
            const caretakersList = caretakers.join(', ');
            textAreaNameElement.value = `飞控值班人: ${caretakersList}`;
        } else {
            textAreaNameElement.value = '飞控值班人: 测运控AI';
        }
    }
            // Function to update "制作人" and "修订人"
    function updateProducerAndReviser(caretakers) {
        const producerElement = document.getElementById('producerName');
        const reviserElement = document.getElementById('reviserName');

        if (caretakers.length > 0) {
            // For example, set the first caretaker as the producer and the second as the reviser
            producerElement.textContent = caretakers[0];
            reviserElement.textContent = caretakers[1] || caretakers[0]; // Use first if second is not available
        } else {
            producerElement.textContent = '未知';
            reviserElement.textContent = '未知';
        }
    }

    async function fetchSpaceWeatherData(start, end) {
        const requestSpaceweatherData = {
            start: new Date(start).toISOString(),
            end: new Date(end).toISOString()
        };

        try {
            const response = await fetch(local_space_weather_enviroment, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(requestSpaceweatherData)  // ✅ Now correctly defined inside the function
            });

            if (!response.ok) {
                console.error("Failed to fetch space weather data");
                return null;
            }

            const data = await response.json();
            return data.message.space_env_data;  // Extract relevant data
        } catch (error) {
            console.error("Error fetching space weather data:", error);
            return null;
        }
    }


    // Update Summary with Space Weather Data
    async function updateSummaryTextarea1(data, missionQuality, fireRecordsData, spaceWeatherData) {
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
        ) ? "" : data.satellites.map(satellite => {
            const inspectTasks = satellite.flightcontrol.filter(fc => fc.fileinspect !== "").map(fc => fc.fileinspect);
            return inspectTasks.length > 0 ? `${satellite.satID}执行文件巡检任务，${inspectTasks.join(", ")}` : "";
        }).filter(Boolean).join("，");

        let summaryText = `    今日小蜘蛛8星，总计跟踪 ${data.total_mission} 个轨次。`;
        summaryText += unstableMissionsCount === 0 ? "全部飞控任务执行正常。" :
            (telemetryZeroCount === 0 ? "地面站全部跟踪正常。" : `其中${telemetryZeroCount}个轨次由于地面站原因跟踪失败。`);
        summaryText += `共上注 ${data.total_comtask_sent} 个通信任务。`;
        summaryText += vTransmissionsCount === 0 ? "无 v 数传任务。" : `执行 v 数传任务 ${vTransmissionsCount} 次。`;
        if (fileInspectStatus !== "") {
            summaryText += `${fileInspectStatus}`;
        }

        if (data.auto_anomal_mission === 0) {
            summaryText += "无FATAL（致命）级别异常。";
        } else {
            data.satellites.forEach(satellite => {
                if (satellite.total_anomal_sum > 0) {
                    summaryText += ` ${satellite.satID} 出现复位/切机 ${satellite.total_anomal_sum} 次。`;
                }
            });
        }

        summaryText += '\n';

        summaryText += `    共计发令 ${data.total_command_sent} 条。`;

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

            const totalUnstableCount = Math.min(satellite.flightcontrol.length, telemetryUnstableCount + uplinkUnstableCount);

            if (totalUnstableCount > 0) {
                summaryText += `${satellite.satID}今日共出现${totalUnstableCount}轨跟踪不稳定轨次，`;
                hasUnstableMissions = true;
            }
        });

        if (!hasUnstableMissions) {
            summaryText += "今日全部轨次跟踪正常。";
        } else {
            summaryText += "其余轨次跟踪正常。";
        }

        summaryText += '\n    ';

        const stateMapping = {
            0: '已创建',
            1: '未确定',
            2: '正常结束',
            3: '异常结束',
            4: '已取消',
            5: '已删除'
        };

        const periodDirectionMapping = {
            0: '升轨',
            1: '降轨',
            2: '+Y方向',
            3: '-Y方向',
            4: '+Z方向',
            5: '-Z方向',
            6: '飘飞'
        };

        fireRecordsData.data.list.forEach(record => {
            const state = stateMapping[record.state] || '未知';
            const periodDirection = periodDirectionMapping[record.direction] || '未知';
            const startTime = new Date(record.beginTime).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
            const duration = (record.endTime - record.beginTime) / 1000;

            if (record.state === 1) {
                summaryText += `${record.spacecraftCode}出现新序列，${periodDirection}，起控时间 ${startTime}，时长 ${duration} 秒。`;
            } else if (record.state === 2) {
                summaryText += `${record.spacecraftCode}轨控正常结束，实际控制时长 ${duration} 秒。`;
            } else if (record.state === 3) {
                summaryText += `${record.spacecraftCode}轨控异常结束，实际控制时长 ${duration} 秒。`;
            }
        });

       summaryText += '\n    ';

        if (spaceWeatherData) {
          // Past 12-hour summary
          summaryText += ` 今日${spaceWeatherData.past12hoursF107}。${spaceWeatherData.past12hoursAp}，${spaceWeatherData.past12hoursKp}。\n`;

          // Future 12-hour forecast
          summaryText += ` 未来12小时${spaceWeatherData.future12hoursAp}，${spaceWeatherData.future12hoursF107}。\n`;
        }


        // Update the summary textarea
        const summaryTextarea1 = document.getElementById("summaryTextarea1");
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

        const series = ['距上次切机复位次数', '今日新增复位次数', 'MAX'].map((name, sid) => {
            return {
                name: sid === 2 ? '' : name, // 将 MAX 系列的名称设置为空字符串，使其不出现在图例中
                type: 'bar',
                stack: 'total',
                barWidth: '60%',
                itemStyle: {
                    color: name === '距上次切机复位次数' ? '#00dcc2' : (name === '今日新增复位次数' ? '#b83f3f' : 'lightgray')
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
            height: "80%",
            legend: [{
                x: 'left',
                y: '3%',
                data: ["距上次切机复位次数"],
                selectedMode: false,
                textStyle: {
                    fontSize: 32
                },
            },
                {
                x: 'left',
                y: '10%',
                data: ["今日新增复位次数"],
                bottom: "50",
                selectedMode: false,
                textStyle: {
                fontSize: 32,
                    }
             }],
            yAxis: {
                type: 'value',
                max: 8,
                axisLabel: {
                    textStyle: {
                        fontSize: 32
                    }
                },
            },
            xAxis: {
                type: 'category',
                data: satCodes,
                interval: 0,
                axisLabel: {
                    rotate: 60,
                    textStyle: {
                        fontSize: 28
                    }
                }
            },
            grid: {
                top:"20%",
                left:"0%",
                right:"0%",
                bottom:"0%",
                containLabel: true
            },
            label: {
                fontSize: 34
            },
            series
        };

        const chartDom = document.getElementById('cumulativeResetChart');
        const myChart = echarts.init(chartDom);
        myChart.setOption(option);
    }


    function plotSatellites(data, fireRecords) {
        const satelliteData = data.satellites;
        // console.log(satelliteData);
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

        const satelliteContainer = document.getElementById('satelliteContainer');
        satelliteContainer.innerHTML = '';
        const names = ["GS-1a", "GS-2", "GS-2AP01", "GS-2AP02", "GS-2BP01", "GS-2AP03", "GS-2BP02", "GS-NY01"];

        const itemContainer = document.createElement('div');
        itemContainer.className = 'item-container';
        satelliteContainer.appendChild(itemContainer);

        // Collect altitudes for the specified satellites
        const altitudes = names.map(name => {
            const satellite = satelliteData.find(sat => sat.satID === name);
            return satellite && satellite.orbit && satellite.orbit.h ? satellite.orbit.h.alt : null;
        }).filter(alt => alt !== null).sort((a, b) => a - b);

        names.forEach((name) => {
            const itemDiv = document.createElement('div');
            itemDiv.className = 'item-div';

            const nameDiv = document.createElement('div');
            nameDiv.textContent = name;
            nameDiv.className = 'name-div';

            const svgDiv = document.createElement('div');
            svgDiv.className = 'svg-div';

            const miniNameDiv = document.createElement('div');
            miniNameDiv.textContent = name;
            miniNameDiv.className = 'mini-name-div';
            // miniNameDiv.style.fontSize = '0.8rem'; // Adjust font size for mini name

            const latestFireRecord = fireRecords.reduce((latest, record) => {
                if (record.spacecraftCode === name && (!latest || record.periodStartMs > latest.periodStartMs)) {
                    return record;
                }
                return latest;
            }, null);

            let svgPath = svgPaths.default;
            if (latestFireRecord) {
                const { state, direction } = latestFireRecord;
                if (state === 1) {
                    svgPath = direction === 0 ? svgPaths.state1Up : svgPaths.state1Down;
                } else if (state === 2) {
                    svgPath = direction === 0 ? svgPaths.state2Up : svgPaths.state2Down;
                } else if (state === 3) {
                    svgPath = direction === 0 ? svgPaths.state3Up : svgPaths.state3Down;
                }
            }

            svgDiv.innerHTML = `<img src="${svgPath}" alt="Satellite">`;
            svgDiv.appendChild(miniNameDiv); // Append mini name-div inside svg-div

            itemDiv.appendChild(svgDiv);
            itemDiv.appendChild(nameDiv); // Append nameDiv last

            const satellite = satelliteData.filter(sat => !["GS-1a", "GS-NY01", "GS-2BP02"].includes(sat.satID)).find(sat => sat.satID === name);
            const satellitefixed = satelliteData.filter(sat => ["GS-1a", "GS-NY01", "GS-2BP02"].includes(sat.satID)).find(sat => sat.satID === name);

            // Create altDiv for both satellite and satellitefixed
            const createAltDiv = (satellite) => {
                if (satellite && satellite.orbit && satellite.orbit.h) {
                    const altDiv = document.createElement('div');
                    altDiv.textContent = `${satellite.orbit.h.alt.toFixed(3)} km`;
                    altDiv.className = 'alt-div';
                    itemDiv.appendChild(altDiv); // Append altDiv

                    // Adjust svgDiv margins based on altitude ranking for non-fixed satellites
                    if (!["GS-1a", "GS-NY01", "GS-2BP02"].includes(name)) {
                        const altIndex = altitudes.indexOf(satellite.orbit.h.alt);
                        const altMargins = [
                            { marginTop: '6.5rem', marginBottom: '3.5rem' },
                            { marginTop: '6rem', marginBottom: '4rem' },
                            { marginTop: '5.5rem', marginBottom: '4.5rem' },
                            { marginTop: '5rem', marginBottom: '5rem' },
                            { marginTop: '4.5rem', marginBottom: '5.5rem' }
                        ];

                        if (altIndex >= 0 && altIndex < altMargins.length + 1) {
                            svgDiv.style.marginTop = altMargins[altIndex - 1].marginTop;
                            svgDiv.style.marginBottom = altMargins[altIndex - 1].marginBottom;
                        }
                    }
                }
            };

            createAltDiv(satellite);
            createAltDiv(satellitefixed);


            // Special cases for specific satellites
            if (satellitefixed) {
                if (name === 'GS-1a') {
                    svgDiv.style.marginTop = '3rem';
                    svgDiv.style.marginBottom = '7rem';
                } else if (name === 'GS-2BP02') {
                    svgDiv.style.marginTop = '0rem';
                    svgDiv.style.marginBottom = '10rem';
                } else if (name === 'GS-NY01') {
                    svgDiv.style.marginTop = '10rem';
                    svgDiv.style.marginBottom = '0rem';
                }
            }

            itemDiv.appendChild(nameDiv);  // Append nameDiv last

            itemContainer.appendChild(itemDiv);
        });

        // Add dashed line across the arc-container
        const dashedLine = document.createElement('div');
        dashedLine.className = 'dashed-line';
        satelliteContainer.appendChild(dashedLine);

        // Clearfix to ensure no overlap
        const clearfix = document.createElement('div');
        clearfix.style.clear = 'both';
        satelliteContainer.appendChild(clearfix);

        function plotSatellitesInArc(satelliteNames, phaseDiffData) {
            // Get the dimensions of the SVG container
            const svgContainer = document.getElementById('svgContainer');
            const svgWidth = svgContainer.clientWidth;
            const svgHeight = svgContainer.clientHeight;

            // Calculate the center of the SVG container
            const centerX = svgWidth / 2;
            const centerY = svgHeight / 2 + 120;

            // Set radii proportional to the container size
            const radiusX = (svgWidth - 80) * 0.4; // 40% of the width
            const radiusY = svgHeight * 0.3; // 20% of the height

            const angleIncrement = Math.PI / (satelliteNames.length - 1); // angle between satellites
            // console.log(angleIncrement)

            // Clear previous SVG content
            while (svgContainer.firstChild) {
                svgContainer.removeChild(svgContainer.firstChild);
            }

            // Create and append the arc path (Earth's surface)
            const arcPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
            const startX = centerX - radiusX ;
            const startY = centerY ;
            const endX = centerX + radiusX;
            const endY = centerY;
            const arcD = `M ${startX} ${startY} A ${radiusX} ${radiusY} 0 0 1 ${endX} ${endY}`;
            arcPath.setAttribute("d", arcD);
            arcPath.setAttribute("stroke", "black");
            arcPath.setAttribute("stroke-width", "2");
            arcPath.setAttribute("fill", "none");
            svgContainer.appendChild(arcPath);

            satelliteNames.forEach((name, index) => {
                const angle = index * angleIncrement; // calculate the angle for the current satellite
                // console.log(angle)
                const x = centerX + radiusX * Math.cos(angle); // x coordinate of the satellite
                const y = centerY - radiusY * Math.sin(angle); // y coordinate of the satellite

                const satelliteSvg = document.createElementNS("http://www.w3.org/2000/svg", "image");
                satelliteSvg.setAttributeNS(null, 'href', "data:image/svg+xml;base64,PCFET0NUWVBFIHN2ZyBQVUJMSUMgIi0vL1czQy8vRFREIFNWRyAxLjEvL0VOIiAiaHR0cDovL3d3dy53My5vcmcvR3JhcGhpY3MvU1ZHLzEuMS9EVEQvc3ZnMTEuZHRkIj4KDTwhLS0gVXBsb2FkZWQgdG86IFNWRyBSZXBvLCB3d3cuc3ZncmVwby5jb20sIFRyYW5zZm9ybWVkIGJ5OiBTVkcgUmVwbyBNaXhlciBUb29scyAtLT4KPHN2ZyB3aWR0aD0iODAwcHgiIGhlaWdodD0iODAwcHgiIHZpZXdCb3g9IjAgMCAyNCAyNCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiBmaWxsPSIjMDAwMDAwIiBzdHJva2U9IiMwMDAwMDAiIHN0cm9rZS13aWR0aD0iMC4wMDAyNDAwMDAwMDAwMDAwMDAwMyIgdHJhbnNmb3JtPSJyb3RhdGUoLTQ1KW1hdHJpeCgxLCAwLCAwLCAxLCAwLCAwKSI+Cg08ZyBpZD0iU1ZHUmVwb19iZ0NhcnJpZXIiIHN0cm9rZS13aWR0aD0iMCIvPgoNPGcgaWQ9IlNWR1JlcG9fdHJhY2VyQ2FycmllciIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBzdHJva2U9IiNDQ0NDQ0MiIHN0cm9rZS13aWR0aD0iMC4wNDgiLz4KDTxnIGlkPSJTVkdSZXBvX2ljb25DYXJyaWVyIj4KDTxwYXRoIGQ9Ik0xMS41IDcuMjA3bDEtMUwxMy43OTMgNy41bC0yIDIgMi43MDcgMi43MDcgMi0yIDEuMjkzIDEuMjkzLTEgMSA0LjcwNyA0LjcwNyAyLjcwNy0yLjcwN0wxOS41IDkuNzkzbC0xIDFMMTcuMjA3IDkuNWwyLTJMMTYuNSA0Ljc5M2wtMiAyTDEzLjIwNyA1LjVsMS0xTDkuNS0uMjA3IDYuNzkzIDIuNXpNMjIuNzkzIDE0LjVMMjEuNSAxNS43OTMgMTguMjA3IDEyLjVsMS4yOTMtMS4yOTN6bS01LTdMMTQuNSAxMC43OTMgMTMuMjA3IDkuNSAxNi41IDYuMjA3em0tNS0zTDExLjUgNS43OTMgOC4yMDcgMi41IDkuNSAxLjIwN3oiLz4KDTxwYXRoIGZpbGw9Im5vbmUiIGQ9Ik0wIDBoMjR2MjRIMHoiLz4KDTwvZz4KDTwvc3ZnPg==");
                satelliteSvg.setAttributeNS(null, 'x', x - 30);
                satelliteSvg.setAttributeNS(null, 'y', y - 150);
                satelliteSvg.setAttributeNS(null, 'width', 100);
                satelliteSvg.setAttributeNS(null, 'height', 100);
                satelliteSvg.setAttributeNS(null, 'alt', 'Satellite');

                svgContainer.appendChild(satelliteSvg);

                // Create and add satellite name text
                const satelliteText = document.createElementNS("http://www.w3.org/2000/svg", "text");
                satelliteText.setAttributeNS(null, 'x', x + 25);
                satelliteText.setAttributeNS(null, 'y', y - 85);
                satelliteText.setAttributeNS(null, 'text-anchor', 'middle');
                satelliteText.setAttributeNS(null, 'font-size', '1.4rem');
                satelliteText.setAttributeNS(null, 'fill', 'black');
                satelliteText.textContent = name;
                svgContainer.appendChild(satelliteText);

                if (index < satelliteNames.length - 1) {
                    const phaseDiff = phaseDiffData[index].phase_diff.toFixed(2);
                    const midAngle = (angle + (index + 1) * angleIncrement) / 2;
                    const textX = centerX + (radiusX + 20 ) * Math.cos(midAngle);
                    const textY = centerY - (radiusY + 70 ) * Math.sin(midAngle) - 100;

                    const phaseText = document.createElementNS("http://www.w3.org/2000/svg", "text");
                    phaseText.setAttributeNS(null, 'x', textX);
                    phaseText.setAttributeNS(null, 'y', textY);
                    phaseText.setAttributeNS(null, 'text-anchor', 'middle');
                    phaseText.setAttributeNS(null, 'dominant-baseline', 'middle');
                    phaseText.textContent = `${phaseDiff}°`;

                    svgContainer.appendChild(phaseText);
                }
            });
        }

        plotSatellitesInArc(["GS-2", "GS-2AP01", "GS-2AP02", "GS-2BP01", "GS-2AP03"], phaseDiffData);
    }

    function populateFlightControlTable(satellites) {
        const flightControlTableBody = document.getElementById('flightControlTable').getElementsByTagName('tbody')[0];
        flightControlTableBody.innerHTML = '';

        const allTasks = [];

        satellites.forEach(satellite => {
            satellite.flightcontrol.forEach(task => {
                allTasks.push(task);
            });
        });

        // Sort all tasks by satellite_code and then by starting time
        allTasks.sort((a, b) => {
            if (a.satellite_code === b.satellite_code) {
                return new Date(a.starting) - new Date(b.starting);
            } else {
                return a.satellite_code.localeCompare(b.satellite_code);
            }
        });

        allTasks.forEach(task => {
            const row = flightControlTableBody.insertRow();
            row.setAttribute('data-mission-id', task['mission_id']); // Add data-mission-id attribute

            // Process the task for starting time and up/increase combination
            let processedTask = { ...task };
            if (processedTask.starting) {
                processedTask.starting = processedTask.starting.replace(' CST+0800', '').slice(5); // Remove ' CST+0800' and the year
            }
            if (processedTask.up !== undefined && processedTask.increase !== undefined) {
                processedTask['up/increase'] = `${processedTask.up}/${processedTask.increase}`;
                delete processedTask.up;
                delete processedTask.increase;
            }

            // Process the remark field
            if (processedTask.remark) {
                if (/异常|处置/.test(processedTask.remark)) {
                    processedTask.remark = '异常处置';
                } else if (/V数传/.test(processedTask.remark)) {
                    processedTask.remark = 'V数传';
                } else if (/通信/.test(processedTask.remark)) {
                    processedTask.remark = '通信监视';
                } else {
                    processedTask.remark = '常规任务';
                }
            }

            // Define the order of keys to ensure the correct column order
            const keysInOrder = [
                'satellite_code',
                'remark',
                'starting',
                'station_name',
                'up/increase',
                'combined_status'
            ];

            // Prepare the combined status (com_status, fileinspect, and anomaly)
            processedTask['combined_status'] = `
                ${processedTask.com_status === '通信' ? '<img src="static/svg/gateway-station.svg" class="status-icon" alt="gateway-station">' : ''}
                ${processedTask.com_status === '通信+v数传' ? '<img src="static/svg/gateway-station.svg" class="status-icon" alt="gateway-station"><img src="static/svg/satellite-com.svg" class="status-icon" alt="satellite-com">' : ''}
                ${processedTask.fileinspect === '文件巡检正常' ? '<img src="static/svg/file-scan-green.svg" class="status-icon" alt="file-scan-green">' : ''}
                ${processedTask.fileinspect && processedTask.fileinspect !== '文件巡检正常' ? '<img src="static/svg/file-scan-red.svg" class="status-icon" alt="file-scan-red">' : ''}
                ${processedTask.anomal ? `${processedTask.anomal.replace('境外复位', '复位入境')}` : ''}
            `.trim();

            keysInOrder.forEach((key, cellIndex) => {
                const cell = row.insertCell();
                cell.innerHTML = processedTask[key] !== undefined ? processedTask[key] : '';
                if (key === 'satellite_code' || key === 'remark' || key === 'starting' || key === 'station_name' || key === 'up/increase' || key === 'combined_status') {
                    cell.setAttribute('contenteditable', 'true');
                }
            });

            // Add a new row for the plot container
            const plotRow = flightControlTableBody.insertRow();
            const plotCell = plotRow.insertCell();
            plotCell.colSpan = keysInOrder.length; // Span all columns
            plotCell.innerHTML = `<div id="id_${task['mission_id']}-chart1" class="chart-container"></div>`;
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
                    <td>无告警</td>
                    <td>0</td>
                    <td><div id="chart_${satellite.satID}_empty" class="subsystem-chart-container"></div></td>
                `;
                rows.push(row);
            } else {
                for (let subsystem in subsystems) {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${satellite.satID}</td>
                        <td>${subsystem}</td>
                        <td>${subsystems[subsystem].count}</td>
                        <td><div id="chart_${satellite.satID}_${subsystem}" class="subsystem-chart-container"></div></td>
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
                    { value: levelData.CRITICAL, name: 'CRITICAL', itemStyle: { color: '#f88800' } },
                    { value: levelData.WARNING, name: 'WARNING', itemStyle: { color: '#f8df00' } },
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

            // const emToPx = parseFloat(getComputedStyle(document.documentElement).fontSize); // Get the root font size in pixels
            // const width = 68 * emToPx; // Convert 40em to pixels
            // const svgDiv = d3.select(`#${missionId }-chart1 .chart-container`);
            const svgDivWidth = missionDiv.node().getBoundingClientRect().width;
            const width = svgDivWidth ; // Use the width of the parent .svg-div
            const height = 25;
            const margin = { left: 5, right: 5 };

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
                .attr("stroke", "#8b8a8a")
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
                text: '2.各家测控资源使用统计',
                left: 'left',
                textStyle: {
                    fontSize: 30
                }
            },
            tooltip: {
                trigger: 'item',
                formatter: '{a} <br/>{b}: {c} ({d}%)'
            },
            legend: {
                orient: 'vertical',
                left: '80%',
                textStyle: {
                    fontSize: 30,
                    fontWeight: "bold"
                }
            },
            series: [{
                name: '供应商',
                type: 'pie',
                radius: ['0%', '65%'], // 环状图的内外半径
                data: chartData,
                label: {
                    show: true, // 显示标签
                    formatter: '{b}: {c}', // 格式化标签显示内容
                    fontSize: '30'
                },
                labelLine: {
                    length2: 40,
                    show:true,
                    lineStyle:{
                        width: 4
                    }
                },
                grid: {
                top:"0%",
                left:"0%",
                right:"4%",
                bottom:"0%",
                containLabel: true
            },
                // emphasis: {
                //     label: {
                //         show: true,
                //         fontSize: '10',
                //         fontWeight: 'bold'
                //     }
                // }
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

        const headers = ['卫星代号', '轨控区间', '实控时长(秒)', '完成状态', '方向'];
        const widths = ['16%', '45%', '14%', '15%', '9%']; // Widths corresponding to each column

    headers.forEach((header, index) => {
        const th = document.createElement('th');
        th.textContent = header;
        th.style.width = widths[index]; // Now correctly references the widths array
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
        const periodStart = moment(record.beginTime).tz('Asia/Shanghai').format('MM-DD HH:mm:ss');
        const periodEnd = moment(record.endTime).tz('Asia/Shanghai').format('MM-DD HH:mm:ss');
        periodCell.textContent = `${periodStart} - ${periodEnd}`;
        periodCell.setAttribute('contenteditable', 'true'); // Make editable
        row.appendChild(periodCell);

        const thrusterTimeCell = document.createElement('td');
        thrusterTimeCell.textContent = record.duration;
        thrusterTimeCell.setAttribute('contenteditable', 'true'); // Make editable
        row.appendChild(thrusterTimeCell);

        const stateCell = document.createElement('td');
        const stateMapping = {
            0: '已创建',
            1: '未确定',
            2: '正常结束',
            3: '异常结束',
            4: '已取消',
            5: '已删除'
        };
        stateCell.textContent = stateMapping[record.state] || record.state;
        stateCell.setAttribute('contenteditable', 'true'); // Make editable

        // Set text color based on state
        switch (stateCell.textContent) {
            case '已创建':
                stateCell.style.color = '#00b800';
                break;
            case '正常结束':
                stateCell.style.color = '#00b800';
                break;
            case '异常结束':
                stateCell.style.color = '#cd0020';
                break;
            case '已取消':
                stateCell.style.color = '#616161';
                break;
            case '未确定':
                stateCell.style.color = '#616161';
                break;
            case '已删除':
                stateCell.style.color = '#f8c200';
                break;
            default:
                stateCell.style.color = '#000000';
        }

        row.appendChild(stateCell);

        // Add control direction column
        const controlDirectionCell = document.createElement('td');
        const directionMapping = {
            0: '升轨',
            1: '降轨',
            2: '+Y方向',
            3: '-Y方向',
            4: '+Z方向',
            5: '-Z方向',
            6: '飘飞'
        };
        controlDirectionCell.textContent = directionMapping[record.direction] || '转移';
        controlDirectionCell.setAttribute('contenteditable', 'true'); // Make editable
        row.appendChild(controlDirectionCell);

        // Add buttons cell
        const actionCell = document.createElement('td');
        actionCell.classList.add('action-cell');
        actionCell.innerHTML = `
            <button class="delete-button" style="display: none;">删除</button>
            <button class="new-row-button" style="display: none;">新建</button>
        `;
        row.appendChild(actionCell);

        tbody.appendChild(row);

        // Show buttons on hover
        row.addEventListener('mouseenter', () => {
            actionCell.querySelector('.delete-button').style.display = 'block';
            actionCell.querySelector('.new-row-button').style.display = 'block';
        });

        row.addEventListener('mouseleave', () => {
            actionCell.querySelector('.delete-button').style.display = 'none';
            actionCell.querySelector('.new-row-button').style.display = 'none';
        });

        // Delete row on button click
        actionCell.querySelector('.delete-button').addEventListener('click', () => {
            tbody.removeChild(row);
        });

        // Add new empty row below current row
        actionCell.querySelector('.new-row-button').addEventListener('click', () => {
            const newRow = document.createElement('tr');
            newRow.innerHTML = `
                <td contenteditable="true"></td>
                <td contenteditable="true"></td>
                <td contenteditable="true"></td>
                <td contenteditable="true"></td>
                <td contenteditable="true"></td>
                <td>
                    <button class="delete-button" style="display: none;">删除</button>
                    <button class="new-row-button" style="display: none;">新建</button>
                </td>
            `;
            tbody.insertBefore(newRow, row.nextSibling);

            // Add hover effect and delete functionality to the new row
            newRow.addEventListener('mouseenter', () => {
                newRow.querySelector('.delete-button').style.display = 'block';
                newRow.querySelector('.new-row-button').style.display = 'block';
            });

            newRow.addEventListener('mouseleave', () => {
                newRow.querySelector('.delete-button').style.display = 'none';
                newRow.querySelector('.new-row-button').style.display = 'none';
            });

            newRow.querySelector('.delete-button').addEventListener('click', () => {
                tbody.removeChild(newRow);
            });
        });
    });

    table.appendChild(tbody);
    fireRecordsTableContainer.appendChild(table);
}


    function populateGatewayTasksTable(tasks) {
        const tableContainer = document.getElementById('gatewayTasksTableContainer');
        tableContainer.innerHTML = ''; // Clear any existing content

        const table = document.createElement('table');
        table.classList.add('styled-table'); // Use the styled-table class for consistent styling

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
            'flatten': '平飞',
            'stare': '凝视'
        };

        // const systemMapping = {
        //     'ttnonc': '银河测运控',
        //     'yhcom': '银河中心站控'
        // };

        tasks.forEach(task => {
            const row = document.createElement('tr');

            const spacecraftCodeCell = document.createElement('td');
            spacecraftCodeCell.textContent = task.satellite.code;
            spacecraftCodeCell.setAttribute('contenteditable', 'true'); // Make editable
            row.appendChild(spacecraftCodeCell);

            const stationNameCell = document.createElement('td');
            stationNameCell.textContent = task.antenna.name;
            stationNameCell.setAttribute('contenteditable', 'true'); // Make editable
            row.appendChild(stationNameCell);

            const taskTimeCell = document.createElement('td');
            const startAt = moment(task.startAt).tz('Asia/Shanghai').format('MM-DD HH:mm:ss');
            const endAt = moment(task.endAt).tz('Asia/Shanghai').format('MM-DD HH:mm:ss');
            taskTimeCell.textContent = `${startAt} - ${endAt}`;
            taskTimeCell.setAttribute('contenteditable', 'true'); // Make editable
            row.appendChild(taskTimeCell);

            const modeCell = document.createElement('td');
            modeCell.textContent = modeMapping[task.flightAttitude] || task.flightAttitude;
            modeCell.setAttribute('contenteditable', 'true'); // Make editable
            row.appendChild(modeCell);

            const beamCell = document.createElement('td');
            beamCell.textContent = parseInt(task.stareBeamIndex) + 1;
            beamCell.setAttribute('contenteditable', 'true'); // Make editable
            row.appendChild(beamCell);

            const systemCell = document.createElement('td');
            systemCell.textContent = "银河站控";
            systemCell.setAttribute('contenteditable', 'true'); // Make editable
            row.appendChild(systemCell);

            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        tableContainer.appendChild(table);
    }

    document.getElementById('snapshotButton').addEventListener('click', function() {
        // Get all buttons, checkboxes, forms, and loader elements
        const elementsToHide = document.querySelectorAll('form, button, input[type="checkbox"], .loader-overlay, .loader, .loader-text');

        // Hide all targeted elements
        elementsToHide.forEach(element => element.style.display = 'none');

        // Take the screenshot of the #overall div
        html2canvas(document.getElementById('overall'),  { allowTaint: true , scrollX:0, scrollY: -window.scrollY }).then(canvas => {
            // Restore the visibility of the targeted elements
            elementsToHide.forEach(element => element.style.display = '');

            // Create a link to download the screenshot
            const link = document.createElement('a');
            link.href = canvas.toDataURL();
            link.download = 'screenshot.png';
            link.click();
        });
    });

    let currentEditableTd = null;
    const dropdown = document.getElementById('svgDropdown');

    function showDropdown(event) {
        currentEditableTd = event.target;
        const rect = currentEditableTd.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

        dropdown.style.left = `${(rect.left + scrollLeft - 200)}px`; // Position to the left of the cell
        dropdown.style.top = `${rect.top + scrollTop}px`; // Align top of dropdown with top of cell
        dropdown.style.display = 'block';
    }

    function hideDropdown() {
        dropdown.style.display = 'none';
    }

    function insertSvgIcon(iconPath) {
        if (currentEditableTd) {
            const imgElement = document.createElement('img');
            imgElement.src = iconPath;
            imgElement.className = 'status-icon';
            imgElement.alt = iconPath.split('/').pop().split('.')[0]; // Alt text from file name

            currentEditableTd.appendChild(imgElement);
            hideDropdown();
        } else {
            alert('Please select a cell to insert the icon.');
        }
    }

    dropdown.addEventListener('click', (event) => {
        if (event.target.tagName === 'IMG') {
            insertSvgIcon(event.target.dataset.icon);
        }
    });

    document.getElementById('flightControlTable').addEventListener('click', function(event) {
        if (event.target.tagName === 'TD' && event.target.isContentEditable && event.target.cellIndex === 5) { // Assuming 'combined_status' is the 6th column
            showDropdown(event);
        } else {
            hideDropdown();
        }
    });

function populateAlertTable(alertData) {
    const alertTableBody = document.querySelector('#alertTable tbody');
    alertTableBody.innerHTML = ''; // Clear existing rows

    alertData.forEach(alert => {
        // Convert eventTime to Beijing time using Moment.js
        const eventTime = moment(alert.eventTime).tz('Asia/Shanghai').format('MM-DD HH:mm:ss');

        // Check if eventRemark contains ">" or "<"
        const eventRemarkContainsSpecialChars = /[<>]/.test(alert.eventRemark);

        // Determine the value to display in the param.ext field
        const paramExtValue = eventRemarkContainsSpecialChars
            ? alert.itemValue.toFixed(2)
            : alert['param.ext'].join(', ');

        const row = document.createElement('tr');

        row.innerHTML = `
            <td contenteditable="true">${eventTime}</td>
            <td contenteditable="true">${alert.satCode}</td>
            <td contenteditable="true">${alert.subsystem}</td>
            <td contenteditable="true">${alert.eventName.split('_').slice(1).join('_')}</td>
            <td contenteditable="true">${paramExtValue}</td>
            <td contenteditable="true">${alert.eventLevel}</td>
        `;

        // Handle special characters in eventRemark
        const eventRemarkCell = document.createElement('td');
        eventRemarkCell.contentEditable = true;
        eventRemarkCell.innerHTML = alert.eventRemark.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        row.appendChild(eventRemarkCell);

        // Add delete button cell
        const deleteButtonCell = document.createElement('td');
        deleteButtonCell.classList.add('delete-cell');
        deleteButtonCell.innerHTML = '<button class="delete-button" style="display: none;">删除</button>';
        row.appendChild(deleteButtonCell);

        alertTableBody.appendChild(row);

        // Show delete button on hover
        row.addEventListener('mouseenter', () => {
            deleteButtonCell.querySelector('.delete-button').style.display = 'block';
        });

        row.addEventListener('mouseleave', () => {
            deleteButtonCell.querySelector('.delete-button').style.display = 'none';
        });

        // Delete row on button click
        deleteButtonCell.querySelector('.delete-button').addEventListener('click', () => {
            alertTableBody.removeChild(row);
        });
    });
}

// Add the following CSS to style the delete button and hide it initially
const style = document.createElement('style');
style.innerHTML = `
    .delete-cell {
        text-align: center;
    }
    .delete-button {
        background-color: red;
        color: white;
        border: none;
        cursor: pointer;
        padding: 5px;
        display: none;
    }
`;
document.head.appendChild(style);


});

document.addEventListener('DOMContentLoaded', () => {
    const legend = document.getElementById('legend');

    const replacements = [
        { text: '地面站', imgSrc: 'static/svg/gateway-station.svg', alt: 'gateway-station' },
        { text: '卫星', imgSrc: 'static/svg/satellite-com.svg', alt: 'satellite-com' },
        { text: '绿色文件', imgSrc: 'static/svg/file-scan-green.svg', alt: 'file-scan-green' },
        { text: '红色文件', imgSrc: 'static/svg/file-scan-red.svg', alt: 'file-scan-red' },
    ];

    replacements.forEach(replacement => {
        const regex = new RegExp(replacement.text, 'g');
        legend.innerHTML = legend.innerHTML.replace(
            regex,
            `<img src="${replacement.imgSrc}" class="status-icon" alt="${replacement.alt}" style="vertical-align: middle;">`
        );
    });
});

document.getElementById('publishtodingtalkButton').addEventListener('click', function() {
    // Hide elements that should not appear in the screenshot
    const elementsToHide = document.querySelectorAll('form, button, input[type="checkbox"], .loader-overlay, .loader, .loader-text');

    // Hide all targeted elements
    elementsToHide.forEach(element => element.style.display = 'none');

    // Take the screenshot of the #overall div
    html2canvas(document.getElementById('overall'), { allowTaint: true, scrollX: 0, scrollY: -window.scrollY }).then(canvas => {
        // Restore the visibility of the targeted elements
        elementsToHide.forEach(element => element.style.display = '');

        // Convert canvas to data URL
        const imageData = canvas.toDataURL('image/png');

        // Prepare the data to send to the backend
        const uuidv1 = uuid.v1(); // Use the uuid library to generate a UUID
                // Get the current date and time
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        const day = String(now.getDate()).padStart(2, '0');
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');

        // Create the file name
        const fileName = `${uuidv1}_${year}${month}${day}_${hours}${minutes}${seconds}_spiderlingdailyreport.png`;

        // Send the image data to the backend
        fetch('/publish-spiderlingdailyreport', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ image: imageData, fileName: fileName })
        })
        .then(response => response.json())
        .then(data => {
            console.log(data)
            if (data.message === 'sucess') {
                alert('飞控日报已发布至钉钉');
            } else {
                alert('飞控日报发布失败,请联系管理员');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('飞控日报自动生成失败,请联系管理员');
        });
    });
});
