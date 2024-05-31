document.addEventListener('DOMContentLoaded', () => {
    const satIDMapping = {
        1: 'GS-1a',
        2: 'GS-2',
        3: 'GS-2AP01',
        4: 'GS-2AP02',
        5: 'GS-2AP03',
        6: 'GS-2BP01',
        7: 'GS-2BP02',
        8: 'HT1-A',
        9: 'HT1-B',
        10: 'HT1-C',
        11: 'HT1-D',
        12: 'AS02',
        13: 'AS03',
        14: 'GS-NY01'
    };

    const satIDCheckboxes = document.getElementById('satIDCheckboxes');
    for (let i = 1; i <= 14; i++) {
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `satID_${i}`;
        checkbox.value = i;
        checkbox.name = 'satID';

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

    submitButton.addEventListener('click', () => {
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
            populateOrbitTable(data.satellites);
        })
        .catch(error => console.error('Error:', error))
        .finally(() => {
            fetch('http://172.16.10.56:7877/trackquality', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            })
            .then(response => response.json())
            .then(data => {
                // console.log(data);
                plotHorizontalLines(data.mission_quality);
            })
            .catch(error => console.error('Error:', error));
        });
    });


            // Load SVGs
    const svgPath = "/static/svg/satellite-icon1.svg";;
    const container = document.getElementById('satelliteContainer');
    const names = ["GS-1a", "GS-2", "GS-2AP01", "GS-2AP02", "GS-2AP03", "GS-2BP01", "GS-2BP02", "GS-NY01"];


    for (let i = 0; i < names.length; i++) {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'item-div';
        // itemDiv.style.display = 'flex';
        // itemDiv.style.flexDirection = 'column';
        // itemDiv.style.alignItems = 'center';
        // itemDiv.style.margin = '0 10px'; // Adding some horizontal margin for spacing

        const nameDiv = document.createElement('div');
        nameDiv.textContent = names[i];
        nameDiv.className = 'name-div';
        // nameDiv.style.marginBottom = '5px';  // Adjust the spacing as needed

        const svgDiv = document.createElement('div');
        svgDiv.className = 'svg-div';
        svgDiv.innerHTML = `<img src="${svgPath}" alt="Satellite" style="width: 80%; height: 40px; margin: 50px;">`;

        itemDiv.appendChild(nameDiv);
        itemDiv.appendChild(svgDiv);
        container.appendChild(itemDiv);
    }



    function populateFlightControlTable(satellites) {
        const flightControlTableBody = document.getElementById('flightControlTable').getElementsByTagName('tbody')[0];
        flightControlTableBody.innerHTML = '';

        let prevSatID = '';
        let rowspanCount = 0;
        let firstCell = null;

        satellites.forEach(satellite => {
            satellite.flightcontrol.forEach((task, index) => {
                const row = flightControlTableBody.insertRow();

                if (prevSatID !== satellite.satID) {
                    if (firstCell) {
                        firstCell.rowSpan = rowspanCount;
                    }
                    prevSatID = satellite.satID;
                    rowspanCount = 1;

                    firstCell = row.insertCell();
                    firstCell.textContent = satellite.satID;
                } else {
                    rowspanCount++;
                }
                Object.values(task).forEach((val, i) => {
                    const cell = row.insertCell();
                    if (i === 0 && firstCell) {
                        firstCell.rowSpan = rowspanCount;
                    }
                    cell.textContent = val;
                });
                const cell = row.insertCell();
                cell.className = 'track-quality'; // Assign class to '跟踪质量' cells
                cell.innerHTML = `<div id="id_${task['mission_id']}-chart1" class="chart-container"></div>`;
            });
        });

        if (firstCell) {
            firstCell.rowSpan = rowspanCount;
        }
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
                    { value: levelData.FATAL, name: 'FATAL', itemStyle: { color: '#a80020' } },
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

    function plotHorizontalLines(missionQuality) {
        const rows = Object.values(missionQuality);

        rows.forEach(mission => {
            const missionId = `id_${mission.mission_id}`
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
                    .on("mouseout", function()
                    {
                        d3.select(".tooltip").transition().duration(500).style("opacity", 0);
                    });
            });
                    console.log(`Finished rendering mission: ${mission.mission_id}`);

        });
    }
});
