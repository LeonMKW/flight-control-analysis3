
console.log(echarts)
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
        console.log(data)
            populateFlightControlTable(data.satellites);
            populateSubsystemTable(data.satellites);
            populateLevelDoughnutChart(data.satellites);
            populateOrbitTable(data.satellites);
        })
        .catch(error => console.error('Error:', error))
        .finally(()=>{
         fetch('http://172.16.10.56:7877/trackquality', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            console.log(data);
            plotHorizontalLines(data.mission_quality);
        })
        .catch(error => console.error('Error:', error));

        });

    });

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
                 cell.innerHTML="<div id='"+task['任务代号']+"-chart'></div>"
            });
        });

        if (firstCell) {
            firstCell.rowSpan = rowspanCount;
        }
    }

function populateSubsystemTable(satellites) {
    console.log('Populating subsystem table...');
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
    console.log('Populating doughnut chart...');

    satellites.forEach(satellite => {
        const levels = satellite.level;

        if (Object.keys(levels).length === 0) {
            return; // Skip rendering if no level data exists
        }

        for (let subsystem in levels) {
            const levelData = levels[subsystem];
            const chartId = `chart_${satellite.satID}_${subsystem}`;
            console.log("Chart ID:", chartId);

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

            row.insertCell().textContent = satellite.orbit.p.mse;
            row.insertCell().textContent = satellite.orbit.h.alt;
        });
    }

    function plotHorizontalLines(missionQuality) {
//        const flightControlTableBody = document.getElementById('flightControlTable2').getElementsByTagName('tbody')[0];
//        flightControlTableBody.innerHTML = '';

        Object.values(missionQuality).forEach(mission => {
            const row =  document.getElementById(mission.mission_id+'-chart')
            row.style.position = 'relative'; // Ensure the row is positioned relatively to contain absolute positioned elements

            const starting = mission.starting;
            const ending = mission.ending;

            const telemetry = mission.telemetry;
            const uplink = mission.uplink;

            console.log(`Plotting mission ID: ${mission.mission_id}`);
            // Plot horizontal line for starting to ending (grey)
            plotLine(starting, ending, 'grey', row);

            // Plot horizontal lines for telemetry (red)
            for (const telemetryData of Object.values(telemetry)) {
                plotLine(telemetryData.start, telemetryData.end, 'red', row);
            }

            // Plot horizontal lines for uplink (green)
            for (const uplinkData of Object.values(uplink)) {
                plotLine(uplinkData.start, uplinkData.end, 'green', row);
            }
        });
    }

    function plotLine(start, end, color, row) {
        // Calculate the width of the line based on start and end timestamps
        const duration = end - start;

        // Normalize start and duration for visualization purposes (e.g., divide by 1000 if timestamps are in milliseconds)
        const normalizedStart = (start - row.dataset.start) / 1000; // Adjust as necessary
        const normalizedDuration = duration / 1000; // Adjust as necessary

        // Create a div element for the line
        const line = document.createElement('div');
        line.style.width = normalizedDuration + 'px';
        line.style.height = '2px'; // Set the height of the line
        line.style.backgroundColor = color; // Set the color of the line
        line.style.position = 'absolute'; // Ensure the line is positioned absolutely within the row
        line.style.left = normalizedStart + 'px'; // Position the line horizontally

        console.log(`Plotting line from ${start} to ${end} with color ${color}`);
        // Add the line to the row
        row.appendChild(line);
    }
});
