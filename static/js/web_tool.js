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

        // console.log('Request Data:', requestData);  // Log the request data


        fetch('http://172.16.10.56:7877/spiderlingdailyreport', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            // console.log(data);
            populateFlightControlTable(data.satellites);
            populateSubsystemTable(data.satellites);
            populateLevelDoughnutChart(data.satellites);
            plotSatellites(data.satellites);
            plotCompanyChart(data.satellites);
            updateSummaryTextarea(data)
        })
        .catch(error => console.error('Error:', error))
        .finally(async () => {
                try {
                    const trackQualityResponse = await fetch('http://172.16.10.56:7877/trackquality', {
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
                    // console.log('Track Quality Data:', trackQualityData);  // Log the response data
                    plotHorizontalLines(trackQualityData.mission_quality);
                } catch (error) {
                    console.error('Track Quality Error:', error);
                }

                try {
                    const cumulativeResetResponse = await fetch('http://172.16.10.56:7877/cumulative-reset', {
                        method: 'POST', // Ensure method is POST
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(requestData) // Include the request body
                    });
                    if (!cumulativeResetResponse.ok) {
                        throw new Error(`Error: ${cumulativeResetResponse.status} ${cumulativeResetResponse.statusText}`);
                    }
                    const cumulativeResetData = await cumulativeResetResponse.json();
                    // console.log('Cumulative Reset Data:', cumulativeResetData);  // Log the response data
                    plotCumulativeResetChart(cumulativeResetData);
                } catch (error) {
                    console.error('Cumulative Reset Error:', error);
                }
            });
        });

    function updateSummaryTextarea(data) {
        const date = new Date().toISOString().split('T')[0];
        const summaryText = `今日(${date}) 共执行小蜘蛛卫星飞控任务 ${data.total_mission} 轨。正常执飞任务 ${data.normal_mission} 轨,自动监测异常任务 ${data.auto_anomal_mission} 轨。共计发令 ${data.total_command_sent} 条。`;
        const summaryTextarea = document.getElementById('summaryTextarea1');
        summaryTextarea.value = summaryText;
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

    // const grid = {
    //     left: 100,
    //     right: 100,
    //     top: 50,
    //     bottom: 50
    // };

    const series = ['OLD', 'NEW', 'MAX'].map((name, sid) => {
        return {
            name: sid === 2 ? '' : name, // 将 MAX 系列的名称设置为空字符串，使其不出现在图例中
            type: 'bar',
            stack: 'total',
            barWidth: '60%',
            itemStyle: {
                color: name === 'OLD' ? '#00DCDC' : (name === 'NEW' ? '#D64161FF' : 'lightgray')
            },
            // show: sid === 2 ? false : true,
            label: {
            show: sid !== 2,
              formatter: (params) => Math.round(params.value)
            },
            data: rawData[sid].map((d, i) => sid !== 2 ? d : rawData[sid][i])
          };
    });
    const option = {
        title: {
            text:'02批卫星复位情况'
          },
        legend: {
            selectedMode: false
        },
        // grid,
        yAxis: {
            type: 'value',
            max: 8
        },
        xAxis: {
            type: 'category',
            data: satCodes,
            interval: 0,
            fontSize: 8
        },
        series
    };

    const chartDom = document.getElementById('cumulativeResetChart');
    const myChart = echarts.init(chartDom);
    myChart.setOption(option);
}

// Ensure your HTML has a div with id 'cumulativeResetChart'
// <div id="cumulativeResetChart" style="width: 600px; height: 400px;"></div>


function plotSatellites(satelliteData) {
    const svgPath = "/static/svg/satellite-icon1.svg";
    const container = document.getElementById('satelliteContainer');
    container.innerHTML = '';
    const names = ["GS-1a", "GS-2", "GS-2AP01", "GS-2AP02", "GS-2BP01", "GS-2AP03", "GS-2BP02", "GS-NY01"];

    const radius = 150; // Adjust radius for better fit
    const centerX = container.offsetWidth / 2; // Center X of the arc
    const centerY = 200; // Center Y of the arc (adjust based on your design)
    const totalSatellites = names.length;
    const angleIncrement = Math.PI / (totalSatellites + 1); // Angle increment based on number of satellites

    const positions = [];

    for (let i = 0; i < totalSatellites; i++) {
        const angle = angleIncrement * (i + 1);
        const x = centerX + radius * Math.cos(angle) - 20;
        const y = centerY - radius * Math.sin(angle);

        positions.push({ x, y });

        const itemDiv = document.createElement('div');
        itemDiv.className = 'item-div';
        itemDiv.style.position = 'absolute';
        itemDiv.style.left = `${x}px`;
        itemDiv.style.top = `${y}px`;
        itemDiv.style.transform = 'translate(-50%, -50%)'; // Center the div

        const nameDiv = document.createElement('div');
        nameDiv.textContent = names[i];
        nameDiv.className = 'name-div';

        const svgDiv = document.createElement('div');
        svgDiv.className = 'svg-div';
        svgDiv.innerHTML = `<img src="${svgPath}" alt="Satellite">`;

        itemDiv.appendChild(nameDiv);
        itemDiv.appendChild(svgDiv);

        const satellite = satelliteData.find(sat => sat.satID === names[i]);
        if (satellite && satellite.orbit && satellite.orbit.h) {
            const altDiv = document.createElement('div');
            altDiv.textContent = `${satellite.orbit.h.alt.toFixed(3)} km`;
            altDiv.className = 'alt-div';
            itemDiv.appendChild(altDiv);
        }

        container.appendChild(itemDiv);
    }

    for (let i = 0; i < totalSatellites - 1; i++) {
        if ((i === 0) || (i === 5) || (i === 6)) {
            continue;
        }

        const sat1 = satelliteData.find(sat => sat.satID === names[i]);
        const sat2 = satelliteData.find(sat => sat.satID === names[i + 1]);

        if (sat1 && sat2 && sat1.orbit && sat2.orbit) {
            const phaseDiff = Math.abs(sat2.orbit.p.phase - sat1.orbit.p.phase);
            const phaseDiv = document.createElement('div');
            phaseDiv.textContent = `${phaseDiff.toFixed(2)}°`;
            phaseDiv.className = 'phase-div';
            phaseDiv.style.position = 'absolute';
            phaseDiv.style.left = `${(positions[i].x + positions[i + 1].x) / 2}px`;
            phaseDiv.style.top = `${(positions[i].y + positions[i + 1].y) / 2}px`;
            phaseDiv.style.transform = 'translate(-50%, -50%)'; // Center the div
            container.appendChild(phaseDiv);
        }
    }
}



function populateFlightControlTable(satellites) {
    const flightControlTableBody = document.getElementById('flightControlTable').getElementsByTagName('tbody')[0];
    flightControlTableBody.innerHTML = '';

    satellites.forEach(satellite => {
        const tasks = satellite.flightcontrol;
        const totalRows = tasks.length * 2; // Each mission has a corresponding line row

        let satIDCell = null;

        tasks.forEach((task, index) => {
            const row = flightControlTableBody.insertRow();
            row.setAttribute('data-mission-id', task['mission_id']); // Add data-mission-id attribute

            if (index === 0) {
                // Create the satID cell only for the first mission row
                satIDCell = row.insertCell();
                satIDCell.textContent = satellite.satID;
                satIDCell.rowSpan = totalRows;
            }

            Object.entries(task).forEach(([key, val]) => {
                if (key !== 'company_name') { // Skip the 'company_name' property
                    const cell = row.insertCell();
                    cell.textContent = val;
                }
            });

            // Add a new row for the plot container
            const plotRow = flightControlTableBody.insertRow();
            const plotCell = plotRow.insertCell();
            plotCell.colSpan = 11; // Span all columns except the satID column
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
                        radius: ['20%', '40%'],
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

    function populateOrbitTable(satellites) {
        const orbitTableBody = document.getElementById('orbitTable').getElementsByTagName('tbody')[0];
        orbitTableBody.innerHTML = '';

        satellites.forEach(satellite => {
            const row = orbitTableBody.insertRow();

            const satIDCell = row.insertCell();
            satIDCell.textContent = satellite.satID;

            row.insertCell().textContent = satellite.orbit.h.alt;
            row.insertCell().textContent = satellite.orbit.p.phase;
        });
    }

    // function plotHorizontalLines(missionQuality) {
    //     Object.values(missionQuality).forEach(mission => {
    //         const row = document.getElementById(mission.mission_id + '-chart');
    //         row.style.position = 'relative'; // Ensure the row is positioned relatively to contain absolute positioned elements
    //
    //     if (firstCell) {
    //         firstCell.rowSpan = rowspanCount;
    //     }
    // }

    // function plotHorizontalLines(missionQuality) {
    //     const rows = Object.values(missionQuality);
    //
    //     rows.forEach(mission => {
    //         const missionId = `id_${mission.mission_id}`
    //         const missionDiv = d3.select(`#${missionId }-chart1`)
    //             .style("position", "relative")
    //             .append("div")
    //             .attr("class", "plot-container");
    //
    //         const width = 150;
    //         const height = 40;
    //         const margin = { left: 10, right: 10 };
    //
    //         const svg = missionDiv.append("svg")
    //             .attr("width", width)
    //             .attr("height", height);
    //
    //         const xScale = d3.scaleTime()
    //             .domain([new Date(mission.starting), new Date(mission.ending)])
    //             .range([margin.left, width - margin.right]);
    //
    //         svg.append("line")
    //             .attr("x1", xScale(new Date(mission.starting)))
    //             .attr("x2", xScale(new Date(mission.ending)))
    //             .attr("y1", height / 2)
    //             .attr("y2", height / 2)
    //             .attr("stroke", "grey")
    //             .attr("stroke-width", 4);
    //
    //         Object.values(mission.telemetry).forEach(d => {
    //             svg.append("line")
    //                 .attr("x1", xScale(new Date(d.start)))
    //                 .attr("x2", xScale(new Date(d.end)))
    //                 .attr("y1", height / 2)
    //                 .attr("y2", height / 2)
    //                 .attr("stroke", "red")
    //                 .attr("stroke-width", 4)
    //                 .on("mouseover", function(event) {
    //                     d3.select(".tooltip").transition().duration(200).style("opacity", .9);
    //                     d3.select(".tooltip").html(`Telemetry Start: ${new Date(d.start).toLocaleString()}<br/>Telemetry End: ${new Date(d.end).toLocaleString()}`)
    //                         .style("left", (event.pageX) + "px")
    //                         .style("top", (event.pageY - 28) + "px");
    //                 })
    //                 .on("mouseout", function() {
    //                     d3.select(".tooltip").transition().duration(500).style("opacity", 0);
    //                 });
    //         });
    //
    //         Object.values(mission.uplink).forEach(d => {
    //             svg.append("line")
    //                 .attr("x1", xScale(new Date(d.start)))
    //                 .attr("x2", xScale(new Date(d.end)))
    //                 .attr("y1", height / 2)
    //                 .attr("y2", height / 2)
    //                 .attr("stroke", "green")
    //                 .attr("stroke-width", 4)
    //                 .on("mouseover", function(event) {
    //                     d3.select(".tooltip").transition().duration(200).style("opacity", .9);
    //                     d3.select(".tooltip").html(`Uplink Start: ${new Date(d.start).toLocaleString()}<br/>Uplink End: ${new Date(d.end).toLocaleString()}`)
    //                         .style("left", (event.pageX) + "px")
    //                         .style("top", (event.pageY - 28) + "px");
    //                 })
    //                 .on("mouseout", function()
    //                 {
    //                     d3.select(".tooltip").transition().duration(500).style("opacity", 0);
    //                 });
    //         });
    //                 // console.log(`Finished rendering mission: ${mission.mission_id}`);
    //
    //     });
    // }

    function plotHorizontalLines(missionQuality) {
        const rows = Object.values(missionQuality);

        rows.forEach(mission => {
            const missionId = `id_${mission.mission_id}`;
            const missionDiv = d3.select(`#${missionId }-chart1`)
                .style("position", "relative")
                .append("div")
                .attr("class", "plot-container");

            const width = 150;
            const height = 40;
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
                    .attr("stroke", "green")
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


        // Function to calculate phase differences
    // function calculatePhaseDifferences(satelliteData) {
    //     const phaseDiffs = {};
    //     const relevantNames = ["GS-2", "GS-2AP01", "GS-2AP02", "GS-2AP03", "GS-2BP01"];
    //
    //     for (let i = 0; i < relevantNames.length - 1; i++) {
    //         const sat1 = satelliteData.find(sat => sat.satID === relevantNames[i]);
    //         const sat2 = satelliteData.find(sat => sat.satID === relevantNames[i + 1]);
    //
    //         if (sat1 && sat2 && sat1.orbit && sat2.orbit && sat1.orbit.p && sat2.orbit.p) {
    //             const phaseDiff = Math.abs(sat1.orbit.p.phase - sat2.orbit.p.phase).toFixed(2);
    //             phaseDiffs[relevantNames[i]] = phaseDiff;
    //         }
    //     }
    //
    //     return phaseDiffs;
    // }
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

            const chartData = Object.keys(companyCount).map(companyName => {
                return {
                    name: companyName,
                    value: companyCount[companyName]
                };
            });

            const chart = echarts.init(document.getElementById('companyChart'));
            const option = {
                title: {
                    text: '测控供应商统计'
                },
                tooltip: {},
                xAxis: {
                    type: 'category',
                    data: chartData.map(item => item.name)
                },
                yAxis: {
                    type: 'value'
                },
                series: [{
                    type: 'bar',
                    data: chartData.map(item => item.value),
                    label:{
                        show: true,
                        position: 'top'
                    }
                }]
            };

            chart.setOption(option);

            // Calculate the total frequency
            const totalFrequency = chartData.reduce((sum, item) => sum + item.value, 0);

            // Display the total frequency
            document.getElementById('totalFrequency').innerText = `轨次总计: ${totalFrequency}`;
        }
});
